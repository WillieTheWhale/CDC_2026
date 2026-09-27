# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""People API: bounded, paginated search over the curated, source-cited People dataset.

The dataset is the frontend team's reviewed manifest (`frontend/data/people/manifest.json`, built by
`frontend/scripts/aggregate-people.mjs`); this module only reads it. Query semantics mirror the frontend's own
route handlers (`frontend/lib/people-query.ts`) so the UI behaves the same against either server.

Freshness: with `TRACE_PEOPLE_REMOTE=1` (set on Vercel) the manifest is re-read from GitHub `main` at most every
`TRACE_PEOPLE_REFRESH_SECONDS` (default 600; 0 disables) within a ~5 s deadline, falling back to the bundled copy
on any error. `meta.people_snapshot` says which copy answered. Cursors encode sort keys, so they survive a refresh.

Design boundary: people are associated with countries only (never coordinates), every person, organization and
connection must carry at least one citable source, and connections are never inferred from shared membership.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .. import config

router = APIRouter()

_CANDIDATES = [Path(os.environ["TRACE_PEOPLE_MANIFEST"])] if os.environ.get("TRACE_PEOPLE_MANIFEST") else []
_CANDIDATES += [config.REPO / "frontend" / "data" / "people" / "manifest.json",
                config.DATA / "people" / "manifest.json"]
STATUSES = {"convicted", "charged", "sanctioned", "reported"}
EVENT_TYPES = {"arrest", "charge", "conviction", "sentence", "sanction", "development"}
LIFE_STATUSES = {"deceased", "unknown"}
LEGAL_STATUSES = {"reported", "arrested", "charged", "convicted", "sentenced", "acquitted", "overturned",
                  "dismissed", "sanctioned", "delisted", "extradited", "released"}
REMOTE_URL = "https://raw.githubusercontent.com/WillieTheWhale/CDC_2026/main/frontend/data/people/manifest.json"
REMOTE_TIMEOUT = 5.0
NETWORK_LIMIT = 48
NOTES = ["Curated sample of publicly reported, source-cited people; not a census. Status reflects the cited "
         "source as of statusAsOf (charged is not convicted). Locations are country-level associations only.",
         "Connections are listed only where a source documents that specific relationship."]


def _bad(message: str):
    raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": message})


def _http(url) -> bool:
    return isinstance(url, str) and re.match(r"^https?://\S+$", url, re.I) is not None


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _citable(s) -> bool:
    return isinstance(s, dict) and _http(s.get("url")) and all(_text(s.get(k))
                                                               for k in ("title", "publisher", "language", "claim"))


def _sources(values) -> list[dict]:
    return [s for s in values if _citable(s)] if isinstance(values, list) else []


def _day(v) -> bool:
    """YYYY-MM-DD that JavaScript's Date.parse accepts (month 01-12, day 01-31), as the frontend checks."""
    return isinstance(v, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", v) is not None


def _real_date(v, partial: bool = False) -> bool:
    """A real calendar date; `partial` also allows YYYY or YYYY-MM when the source gives no day."""
    if not isinstance(v, str):
        return False
    if partial and re.fullmatch(r"\d{4}(-(0[1-9]|1[0-2]))?", v):
        return True
    try:
        return re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) is not None and bool(date.fromisoformat(v))
    except ValueError:
        return False


def _event_ok(e) -> bool:
    return (isinstance(e, dict) and _text(e.get("id")) and _day(e.get("occurredAt")) and e.get("type") in EVENT_TYPES
            and _text(e.get("title")) and _text(e.get("summary")) and _citable(e.get("source")))


def _life_ok(v) -> bool:
    """Biographical status with its own source; a death date only on `deceased`."""
    return (isinstance(v, dict) and v.get("value") in LIFE_STATUSES and _citable(v.get("source"))
            and (v.get("asOf") is None or _real_date(v["asOf"]))
            and (v.get("deathDate") is None or (v["value"] == "deceased" and _real_date(v["deathDate"], True))))


def _legal_ok(e) -> bool:
    """One dated legal-status claim with its qualifier and source; a past charge does not mean it is pending."""
    return (isinstance(e, dict) and e.get("status") in LEGAL_STATUSES and _real_date(e.get("date"), True)
            and _text(e.get("qualifier")) and _citable(e.get("source"))
            and all(e.get(k) is None or _text(e[k]) for k in ("jurisdiction", "offense"))
            and (e.get("partial") is None or isinstance(e["partial"], bool)))


