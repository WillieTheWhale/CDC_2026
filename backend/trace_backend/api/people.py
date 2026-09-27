# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""People API: bounded, paginated search over the curated, source-cited People dataset.

The dataset is the frontend team's reviewed manifest (`frontend/data/people/manifest.json`, built by
`frontend/scripts/aggregate-people.mjs`); this module only reads it. Query semantics mirror the frontend's own
route handlers (`frontend/lib/people-query.ts`) so the UI behaves the same against either server.

Design boundary: people are associated with countries only (never coordinates), every person, organization and
connection must carry at least one citable source, and connections are never inferred from shared membership.
"""
from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
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
NETWORK_LIMIT = 48
NOTES = ["Curated sample of publicly reported, source-cited people; not a census. Status reflects the cited "
         "source as of statusAsOf (charged is not convicted). Locations are country-level associations only.",
         "Connections are listed only where a source documents that specific relationship."]


def _bad(message: str):
    raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": message})


def _http(url) -> bool:
    return isinstance(url, str) and re.match(r"^https?://\S+$", url, re.I) is not None


def _citable(s) -> bool:
    return isinstance(s, dict) and _http(s.get("url")) and all(
        isinstance(s.get(k), str) and s[k].strip() for k in ("title", "publisher", "language", "claim"))


def _sources(values) -> list[dict]:
    return [s for s in values if _citable(s)] if isinstance(values, list) else []


def _event_ok(e) -> bool:
    return (isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"].strip()
            and isinstance(e.get("occurredAt"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["occurredAt"])
            and e.get("type") in EVENT_TYPES and all(isinstance(e.get(k), str) and e[k].strip()
                                                    for k in ("title", "summary")) and _citable(e.get("source")))


def normalize(raw: dict) -> dict:
    """Same acceptance rules as the frontend's normalizeDataset: drop anything that is not citable."""
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
            if not (isinstance(r, dict) and re.fullmatch(r"[A-Z]{3}", str(r.get("iso3")))
                    and isinstance(r.get("label"), str) and r["label"].strip()):
                continue
            ev = r.get("evidence")
            ok = (isinstance(ev, dict) and isinstance(ev.get("claim"), str) and ev["claim"].strip()
                  and ev.get("sourceUrl") in urls and (ev.get("period") is None or
                                                       (isinstance(ev["period"], str) and ev["period"].strip())))
            regions.append({**{k: v for k, v in r.items() if k != "evidence"}, **({"evidence": ev} if ok else {})})
        person = {**p, "sources": srcs, "regions": regions,
                  "organizationIds": [i for i in p["organizationIds"] if i in org_ids],
                  "events": sorted([e for e in p.get("events") or [] if _event_ok(e)],
                                   key=lambda e: e["occurredAt"], reverse=True)}
        photo = p.get("photo")
        if not (isinstance(photo, dict) and _http(photo.get("url")) and _http(photo.get("sourceUrl"))
                and (not photo.get("licenseUrl") or _http(photo["licenseUrl"])) and photo["sourceUrl"] in urls
                and all(isinstance(photo.get(k), str) and photo[k].strip() for k in ("credit", "license"))):
            person.pop("photo", None)
        people.append(person)
    ids = {p["id"] for p in people}
    conns = [{**c, "sources": _sources(c.get("sources"))} for c in raw.get("connections", [])
             if isinstance(c.get("id"), str) and c.get("fromId") in ids and c.get("toId") in ids
             and _sources(c.get("sources")) and isinstance(c.get("label"), str) and c["label"].strip()]
    return {"organizations": orgs, "people": people, "connections": conns}


@lru_cache(maxsize=1)
def dataset() -> dict:
    for path in _CANDIDATES:
        if path.exists():
            return normalize(json.loads(path.read_text(encoding="utf-8")))
    return {"organizations": [], "people": [], "connections": []}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def _key(p: dict) -> tuple[str, str]:
    return (_fold(p["name"]), p["id"])


def _matches(p: dict, needle: str) -> bool:
    return any(needle in _fold(v) for v in [p["name"], *(p.get("aliases") or [])])


def _in_bbox(lon: float, lat: float, box: tuple[float, float, float, float]) -> bool:
    west, south, east, north = box
    if lat < south or lat > north:
        return False
    if east - west >= 360:
        return True
    return ((lon - west) % 360 + 360) % 360 <= east - west


