# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T8: Live Wire. GDELT poll every 15 minutes, dedupe, classify via JevClassifier, push over WebSocket.

- Dates come from GDELT `seendate`, never from the classifier.
- Every classification passes the grounding guardrails (`jev/grounding.py`): countries and drugs the headline does
  not state are removed ("not stated"), size comes only from a stated quantity (`size_stated`).
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
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .. import config
from ..jev.base import Classification, JevClassifier
from ..jev.grounding import MIN_CONFIDENCE, ground, passes_wire
from ..jev.mock import MockJevClassifier
from ..jev.real import get_classifier
from ..sources import SOURCES

log = logging.getLogger(__name__)
router = APIRouter()
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = ('(cocaine OR heroin OR methamphetamine OR cannabis OR fentanyl OR hashish OR "drug trafficking") '
         '(seized OR seizure OR bust OR smuggling OR trafficking OR cartel OR legalization) sourcelang:english')
MIN_CONF = MIN_CONFIDENCE
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
        self.classifier_fallback: str | None = None  # why the requested classifier is not running (/api/meta)
        self.classifier: JevClassifier = self._pick_classifier(s.countries)
        self.classifier_name = self.classifier.name
        self._backlog_pending, self._backlog_lock = False, threading.Lock()
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

    # ------------------------------------------------------------------ classifier choice and fallback
    def _pick_classifier(self, countries: list[dict]) -> JevClassifier:
        """get_classifier, but never silently the mock: if TRACE_CLASSIFIER asks for jev/reflex and that cannot be
        built (or later fails, e.g. the lazily loaded ONNX session), log an error and report it in /api/meta."""
        want = os.environ.get("TRACE_CLASSIFIER", "").strip().lower()
        try:
            clf = get_classifier(countries)
        except Exception as exc:  # e.g. missing or unreadable Reflex model files
            self._fall_back(f"{want or 'classifier'} failed to load ({type(exc).__name__}: {str(exc)[:160]})")
            return MockJevClassifier()
        if want and want != "mock" and clf.name.split("-")[0] != want.split("-")[0]:  # reflex-remote -> reflex
            self._fall_back(f"TRACE_CLASSIFIER={want} requested but unavailable (see server log)")
        return clf if clf.name == "mock" else _Guarded(clf, self)

    def _fall_back(self, why: str) -> None:
        self.classifier_fallback = f"{why}; Live Wire uses the keyword mock"
        log.error("Live Wire classifier fallback: %s", self.classifier_fallback)

    def ensure_backlog(self, n: int = 12) -> None:
        """Without a poller (TRACE_LIVEWIRE_POLL=0, e.g. Vercel) a model classifier fills the replay backlog on the
        first Live Wire read, so the model loads on first use and never on another endpoint's cold start."""
        if not self._backlog_pending:
            return
        with self._backlog_lock:
            while self._backlog_pending and len(self.events) < n:
                ev = self._replay_build()
                if not ev:
                    break
                self._publish(ev, push=False)
            self._backlog_pending = False

    # ------------------------------------------------------------------ model probabilities
    @staticmethod
    def _load_all_probabilities() -> dict:
        """Probabilities for every candidate corridor (not only those shown on the map)."""
        try:  # plain sqlite3 (same rows as db.read_table) so a cold start does not import pandas
            from .. import db
            with db.connect(read_only=True) as con:
                schema = db.schema_of(con, "predictions")
                if schema is None:
                    return {}
                rows = con.execute(f'SELECT drug, from_iso3, to_iso3, probability FROM {schema}."predictions"')
                return {(d, o, t): float("nan") if p is None else float(p) for d, o, t, p in rows}
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
        if not self.events and self.classifier_name == "mock":  # heavier classifiers fill the backlog off-loop
            for _ in range(12):
                self._replay_one(push=False)
        elif not self.events and os.environ.get("TRACE_LIVEWIRE_POLL", "1") == "0":
            self._backlog_pending = True  # no poller: the first reader fills it (ensure_backlog)

    def _save(self):
        try:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STORE_PATH.write_text(json.dumps(list(self.events)), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ classification
    def build_event(self, title: str, url: str, published: datetime, domain: str, language: str = "English",
                    text: str = "") -> dict | None:
        c = ground(self.classifier.classify(title, text), title, text)  # idempotent for Reflex
        if not passes_wire(c, MIN_CONF):  # confident non-events never reach the wire
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
                "destination": d, "size": c.size, "size_stated": c.size_stated, "is_event": round(c.is_event, 3),
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
    def poll_gdelt(self, timespan: str = "1h", maxrecords: int = 75) -> list[dict]:
        """One GDELT DOC request (>= 5 s apart per GDELT policy). Classifies in the calling (worker) thread and
        returns the new events; publishing to WebSocket queues happens on the event loop."""
        wait = 5.5 - (time.time() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.time()
        params = {"query": QUERY, "mode": "artlist", "format": "json", "maxrecords": maxrecords,
                  "timespan": timespan, "sort": "datedesc"}
        import requests  # lazy: only the GDELT poller needs it

        r = requests.get(f"{GDELT}?{urlencode(params)}", timeout=30,
                         headers={"User-Agent": "TRACE/0.1 (CDC 2026 research)"})
        if r.status_code != 200 or not r.text.lstrip().startswith("{"):
            raise RuntimeError(f"GDELT HTTP {r.status_code}: {r.text[:120]}")
        arts = r.json().get("articles", [])
        if not arts:
            raise RuntimeError("GDELT returned no articles")
        new: list[dict] = []
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
                new.append(ev)
        self.status, self.retrieved_at, self.note = "live", _iso(_now()), f"{len(arts)} articles, {len(new)} new events"
        return new

    def _replay_build(self) -> dict | None:
        """Classify one synthetic sample headline (clearly marked sample.trace.local); thread-safe, no publish."""
        for _ in range(len(self._replay)):
            title = self._replay[self._replay_i % len(self._replay)]
            self._replay_i += 1
            now = _now()
            url = f"https://sample.trace.local/replay/{self._replay_i}-{int(now.timestamp())}"
            ev = self.build_event(title, url, now, "sample.trace.local", "English")
            if ev:
                return ev
        return None

    def _replay_one(self, push: bool = True) -> dict | None:
        ev = self._replay_build()
        if ev:
            self._publish(ev, push=push)
        return ev

    async def poll_forever(self):
        replay_s = float(os.environ.get("TRACE_LIVEWIRE_REPLAY_SECONDS", "45"))
        first = True
        while len(self.events) < 12:  # initial backlog, classified off the event loop
            ev = await asyncio.to_thread(self._replay_build)
            if not ev:
                break
            self._publish(ev, push=False)
        while True:
            try:
                new = await asyncio.to_thread(self.poll_gdelt, "24h" if first else "1h")
                for ev in new:
                    self._publish(ev)
                self._save()
                log.info("GDELT poll: %d new events", len(new))
                first = False
                self.next_poll_at = _now() + timedelta(minutes=config.GDELT_POLL_MINUTES)
                await asyncio.sleep(config.GDELT_POLL_MINUTES * 60)
            except Exception as exc:
                self.status, self.note = "fallback", f"GDELT unavailable ({str(exc)[:80]}); replaying synthetic sample"
                log.warning("Live Wire fallback: %s", exc)
                deadline = time.time() + min(config.GDELT_POLL_MINUTES * 60, 300)
                self.next_poll_at = _now() + timedelta(seconds=deadline - time.time())
                while time.time() < deadline:
                    ev = await asyncio.to_thread(self._replay_build)
                    if ev:
                        self._publish(ev)
                    await asyncio.sleep(replay_s)

    # ------------------------------------------------------------------ reporting
    def source_status(self) -> dict:
        note = self.note + (f"; classifier fallback: {self.classifier_fallback}" if self.classifier_fallback else "")
        return {**SOURCES["gdelt"], "status": self.status, "retrieved_at": self.retrieved_at, "last_updated": None,
                "latest_year": _now().year, "note": note}

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
        if self.classifier_name.startswith("reflex"):  # precomputed by `trace reflex-eval` (slow on CPU)
            ev = config.DATA / "reflex" / "eval.json"
            if ev.exists():
                d = json.loads(ev.read_text(encoding="utf-8"))["L6_domain"]
                r = {k: v for k, v in d["reflex"].items() if k != "ms_per_article"}
                return {"classifier": self.classifier_name, "n_labeled": 100, "field_accuracy": r,
                        "note": ("Reflex (TRACE's own System One model) on 100 synthetic headlines with provisional "
                                 "labels; mock keyword classifier on the same set: "
                                 + ", ".join(f"{k} {v}" for k, v in d["mock"].items() if k != "ms_per_article"))}
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


class _Guarded(JevClassifier):
    """Wraps a model classifier: the first exception (e.g. the ONNX session cannot be created) switches the Live Wire
    to the keyword mock for good, logged as an error and reported in /api/meta, instead of failing every article."""

    def __init__(self, inner: JevClassifier, wire: LiveWire):
        self.inner, self.wire, self.name = inner, wire, inner.name

    def classify(self, title: str, text: str = "") -> Classification:
        try:
            return self.inner.classify(title, text)
        except Exception as exc:
            if getattr(self.inner, "url", None):  # remote Reflex: a network blip must not downgrade the wire for good
                log.warning("Reflex service call failed (%s); keyword mock for this article only", exc)
                return MockJevClassifier().classify(title, text)
            w = self.wire
            if w.classifier is self:
                w._fall_back(f"{self.name} failed ({type(exc).__name__}: {str(exc)[:160]})")
                log.exception("Live Wire classifier %s failed", self.name)
                w.classifier, w.classifier_name = MockJevClassifier(), "mock"
            return w.classifier.classify(title, text)


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
    lw.ensure_backlog()
    return envelope({"classifier": lw.classifier_name, "events": lw.recent(since, limit, drug)}, "gdelt",
                    notes=["Dates are GDELT publication metadata. Events below 0.6 confidence are hidden.",
                           *(["GDELT unavailable: replaying synthetic sample headlines (sample.trace.local)."]
                             if lw.status == "fallback" else [])])


@router.websocket("/ws/livewire")
async def ws_livewire(ws: WebSocket, drug: str | None = None):
    await ws.accept()
    lw = state()
    await asyncio.to_thread(lw.ensure_backlog)
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
            for ev in lw.poll_gdelt("24h"):
                lw._publish(ev, push=False)
        except Exception as exc:
            print(f"GDELT unavailable ({exc}); showing replayed sample")
            for _ in range(10):
                lw._replay_one(push=False)
    return list(lw.events)[before:]


class ClassifyIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    text: str = Field("", max_length=2000)


@router.post("/api/livewire/classify")
def classify_headline(body: ClassifyIn):
    """Classify one headline live with the deployed classifier (Reflex through ONNX in production) and the same
    grounding guardrails the wire uses: a country, drug or size the text does not state comes back as not stated.
    `on_wire` says whether the article would pass the Live Wire's event and confidence gate. Nothing is stored."""
    from .app import envelope
    from fastapi import HTTPException
    lw = state()
    clf = getattr(lw.classifier, "inner", lw.classifier)  # unwrap: never answer with a silent mock fallback here
    t0 = time.perf_counter()
    try:
        c = ground(clf.classify(body.title, body.text), body.title, body.text)
    except Exception as exc:
        log.warning("live classify failed: %s", exc)
        raise HTTPException(status_code=503, detail={"code": "classifier_unavailable",
                                                     "message": f"{clf.name} is unavailable; try again shortly."})
    ms = round((time.perf_counter() - t0) * 1000)
    return envelope({"classifier": clf.name, "on_wire": passes_wire(c, MIN_CONF), "latency_ms": ms,
                     "classification": c.to_dict()},
                    notes=["Live classification of the text you sent; nothing is stored or published to the wire.",
                           "Guardrails: countries, drugs and sizes must be stated in the text, otherwise not stated."])