def normalize(raw: dict) -> dict:
    """Same acceptance rules as the frontend's normalizeDataset: drop anything that is not citable.

    `lifeStatus` and `legalHistory` are optional and independent of legal `status`, which a death never replaces;
    invalid ones are dropped, not fatal."""
    orgs = [{**o, "sources": _sources(o.get("sources"))} for o in raw.get("organizations", [])
            if isinstance(o.get("id"), str) and isinstance(o.get("name"), str)
            and isinstance(o.get("regions"), list) and _sources(o.get("sources"))]
    org_ids = {o["id"] for o in orgs}
    people = []
    for p in raw.get("people", []):
        srcs = _sources(p.get("sources"))
        if not (isinstance(p.get("id"), str) and isinstance(p.get("name"), str) and srcs
                and isinstance(p.get("organizationIds"), list) and isinstance(p.get("regions"), list)
                and p.get("status") in STATUSES and p.get("prominence") in (1, 2, 3)):
            continue
        urls = {s["url"] for s in srcs}
        regions = []
        for r in p["regions"]:
            if not (isinstance(r, dict) and re.fullmatch(r"[A-Z]{3}", str(r.get("iso3"))) and _text(r.get("label"))):
                continue
            ev = r.get("evidence")
            ok = (isinstance(ev, dict) and _text(ev.get("claim")) and ev.get("sourceUrl") in urls
                  and (ev.get("period") is None or _text(ev["period"])))
            regions.append({**{k: v for k, v in r.items() if k != "evidence"}, **({"evidence": ev} if ok else {})})
        person = {**p, "sources": srcs, "regions": regions,
                  "organizationIds": [i for i in p["organizationIds"] if i in org_ids],
                  "events": sorted([e for e in p.get("events") or [] if _event_ok(e)],
                                   key=lambda e: e["occurredAt"], reverse=True)}
        photo = p.get("photo")
        if not (isinstance(photo, dict) and _http(photo.get("url")) and _http(photo.get("sourceUrl"))
                and (not photo.get("licenseUrl") or _http(photo["licenseUrl"])) and photo["sourceUrl"] in urls
                and _text(photo.get("credit")) and _text(photo.get("license"))):
            person.pop("photo", None)
        if not _life_ok(p.get("lifeStatus")):
            person.pop("lifeStatus", None)
        if "legalHistory" in p:
            hist = p["legalHistory"] if isinstance(p["legalHistory"], list) else []
            person["legalHistory"] = sorted([e for e in hist if _legal_ok(e)], key=lambda e: e["date"], reverse=True)
        people.append(person)
    ids = {p["id"] for p in people}
    conns = [{**c, "sources": _sources(c.get("sources"))} for c in raw.get("connections", [])
             if isinstance(c.get("id"), str) and c.get("fromId") in ids and c.get("toId") in ids
             and _sources(c.get("sources")) and _text(c.get("label"))]
    return {"organizations": orgs, "people": people, "connections": conns}


@lru_cache(maxsize=1)
def _bundled() -> dict:
    """The manifest packaged with this deployment (the repo checkout in local dev)."""
    snap = {"origin": "bundled", "fetched_at": None}
    for path in _CANDIDATES:
        if path.exists():
            return {**normalize(json.loads(path.read_text(encoding="utf-8"))), "snapshot": snap}
    return {"organizations": [], "people": [], "connections": [], "snapshot": snap}


def _fetch(url: str, etag: str | None, timeout: float) -> tuple[dict | None, str | None]:
    """GET the raw manifest within `timeout` seconds overall. Returns (None, etag) when unchanged (HTTP 304)."""
    deadline = time.monotonic() + timeout
    headers = {"User-Agent": "trace-backend", **({"If-None-Match": etag} if etag else {})}
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag
        raise
    with resp:
        chunks = []
        while chunk := resp.read(1 << 16):
            chunks.append(chunk)
            if time.monotonic() > deadline:
                raise TimeoutError("people manifest download exceeded the deadline")
        return json.loads(b"".join(chunks).decode("utf-8")), resp.headers.get("ETag")


_state: dict = {"data": None, "etag": None, "checked": None}
_lock = threading.Lock()


