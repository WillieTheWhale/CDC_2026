# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Evidence drilldown API: value -> formula -> exact source rows, health labels, CDC overdose labels, paging."""
import pytest
from fastapi.testclient import TestClient

from trace_backend.api import evidence
from trace_backend.api.app import app

client = TestClient(app)
pytestmark = pytest.mark.skipif(not evidence.available(), reason="evidence tables not available (no archive)")


def _get(url: str, status: int = 200, **params) -> dict:
    r = client.get(url, params=params)
    assert r.status_code == status, r.text[:500]
    return r.json()


def _ids(**params) -> list[dict]:
    out, cursor = [], None
    while True:
        body = _get("/api/evidence/values", **params, **({"cursor": cursor} if cursor else {}))
        out += body["data"]["values"]
        cursor = body["meta"]["next_cursor"]
        if not cursor:
            return out


def _value(metric_key: str, **params) -> dict:
    rows = _get("/api/evidence/values", kind="research", limit=500, **params)["data"]["values"]
    vid = next(v["id"] for v in rows if v["metric_key"] == metric_key)
    return _get(f"/api/evidence/value/{vid}")


def test_research_drilldown_links_real_source_rows():
    body = _value("cocaine_seizure_next_homicide", iso3="COL")
    d = body["data"]
    assert d["kind"] == "research" and d["formula"]["version"] >= 1 and d["formula"]["selection_rule"]
    assert "not independent countries" in d["support_count_basis"] and d["support_count"] == len(d["inputs"])
    assert d["observation_year"] == d["year"] + 1 and d["source_publication_year"] is None  # WB: no publication year
    assert "retrospective" in d["caveat"].lower()
    roles = {i["role"] for i in d["inputs"]}
    assert {"outcome", "predictor", "predictor_source_row"} <= roles
    assert all(i["source_url"].startswith("https://") for i in d["inputs"])
    wb = next(i for i in d["inputs"] if i["source_table"] == "wb_indicators")["world_bank"]
    assert wb["indicator_code"] == "VC.IHR.PSRC.P5" and wb["source_id"] == 2
    assert wb["download_url"].startswith("https://api.worldbank.org/v2/") and "source=2" in wb["download_url"]
    assert wb["lastupdated"] and wb["sha256"]
    annex = next(i for i in d["inputs"] if i["source_table"] == "seizures_annex")
    assert annex["edition"] == annex["publication_year"] and annex["editions"]
    for row in (i for i in d["inputs"] if i["source_table"] == "unodc_seizure_observations"):
        sr = row["source_row"]
        assert sr["observation"]["iso3"] == "COL" and sr["cells"]
        assert any(c["value_number"] == pytest.approx(sr["observation"]["quantity"]) for c in sr["cells"])
    assert d["regression_sample"]["outcome_year"] == d["observation_year"]
    assert {s["id"] for s in body["meta"]["sources"]} >= {"trace_research_v2", "unodc_wdr_editions", "wb_wdi"}


def test_revision_values_are_labelled():
    d = _value("seizure_edition_revision_pct", iso3="COL")["data"]
    assert "source_edition_revision" in d["quality_flags"] and "not a real-world" in d["revision_label"]
    old, new = (next(i for i in d["inputs"] if i["role"] == r) for r in ("oldest", "newest"))
    assert old["publication_year"] < new["publication_year"] == d["source_publication_year"]
    assert d["value"] == pytest.approx(100 * (new["input_value"] - old["input_value"]) / old["input_value"])
    assert new["revised_between_editions"] and len(new["editions"]) >= 2


def test_market_drilldown_has_workbook_cells_and_source():
    d = _get("/api/evidence/value/1")["data"]
    assert d["kind"] == "market" and d["id"] == "1" and d["support_count"] == len(d["inputs"]) == 2
    src = d["market"]["source"]
    assert src["url"].startswith("https://") and src["edition"] == d["source_publication_year"] and src["sha256"]
    assert "not a profit margin" in d["caveat"]
    for i in d["inputs"]:
        o = i["source_row"]["observation"]
        assert i["source_table"] == "market_observations" and o["iso3"] == d["iso3"] and i["source_row"]["cells"]
        assert any(c["value_number"] == pytest.approx(o["original_value"]) for c in i["source_row"]["cells"])
    retail, wholesale = (next(i for i in d["inputs"] if i["role"] == r) for r in ("retail", "wholesale"))
    assert d["value"] == pytest.approx(retail["input_value"] / wholesale["input_value"])


