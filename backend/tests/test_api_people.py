# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""People API: paging, filters, network and detail, plus the dataset's citation and privacy guarantees."""
import pytest
from fastapi.testclient import TestClient

from trace_backend.api import people
from trace_backend.api.app import app

client = TestClient(app)
pytestmark = pytest.mark.skipif(not people.dataset()["people"], reason="People manifest not available")


def _all(params: dict) -> list[dict]:
    out, cursor = [], None
    while True:
        body = client.get("/api/people", params={**params, **({"cursor": cursor} if cursor else {})}).json()
        out += body["data"]["people"]
        cursor = body["meta"]["next_cursor"]
        if not cursor:
            return out


def test_paging_is_complete_sorted_and_stable():
    first = client.get("/api/people", params={"zoom": 3, "limit": 7}).json()
    assert first["meta"]["total"] >= len(first["data"]["people"]) == 7
    rows = _all({"zoom": 3, "limit": 7})
    assert len(rows) == first["meta"]["total"] == len({p["id"] for p in rows})
    keys = [(people._fold(p["name"]), p["id"]) for p in rows]
    assert keys == sorted(keys)


def test_zoom_tiers_and_country_filter():
    z1 = client.get("/api/people", params={"zoom": 1, "limit": 250}).json()["data"]["people"]
    assert all(p["prominence"] == 1 for p in z1)
    iso3 = z1[0]["regions"][0]["iso3"]
    by_country = _all({"country": iso3, "zoom": 1, "limit": 50})
    assert by_country and all(any(r["iso3"] == iso3 for r in p["regions"]) for p in by_country)
    counts = {c["iso3"]: c for c in client.get("/api/people/countries", params={"zoom": 1}).json()["data"]}
    assert counts[iso3]["total"] == len(by_country) >= counts[iso3]["visible"]


def test_search_matches_names_and_aliases_across_tiers():
    target = next(p for p in people.dataset()["people"] if p.get("aliases"))
    got = _all({"search": target["aliases"][0][:6], "limit": 250})
    assert target["id"] in {p["id"] for p in got}


def test_bad_inputs_are_rejected():
    assert client.get("/api/people", params={"bbox": "1,2,3"}).status_code == 400
    assert client.get("/api/people", params={"zoom": 4}).status_code == 422
    other = client.get("/api/people", params={"zoom": 3, "limit": 1}).json()["meta"]["next_cursor"]
    assert client.get("/api/people", params={"zoom": 1, "cursor": other}).status_code == 400


def test_network_and_detail():
    conn = people.dataset()["connections"][0]
    net = client.get("/api/people/network", params={"person_id": conn["fromId"]}).json()
    ids = {p["id"] for p in net["data"]["people"]}
    assert conn["id"] in {c["id"] for c in net["data"]["connections"]} and {conn["fromId"], conn["toId"]} <= ids
    assert net["meta"]["total_connections"] >= len(net["data"]["connections"])
    detail = client.get(f"/api/people/{conn['fromId']}").json()["data"]
    assert detail["person"]["id"] == conn["fromId"] and detail["connections"]
    assert client.get("/api/people/no-such-person").status_code == 404
    assert client.get("/api/people/network", params={"person_id": "no-such-person"}).status_code == 404


def test_every_record_is_cited_and_country_level_only():
    d = people.dataset()
    for rec in d["people"] + d["organizations"] + d["connections"]:
        assert rec["sources"] and all(s["url"].startswith("http") for s in rec["sources"])
    for p in d["people"]:
        assert not {"lat", "lon", "latitude", "longitude", "address"} & set(p)
        assert all(set(r) <= {"iso3", "label", "evidence"} for r in p["regions"])


