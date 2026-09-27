# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""People snapshot consumer: sharded refresh, verification, atomic swap, fallback chain, /tmp persistence, stale
metadata, stalled-refresh recovery, and index parity with the naive query code. No real network: `people._get`
is replaced by an in-memory fake server holding snapshots built by `publish()` (same format as the publisher)."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import threading
import time
import urllib.error

import pytest
from fastapi.testclient import TestClient

from trace_backend.api import people
from trace_backend.api.app import app

client = TestClient(app)
BASE = "https://snapshot.test/v1/"
SRC = {"url": "https://example.org/a", "title": "T", "publisher": "P", "language": "en", "claim": "C"}
COMMIT = "a" * 40


def _person(pid: str, name: str, **kw) -> dict:
    return {"id": pid, "name": name, "status": "charged", "statusAsOf": "2024-01-01", "prominence": 3,
            "organizationIds": [], "regions": [], "drugs": [], "sources": [SRC], **kw}


def manifest(n: int = 40, rename: dict | None = None) -> dict:
    rename = rename or {}
    ppl = [_person(f"p{i:03d}", rename.get(i, f"Person {i}"), prominence=1 + i % 3, organizationIds=[f"o{i % 3}"],
                   regions=[{"iso3": ("COL", "MEX", "PER")[i % 3], "label": "x"}] if i % 4 else [],
                   aliases=[f"Alias{i}"] if i % 5 == 0 else [])
           for i in range(n)]
    orgs = [{"id": f"o{i}", "name": f"Org {i}", "regions": [], "sources": [SRC]} for i in range(3)]
    conns = [{"id": f"c{i:03d}", "fromId": f"p{i:03d}", "toId": f"p{(i + 1) % n:03d}", "type": "associate",
              "label": "documented", "sources": [SRC]} for i in range(0, n, 2)]
    return {"organizations": orgs, "people": ppl, "connections": conns}


