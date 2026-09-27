# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""People API: bounded, paginated search over the curated, source-cited People dataset.

The dataset is the frontend team's reviewed manifest (`frontend/data/people/manifest.json`, built by
`frontend/scripts/aggregate-people.mjs`); this module only reads it. Query semantics mirror the frontend's own
route handlers (`frontend/lib/people-query.ts`) so the UI behaves the same against either server.

Freshness (TRACE_PEOPLE_REMOTE=1, set on Vercel): requests never wait on the network. They read the current
dataset, and once TRACE_PEOPLE_REFRESH_SECONDS (default 600; 0 disables) have passed one background refresh at a
time revalidates it, in this order:

1. the sharded, versioned snapshot (`trace-people-snapshot/1`, TRACE_PEOPLE_SNAPSHOT_URL, see
   docs/PEOPLE_SNAPSHOT.md): a small `index.json` (If-None-Match; same version = no-op), then only the
   content-addressed shards not already cached in memory or under the cache dir, fetched concurrently within
   TRACE_PEOPLE_SNAPSHOT_DEADLINE (default 20 s) and each checked for sha256, size, kind and record count;
2. the raw manifest on GitHub `main` (the older path), when the snapshot is unavailable or invalid.

A new dataset is normalized and indexed off to the side and swapped in with one reference assignment, so a
request sees either the old or the new dataset, never a mix; any failure keeps the current one. Cold starts serve
the last-good copy persisted under the cache dir (TRACE_PEOPLE_CACHE_DIR, default <tmp>/trace_people_snapshot),
else the bundled manifest. A refresh that stalls (Vercel Fluid Compute can pause background threads between
invocations) is superseded after a lease by the next request's refresh, which reuses every shard already cached;
the stalled one can no longer swap. `meta.people_snapshot` says which copy answered and whether it is stale.

Records are served in the manifest's order whatever the origin (snapshot shards carry each record's manifest
position), so every origin answers identically for the same manifest, and response arrays match the frontend's
fixture mode. Cursors encode sort keys, so they survive a refresh.