def test_unlocated_lists_every_tier_of_countryless_people():
    expected = {p["id"] for p in people.dataset()["people"] if not p["regions"]}
    first = client.get("/api/people", params={"unlocated": 1, "limit": 5}).json()
    assert first["meta"]["total"] == len(expected)
    rows = _all({"unlocated": 1, "limit": 5, "zoom": 1})
    assert {p["id"] for p in rows} == expected and len(rows) == len(expected)
    assert all(p["regions"] == [] for p in rows)
    keys = [(people._fold(p["name"]), p["id"]) for p in rows]
    assert keys == sorted(keys)
    target = next((p for p in people.dataset()["people"] if not p["regions"] and p.get("aliases")), None)
    if target:
        got = _all({"unlocated": 1, "search": target["aliases"][0][:6], "limit": 250})
        assert target["id"] in {p["id"] for p in got} and all(not p["regions"] for p in got)


def test_unlocated_conflicts_and_cursor_binding():
    for extra in ({"country": "COL"}, {"bbox": "-80,0,-70,10"}):
        r = client.get("/api/people", params={"unlocated": 1, **extra})
        assert r.status_code == 400 and "unlocated cannot be combined" in r.json()["error"]["message"]
    assert client.get("/api/people", params={"unlocated": "true"}).status_code == 400
    cur = client.get("/api/people", params={"unlocated": 1, "limit": 1}).json()["meta"]["next_cursor"]
    if cur:
        assert client.get("/api/people", params={"zoom": 3, "cursor": cur}).status_code == 400
        assert client.get("/api/people", params={"unlocated": 1, "cursor": cur}).status_code == 200


# --- synthetic datasets: life/legal status validation and remote refresh (never touches the network) ---

SRC = {"url": "https://example.org/a", "title": "T", "publisher": "P", "language": "en", "claim": "C"}


def _person(pid: str, name: str, **kw) -> dict:
    return {"id": pid, "name": name, "status": "charged", "statusAsOf": "2024-01-01", "prominence": 3,
            "organizationIds": [], "regions": [], "drugs": [], "sources": [SRC], **kw}


def test_normalize_life_and_legal_status():
    legal = [{"status": "charged", "date": "2019-03-04", "qualifier": "Indictment; allegation only", "source": SRC},
             {"status": "convicted", "date": "2021", "qualifier": "Jury verdict", "jurisdiction": "US", "source": SRC},
             {"status": "charged", "date": "2019-02-30", "qualifier": "bad date", "source": SRC},
             {"status": "pending", "date": "2020-01-01", "qualifier": "bad status", "source": SRC},
             {"status": "charged", "date": "2020-01-01", "qualifier": "", "source": SRC},
             {"status": "charged", "date": "2020-01-01", "qualifier": "no source"}]
    raw = {"organizations": [], "connections": [], "people": [
        _person("a", "A", lifeStatus={"value": "deceased", "deathDate": "2022-05", "source": SRC}, legalHistory=legal),
        _person("b", "B", lifeStatus={"value": "unknown", "deathDate": "2022-05-01", "source": SRC}),
        _person("c", "C", lifeStatus={"value": "deceased"}, legalHistory="nope"),
        _person("d", "D", lifeStatus={"value": "alive", "source": SRC}),
        _person("e", "E", status="deceased")]}
    got = {p["id"]: p for p in people.normalize(raw)["people"]}
    assert set(got) == {"a", "b", "c", "d"}  # death is not a legal status
    a = got["a"]
    assert a["status"] == "charged" and a["statusAsOf"] == "2024-01-01" and a["lifeStatus"]["value"] == "deceased"
    assert [(e["status"], e["date"]) for e in a["legalHistory"]] == [("convicted", "2021"), ("charged", "2019-03-04")]
    assert all("lifeStatus" not in got[k] for k in "bcd")
    assert got["c"]["legalHistory"] == [] and "legalHistory" not in got["b"]
    ev = [{"id": i, "occurredAt": d, "type": "charge", "title": "t", "summary": "s", "source": SRC}
          for i, d in (("x", "2023-02-30"), ("y", "2023-13-01"))]
    assert [e["id"] for e in people.normalize({"people": [_person("f", "F", events=ev)]})["people"][0]["events"]] == ["x"]