def _refresh_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("TRACE_PEOPLE_REFRESH_SECONDS", "600")))
    except ValueError:
        return 600.0


def dataset() -> dict:
    """Normalized People data: GitHub `main` when TRACE_PEOPLE_REMOTE=1 and reachable, else the bundled manifest.

    One request at a time refreshes (others keep serving the current copy); a failed fetch retries after 60 s."""
    ttl = _refresh_seconds()
    if os.environ.get("TRACE_PEOPLE_REMOTE") != "1" or ttl == 0:
        return _bundled()
    now = time.monotonic()
    wait = ttl if _state["data"] else min(ttl, 60.0)
    if (_state["checked"] is None or now - _state["checked"] >= wait) and _lock.acquire(blocking=False):
        try:
            _state["checked"] = now
            raw, etag = _fetch(REMOTE_URL, _state["etag"] if _state["data"] else None, REMOTE_TIMEOUT)
            stamp = datetime.now(UTC).replace(microsecond=0).isoformat()
            if raw is None:
                _state["data"] = {**_state["data"], "snapshot": {"origin": "github-main", "fetched_at": stamp}}
            else:
                data = normalize(raw)
                if not data["people"]:
                    raise ValueError("remote People manifest has no valid people")
                _state.update(data={**data, "snapshot": {"origin": "github-main", "fetched_at": stamp}}, etag=etag)
        except Exception:  # network, HTTP, JSON or shape error: keep serving what we have
            pass
        finally:
            _lock.release()
    return _state["data"] or _bundled()


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def _key(p: dict) -> tuple[str, str]:
    return (_fold(p["name"]), p["id"])


def _js(v) -> str:
    """JSON.stringify-compatible text, so cursors match the frontend route handlers byte for byte."""
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)


def _tokens(value: str) -> list[str]:
    """Search tokens as the frontend's searchTokens: NFKD, lower-case, strip combining marks, split on anything that
    is not a letter or number (so "jose" finds "José" and word order does not matter)."""
    s = unicodedata.normalize("NFD", unicodedata.normalize("NFKD", value).lower())
    s = "".join(ch for ch in s if not unicodedata.category(ch).startswith("M"))
    return re.findall(r"[^\W_]+", s)


def _matches(p: dict, tokens: list[str]) -> bool:
    """Every search token is a substring of some token of the name or of one alias (matchesSearch)."""
    if not tokens:
        return True
    return any(all(any(t in part for part in _tokens(v)) for t in tokens)
               for v in [p["name"], *(p.get("aliases") or [])])


def _in_bbox(lon: float, lat: float, box: tuple[float, float, float, float]) -> bool:
    west, south, east, north = box
    if lat < south or lat > north:
        return False
    if east - west >= 360:
        return True
    return ((lon - west) % 360 + 360) % 360 <= east - west


def _page_extras(d: dict, people: list[dict]) -> dict:
    pids = {p["id"] for p in people}
    oids = {o for p in people for o in p["organizationIds"]}
    return {"people": people, "organizations": [o for o in d["organizations"] if o["id"] in oids],
            "connections": [c for c in d["connections"] if c["fromId"] in pids and c["toId"] in pids]}


def _envelope(d: dict, data, **extra) -> dict:
    from .app import envelope
    body = envelope(data, notes=NOTES)
    body["meta"].update(extra)
    if d.get("snapshot"):
        body["meta"]["people_snapshot"] = d["snapshot"]
    return body


