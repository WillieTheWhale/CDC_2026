# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Edge allocation and confidence scoring on a toy network."""
import numpy as np
import pandas as pd

from trace_backend.model import edges as E

DIST = pd.DataFrame([
    ("COL", "ECU", 700, 1), ("ECU", "COL", 700, 1), ("ECU", "BEL", 9300, 0), ("COL", "BEL", 8800, 0),
    ("BEL", "ECU", 9300, 0), ("BEL", "COL", 8800, 0),
], columns=["from_iso3", "to_iso3", "dist", "contig"])
SEED = pd.DataFrame([("cocaine", "COL", "ECU"), ("cocaine", "ECU", "BEL"), ("cocaine", "COL", "BEL")],
                    columns=["drug", "from_iso3", "to_iso3"])


def seiz(bel=100.0):
    return pd.DataFrame([("COL", 2020, "cocaine", 500.0), ("ECU", 2020, "cocaine", 200.0),
                         ("BEL", 2020, "cocaine", bel)], columns=["iso3", "year", "drug", "kg"])


def test_allocation_respects_destination_seizures():
    c = E.candidates(seiz(), SEED, DIST)
    e = E.allocate(c, seiz(), pd.DataFrame(columns=["iso3", "year", "drug", "prod_kg"]), DIST, [2020])
    assert (e["kg"] >= 0).all()
    inflow = e.groupby("to_iso3")["kg"].sum()
    assert inflow["BEL"] <= 100.0 + 1e-6 and inflow["ECU"] <= 200.0 + 1e-6


def test_no_seizures_at_destination_means_no_flow():
    s = seiz(bel=0.0)
    c = E.candidates(s, SEED, DIST)
    e = E.allocate(c, s, pd.DataFrame(columns=["iso3", "year", "drug", "prod_kg"]), DIST, [2020])
    assert np.allclose(e.loc[e["to_iso3"] == "BEL", "kg"], 0)


def test_reverse_of_documented_corridor_dropped():
    c = E.candidates(seiz(), SEED, DIST)
    assert not ((c["from_iso3"] == "ECU") & (c["to_iso3"] == "COL")).any()


def test_confidence_weights_sum_to_100():
    assert sum(E.WEIGHTS.values()) == 100


def test_production_units():
    cult = pd.DataFrame([("COL", "coca", 2020, 100.0, np.nan), ("AFG", "opium_poppy", 2020, 1000.0, 2.0)],
                        columns=["iso3", "crop", "year", "hectares", "production_t"])
    p = E.production(cult).set_index("iso3")["prod_kg"]
    assert p["COL"] == 100 * E.COCA_KG_PER_HA and p["AFG"] == 2.0 * E.OPIUM_T_TO_HEROIN_KG
