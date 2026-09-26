# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T8: Live Wire. GDELT poll every 15 minutes, dedupe, classify via JevClassifier, push over WebSocket.

- Dates come from GDELT `seendate`, never from the classifier.
- Events under 0.6 confidence are dropped.
- Anomaly: a confident event on an origin->destination edge the route model gave under 10% probability
  (or never considered at all).
- If GDELT is unreachable or rate-limited, the wire replays the bundled synthetic sample so the demo streams;
  /api/meta reports the GDELT status as `fallback`.

Env: TRACE_LIVEWIRE_POLL=0 disables background polling (tests); TRACE_LIVEWIRE_REPLAY_SECONDS sets the replay drip.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .. import config
from ..jev.base import JevClassifier
from ..jev.real import get_classifier
from ..sources import SOURCES

log = logging.getLogger(__name__)
router = APIRouter()
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = ('(cocaine OR heroin OR methamphetamine OR cannabis OR fentanyl OR hashish OR "drug trafficking") '
         '(seized OR seizure OR bust OR smuggling OR trafficking OR cartel OR legalization) sourcelang:english')
MIN_CONF = 0.6
ANOMALY_P = 0.10
EVAL_PATH = Path(__file__).resolve().parents[1] / "jev" / "data" / "labeled_eval.json"
STORE_PATH = config.PROCESSED / "live_events.json"
MODELED = {"cocaine", "heroin", "meth", "cannabis"}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_eval() -> list[dict]:
    d = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    return [dict(zip(d["columns"], r, strict=True)) for r in d["rows"]]