@router.get("/api/people")
def get_people(search: str = Query("", max_length=120), zoom: int = Query(1, ge=1, le=3),
               bbox: str | None = None, country: str | None = Query(None, pattern="^[A-Z]{3}$"),
               unlocated: str | None = None,
               limit: int = Query(100, ge=1, le=250), cursor: str | None = Query(None, max_length=4096)):
    """People page. Without search, country or unlocated, only people at or above the zoom's prominence tier are
    listed, optionally within a viewport (a person matches if any associated country's capital is inside it).
    `unlocated=1` lists every tier's people with no sourced country (`regions: []`)."""
    box = None
    if bbox is not None:
        try:
            box = tuple(float(v) for v in bbox.split(","))
        except ValueError:
            box = ()
        if (len(box) != 4 or not all(v == v and abs(v) != float("inf") for v in box)
                or not (-90 <= box[1] <= 90 and -90 <= box[3] <= 90) or box[1] > box[3]
                or box[2] < box[0] or box[2] - box[0] > 720):
            _bad("bbox must be west,south,east,north")
    if unlocated is not None and unlocated != "1":
        _bad("unlocated must be 1")
    lone = unlocated == "1"
    if lone and (country or box):
        _bad("unlocated cannot be combined with country or bbox")
    tokens = _tokens(search)
    needle = bool(tokens)
    from .app import store
    coords = {c["iso3"]: (c.get("lon"), c.get("lat")) for c in store().countries}

    def visible(p: dict) -> bool:
        if not (lone or needle or country or p["prominence"] <= zoom):
            return False
        if not _matches(p, tokens):
            return False
        if lone and p["regions"]:
            return False
        if country and not any(r["iso3"] == country for r in p["regions"]):
            return False
        if not needle and not country and box:
            return any(coords.get(r["iso3"], (None, None))[0] is not None
                       and _in_bbox(*coords[r["iso3"]], box) for r in p["regions"])
        return True

    d = dataset()
    rows = sorted((p for p in d["people"] if visible(p)), key=_key)
    num = [int(v) if v == int(v) else v for v in box] if box else None
    key_tokens = sorted(tokens)
    fkey = (_js([key_tokens, "unlocated"]) if lone else _js([key_tokens, country]) if country else
            _js([key_tokens, "global-search"]) if needle else _js(["", zoom, num]))
    start = 0
    if cursor:
        try:
            last = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
            assert isinstance(last, list) and len(last) == 3 and last[0] == fkey
            assert isinstance(last[1], str) and isinstance(last[2], str)
        except Exception:
            _bad("cursor does not match these filters")
        start = next((i for i, p in enumerate(rows) if _key(p) > (last[1], last[2])), len(rows))
    page = rows[start:start + limit]
    nxt = None
    if page and start + len(page) < len(rows):
        nxt = base64.urlsafe_b64encode(_js([fkey, *_key(page[-1])]).encode()).decode().rstrip("=")
    return _envelope(d, _page_extras(d, page), total=len(rows), next_cursor=nxt)


@router.get("/api/people/countries")
def get_people_countries(search: str = Query("", max_length=120), zoom: int = Query(3, ge=1, le=3)):
    """Per-country counts: `total` people associated with the country, `visible` at this zoom tier."""
    tokens = _tokens(search)
    counts: dict[str, dict] = {}
    d = dataset()
    for p in d["people"]:
        if not _matches(p, tokens):
            continue
        for iso3 in {r["iso3"] for r in p["regions"]}:
            c = counts.setdefault(iso3, {"iso3": iso3, "total": 0, "visible": 0})
            c["total"] += 1
            c["visible"] += bool(tokens or p["prominence"] <= zoom)
    return _envelope(d, sorted(counts.values(), key=lambda c: c["iso3"]))


@router.get("/api/people/network")
def get_people_network(person_id: str = Query(..., min_length=1, max_length=160)):
    """A person's documented connections (first 48 by id) and the people and organizations they touch."""
    d = dataset()
    if not any(p["id"] == person_id for p in d["people"]):
        raise HTTPException(status_code=404, detail={"code": "unknown_person", "message": "Person not found"})
    conns = sorted((c for c in d["connections"] if person_id in (c["fromId"], c["toId"])), key=lambda c: c["id"])
    shown = conns[:NETWORK_LIMIT]
    pids = {person_id} | {i for c in shown for i in (c["fromId"], c["toId"])}
    people = [p for p in d["people"] if p["id"] in pids]
    oids = {o for p in people for o in p["organizationIds"]}
    data = {"people": people, "organizations": [o for o in d["organizations"] if o["id"] in oids],
            "connections": shown}
    return _envelope(d, data, total=len(people), total_connections=len(conns), next_cursor=None)


@router.get("/api/people/{person_id}")
def get_person(person_id: str):
    """One person's full evidence record (sources, dated events, country associations), their organizations,
    and their documented connections."""
    d = dataset()
    person = next((p for p in d["people"] if p["id"] == person_id), None)
    if person is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_person", "message": "Person not found"})
    conns = [c for c in d["connections"] if person_id in (c["fromId"], c["toId"])]
    return _envelope(d, {"person": person,
                         "organizations": [o for o in d["organizations"] if o["id"] in person["organizationIds"]],
                         "connections": conns})