Design boundary: people are associated with countries only (never coordinates), every person, organization and
connection must carry at least one citable source, and connections are never inferred from shared membership.
"""
from __future__ import annotations

import base64
import bisect
import gzip
import hashlib
import json
import logging
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
log = logging.getLogger(__name__)

_CANDIDATES = [Path(os.environ["TRACE_PEOPLE_MANIFEST"])] if os.environ.get("TRACE_PEOPLE_MANIFEST") else []
_CANDIDATES += [config.REPO / "frontend" / "data" / "people" / "manifest.json",
                config.DATA / "people" / "manifest.json"]
STATUSES = {"convicted", "charged", "sanctioned", "reported"}
EVENT_TYPES = {"arrest", "charge", "conviction", "sentence", "sanction", "development"}
LIFE_STATUSES = {"deceased", "unknown"}
LEGAL_STATUSES = {"reported", "arrested", "charged", "convicted", "sentenced", "acquitted", "overturned",
                  "dismissed", "sanctioned", "delisted", "extradited", "released"}
KINDS = ("people", "organizations", "connections")
SNAPSHOT_URL = "https://raw.githubusercontent.com/WillieTheWhale/CDC_2026/people-snapshot/v1/"
SNAPSHOT_FORMAT = "trace-people-snapshot/1"
REMOTE_URL = "https://raw.githubusercontent.com/WillieTheWhale/CDC_2026/main/frontend/data/people/manifest.json"
INDEX_TIMEOUT = 5.0  # index.json is small
REMOTE_TIMEOUT = 15.0  # the raw manifest (~10 MB) is only a background fallback now
FAILURE_RETRY = 60.0  # after a failed refresh, retry this soon (capped by the TTL)
SHARD_WORKERS = 8
NETWORK_LIMIT = 48
NOTES = ["Curated sample of publicly reported, source-cited people; not a census. Status reflects the cited "
         "source as of statusAsOf (charged is not convicted). Locations are country-level associations only.",
         "Connections are listed only where a source documents that specific relationship."]
_HEX64 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{7,40}")

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


# ------------------------------------------------------------------------------------------ search primitives
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


# ------------------------------------------------------------------------------------------------------ indexes
class _Index:
    """Lookups precomputed once per dataset swap, so a request filters small, already-sorted lists instead of
    re-tokenizing and re-sorting every person. Lists hold the dataset's own dicts; every derived order is the one
    the naive filter-then-sort would produce (stable sort by `_key`, dataset order elsewhere)."""

    def __init__(self, d: dict):
        people, orgs, conns = d["people"], d["organizations"], d["connections"]
        self.sorted = sorted(people, key=_key)
        self.rank = {id(p): i for i, p in enumerate(self.sorted)}
        self.by_id: dict[str, dict] = {}
        self.positions: dict[str, list[int]] = {}
        for i, p in enumerate(people):
            self.by_id.setdefault(p["id"], p)
            self.positions.setdefault(p["id"], []).append(i)
        self.tier = {z: [p for p in self.sorted if p["prominence"] <= z] for z in (1, 2, 3)}
        self.unlocated = [p for p in self.sorted if not p["regions"]]
        self.by_country: dict[str, list[dict]] = {}
        for p in self.sorted:
            for iso3 in dict.fromkeys(r["iso3"] for r in p["regions"]):
                self.by_country.setdefault(iso3, []).append(p)
        self.variants: dict[int, list[list[str]]] = {}
        self.blob: dict[int, str] = {}
        for p in people:
            parts = [_tokens(v) for v in [p["name"], *(p.get("aliases") or [])]]
            self.variants[id(p)] = parts
            self.blob[id(p)] = "\x00".join(t for part in parts for t in part)  # tokens never contain NUL
        self.org_positions: dict[str, list[int]] = {}
        for i, o in enumerate(orgs):
            self.org_positions.setdefault(o["id"], []).append(i)
        self.adjacent: dict[str, list[int]] = {}
        for i, c in enumerate(conns):
            for pid in dict.fromkeys((c["fromId"], c["toId"])):
                self.adjacent.setdefault(pid, []).append(i)
        self.country_totals = {z: self.count_countries(people, [], z) for z in (1, 2, 3)}

    def matches(self, p: dict, tokens: list[str]) -> bool:
        if not tokens:
            return True
        blob = self.blob[id(p)]
        if not all(t in blob for t in tokens):  # cheap necessary condition before the exact per-name check
            return False
        return any(all(any(t in part for part in parts) for t in tokens) for parts in self.variants[id(p)])

    def count_countries(self, people: list[dict], tokens: list[str], zoom: int) -> list[tuple[str, int, int]]:
        counts: dict[str, list[int]] = {}
        for p in people:
            if not self.matches(p, tokens):
                continue
            for iso3 in {r["iso3"] for r in p["regions"]}:
                c = counts.setdefault(iso3, [0, 0])
                c[0] += 1
                c[1] += bool(tokens or p["prominence"] <= zoom)
        return sorted((iso3, t, v) for iso3, (t, v) in counts.items())

    def organizations(self, d: dict, ids) -> list[dict]:
        return [d["organizations"][i] for i in sorted({i for o in ids for i in self.org_positions.get(o, ())})]


def _materialize(raw: dict, snapshot: dict) -> dict:
    """Normalize (manifest order: snapshot shards carry positions, so every origin yields the same order) and index."""
    d = normalize(raw)
    d["snapshot"] = {**snapshot, "records": {kind: len(d[kind]) for kind in KINDS}}
    d["index"] = _Index(d)
    return d


def _canonical_sha(raw: dict) -> str:
    """The snapshot `version`: sha256 of the manifest's canonical JSON (as the publisher computes it)."""
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _bundled() -> dict:
    """The manifest packaged with this deployment (the repo checkout in local dev)."""
    snap = {"origin": "bundled", "fetched_at": None, "version": None, "source_commit": None}
    for path in _CANDIDATES:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return _materialize(raw, {**snap, "version": _canonical_sha(raw)})
    return _materialize({}, snap)