@pytest.fixture
def remote(monkeypatch, tmp_path):
    """TRACE_PEOPLE_REMOTE=1 with a fake raw-manifest fetch (the snapshot branch is absent); `payload` None means
    304, an exception means failure. Refreshes run inline here; test_people_snapshot_consumer.py covers the rest."""
    class Remote:
        calls = 0
        payload = {"people": [_person("r1", "Remote One")]}

        def fetch(self, url, etag, timeout):
            self.calls += 1
            assert url == people.REMOTE_URL and timeout <= people.REMOTE_TIMEOUT
            if isinstance(self.payload, Exception):
                raise self.payload
            return (None, etag) if self.payload is None else (self.payload, "v1")

    def no_snapshot(url, etag, timeout):
        raise OSError("snapshot branch unavailable")

    r = Remote()
    monkeypatch.setenv("TRACE_PEOPLE_REMOTE", "1")
    monkeypatch.setenv("TRACE_PEOPLE_REFRESH_SECONDS", "600")
    monkeypatch.setenv("TRACE_PEOPLE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(people, "_fetch", r.fetch)
    monkeypatch.setattr(people, "_get", no_snapshot)
    monkeypatch.setattr(people, "_spawn", lambda fn: fn())
    monkeypatch.setattr(people, "_S", people._State())
    return r


def _expire():
    people._S.checked -= 10_000


def test_remote_refresh_ttl_304_and_last_good_copy(remote):
    body = client.get("/api/people", params={"unlocated": 1}).json()
    assert [p["id"] for p in body["data"]["people"]] == ["r1"]
    snap = body["meta"]["people_snapshot"]
    assert snap["origin"] == "github-main" and snap["fetched_at"]
    client.get("/api/people/countries")
    assert remote.calls == 1  # cached within the TTL
    remote.payload = None  # 304 Not Modified keeps the data
    _expire()
    assert client.get("/api/people/r1").json()["meta"]["people_snapshot"]["origin"] == "github-main"
    assert remote.calls == 2
    remote.payload = OSError("offline")  # an error keeps the last good copy
    _expire()
    assert client.get("/api/people/r1").status_code == 200 and remote.calls == 3


def test_remote_failure_falls_back_to_bundled(remote, monkeypatch):
    bundled = people._bundled()
    remote.payload = TimeoutError()
    meta = client.get("/api/people", params={"limit": 1, "zoom": 3}).json()["meta"]
    assert meta["people_snapshot"]["origin"] == "bundled" and meta["people_snapshot"]["fetched_at"] is None
    assert meta["people_snapshot"]["stale"] is True  # never confirmed against a remote
    assert meta["total"] == len(bundled["people"])
    client.get("/api/people", params={"limit": 1})
    assert remote.calls == 1  # failures back off instead of retrying on every request
    remote.payload = {"people": [{"id": "bad"}]}  # nothing valid: treated as a failure
    _expire()
    assert client.get("/api/people", params={"limit": 1}).json()["meta"]["people_snapshot"]["origin"] == "bundled"
    monkeypatch.setenv("TRACE_PEOPLE_REFRESH_SECONDS", "0")  # 0 disables the remote fetch
    _expire()
    client.get("/api/people", params={"limit": 1})
    assert remote.calls == 2


def test_cursor_survives_a_refresh(remote):
    remote.payload = {"people": [_person(f"p{i}", f"Person {i}") for i in (1, 3, 5)]}
    cur = client.get("/api/people", params={"unlocated": 1, "limit": 2}).json()["meta"]["next_cursor"]
    remote.payload = {"people": [_person(f"p{i}", f"Person {i}") for i in range(6)]}
    _expire()
    rest = client.get("/api/people", params={"unlocated": 1, "limit": 10, "cursor": cur}).json()
    assert [p["id"] for p in rest["data"]["people"]] == ["p4", "p5"] and rest["meta"]["total"] == 6


def test_fetch_enforces_an_overall_deadline(monkeypatch):
    clock = [0.0]

    class Slow:
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n):
            clock[0] += 2
            return b" "

    monkeypatch.setattr(people.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(people.urllib.request, "urlopen", lambda req, timeout: Slow())
    with pytest.raises(TimeoutError):
        people._fetch(people.REMOTE_URL, None, 5)
