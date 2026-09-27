# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""The simulator's baseline must equal the saved risk board (/api/risk) for the same year and country."""
import pytest

from trace_backend import config

needs_db = pytest.mark.skipif(not (config.PROCESSED / "models" / "hurdle.joblib").exists() or not config.DB_PATH.exists(),
                              reason="simulator needs the pipeline outputs (uv run trace pipeline)")


def _risk(client, year: int) -> dict[str, float]:
    rows = client.get("/api/risk", params={"year": year}).json()["data"]["rows"]
    return {r["iso3"]: r["score"] for r in rows}


@needs_db
@pytest.mark.parametrize("year", [None, 2016])
def test_baseline_matches_risk_board(client, year):
    body = {"shocks": [{"type": "cultivation", "iso3": "COL", "drug": "cocaine", "value": 0.5}], "year": year}
    d = client.post("/api/simulate", json=body).json()["data"]
    assert d["risk_deltas"], "a 50% coca cut should move some risk scores"
    board = _risk(client, d["year"])
    for rd in d["risk_deltas"]:
        assert rd["baseline_score"] == pytest.approx(board[rd["iso3"]], abs=0.05), rd
        assert rd["delta"] == pytest.approx(rd["scenario_score"] - rd["baseline_score"], abs=0.05), rd


@needs_db
def test_null_shock_has_no_effect(client):
    body = {"shocks": [{"type": "cultivation", "iso3": "COL", "drug": "cocaine", "value": 1.0}]}
    d = client.post("/api/simulate", json=body).json()["data"]
    assert all(abs(rd["delta"]) <= 0.1 for rd in d["risk_deltas"]), d["risk_deltas"]