# ---------------------------------------------------------------------------------------------------- settings
def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return default


def _refresh_seconds() -> float:
    return _env_float("TRACE_PEOPLE_REFRESH_SECONDS", 600.0)


def _remote() -> bool:
    return os.environ.get("TRACE_PEOPLE_REMOTE") == "1" and _refresh_seconds() > 0


def _snapshot_url() -> str:
    url = os.environ.get("TRACE_PEOPLE_SNAPSHOT_URL") or SNAPSHOT_URL
    return url if url.endswith("/") else url + "/"


def _shard_deadline() -> float:
    return _env_float("TRACE_PEOPLE_SNAPSHOT_DEADLINE", 20.0)


def _lease() -> float:
    """How long a refresh may run before a later request presumes it stalled (e.g. a paused thread)."""
    return INDEX_TIMEOUT + _shard_deadline() + REMOTE_TIMEOUT + 15.0


def _cache_dir() -> Path:
    import tempfile
    env = os.environ.get("TRACE_PEOPLE_CACHE_DIR")
    return Path(env) if env else Path(tempfile.gettempdir()) / "trace_people_snapshot"


def _now() -> float:
    """Wall clock for TTLs and leases: it keeps running while Fluid Compute has the instance paused."""
    return time.time()


def _stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# -------------------------------------------------------------------------------------------------------- HTTP
def _get(url: str, etag: str | None, timeout: float) -> tuple[bytes | None, str | None]:
    """GET `url` within `timeout` seconds overall. Returns (None, etag) when unchanged (HTTP 304)."""
    deadline = time.monotonic() + timeout
    headers = {"User-Agent": "trace-backend", "Accept-Encoding": "gzip", **({"If-None-Match": etag} if etag else {})}
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
                raise TimeoutError(f"download of {url} exceeded the deadline")
        body = b"".join(chunks)
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            body = gzip.decompress(body)  # transfer encoding only; a .json.gz shard stays gzip underneath
        return body, resp.headers.get("ETag")


def _fetch(url: str, etag: str | None, timeout: float) -> tuple[dict | None, str | None]:
    """GET the raw manifest as JSON. Returns (None, etag) when unchanged (HTTP 304)."""
    body, tag = _get(url, etag, timeout)
    return (None, tag) if body is None else (json.loads(body.decode("utf-8")), tag)


# ------------------------------------------------------------------------------------------- snapshot format
def _parse_index(body: bytes) -> dict:
    idx = json.loads(body.decode("utf-8"))
    if not isinstance(idx, dict) or idx.get("format") != SNAPSHOT_FORMAT:
        raise ValueError("not a trace-people-snapshot/1 index")
    if not (isinstance(idx.get("version"), str) and _HEX64.fullmatch(idx["version"])):
        raise ValueError("index version is not a sha256")
    counts = idx.get("counts")
    if not (isinstance(counts, dict) and all(type(counts.get(k)) is int and counts[k] >= 0 for k in KINDS)):
        raise ValueError("index counts are malformed")
    shards = idx.get("shards")
    if not (isinstance(shards, list) and shards):
        raise ValueError("index lists no shards")
    for e in shards:
        ok = (isinstance(e, dict) and e.get("kind") in KINDS and isinstance(e.get("sha256"), str)
              and _HEX64.fullmatch(e["sha256"]) is not None
              and e.get("file") == f"shards/{e['kind']}-{e['sha256'][:16]}.json.gz"
              and type(e.get("bytes")) is int and e["bytes"] > 0
              and type(e.get("records")) is int and e["records"] >= 0)
        if not ok:
            raise ValueError(f"malformed shard entry {e!r:.200}")
    commit = idx.get("source_commit")
    idx["source_commit"] = commit if isinstance(commit, str) and _COMMIT.fullmatch(commit) else None
    return idx


