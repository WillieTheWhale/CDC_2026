# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""GET /api/estimated-flows: snapshot-file shape, parity with the committed snapshots, year/mode echo, 404, lazy imports."""
import json
import subprocess
import sys

import pytest

from trace_backend import config
from trace_backend.api.estimated_flows import compute

SNAP = config.REPO / "frontend" / "public" / "data"


def _snapshot(kind: str, mode: str, year: int) -> dict:
    f = SNAP / kind / f"{mode}-{year}.json"
    if not f.exists():
        pytest.skip(f"no snapshot {f.name}")
    return json.loads(f.read_text(encoding="utf-8"))


def _core(edges: list[dict]) -> list:
    return sorted((e["drug"], e["from"], e["to"], e["volume_norm"], e["confidence"]) for e in edges)


def test_shape_and_meta(client):
    r = client.get("/api/estimated-flows", params={"year": 2014, "mode": "observed"})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    d, meta = body["data"], body["meta"]
    assert d["year"] == 2014 and d["mode"] == "observed"
    assert d["city_fields"] == ["name", "iso3", "lon", "lat", "intensity"]
    assert d["flow_fields"] == ["drug", "generation", "strength", "from", "to", "km"]
    assert set(d["drugs"]) <= {"cocaine", "heroin", "meth", "cannabis"} and d["flows"] and d["cities"]
    n = len(d["cities"])
    assert d["cities"][0][4] == 1.0 and all(len(c) == 5 and 0 <= c[4] <= 1 for c in d["cities"])
    for drug, gen, strength, a, b, km in d["flows"]:
        assert 0 <= drug < len(d["drugs"]) and gen in (1, 2, 3) and 0 <= strength <= 1
        assert 0 <= a < n and 0 <= b < n and a != b and 25 <= km <= 1500
    assert meta["kind"] == "estimated" and "not used in any score" in meta["note"]
    assert meta["city_role"] == "placement_anchor"
    assert any("placement anchors" in s and "not evidence of city-level trafficking" in s for s in meta["notes"])
    assert {"natural_earth", "wb_wdi"} <= {s["id"] for s in meta["sources"]}
    text = json.dumps(body).lower()
    for word in ("enforcement", "detection", "monitor", "customs"):
        assert word not in text  # design boundary: no enforcement framing in the layer


@pytest.mark.parametrize("year", [2006, 2014, 2024])
def test_parity_with_observed_snapshots(client, year):
    static = _snapshot("estimated", "observed", year)
    routes = _snapshot("routes", "observed", year)["data"]["edges"]
    from trace_backend.api.app import store
    if _core(store().routes("observed", year) or []) != _core(routes):
        pytest.skip("served routes differ from the snapshot the static layer was built from")
    assert client.get("/api/estimated-flows", params={"year": year, "mode": "observed"}).json()["data"] == static["data"]


def test_parity_predicted_from_snapshot_edges(client):
    """predicted-2025.json was built from the snapshot routes; the seeds + algorithm reproduce it exactly."""
    static = _snapshot("estimated", "predicted", 2025)
    edges = _snapshot("routes", "predicted", 2025)["data"]["edges"]
    assert json.loads(json.dumps(compute(edges, 2025, "predicted"))) == static["data"]


def test_year_and_mode_echo_and_defaults(client):
    from trace_backend.api.app import store
    meta = store().meta
    y = meta["predicted_years"][0]
    d = client.get("/api/estimated-flows", params={"mode": "predicted"}).json()["data"]
    assert (d["year"], d["mode"]) == (y, "predicted")
    d = client.get("/api/estimated-flows", params={"year": y, "mode": "predicted"}).json()["data"]
    assert (d["year"], d["mode"]) == (y, "predicted")
    d = client.get("/api/estimated-flows").json()["data"]
    assert (d["year"], d["mode"]) == (meta["latest_observed_year"], "observed")


def test_not_found_and_bad_mode(client):
    for params in ({"year": 1990}, {"year": 2010, "mode": "predicted"}):
        r = client.get("/api/estimated-flows", params=params)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "year_not_available"
    assert client.get("/api/estimated-flows", params={"mode": "bogus"}).status_code == 422


def test_non_ascii_city_names_survive_any_client(client):
    r = client.get("/api/estimated-flows", params={"year": 2014})
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert r.content.isascii()  # \u escapes: decodes the same as UTF-8, latin-1 or cp1252
    names = {c[0] for c in json.loads(r.content.decode("latin-1"))["data"]["cities"]}
    assert "São Paulo" in names or any(any(ord(ch) > 127 for ch in n) for n in names)


def test_module_import_stays_light():
    code = ("import sys, trace_backend.api.estimated_flows; "
            "print(sorted(m for m in ('pandas', 'numpy', 'lightgbm') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=config.BACKEND, check=True)
    assert out.stdout.strip() == "[]"
