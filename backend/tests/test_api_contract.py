# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Static endpoints validate against contracts/openapi.yaml (see conftest for the data used)."""
import pytest  # noqa: F401

from trace_backend import contract  # noqa: F401

from .conftest import check  # noqa: F401


def test_meta(client):
    d = check(client.get("/api/meta"), "/api/meta")["data"]
    assert d["observed_years"] and d["predicted_years"]
    assert any(s["id"] == "wb_wdi" for s in d["sources"])


def test_countries(client):
    d = check(client.get("/api/countries"), "/api/countries")["data"]
    assert len(d) >= 5 and all(len(c["iso3"]) == 3 for c in d)


@pytest.mark.parametrize("params", [{}, {"mode": "predicted"}, {"drug": "heroin"}, {"drug": "cocaine", "min_confidence": 60},
                                    {"mode": "observed", "year": "first"}])
def test_routes(client, params):
    params = dict(params)
    if params.get("year") == "first":
        params["year"] = client.get("/api/meta").json()["data"]["observed_years"][0]
    d = check(client.get("/api/routes", params=params), "/api/routes")["data"]
    if "drug" in params:
        assert all(e["drug"] == params["drug"] for e in d["edges"])
    if params.get("mode") == "predicted":
        assert all(e["probability"] is not None for e in d["edges"])


def test_routes_404(client):
    check(client.get("/api/routes", params={"year": 1900}), "/api/routes", status=404)


def test_country(client):
    iso3 = client.get("/api/risk", params={"limit": 1}).json()["data"]["rows"][0]["iso3"]
    d = check(client.get(f"/api/country/{iso3}"), "/api/country/{iso3}")["data"]
    assert d["country"]["iso3"] == iso3
    vals = [i for g in d["indicators"] for i in g["indicators"]]
    assert vals and all({"code", "source_id", "year", "value"} <= i.keys() for i in vals)
    assert not any(i["code"] == "LP.LPI.CUST.XQ" for i in vals)  # design boundary
    y0 = client.get("/api/meta").json()["data"]["risk_years"][0]
    check(client.get(f"/api/country/{iso3.lower()}", params={"year": y0}), "/api/country/{iso3}")


def test_country_404(client):
    check(client.get("/api/country/XXX"), "/api/country/{iso3}", status=404)


def test_risk(client):
    d = check(client.get("/api/risk", params={"limit": 20}), "/api/risk")["data"]
    assert len(d["rows"]) <= 20 and [r["rank"] for r in d["rows"]] == sorted(r["rank"] for r in d["rows"])
    check(client.get("/api/risk", params={"year": 1900}), "/api/risk", status=404)


def test_prices(client):
    check(client.get("/api/prices"), "/api/prices")
    d = check(client.get("/api/prices", params={"drug": "cocaine"}), "/api/prices")["data"]
    assert all(s["drug"] == "cocaine" for s in d["series"])


def test_afghan_ban(client):
    d = check(client.get("/api/experiments/afghan-ban"), "/api/experiments/afghan-ban")["data"]
    assert d["ban_year"] == 2022


def test_metrics(client):
    d = check(client.get("/api/metrics"), "/api/metrics")["data"]
    assert d["backtest"]["train_through"] == 2019