def _check_blob(entry: dict, gz: bytes) -> bytes:
    if len(gz) != entry["bytes"] or hashlib.sha256(gz).hexdigest() != entry["sha256"]:
        raise ValueError(f"{entry['file']}: size or sha256 does not match the index")
    return gz


def _assemble(idx: dict, blobs: dict[str, bytes]) -> dict:
    """Shard records per kind; every shard's kind and record count, and every kind's total, must match."""
    raw: dict[str, list] = {kind: [] for kind in KINDS}
    placed: dict[str, list] = {kind: [] for kind in KINDS}
    for e in idx["shards"]:
        body = json.loads(gzip.decompress(blobs[e["file"]]).decode("utf-8"))
        records = body.get("records") if isinstance(body, dict) else None
        if not isinstance(records, list) or body.get("kind") != e["kind"] or len(records) != e["records"]:
            raise ValueError(f"{e['file']}: kind or record count does not match the index")
        positions = body.get("positions")
        if positions is not None and (not isinstance(positions, list) or len(positions) != len(records)
                                      or not all(type(p) is int for p in positions)):
            raise ValueError(f"{e['file']}: positions do not match its records")
        placed[e["kind"]].extend(zip(positions, records) if positions is not None else ((None, r) for r in records))
    for kind in KINDS:
        items = placed[kind]
        if len(items) != idx["counts"][kind]:
            raise ValueError(f"{kind}: shards hold {len(items)} records, index counts {idx['counts'][kind]}")
        if all(p is not None for p, _ in items):  # rebuild the manifest's exact order
            if sorted(p for p, _ in items) != list(range(len(items))):
                raise ValueError(f"{kind}: shard positions are not a permutation of 0..{len(items) - 1}")
            raw[kind] = [r for _, r in sorted(items, key=lambda x: x[0])]
        else:  # shards without positions (publisher before 2026-09-27): a reproducible order
            raw[kind] = sorted((r for _, r in items), key=lambda r: str(r.get("id")) if isinstance(r, dict) else "")
    return raw


# ------------------------------------------------------------------------------------------------- local cache
def _disk_read(entry: dict) -> bytes | None:
    try:
        return _check_blob(entry, (_cache_dir() / "shards" / entry["file"].split("/")[-1]).read_bytes())
    except (OSError, ValueError):
        return None


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _disk_write(entry: dict, gz: bytes) -> None:
    try:
        _write_atomic(_cache_dir() / "shards" / entry["file"].split("/")[-1], gz)
    except OSError as e:  # read-only or full: the memory cache still works
        log.debug("people shard cache not writable: %s", e)


