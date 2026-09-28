# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""US documented routes: every row is cited, placed no more precisely than its source, and in bounds."""
import csv

import pytest

from trace_backend.us import routes as us

pytestmark = pytest.mark.skipif(not (us.PLACES.exists() and us.STATES.exists()),
                                reason="Natural Earth files not downloaded")
BASE = {"basis": "hidta_assessment", "source_id": "t", "source_url": "https://example.gov/r.pdf", "publisher": "HIDTA",
        "title": "Test", "publication_year": "2024", "locator": "p. 3", "quote": "moved from A to B",
        "from_country": "", "to_country": "", "period_start": "", "period_end": ""}


def _write(tmp_path, rows):
    p = tmp_path / "r.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv.reader(open(us.SEED, encoding="utf-8")).__next__()))
        w.writeheader()
        for r in rows:
            w.writerow({**BASE, **r})
    return p


def test_city_state_and_foreign_places(tmp_path):
    p = _write(tmp_path, [
        {"route_id": "a", "drug": "meth", "from_city": "Phoenix", "from_state": "AZ", "to_city": "Columbus",
         "to_state": "OH"},
        {"route_id": "b", "drug": "fentanyl", "from_city": "", "from_state": "", "from_country": "MEX",
         "to_city": "", "to_state": "AZ"},
    ])
    routes, problems = us.load(p)
    assert problems == []
    a, b = routes
    assert a["precision"] == "city" and a["to"]["state"] == "OH" and 39 < a["to"]["lat"] < 41  # Ohio, not Georgia
    assert b["from"]["precision"] == "country" and b["to"]["precision"] == "state"


def test_uncited_or_out_of_bounds_rows_are_rejected(tmp_path):
    p = _write(tmp_path, [
        {"route_id": "c", "drug": "meth", "from_city": "Phoenix", "from_state": "AZ", "to_city": "Nowhereville",
         "to_state": "OH"},
        {"route_id": "d", "drug": "meth", "from_city": "Phoenix", "from_state": "AZ", "to_city": "", "to_state": "OH",
         "quote": ""},
        {"route_id": "e", "drug": "meth", "from_city": "Phoenix", "from_state": "AZ", "to_city": "", "to_state": "OH",
         "locator": "route avoids checkpoint"},
        {"route_id": "f", "drug": "lsd", "from_city": "Phoenix", "from_state": "AZ", "to_city": "", "to_state": "OH"},
    ])
    routes, problems = us.load(p)
    assert routes == [] and len(problems) == 4
    assert any("design boundary" in x for x in problems)


def test_committed_seed_is_valid():
    routes, problems = us.load()
    assert problems == []


def test_api_serves_placed_routes_with_filters():
    from fastapi.testclient import TestClient

    from trace_backend import contract
    from trace_backend.api.app import app
    c = TestClient(app)
    body = c.get("/api/us-routes").json()
    contract.validate("UsRoutesResponse", body)
    assert body["data"]["total"] == len(body["data"]["routes"]) > 0
    tx = c.get("/api/us-routes", params={"drug": "heroin", "state": "TX"}).json()["data"]["routes"]
    assert tx and all(r["drug"] == "heroin" and "TX" in (r["from"]["state"], r["to"]["state"]) for r in tx)
    assert c.get("/api/us-routes", params={"drug": "lsd"}).status_code == 422


def test_placed_seed_matches_csv():
    import json
    placed = json.loads(us.PLACED.read_text(encoding="utf-8"))["data"]["routes"]
    routes, _ = us.load()
    assert [r["id"] for r in placed] == [r["id"] for r in routes]  # rerun `uv run trace us-routes` after editing the CSV