def test_health_labels_modelled_vs_country_reported():
    d = _get("/api/evidence/health/MEX", limit=2000)["data"]
    assert d["prevalence"]["total"] == len(d["prevalence"]["rows"]) > 0
    cov = d["treatment_coverage"]["rows"]
    assert {r["nature_code"] for r in cov} == {"M", "C"}
    for r in cov:
        assert r["modelled"] == (r["nature_code"] == "M")
        assert ("modelled" in r["nature_label"].lower()) == (r["nature_code"] == "M")
        assert "country-reported" in r["nature_label"].lower() or r["nature_code"] == "M"
    for r in d["prevalence"]["rows"]:
        assert r["estimate_label"] and r["source"]["url"].startswith("https://") and r["source"]["edition_year"]
    small = _get("/api/evidence/health/MEX", limit=3)["data"]
    assert len(small["prevalence"]["rows"]) == 3 and small["prevalence"]["total"] == d["prevalence"]["total"]


def test_overdose_labels_and_null_suppression():
    body = _get("/api/evidence/overdose", limit=5)
    assert "must not be summed" in body["data"]["label"] and "suppressed values are null" in body["data"]["label"]
    assert "Synthetic opioids, excl. methadone (T40.4)" in body["data"]["indicators"]
    assert all(r["status"] == "provisional" and r["period_kind"] == "12 month-ending" for r in body["data"]["rows"])
    rows = _get("/api/evidence/overdose", state="AK", indicator="Cocaine (T40.5)", limit=5000)["data"]["rows"]
    sup = [r for r in rows if r["suppressed"]]
    assert sup and all(r["reported_value"] is None and r["predicted_value"] is None for r in sup)
    syn = _get("/api/evidence/overdose", indicator="Synthetic opioids, excl. methadone (T40.4)", limit=1)["data"]
    assert syn["rows"][0]["indicator"] == "Synthetic opioids, excl. methadone (T40.4)"


def test_research_model_caveat():
    d = _get("/api/evidence/research-model")["data"]
    assert d["n"] == d["sample_rows"] and d["ci_low"] < d["coefficient"] < d["ci_high"]
    assert "not route validation" in d["interpretation"] and "forecast" in d["interpretation"]


def test_not_found_and_bad_requests():
    for url, code in [("/api/evidence/value/999999", "unknown_value"), ("/api/evidence/value/nope", "unknown_value"),
                      ("/api/evidence/health/QQQ", "no_health_evidence")]:
        assert _get(url, 404)["error"]["code"] == code
    assert _get("/api/evidence/overdose", 404, state="ZZ")["error"]["code"] == "unknown_state"
    assert _get("/api/evidence/overdose", 404, indicator="Fentanyl")["error"]["code"] == "unknown_indicator"
    cur = _get("/api/evidence/values", limit=2)["meta"]["next_cursor"]
    assert _get("/api/evidence/values", 400, limit=2, kind="market", cursor=cur)["error"]["code"] == "invalid_request"


def test_values_paging_is_complete_and_stable():
    first = _get("/api/evidence/values", kind="market", drug="cocaine", limit=7)
    rows = _ids(kind="market", drug="cocaine", limit=7)
    assert len(rows) == first["meta"]["total"] == len({r["id"] for r in rows}) > 7
    assert all(r["kind"] == "market" and "cocaine" in r["drug"].lower() for r in rows)
    col = _ids(iso3="COL", limit=50)
    assert {r["kind"] for r in col} == {"research", "market"} and all(r["iso3"] == "COL" for r in col)
    assert [(r["kind"], r["id"]) for r in col if r["kind"] == "research"] == sorted(
        (r["kind"], r["id"]) for r in col if r["kind"] == "research")


def test_overdose_paging():
    total = _get("/api/evidence/overdose", state="US", from_year=2024, limit=1)["meta"]["total"]
    out, cursor = [], None
    while True:
        body = _get("/api/evidence/overdose", state="US", from_year=2024, limit=40, **({"cursor": cursor} if cursor else {}))
        out += body["data"]["rows"]
        cursor = body["meta"]["next_cursor"]
        if not cursor:
            break
    assert len(out) == total and len({(r["period_end"], r["indicator"]) for r in out}) == total