class LiveWire:
    def __init__(self):
        from .app import store
        s = store()
        self.countries = {c["iso3"]: c for c in s.countries}
        self.classifier: JevClassifier = get_classifier(s.countries)
        self.classifier_name = self.classifier.name
        preds = s.predicted.get(max(s.predicted), []) if s.predicted else []
        self.edge_p = {(e["drug"], e["from"], e["to"]): e["probability"] for e in preds}
        self._all_p = self._load_all_probabilities()
        self.events: deque[dict] = deque(maxlen=500)
        self.seen: set[str] = set()
        self.subscribers: set[asyncio.Queue] = set()
        self.status, self.retrieved_at, self.note = "fallback", None, "not polled yet"
        self.last_request = 0.0
        self.next_poll_at = _now()
        self._replay = [r["title"] for r in load_eval() if r["is_event"]]
        self._replay_i = 0
        self._load()

    # ------------------------------------------------------------------ model probabilities
    @staticmethod
    def _load_all_probabilities() -> dict:
        """Probabilities for every candidate corridor (not only those shown on the map)."""
        try:
            from .. import db
            p = db.read_table("predictions")
            return {(r.drug, r.from_iso3, r.to_iso3): float(r.probability) for r in p.itertuples()}
        except Exception:  # API may run from exported JSON only
            return {}

    def edge_probability(self, drug: str, o: str | None, d: str | None) -> float | None:
        if not (o and d) or drug not in MODELED:
            return None
        return self._all_p.get((drug, o, d), self.edge_p.get((drug, o, d), 0.0))

    # ------------------------------------------------------------------ persistence
    def _load(self):
        if STORE_PATH.exists():
            try:
                for e in json.loads(STORE_PATH.read_text(encoding="utf-8"))[-500:]:
                    self.events.append(e)
                    self.seen.add(e["id"])
            except (ValueError, KeyError):
                pass
        if not self.events:
            for _ in range(12):
                self._replay_one(push=False)

    def _save(self):
        try:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STORE_PATH.write_text(json.dumps(list(self.events)), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ classification
    def build_event(self, title: str, url: str, published: datetime, domain: str, language: str = "English",
                    text: str = "") -> dict | None:
        c = self.classifier.classify(title, text)
        if c.confidence < MIN_CONF:
            return None
        o, d = c.origin, c.destination
        p = self.edge_probability(c.drug, o, d)
        anomaly = bool(p is not None and p < ANOMALY_P and c.route_mentioned >= 0.5 and c.event_type == "seizure")
        reason = None
        if anomaly:
            reason = (f"Edge {o}->{d} ({c.drug}) had {p:.0%} model probability" if p else
                      f"Edge {o}->{d} ({c.drug}) is not a modelled corridor")
        pin = self.countries.get(c.location or d or o or "")
        eid = "gdelt-" + hashlib.sha1(url.encode()).hexdigest()[:10]
        return {"id": eid, "published_at": _iso(published), "title": title, "url": url, "source_domain": domain,
                "language": language, "event_type": c.event_type, "drug": c.drug, "origin": o, "transit": c.transit,
                "destination": d, "size": c.size, "is_event": round(c.is_event, 3),
                "route_mentioned": round(c.route_mentioned, 3), "confidence": round(c.confidence, 3),
                "is_anomaly": anomaly, "anomaly_reason": reason,
                "edge_probability": None if p is None else round(p, 4), "classifier": self.classifier_name,
                "lat": pin["lat"] if pin else None, "lon": pin["lon"] if pin else None}

    def _publish(self, e: dict, push: bool = True):
        self.events.append(e)
        self.seen.add(e["id"])
        if push:
            frame = {"type": "anomaly" if e["is_anomaly"] else "event", "data": e}
            for q in list(self.subscribers):
                q.put_nowait(frame)

    # ------------------------------------------------------------------ sources
    def poll_gdelt(self, timespan: str = "1h", maxrecords: int = 75) -> int:
        """One GDELT DOC request (>= 5 s apart per GDELT policy). Returns number of new events."""
        wait = 5.5 - (time.time() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.time()
        params = {"query": QUERY, "mode": "artlist", "format": "json", "maxrecords": maxrecords,
                  "timespan": timespan, "sort": "datedesc"}
        r = requests.get(f"{GDELT}?{urlencode(params)}", timeout=30,
                         headers={"User-Agent": "TRACE/0.1 (CDC 2026 research)"})
        if r.status_code != 200 or not r.text.lstrip().startswith("{"):
            raise RuntimeError(f"GDELT HTTP {r.status_code}: {r.text[:120]}")
        arts = r.json().get("articles", [])
        if not arts:
            raise RuntimeError("GDELT returned no articles")
        new = 0
        titles = {re.sub(r"\W+", " ", e["title"].lower()).strip() for e in self.events}
        for a in arts:
            url, title = a.get("url", ""), (a.get("title") or "").strip()
            key = re.sub(r"\W+", " ", title.lower()).strip()
            eid = "gdelt-" + hashlib.sha1(url.encode()).hexdigest()[:10]
            if not title or eid in self.seen or key in titles:
                continue  # dedupe by URL and normalised title
            titles.add(key)
            seen = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            ev = self.build_event(title, url, seen, a.get("domain") or urlparse(url).netloc, a.get("language", ""))
            self.seen.add(eid)
            if ev:
                self._publish(ev)
                new += 1
        self.status, self.retrieved_at, self.note = "live", _iso(_now()), f"{len(arts)} articles, {new} new events"
        self._save()
        return new

    def _replay_one(self, push: bool = True) -> dict | None:
        """Replay one synthetic sample headline (clearly marked sample.trace.local)."""
        for _ in range(len(self._replay)):
            title = self._replay[self._replay_i % len(self._replay)]
            self._replay_i += 1
            now = _now()
            url = f"https://sample.trace.local/replay/{self._replay_i}-{int(now.timestamp())}"
            ev = self.build_event(title, url, now, "sample.trace.local", "English")
            if ev:
                self._publish(ev, push=push)
                return ev
        return None

    async def poll_forever(self):
        replay_s = float(os.environ.get("TRACE_LIVEWIRE_REPLAY_SECONDS", "45"))
        first = True
        while True:
            try:
                n = await asyncio.to_thread(self.poll_gdelt, "24h" if first else "1h")
                log.info("GDELT poll: %d new events", n)
                first = False
                self.next_poll_at = _now() + timedelta(minutes=config.GDELT_POLL_MINUTES)
                await asyncio.sleep(config.GDELT_POLL_MINUTES * 60)
            except Exception as exc:
                self.status, self.note = "fallback", f"GDELT unavailable ({str(exc)[:80]}); replaying synthetic sample"
                log.warning("Live Wire fallback: %s", exc)
                deadline = time.time() + min(config.GDELT_POLL_MINUTES * 60, 300)
                self.next_poll_at = _now() + timedelta(seconds=deadline - time.time())
                while time.time() < deadline:
                    self._replay_one()
                    await asyncio.sleep(replay_s)

    # ------------------------------------------------------------------ reporting
    def source_status(self) -> dict:
        return {**SOURCES["gdelt"], "status": self.status, "retrieved_at": self.retrieved_at, "last_updated": None,
                "latest_year": _now().year, "note": self.note}

    def recent(self, since: datetime | None = None, limit: int = 50, drug: str | None = None) -> list[dict]:
        ev = [e for e in self.events if (drug is None or e["drug"] == drug)
              and (since is None or e["published_at"] > _iso(since))]
        return sorted(ev, key=lambda e: e["published_at"], reverse=True)[:limit]

    def news_edges(self, days: int = 30) -> set[tuple[str, str, str]]:
        cut = _iso(_now() - timedelta(days=days))
        # synthetic replay items never count as evidence
        return {(e["drug"], e["origin"], e["destination"]) for e in self.events
                if e["origin"] and e["destination"] and e["published_at"] >= cut
                and e["source_domain"] != "sample.trace.local"}

    @lru_cache(maxsize=1)  # noqa: B019 - one LiveWire per process
    def accuracy(self) -> dict:
        rows = load_eval()
        clf = self.classifier
        hits = {k: 0 for k in ("is_event", "event_type", "drug", "origin", "destination", "size")}
        for r in rows:
            c = clf.classify(r["title"])
            hits["is_event"] += int((c.is_event >= 0.5) == bool(r["is_event"]))
            hits["event_type"] += int(c.event_type == r["event_type"])
            hits["drug"] += int(c.drug == r["drug"])
            hits["origin"] += int(c.origin == r["origin"])
            hits["destination"] += int(c.destination == r["destination"])
            hits["size"] += int(c.size == r["size"])
        n = len(rows)
        return {"classifier": self.classifier_name, "n_labeled": n,
                "field_accuracy": {k: round(v / n, 3) for k, v in hits.items()},
                "note": ("Evaluated on 100 synthetic headlines with provisional labels drafted by the backend agent "
                         "(jev/data/labeled_eval.json); the mock's rules were written alongside them, so treat these "
                         "as an upper bound. Re-run on team hand-labelled GDELT articles, and with Jev once a key exists.")}


_STATE: LiveWire | None = None


def state() -> LiveWire:
    global _STATE
    if _STATE is None:
        _STATE = LiveWire()
    return _STATE


_POLLER: asyncio.Task | None = None


@router.on_event("startup")
async def _start():
    global _POLLER
    if os.environ.get("TRACE_LIVEWIRE_POLL", "1") != "0" and _POLLER is None:
        _POLLER = asyncio.get_event_loop().create_task(state().poll_forever())


@router.get("/api/livewire")
def get_livewire(since: datetime | None = None, limit: int = Query(50, ge=1, le=500),
                 drug: str | None = Query(None, pattern="^(cocaine|heroin|meth|cannabis|fentanyl|other|unclear)$")):
    from .app import envelope
    lw = state()
    return envelope({"classifier": lw.classifier_name, "events": lw.recent(since, limit, drug)}, "gdelt",
                    notes=["Dates are GDELT publication metadata. Events below 0.6 confidence are hidden.",
                           *(["GDELT unavailable: replaying synthetic sample headlines (sample.trace.local)."]
                             if lw.status == "fallback" else [])])


@router.websocket("/ws/livewire")
async def ws_livewire(ws: WebSocket, drug: str | None = None):
    await ws.accept()
    lw = state()
    q: asyncio.Queue = asyncio.Queue()
    lw.subscribers.add(q)
    try:
        await ws.send_json({"type": "hello", "data": {"classifier": lw.classifier_name,
                                                      "poll_minutes": config.GDELT_POLL_MINUTES,
                                                      "server_time": _iso(_now()),
                                                      "backlog": lw.recent(limit=20, drug=drug)}})

        async def reader():
            while True:
                msg = await ws.receive_json()
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await q.put({"type": "pong", "data": {"server_time": _iso(_now())}})

        rtask = asyncio.create_task(reader())
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=20)
                except TimeoutError:
                    frame = {"type": "heartbeat", "data": {"server_time": _iso(_now()),
                                                           "next_poll_at": _iso(lw.next_poll_at),
                                                           "events_total": len(lw.events)}}
                if rtask.done():
                    break
                if frame["type"] in ("event", "anomaly") and drug and frame["data"]["drug"] != drug:
                    continue
                await ws.send_json(frame)
        finally:
            rtask.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        lw.subscribers.discard(q)


def poll_once(offline: bool = False) -> list[dict]:
    """CLI helper: `uv run trace livewire [--offline]`."""
    lw = state()
    before = len(lw.events)
    if offline:
        for _ in range(10):
            lw._replay_one(push=False)
    else:
        try:
            lw.poll_gdelt("24h")
        except Exception as exc:
            print(f"GDELT unavailable ({exc}); showing replayed sample")
            for _ in range(10):
                lw._replay_one(push=False)
    return list(lw.events)[before:]