def _page_extras(people: list[dict]) -> dict:
    d = dataset()
    pids = {p["id"] for p in people}
    oids = {o for p in people for o in p["organizationIds"]}
    return {"people": people, "organizations": [o for o in d["organizations"] if o["id"] in oids],
            "connections": [c for c in d["connections"] if c["fromId"] in pids and c["toId"] in pids]}


def _envelope(data, **extra) -> dict:
    from .app import envelope
    body = envelope(data, notes=NOTES)
    body["meta"].update(extra)
    return body


@router.get("/api/people")
def get_people(search: str = Query("", max_length=120), zoom: int = Query(1, ge=1, le=3),
               bbox: str | None = None, country: str | None = Query(None, pattern="^[A-Z]{3}$"),
               limit: int = Query(100, ge=1, le=250), cursor: str | None = Query(None, max_length=4096)):
    """People page. Without search or country, only people at or above the zoom's prominence tier are listed,
    optionally within a viewport (a person matches if any associated country's capital is inside it)."""
    box = None
    if bbox is not None:
        try:
            box = tuple(float(v) for v in bbox.split(","))
        except ValueError:
            box = ()
        if (len(box) != 4 or not (-90 <= box[1] <= 90 and -90 <= box[3] <= 90) or box[1] > box[3]
                or box[2] < box[0] or box[2] - box[0] > 720):
            _bad("bbox must be west,south,east,north")
    needle = _fold(search.strip())
    from .app import store
    coords = {c["iso3"]: (c.get("lon"), c.get("lat")) for c in store().countries}

    def visible(p: dict) -> bool:
        if not (needle or country or p["prominence"] <= zoom):
            return False
        if needle and not _matches(p, needle):
            return False
        if country and not any(r["iso3"] == country for r in p["regions"]):
            return False
        if not needle and not country and box:
            return any(coords.get(r["iso3"], (None, None))[0] is not None
                       and _in_bbox(*coords[r["iso3"]], box) for r in p["regions"])
        return True

    rows = sorted((p for p in dataset()["people"] if visible(p)), key=_key)
    fkey = json.dumps([needle, country]) if country else (
        json.dumps([needle, "global-search"]) if needle else json.dumps(["", zoom, list(box) if box else None]))
    start = 0
    if cursor:
        try:
            last = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
            assert isinstance(last, list) and len(last) == 3 and last[0] == fkey
        except Exception:
            _bad("cursor does not match these filters")
        start = next((i for i, p in enumerate(rows) if _key(p) > (last[1], last[2])), len(rows))
    page = rows[start:start + limit]
    nxt = None
    if page and start + len(page) < len(rows):
        nxt = base64.urlsafe_b64encode(json.dumps([fkey, *_key(page[-1])]).encode()).decode().rstrip("=")
    return _envelope(_page_extras(page), total=len(rows), next_cursor=nxt)


@router.get("/api/people/countries")
def get_people_countries(search: str = Query("", max_length=120), zoom: int = Query(3, ge=1, le=3)):
    """Per-country counts: `total` people associated with the country, `visible` at this zoom tier."""
    needle = _fold(search.strip())
    counts: dict[str, dict] = {}
    for p in dataset()["people"]:
        if needle and not _matches(p, needle):
            continue
        for iso3 in {r["iso3"] for r in p["regions"]}:
            c = counts.setdefault(iso3, {"iso3": iso3, "total": 0, "visible": 0})
            c["total"] += 1
            c["visible"] += bool(needle or p["prominence"] <= zoom)
    return _envelope(sorted(counts.values(), key=lambda c: c["iso3"]))


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
    return _envelope(data, total=len(people), total_connections=len(conns), next_cursor=None)


@router.get("/api/people/{person_id}")
def get_person(person_id: str):
    """One person's full evidence record (sources, dated events, country associations), their organizations,
    and their documented connections."""
    d = dataset()
    person = next((p for p in d["people"] if p["id"] == person_id), None)
    if person is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_person", "message": "Person not found"})
    conns = [c for c in d["connections"] if person_id in (c["fromId"], c["toId"])]
    return _envelope({"person": person,
                      "organizations": [o for o in d["organizations"] if o["id"] in person["organizationIds"]],
                      "connections": conns})
