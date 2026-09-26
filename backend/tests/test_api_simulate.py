# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T9 simulator and command bar, plus full contract path coverage."""
import pytest

from trace_backend import config, contract
from trace_backend.model.scenario import parse_rules

from .conftest import check

needs_db = pytest.mark.skipif(not (config.PROCESSED / "models" / "hurdle.joblib").exists() or not config.DB_PATH.exists(),
                              reason="simulator needs the pipeline outputs (uv run trace pipeline)")


def test_every_contract_path_is_served(client):
    served = set(client.app.openapi()["paths"])  # includes routes from included routers
    for path in contract.openapi()["paths"]:
        assert path in served, f"{path} not served"


@pytest.mark.parametrize("text,expected", [
    ("Colombia cuts coca 50%", {"type": "cultivation", "iso3": "COL", "value": 0.5}),
    ("SHOCK AFG CULTIVATION -95%", {"type": "cultivation", "iso3": "AFG", "value": 0.05}),
    ("Mexico legalizes cannabis", {"type": "legalization", "iso3": "MEX", "value": 1.0}),
    ("Turkey cracks down on ports", {"type": "customs_efficiency", "iso3": "TUR", "value": 1.0}),
])
def test_parse_rules(client, text, expected):
    s = parse_rules(text)[0]
    assert {k: s[k] for k in expected} == expected


@needs_db
def test_simulate_structured(client):
    body = {"shocks": [{"type": "cultivation", "iso3": "COL", "drug": "cocaine", "value": 0.5}]}
    d = check(client.post("/api/simulate", json=body), "/api/simulate", "post")["data"]
    assert d["parsed_by"] == "structured" and d["edges_changed"]


@needs_db
def test_simulate_text_and_invalid(client):
    d = check(client.post("/api/simulate", json={"scenario": "Colombia cuts coca 50%"}), "/api/simulate", "post")
    assert d["data"]["shocks"][0]["iso3"] == "COL"
    check(client.post("/api/simulate", json={"scenario": "make it rain"}), "/api/simulate", "post", status=422)


@pytest.mark.parametrize("text,intent", [("HEROIN ROUTES", "routes"), ("MEX <GO>", "country"), ("RISK TOP 20", "risk"),
                                         ("SHOCK AFG CULTIVATION -95%", "shock"), ("NEWS COCAINE", "news"),
                                         ("COMPARE COL PER", "compare"), ("YEAR 2023", "year"),
                                         ("PREDICT ON", "predict"),
                                         ("which route is least watched by customs", "blocked")])
def test_command(client, text, intent):
    d = check(client.post("/api/command", json={"text": text}), "/api/command", "post")["data"]
    assert d["intent"] == intent


