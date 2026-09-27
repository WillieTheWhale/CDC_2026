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