def _persist(raw: dict, snapshot: dict) -> None:
    """Keep the manifest just swapped in as the last-good copy for the next cold start."""
    try:
        payload = json.dumps({"snapshot": {k: v for k, v in snapshot.items() if k != "records"}, "manifest": raw},
                             separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        _write_atomic(_cache_dir() / "last-good.json.gz", gzip.compress(payload, compresslevel=5))
    except OSError as e:
        log.warning("people last-good copy not persisted: %s", e)


def _load_last_good() -> dict | None:
    path = _cache_dir() / "last-good.json.gz"
    try:
        saved = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        raw, snap = saved["manifest"], saved["snapshot"]
        if snap.get("version") != _canonical_sha(raw):
            raise ValueError("last-good copy does not match its recorded version")
        d = _materialize(raw, {"origin": "last-good", "fetched_at": snap.get("fetched_at"),
                               "version": snap["version"], "source_commit": snap.get("source_commit")})
        if not d["people"]:
            raise ValueError("last-good copy has no valid people")
        return d
    except FileNotFoundError:
        return None
    except Exception as e:  # corrupt or unreadable: fall through to the bundled copy
        log.warning("people last-good copy ignored: %s", e)
        return None


def _prune(idx: dict, s: _State) -> None:
    keep = {e["file"] for e in idx["shards"]}
    for name in [n for n in s.shards if n not in keep]:
        s.shards.pop(name, None)
    try:
        for path in (_cache_dir() / "shards").glob("*.json.gz"):
            if f"shards/{path.name}" not in keep:
                path.unlink(missing_ok=True)
    except OSError:
        pass


# ------------------------------------------------------------------------------------------ refresh machinery
class _State:
    """Everything the refresher shares. `current` is replaced by one assignment under `lock`, never mutated."""

    def __init__(self):
        self.lock = threading.Lock()
        self.boot_lock = threading.Lock()
        self.current: dict | None = None
        self.gen = 0  # refresh generation; only the newest may swap
        self.running_since: float | None = None
        self.checked: float | None = None  # when the last refresh finished (success or failure)
        self.last_ok: float | None = None  # when the current data was last confirmed against a remote
        self.failed = False
        self.index_etag: tuple[str, str] | None = None  # (ETag, version) of the last index.json
        self.manifest_etag: tuple[str, str] | None = None  # (ETag, version) of the last raw manifest
        self.shards: dict[str, bytes] = {}  # verified shard bytes by file name (content-addressed)


_S = _State()


def _spawn(fn) -> None:
    threading.Thread(target=fn, name="trace-people-refresh", daemon=True).start()


def _boot(s: _State) -> None:
    """Cold start: the last-good copy persisted by an earlier refresh, else the bundled manifest. No network."""
    with s.boot_lock:
        if s.current is None:
            d = _load_last_good() or _bundled()
            with s.lock:
                s.current = d


def _claim(s: _State, ttl: float) -> int:
    """Start a refresh generation if one is due and none is live; returns its number, or 0."""
    with s.lock:
        now = _now()
        if s.running_since is not None:
            if now - s.running_since < _lease():
                return 0
            log.warning("people refresh generation %d stalled; starting a new one", s.gen)
        elif s.checked is not None and now - s.checked < (min(ttl, FAILURE_RETRY) if s.failed else ttl):
            return 0
        s.gen += 1
        s.running_since = now
        return s.gen


def _swap(s: _State, gen: int, new: dict) -> bool:
    with s.lock:
        if s.gen != gen:
            return False  # superseded while it ran (e.g. paused past its lease): never overwrite newer work
        s.current = new
        return True


def _confirm(s: _State, gen: int, origin: str, source_commit: str | None = None) -> bool:
    """The remote still holds the current version: relabel it, no rebuild."""
    with s.lock:
        if s.gen != gen:
            return False
        snap = {**s.current["snapshot"], "origin": origin, "fetched_at": _stamp()}
        if source_commit is not None or origin != "github-snapshot":
            snap["source_commit"] = source_commit
        s.current = {**s.current, "snapshot": snap}
        return True


def _fetch_shards(s: _State, base: str, idx: dict) -> dict[str, bytes]:
    """Every shard the index names, from memory, disk, or (concurrently, within the deadline) the network."""
    from concurrent.futures import ThreadPoolExecutor, as_completed  # lazy: only a refresh needs it
    deadline = time.monotonic() + _shard_deadline()
    missing = []
    for e in idx["shards"]:
        if e["file"] not in s.shards:
            gz = _disk_read(e)
            if gz is None:
                missing.append(e)
            else:
                s.shards[e["file"]] = gz
    if missing:
        pool = ThreadPoolExecutor(max_workers=min(SHARD_WORKERS, len(missing)), thread_name_prefix="trace-shard")

        def one(e: dict) -> bytes:
            body, _ = _get(base + e["file"], None, max(0.5, deadline - time.monotonic()))
            return _check_blob(e, body)

        error: Exception | None = None
        try:
            futures = {pool.submit(one, e): e for e in missing}
            for f in as_completed(futures, timeout=max(0.1, deadline - time.monotonic())):
                e = futures[f]
                try:
                    s.shards[e["file"]] = gz = f.result()  # kept even if a sibling fails: a retry resumes here
                except Exception as exc:
                    error = error or exc
                    continue
                _disk_write(e, gz)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if error is not None:
            raise error
    return {e["file"]: s.shards[e["file"]] for e in idx["shards"]}


def _refresh_snapshot(s: _State, gen: int) -> bool:
    base = _snapshot_url()
    cur = s.current
    etag = s.index_etag[0] if s.index_etag and s.index_etag[1] == cur["snapshot"]["version"] else None
    body, tag = _get(base + "index.json", etag, INDEX_TIMEOUT)
    if body is None:
        return _confirm(s, gen, "github-snapshot")
    idx = _parse_index(body)
    if idx["version"] == cur["snapshot"]["version"]:
        s.index_etag = (tag, idx["version"]) if tag else None
        return _confirm(s, gen, "github-snapshot", idx["source_commit"])
    raw = _assemble(idx, _fetch_shards(s, base, idx))
    new = _materialize(raw, {"origin": "github-snapshot", "fetched_at": _stamp(), "version": idx["version"],
                             "source_commit": idx["source_commit"]})
    if not new["people"]:
        raise ValueError("snapshot has no valid people")
    if not _swap(s, gen, new):
        return False
    s.index_etag = (tag, idx["version"]) if tag else None
    _persist(raw, new["snapshot"])
    _prune(idx, s)
    return True


def _refresh_raw(s: _State, gen: int) -> bool:
    cur = s.current
    etag = (s.manifest_etag[0] if s.manifest_etag and cur["snapshot"]["origin"] == "github-main"
            and s.manifest_etag[1] == cur["snapshot"]["version"] else None)
    raw, tag = _fetch(REMOTE_URL, etag, REMOTE_TIMEOUT)
    if raw is None:
        return _confirm(s, gen, "github-main")
    if not isinstance(raw, dict):
        raise ValueError("remote People manifest is not an object")
    version = _canonical_sha(raw)
    if version == cur["snapshot"]["version"]:
        s.manifest_etag = (tag, version) if tag else None
        return _confirm(s, gen, "github-main")
    new = _materialize(raw, {"origin": "github-main", "fetched_at": _stamp(), "version": version,
                             "source_commit": None})
    if not new["people"]:
        raise ValueError("remote People manifest has no valid people")
    if not _swap(s, gen, new):
        return False
    s.manifest_etag = (tag, version) if tag else None
    _persist(raw, new["snapshot"])
    return True


def _run(s: _State, gen: int) -> None:
    """One refresh generation: snapshot branch, else raw manifest on main; any failure keeps the current data."""
    ok = False
    try:
        try:
            ok = _refresh_snapshot(s, gen)
        except Exception as e:
            log.warning("people snapshot refresh failed (%s: %s); trying the raw manifest", type(e).__name__, e)
            ok = _refresh_raw(s, gen)
    except Exception as e:
        log.warning("people refresh failed, serving %s copy: %s: %s",
                    (s.current or {}).get("snapshot", {}).get("origin"), type(e).__name__, e)
    finally:
        with s.lock:
            if s.gen == gen:  # a superseded generation leaves the bookkeeping to its successor
                s.running_since = None
                s.checked = _now()
                s.failed = not ok
                if ok:
                    s.last_ok = s.checked


def dataset() -> dict:
    """The current People data. Never waits on the network: a due refresh runs in the background (one at a time)
    and swaps in atomically when complete. Local runs without TRACE_PEOPLE_REMOTE=1 use the bundled manifest."""
    if not _remote():
        return _bundled()
    s = _S
    if s.current is None:
        _boot(s)
    gen = _claim(s, _refresh_seconds())
    if gen:
        _spawn(lambda: _run(s, gen))
    return s.current


def _stale() -> bool:
    """True when the TTL has passed since the data was last confirmed and a refresh is pending or failed."""
    if not _remote():
        return False
    last = _S.last_ok
    return last is None or _now() - last >= _refresh_seconds()


# ----------------------------------------------------------------------------------------------------- routes
def _page_extras(d: dict, people: list[dict]) -> dict:
    ix = d["index"]
    pids = {p["id"] for p in people}
    oids = {o for p in people for o in p["organizationIds"]}
    conns = d["connections"]
    cpos = {i for pid in pids for i in ix.adjacent.get(pid, ())
            if conns[i]["fromId"] in pids and conns[i]["toId"] in pids}
    return {"people": people, "organizations": ix.organizations(d, oids),
            "connections": [conns[i] for i in sorted(cpos)]}


def _envelope(d: dict, data, **extra) -> dict:
    from .app import envelope
    body = envelope(data, notes=NOTES)
    body["meta"].update(extra)
    if d.get("snapshot"):
        body["meta"]["people_snapshot"] = {**d["snapshot"], "stale": _stale()}
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

    d = dataset()
    ix: _Index = d["index"]
    # Candidates already in `_key` order; the filters are those of the frontend's queryPeople.
    if lone:
        rows = ix.unlocated
    elif country:
        rows = ix.by_country.get(country, [])
    elif needle:
        rows = ix.sorted
    elif box:
        from .app import store
        coords = {c["iso3"]: (c.get("lon"), c.get("lat")) for c in store().countries}
        inside = {iso3 for iso3, (lon, lat) in coords.items() if lon is not None and _in_bbox(lon, lat, box)}
        ranks = {ix.rank[id(p)] for iso3 in inside for p in ix.by_country.get(iso3, ()) if p["prominence"] <= zoom}
        rows = [ix.sorted[i] for i in sorted(ranks)]
    else:
        rows = ix.tier[zoom]
    if needle:
        rows = [p for p in rows if ix.matches(p, tokens)]

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
        start = bisect.bisect_right(rows, (last[1], last[2]), key=_key)
    page = rows[start:start + limit]
    nxt = None
    if page and start + len(page) < len(rows):
        nxt = base64.urlsafe_b64encode(_js([fkey, *_key(page[-1])]).encode()).decode().rstrip("=")
    return _envelope(d, _page_extras(d, page), total=len(rows), next_cursor=nxt)


@router.get("/api/people/countries")
def get_people_countries(search: str = Query("", max_length=120), zoom: int = Query(3, ge=1, le=3)):
    """Per-country counts: `total` people associated with the country, `visible` at this zoom tier."""
    tokens = _tokens(search)
    d = dataset()
    ix: _Index = d["index"]
    counts = ix.count_countries(d["people"], tokens, zoom) if tokens else ix.country_totals[zoom]
    return _envelope(d, [{"iso3": iso3, "total": t, "visible": v} for iso3, t, v in counts])


@router.get("/api/people/network")
def get_people_network(person_id: str = Query(..., min_length=1, max_length=160)):
    """A person's documented connections (first 48 by id) and the people and organizations they touch."""
    d = dataset()
    ix: _Index = d["index"]
    if person_id not in ix.by_id:
        raise HTTPException(status_code=404, detail={"code": "unknown_person", "message": "Person not found"})
    conns = sorted((d["connections"][i] for i in ix.adjacent.get(person_id, ())), key=lambda c: c["id"])
    shown = conns[:NETWORK_LIMIT]
    pids = {person_id} | {i for c in shown for i in (c["fromId"], c["toId"])}
    people = [d["people"][i] for i in sorted(i for pid in pids for i in ix.positions.get(pid, ()))]
    data = {"people": people, "organizations": ix.organizations(d, {o for p in people for o in p["organizationIds"]}),
            "connections": shown}
    return _envelope(d, data, total=len(people), total_connections=len(conns), next_cursor=None)


@router.get("/api/people/{person_id}")
def get_person(person_id: str):
    """One person's full evidence record (sources, dated events, country associations), their organizations,
    and their documented connections."""
    d = dataset()
    ix: _Index = d["index"]
    person = ix.by_id.get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_person", "message": "Person not found"})
    conns = [d["connections"][i] for i in ix.adjacent.get(person_id, ())]
    return _envelope(d, {"person": person, "organizations": ix.organizations(d, set(person["organizationIds"])),
                         "connections": conns})