def _gz(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as f:
        f.write(data)
    return buf.getvalue()


def publish(m: dict, commit: str = COMMIT, people_shards: int = 16) -> dict[str, bytes]:
    """A trace-people-snapshot/1 tree as {url: bytes}: people in 16 id-hash shards, the other kinds in one each."""
    files, entries = {}, []
    for kind in people.KINDS:
        n = people_shards if kind == "people" else 1
        buckets = [[] for _ in range(n)]
        for r in m[kind]:
            buckets[int(hashlib.sha256(r["id"].encode()).hexdigest(), 16) % n].append(r)
        for b in buckets:
            gz = _gz(json.dumps({"kind": kind, "records": b}, separators=(",", ":")).encode())
            sha = hashlib.sha256(gz).hexdigest()
            name = f"shards/{kind}-{sha[:16]}.json.gz"
            files[BASE + name] = gz
            entries.append({"kind": kind, "file": name, "sha256": sha, "bytes": len(gz), "records": len(b)})
    index = {"format": "trace-people-snapshot/1", "version": people._canonical_sha(m),
             "generated_at": "2026-09-27T00:00:00Z", "source_commit": commit,
             "source_path": "frontend/data/people/manifest.json",
             "counts": {k: len(m[k]) for k in people.KINDS}, "shards": entries}
    files[BASE + "index.json"] = json.dumps(index).encode()
    return files


class FakeNet:
    """In-memory HTTP: ETag = sha of the body, 304 on a matching If-None-Match, 404 for unknown URLs."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.calls: list[str] = []
        self.fail: set[str] = set()
        self.gate: threading.Event | None = None  # when set, shard downloads wait for it
        self.lock = threading.Lock()

    def get(self, url, etag, timeout):
        with self.lock:
            self.calls.append(url)
        if self.gate is not None and "/shards/" in url:
            assert self.gate.wait(10)
        if url in self.fail:
            raise OSError(f"connection reset: {url}")
        if url not in self.files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        body = self.files[url]
        tag = '"' + hashlib.sha256(body).hexdigest()[:16] + '"'
        return (None, etag) if etag == tag else (body, tag)

    def shard_calls(self) -> list[str]:
        return [u for u in self.calls if "/shards/" in u]

    def reset(self):
        self.calls.clear()


@pytest.fixture
def net(monkeypatch, tmp_path):
    n = FakeNet()
    monkeypatch.setenv("TRACE_PEOPLE_REMOTE", "1")
    monkeypatch.setenv("TRACE_PEOPLE_REFRESH_SECONDS", "600")
    monkeypatch.setenv("TRACE_PEOPLE_SNAPSHOT_URL", BASE)
    monkeypatch.setenv("TRACE_PEOPLE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(people, "_get", n.get)
    monkeypatch.setattr(people, "_spawn", lambda fn: fn())  # inline unless a test opts into threads
    monkeypatch.setattr(people, "_S", people._State())
    return n


def _expire():
    people._S.checked -= 10_000
    if people._S.last_ok is not None:
        people._S.last_ok -= 10_000


def _snap(**params) -> dict:
    return client.get("/api/people", params={"unlocated": 1, "limit": 1, **params}).json()["meta"]["people_snapshot"]


def _ids() -> set[str]:
    return {p["id"] for p in people._S.current["people"]}


def _cold_start(monkeypatch):
    monkeypatch.setattr(people, "_S", people._State())


# ------------------------------------------------------------------------------------------------ refresh
def test_snapshot_load_and_meta(net):
    m = manifest()
    net.files.update(publish(m))
    snap = _snap()
    assert snap["origin"] == "github-snapshot" and snap["fetched_at"]
    assert snap["version"] == people._canonical_sha(m) and snap["source_commit"] == COMMIT
    assert snap["records"] == {"people": 40, "organizations": 3, "connections": 20}
    assert snap["stale"] is False
    assert _ids() == {p["id"] for p in m["people"]}
    assert len(net.shard_calls()) == 18  # 16 people + 1 organizations + 1 connections


def test_unchanged_version_is_a_no_op(net):
    net.files.update(publish(manifest()))
    _snap()
    before = people._S.current
    for regenerate in (False, True):  # 304 on the same ETag; 200 with a new ETag but the same version
        if regenerate:
            idx = json.loads(net.files[BASE + "index.json"])
            net.files[BASE + "index.json"] = json.dumps({**idx, "generated_at": "2026-09-28T00:00:00Z"}).encode()
        net.reset()
        _expire()
        snap = _snap()
        assert net.calls == [BASE + "index.json"] and not net.shard_calls()
        assert people._S.current["index"] is before["index"] and people._S.current["people"] is before["people"]
        assert snap["origin"] == "github-snapshot" and snap["stale"] is False


def test_only_changed_shards_are_fetched(net):
    net.files.update(publish(manifest()))
    _snap()
    new = manifest(rename={7: "Renamed Seven"})
    net.files.update(publish(new))
    net.reset()
    _expire()
    snap = _snap()
    assert len(net.shard_calls()) == 1 and "/shards/people-" in net.shard_calls()[0]
    assert snap["version"] == people._canonical_sha(new)
    assert client.get("/api/people/p007").json()["data"]["person"]["name"] == "Renamed Seven"


def test_sha_mismatch_keeps_the_old_dataset(net):
    net.files.update(publish(manifest()))
    old = _snap()
    files = publish(manifest(rename={3: "Changed"}))
    changed = next(u for u in files if "/shards/" in u and u not in net.files)
    body = files[changed]
    files[changed] = body[:20] + bytes([body[20] ^ 0xFF]) + body[21:]  # corrupt: sha256 no longer matches
    net.files.update(files)
    _expire()
    snap = _snap()
    assert snap["version"] == old["version"] and snap["origin"] == "github-snapshot"
    assert people._S.failed and snap["stale"] is True  # TTL passed, refresh failed (no raw manifest either)
    assert client.get("/api/people/p003").json()["data"]["person"]["name"] == "Person 3"


def test_bad_counts_or_records_keep_the_old_dataset(net):
    net.files.update(publish(manifest()))
    old = _snap()["version"]
    files = publish(manifest(n=41))
    idx = json.loads(files[BASE + "index.json"])
    idx["counts"]["people"] += 1  # per-kind total disagrees with the shards
    files[BASE + "index.json"] = json.dumps(idx).encode()
    net.files.update(files)
    _expire()
    assert _snap()["version"] == old and len(_ids()) == 40


def test_partial_failure_means_no_swap_and_the_retry_resumes(net):
    net.files.update(publish(manifest()))
    old = _snap()["version"]
    m2 = {**manifest(), "people": [_person(f"n{i}", f"New {i}") for i in range(40)]}
    files = publish(m2)
    bad = sorted(u for u in files if "/shards/people-" in u and u not in net.files)[0]
    net.files.update(files)
    net.fail.add(bad)
    net.reset()
    _expire()
    assert _snap()["version"] == old and _ids() == {f"p{i:03d}" for i in range(40)}
    fetched_first = set(net.shard_calls())
    net.fail.clear()
    net.reset()
    _expire()
    snap = _snap()
    assert snap["version"] == people._canonical_sha(m2) and _ids() == {f"n{i}" for i in range(40)}
    assert net.shard_calls() == [bad] and bad in fetched_first  # everything else came from the shard cache


def test_requests_during_a_refresh_see_the_old_dataset_never_a_mix(net, monkeypatch):
    net.files.update(publish(manifest()))
    _snap()
    old_ids = _ids()
    m2 = {**manifest(), "people": [_person(f"n{i:03d}", f"New {i}") for i in range(40)], "connections": []}
    net.files.update(publish(m2))
    new_ids = {p["id"] for p in m2["people"]}
    threads = []
    monkeypatch.setattr(people, "_spawn", lambda fn: threads.append(threading.Thread(target=fn)) or threads[-1].start())
    net.gate = threading.Event()
    net.reset()
    _expire()
    seen, errors, stop = [], [], threading.Event()

    def hammer():
        try:
            while not stop.is_set():
                body = client.get("/api/people", params={"zoom": 3, "limit": 250}).json()
                ids = {p["id"] for p in body["data"]["people"]}
                seen.append((ids, body["meta"]["total"], body["meta"]["people_snapshot"]["version"]))
        except Exception as e:  # pragma: no cover - surfaced below
            errors.append(e)

    workers = [threading.Thread(target=hammer) for _ in range(4)]
    for w in workers:
        w.start()
    time.sleep(0.2)
    assert len(threads) == 1 and people._S.running_since is not None  # one refresh in flight, not one per request
    assert net.calls.count(BASE + "index.json") == 1
    assert _ids() == old_ids  # still the old copy while shards download
    net.gate.set()
    threads[0].join(10)
    time.sleep(0.2)
    stop.set()
    for w in workers:
        w.join(10)
    assert not errors and {v for _, _, v in seen} == {people._canonical_sha(manifest()), people._canonical_sha(m2)}
    for ids, total, version in seen:  # every response is wholly one version
        assert ids in (old_ids, new_ids) and total == len(ids)
        assert version == people._canonical_sha(m2 if ids == new_ids else manifest())
    assert _ids() == new_ids


def test_stalled_refresh_is_superseded_and_cannot_swap_late(net, monkeypatch):
    net.files.update(publish(manifest()))
    _snap()
    net.files.update(publish(manifest(rename={1: "Second"})))
    parked = []
    monkeypatch.setattr(people, "_spawn", parked.append)  # a thread that Fluid Compute paused before it ran
    _expire()
    _snap()
    assert len(parked) == 1 and people._S.running_since is not None
    _snap()
    assert len(parked) == 1  # within the lease: nobody starts a second refresh
    people._S.running_since -= people._lease() + 1
    monkeypatch.setattr(people, "_spawn", lambda fn: fn())
    assert _snap()["version"] == people._canonical_sha(manifest(rename={1: "Second"}))
    third = manifest(rename={1: "Third"})
    net.files.update(publish(third))
    parked[0]()  # the paused generation resumes late: superseded, so it must not swap or touch bookkeeping
    assert people._S.current["snapshot"]["version"] == people._canonical_sha(manifest(rename={1: "Second"}))
    assert people._S.running_since is None and not people._S.failed


# ----------------------------------------------------------------------------------------------- fallback
def test_fallback_chain(net, monkeypatch):
    m = manifest()
    raw = json.dumps(m).encode()
    # 1. no snapshot branch yet: the raw manifest on main
    net.files[people.REMOTE_URL] = raw
    snap = _snap()
    assert snap["origin"] == "github-main" and snap["version"] == people._canonical_sha(m)
    assert snap["source_commit"] is None
    # 2. the branch appears with the same content: relabelled, nothing rebuilt or downloaded
    net.files.update(publish(m))
    net.reset()
    _expire()
    snap = _snap()
    assert snap["origin"] == "github-snapshot" and snap["source_commit"] == COMMIT and not net.shard_calls()
    # 3. a cold start with the network down: the persisted last-good copy
    net.fail.update(net.files)
    _cold_start(monkeypatch)
    snap = _snap()
    assert snap["origin"] == "last-good" and snap["version"] == people._canonical_sha(m) and snap["stale"] is True
    assert _ids() == {p["id"] for p in m["people"]}
    # 4. nothing persisted and nothing reachable: the bundled manifest
    (people._cache_dir() / "last-good.json.gz").unlink()
    _cold_start(monkeypatch)
    assert _snap()["origin"] == "bundled"
    assert people._S.current is people._bundled()


def test_invalid_snapshot_index_falls_back_to_raw_manifest(net):
    m = manifest(n=12)
    net.files[BASE + "index.json"] = json.dumps({"format": "trace-people-snapshot/0"}).encode()
    net.files[people.REMOTE_URL] = json.dumps(m).encode()
    snap = _snap()
    assert snap["origin"] == "github-main" and snap["records"]["people"] == 12


def test_persistence_to_cache_dir_and_reload(net, monkeypatch):
    m = manifest()
    net.files.update(publish(m))
    _snap()
    cache = people._cache_dir()
    assert (cache / "last-good.json.gz").exists() and len(list((cache / "shards").glob("*.json.gz"))) == 18
    # cold start, network fine and unchanged: last-good served, then confirmed with one index request
    _cold_start(monkeypatch)
    net.reset()
    snap = _snap()
    assert snap["origin"] == "github-snapshot" and net.calls == [BASE + "index.json"]
    # cold start without last-good but with cached shards: only the index is downloaded
    (cache / "last-good.json.gz").unlink()
    _cold_start(monkeypatch)
    net.reset()
    snap = _snap()
    assert snap["origin"] == "github-snapshot" and not net.shard_calls() and snap["records"]["people"] == 40
    # a corrupt cached shard is ignored and re-downloaded
    victim = sorted((cache / "shards").glob("people-*.json.gz"))[0]
    victim.write_bytes(b"junk")
    (cache / "last-good.json.gz").unlink()
    _cold_start(monkeypatch)
    net.reset()
    _snap()
    assert [u.rsplit("/", 1)[-1] for u in net.shard_calls()] == [victim.name]
    # superseded shards are pruned once a new version lands
    net.files.update(publish(manifest(rename={2: "Two"})))
    _expire()
    _snap()
    assert len(list((cache / "shards").glob("*.json.gz"))) == 18


def test_corrupt_last_good_is_ignored(net, monkeypatch):
    net.fail.add(BASE + "index.json")
    cache = people._cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "last-good.json.gz").write_bytes(gzip.compress(json.dumps(
        {"snapshot": {"version": "0" * 64}, "manifest": manifest()}).encode()))
    assert _snap()["origin"] == "bundled"


def test_first_request_never_waits_on_the_network(net, monkeypatch):
    net.files.update(publish(manifest()))
    started = []
    monkeypatch.setattr(people, "_spawn", started.append)
    snap = _snap()
    assert snap["origin"] == "bundled" and snap["stale"] is True and len(started) == 1 and not net.calls


def test_remote_off_serves_bundled_and_not_stale(monkeypatch):
    monkeypatch.delenv("TRACE_PEOPLE_REMOTE", raising=False)
    snap = client.get("/api/people", params={"limit": 1}).json()["meta"]["people_snapshot"]
    assert snap["origin"] == "bundled" and snap["stale"] is False and snap["fetched_at"] is None
    assert set(snap) == {"origin", "fetched_at", "version", "source_commit", "records", "stale"}


# ------------------------------------------------------------------------------------ index parity (naive)
def _naive_people(d, coords, search="", zoom=1, box=None, country=None, lone=False, limit=100, cursor=None):
    """The pre-index query code, verbatim in behaviour."""
    tokens = people._tokens(search)
    needle = bool(tokens)

    def visible(p):
        if not (lone or needle or country or p["prominence"] <= zoom):
            return False
        if not people._matches(p, tokens):
            return False
        if lone and p["regions"]:
            return False
        if country and not any(r["iso3"] == country for r in p["regions"]):
            return False
        if not needle and not country and box:
            return any(coords.get(r["iso3"], (None, None))[0] is not None
                       and people._in_bbox(*coords[r["iso3"]], box) for r in p["regions"])
        return True

    rows = sorted((p for p in d["people"] if visible(p)), key=people._key)
    start = 0
    if cursor:
        last = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
        start = next((i for i, p in enumerate(rows) if people._key(p) > (last[1], last[2])), len(rows))
    page = rows[start:start + limit]
    pids = {p["id"] for p in page}
    oids = {o for p in page for o in p["organizationIds"]}
    return {"people": page, "organizations": [o for o in d["organizations"] if o["id"] in oids],
            "connections": [c for c in d["connections"] if c["fromId"] in pids and c["toId"] in pids]}, len(rows)


def _naive_countries(d, search, zoom):
    tokens = people._tokens(search)
    counts = {}
    for p in d["people"]:
        if not people._matches(p, tokens):
            continue
        for iso3 in {r["iso3"] for r in p["regions"]}:
            c = counts.setdefault(iso3, {"iso3": iso3, "total": 0, "visible": 0})
            c["total"] += 1
            c["visible"] += bool(tokens or p["prominence"] <= zoom)
    return sorted(counts.values(), key=lambda c: c["iso3"])


def _naive_network(d, pid):
    conns = sorted((c for c in d["connections"] if pid in (c["fromId"], c["toId"])), key=lambda c: c["id"])
    shown = conns[:people.NETWORK_LIMIT]
    pids = {pid} | {i for c in shown for i in (c["fromId"], c["toId"])}
    ppl = [p for p in d["people"] if p["id"] in pids]
    oids = {o for p in ppl for o in p["organizationIds"]}
    return {"people": ppl, "organizations": [o for o in d["organizations"] if o["id"] in oids],
            "connections": shown}, len(conns)


def test_indexed_results_match_the_naive_queries(monkeypatch):
    monkeypatch.delenv("TRACE_PEOPLE_REMOTE", raising=False)
    d = people.dataset()
    if not d["people"]:
        pytest.skip("People manifest not available")
    from trace_backend.api.app import store
    coords = {c["iso3"]: (c.get("lon"), c.get("lat")) for c in store().countries}
    aliased = next((p for p in d["people"] if p.get("aliases")), d["people"][0])
    iso3 = next(p["regions"][0]["iso3"] for p in d["people"] if p["regions"])
    queries = [dict(zoom=1), dict(zoom=2), dict(zoom=3, limit=250), dict(search="jose"), dict(search="garcia maria"),
               dict(search=aliased.get("aliases", [aliased["name"]])[0][:5]), dict(search="zz-no-match"),
               dict(country=iso3), dict(country=iso3, search="a"), dict(lone=True), dict(lone=True, search="e"),
               dict(zoom=3, box=(-120.0, 5.0, -60.0, 35.0)), dict(zoom=2, box=(-180.0, -90.0, 180.0, 90.0)),
               dict(zoom=3, box=(150.0, -50.0, 250.0, 10.0)), dict(zoom=3, box=(-80.0, 0.0, -70.0, 10.0), search="a")]
    for q in queries:
        params = {k: v for k, v in q.items() if k not in ("box", "lone")}
        if q.get("box"):
            params["bbox"] = ",".join(str(v) for v in q["box"])
        if q.get("lone"):
            params["unlocated"] = 1
        params.setdefault("limit", 37)
        cursor = None
        for _ in range(4):  # the first pages, through the cursor path
            body = client.get("/api/people", params={**params, **({"cursor": cursor} if cursor else {})}).json()
            want, total = _naive_people(d, coords, **{**q, "limit": params["limit"], "cursor": cursor})
            assert body["data"] == want and body["meta"]["total"] == total, q
            cursor = body["meta"]["next_cursor"]
            if not cursor:
                break
    for search, zoom in (("", 1), ("", 3), ("jose", 2), ("a b", 1)):
        got = client.get("/api/people/countries", params={"search": search, "zoom": zoom}).json()["data"]
        assert got == _naive_countries(d, search, zoom)
    for pid in list({c["fromId"] for c in d["connections"]})[:25] + [d["people"][0]["id"]]:
        body = client.get("/api/people/network", params={"person_id": pid}).json()
        want, total_conns = _naive_network(d, pid)
        assert body["data"] == want and body["meta"]["total_connections"] == total_conns
        detail = client.get(f"/api/people/{pid}").json()["data"]
        person = next(p for p in d["people"] if p["id"] == pid)
        assert detail == {"person": person,
                          "organizations": [o for o in d["organizations"] if o["id"] in person["organizationIds"]],
                          "connections": [c for c in d["connections"] if pid in (c["fromId"], c["toId"])]}


def test_publisher_shards_reassemble_in_exact_manifest_order():
    """Publisher positions + consumer assembly reproduce the manifest's order for every kind, so response arrays
    (organizations, connections, /network people) match the frontend's fixture mode record for record."""
    import importlib.util
    import random

    from trace_backend import config
    from trace_backend.api import people

    spec = importlib.util.spec_from_file_location("bps", config.BACKEND / "scripts" / "build_people_snapshot.py")
    bps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bps)
    rng = random.Random(7)
    ids = [f"p{n:04d}" for n in range(300)]
    rng.shuffle(ids)  # manifest order deliberately not id order
    manifest = {"people": [{"id": i, "name": i} for i in ids],
                "organizations": [{"id": f"o{n}"} for n in rng.sample(range(40), 40)],
                "connections": [{"id": f"c{n}"} for n in rng.sample(range(60), 60)]}
    version, entries, blobs, _ = bps.plan(manifest)
    idx = {"counts": {k: len(manifest[k]) for k in ("people", "organizations", "connections")}, "shards": entries}
    raw = people._assemble(idx, dict(blobs))
    for kind in ("people", "organizations", "connections"):
        assert [r["id"] for r in raw[kind]] == [r["id"] for r in manifest[kind]], kind
