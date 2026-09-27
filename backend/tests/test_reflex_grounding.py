# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Grounding guardrails (trace_backend.jev.grounding) and the real-news benchmark (jev/data/real_headlines_v1.jsonl).

The floors below were measured on the benchmark with the guardrails on (docs/REFLEX_SPEC.md, "Real-news benchmark");
they guard against regressions, and the hallucination count must stay at zero.
"""
from __future__ import annotations

import os

import pytest

from trace_backend.jev.base import Classification
from trace_backend.jev.benchmark import load_benchmark, predict, score
from trace_backend.jev.grounding import (
    country_candidates,
    ground,
    has_trade_vocabulary,
    passes_wire,
    supported_countries,
    supported_drugs,
)
from trace_backend.jev.mock import MockJevClassifier


def _c(**kw) -> Classification:
    base = dict(is_event=0.9, event_type="seizure", event_type_conf=0.9, drug="cocaine", drug_conf=0.9, origin=None,
                transit=None, destination=None, location=None, size="small", size_score=0.0, route_mentioned=0.2,
                confidence=0.9)
    base.update(kw)
    return Classification(**base)


# ------------------------------------------------------------------ country evidence
@pytest.mark.parametrize("text, expected", [
    ("Spanish police seize cocaine from Ecuador", {"ESP", "ECU"}),                   # demonym + name
    ("Customs find 900 kg at Antwerp", {"BEL"}),                                       # curated port
    ("Seizure at Mundra port in Kutch", {"IND"}),                                      # port, no country named
    ("Border Patrol stops truck in Arizona", {"USA"}),                                 # US state
    ("Cartel violence in Sinaloa", {"MEX"}),                                           # Mexican state
    ("PH Navy seizes shabu", {"PHL"}),                                                 # upper-case acronym
    ("The U.S. and UK sign a pact", {"USA", "GBR"}),
    ("Medellín and Medellin", {"COL"}),                                                # accents folded
    ("Pakistan's navy", {"PAK"}),                                                      # possessive
])
def test_country_evidence(text, expected):
    assert supported_countries(text) == expected


@pytest.mark.parametrize("text", [
    "Tell us about the market",              # 'us' is not the US
    "A turkey dinner served on china",       # lower-case common nouns
    "Latin American and South American trends",  # regions, not the USA
    "Trafficking surges in the Golden Triangle",  # a region spanning three countries
    "Indian Ocean patrols",
    "Nancy and Victoria went to Reading",    # city names that are also common words or names
])
def test_no_country_evidence(text):
    assert supported_countries(text) == set()


def test_new_mexico_is_usa_not_mexico():
    assert supported_countries("Arrests in New Mexico") == {"USA"}


def test_candidates_are_ordered_and_distinct():
    assert country_candidates("Cocaine from Colombia seized in Spain, Colombian police say") == ["COL", "ESP"]


# ------------------------------------------------------------------ drug evidence
@pytest.mark.parametrize("text, expected", [
    ("1.5 tons of 'shabu' seized", {"meth"}),
    ("yaba pills intercepted", {"meth"}),
    ("Captagon, the 'Jihadi drug'", {"other"}),
    ("Carfentanil trafficker sentenced", {"fentanyl"}),
    ("Xylazine-laced fentanyl and cocaine", {"other", "fentanyl", "cocaine"}),
    ("crystal methadone lab", set()),              # methadone is not meth
    ("Syrian amphetamine trade", {"other"}),        # amphetamine is not methamphetamine
    ("cannabis resin and hashish", {"cannabis"}),
    ("opium poppy cultivation", {"heroin"}),
    ("Police seize drugs worth RM18mil", set()),
    ("ICE agents detain man", set()),               # the agency, not the drug
])
def test_drug_evidence(text, expected):
    assert supported_drugs(text) == expected


def test_trade_vocabulary():
    assert has_trade_vocabulary("Police seize drugs worth RM18mil")
    assert not has_trade_vocabulary("Mexico wins 2-0 over South Africa")


# ------------------------------------------------------------------ the guardrail, one test per rule
def test_ungrounded_country_becomes_not_stated():
    c = ground(_c(origin="COL", destination="ESP"), "Spanish police seize 2 tonnes of cocaine")
    assert c.origin is None and c.destination == "ESP"
    assert "origin:COL" in c.dropped


def test_ungrounded_location_falls_back_to_a_grounded_place():
    c = ground(_c(location="MMR"), "Police seize cocaine in Antwerp")
    assert c.location == "BEL"


def test_ungrounded_drug_is_dropped_or_replaced_by_supported_option():
    assert ground(_c(drug="heroin"), "Police seize drugs worth $2 million").drug == "unclear"
    c = ground(_c(drug="heroin", drug_conf=0.6, confidence=0.8), "Police seize 20 kg of cocaine",
               drug_probs={"heroin": 0.6, "cocaine": 0.3, "unclear": 0.1})
    assert c.drug == "cocaine" and "drug:heroin" in c.dropped
    assert c.confidence < 0.8


def test_supported_drug_is_kept():
    assert ground(_c(drug="meth"), "PDEA seizes shabu in Manila").drug == "meth"


def test_size_only_from_stated_quantity():
    c = ground(_c(size="major"), "CBP seizes $23 million in methamphetamine")
    assert c.size_stated is False
    c = ground(_c(size="small"), "Customs seize 1.5 tonnes of cocaine")
    assert c.size == "major" and c.size_stated


def test_is_event_needs_trade_vocabulary_and_threshold():
    assert ground(_c(is_event=0.95), "Mexico wins 2-0 over South Africa").is_event < 0.5
    assert ground(_c(is_event=0.95), "Police seize 20 kg of cocaine").is_event == 0.95
    assert ground(_c(is_event=0.45), "Police seize 20 kg of cocaine", event_threshold=0.5).is_event < 0.5


def test_ground_is_idempotent():
    t = "Spanish police seize 13 tonnes of cocaine from Ecuador"
    once = ground(_c(origin="ECU", destination="ESP", drug="cocaine"), t)
    assert ground(once, t) == once


def test_passes_wire():
    assert passes_wire(_c(is_event=0.9, confidence=0.9))
    assert not passes_wire(_c(is_event=0.3, confidence=0.9))
    assert not passes_wire(_c(is_event=0.9, confidence=0.3))


# ------------------------------------------------------------------ the real-news benchmark
def test_benchmark_is_well_formed():
    rows = load_benchmark()
    assert 80 <= len(rows) <= 120
    groups = {r["group"] for r in rows}
    assert groups == {"event", "drug_non_event", "near_miss", "unrelated"}
    for r in rows:
        g, s = r["labels"], r["support"]
        assert r["url"].startswith("http") and r["headline"]
        for f in ("origin", "destination"):
            assert g[f] is None or g[f] in s["countries"], r["id"]
        assert g["drug"] == "unclear" or g["drug"] in s["drugs"], r["id"]


# floors measured with the guardrails on (see docs/REFLEX_SPEC.md); a small margin below the measured values
MOCK_FLOORS = {"is_event": 0.82, "event_type": 0.70, "drug": 0.87, "origin": 0.86, "destination": 0.52, "size": 0.90}


def test_benchmark_mock_grounded_end_to_end():
    rows = load_benchmark()
    res = score(rows, predict(MockJevClassifier(), rows, grounded=True))
    assert res["hallucination"]["hallucinated"] == 0, res["hallucination"]["rows"]
    assert res["false_event_rate_negatives"] <= 0.08  # measured 3/39; the keyword mock is a baseline, not shipped
    for f, floor in MOCK_FLOORS.items():
        assert res["field_accuracy"][f] >= floor, (f, res["field_accuracy"])


def test_benchmark_mock_raw_hallucinates_more():
    """The guardrail is doing work: the ungrounded mock names at least one unsupported entity."""
    rows = load_benchmark()
    raw = score(rows, predict(MockJevClassifier(), rows, grounded=False))
    assert raw["hallucination"]["hallucinated"] > 0


REFLEX_FLOORS = {"is_event": 0.88, "event_type": 0.85, "drug": 0.95, "origin": 0.92, "destination": 0.80,
                 "size": 0.90}


def test_benchmark_reflex_grounded():
    pytest.importorskip("torch")
    from trace_backend.reflex.model import WEIGHTS_DIR
    if not (WEIGHTS_DIR / "reflex.json").exists():
        pytest.skip("Reflex weights absent (backend/data/reflex/model)")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from trace_backend.jev.reflex_client import ReflexClassifier
    rows = load_benchmark()
    res = score(rows, predict(ReflexClassifier(grounded=True), rows, grounded=True))
    assert res["hallucination"]["hallucinated"] == 0, res["hallucination"]["rows"]
    assert res["false_event_rate_negatives"] <= 0.06  # measured 2/39 = 0.051
    for f, floor in REFLEX_FLOORS.items():
        assert res["field_accuracy"][f] >= floor, (f, res["field_accuracy"])


def test_country_names_resolve_without_the_contracts_folder(monkeypatch, tmp_path):
    """The Vercel package ships trace_backend and data/ but no contracts/: country names must still resolve (a
    silent empty catalogue made every stated origin/destination come back as not stated in production)."""
    from trace_backend.jev import grounding
    monkeypatch.setattr(grounding, "HERE", tmp_path / "trace_backend" / "jev")  # no contracts/ above this path
    grounding.gazetteer.cache_clear()
    try:
        cands = grounding.country_candidates("Spanish police intercept cocaine shipment from Colombia at Algeciras port")
        assert "COL" in cands and "ESP" in cands
        assert "CHL" in grounding.country_candidates("Police charge three over cocaine imported from Chile")
    finally:
        grounding.gazetteer.cache_clear()
