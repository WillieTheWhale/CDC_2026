# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Hurdle, gravity, metrics, and shock propagation on synthetic data (no pipeline needed)."""
import numpy as np
import pandas as pd
import pytest

from trace_backend.model import edges as E
from trace_backend.model import shocks as SH
from trace_backend.model.features import HIDDEN_DRIVERS, feature_columns
from trace_backend.model.gravity import GravityPPML
from trace_backend.model.hurdle import HurdleModel
from trace_backend.model.train import scores


def synth(n=600, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in feature_columns()})
    df["drug_code"] = rng.integers(0, 4, n)
    df["drug"] = np.array(["cocaine", "heroin", "meth", "cannabis"])[df["drug_code"]]
    df["lag_log_kg"] = rng.uniform(0, 10, n)
    df["kg"] = np.expm1(df["lag_log_kg"])
    df["lag_active"] = (df["lag_log_kg"] > 3).astype(int)
    df["lag_share"] = rng.uniform(0, 0.05, n)
    df["active_next"] = ((df["lag_log_kg"] + rng.normal(0, 1, n)) > 3).astype(float)
    df["kg_next"] = np.where(df["active_next"] == 1, np.expm1(df["lag_log_kg"] + rng.normal(0, 0.3, n)), 0.0)
    df["year"] = rng.integers(2015, 2020, n)
    for c in ["log_gdp_from", "log_gdp_to", "log_pop_from", "log_pop_to", "log_dist", "contig", "price_gap0",
              "price_missing"]:
        df[c] = rng.normal(size=n)
    df["contig"] = (df["contig"] > 1).astype(int)
    return df


def test_hurdle_fits_and_explains():
    df = synth()
    hm = HurdleModel().fit(df)
    p = hm.predict_proba(df)
    assert p.shape == (len(df),) and ((p >= 0) & (p <= 1)).all()
    assert (hm.predict_kg(df) >= 0).all()
    d = hm.drivers(df.head(5))
    assert len(d) == 5 and all(len(x) == 3 for x in d)
    shown = {x["feature"] for row in d for x in row}
    assert not shown & HIDDEN_DRIVERS and "lag_log_kg" not in shown


def test_gravity_ppml_fits():
    df = synth()
    g = GravityPPML().fit(df)
    assert (g.predict_kg(df) > 0).all()
    assert "log_dist" in g.summary()


def test_scores_perfect_ranking():
    df = synth(400)
    s = scores(df, df["kg_next"].values, df["active_next"].values)
    assert s["auc"] == pytest.approx(1.0) and s["spearman"] > 0.99


def _ctx():
    cands = pd.DataFrame([("heroin", "AFG", "IRN", True), ("heroin", "IRN", "TUR", True),
                          ("heroin", "MMR", "THA", True)], columns=["drug", "from_iso3", "to_iso3", "documented"])
    dist = pd.DataFrame([("AFG", "IRN", 900, 1, 0), ("IRN", "TUR", 1500, 1, 0), ("MMR", "THA", 700, 1, 0)],
                        columns=["from_iso3", "to_iso3", "dist", "contig", "comlang_off"])
    seiz = pd.DataFrame([("AFG", 2022, "heroin", 5000.0), ("IRN", 2022, "heroin", 20000.0),
                         ("TUR", 2022, "heroin", 8000.0), ("MMR", 2022, "heroin", 1000.0),
                         ("THA", 2022, "heroin", 1500.0)], columns=["iso3", "year", "drug", "kg"])
    prod = pd.DataFrame([("AFG", 2022, "heroin", 600000.0), ("MMR", 2022, "heroin", 80000.0)],
                        columns=["iso3", "year", "drug", "prod_kg"])
    alloc = E.allocate(cands, seiz, prod, dist, [2022])
    alloc = E.finalize(alloc.assign(**{c: np.nan for c in ["price_from", "price_to", "oc_from", "oc_to"]}))
    ctx = SH.Context.__new__(SH.Context)
    ctx.edges, ctx.seiz, ctx.prod, ctx.dist = alloc, seiz, prod, dist
    ctx.cands = cands
    return ctx


def test_cultivation_shock_cuts_afghan_route_and_cascades():
    ctx = _ctx()
    base = ctx.edges.set_index(["from_iso3", "to_iso3"])["kg"]
    sc = SH.scenario_year(ctx, 2022, [SH.Shock("cultivation", "AFG", 0.05, "heroin")]).set_index(
        ["from_iso3", "to_iso3"])["kg"]
    assert sc[("AFG", "IRN")] < base[("AFG", "IRN")] * 0.5
    assert sc[("IRN", "TUR")] < base[("IRN", "TUR")]          # downstream transit cascades
    assert sc[("MMR", "THA")] == pytest.approx(base[("MMR", "THA")])  # unrelated corridor untouched


def test_customs_shift_displaces_flows():
    ctx = _ctx()
    base = ctx.edges.set_index(["from_iso3", "to_iso3"])["kg"]
    sc = SH.scenario_year(ctx, 2022, [SH.Shock("customs_efficiency", "TUR", 1.0)]).set_index(
        ["from_iso3", "to_iso3"])["kg"]
    assert sc[("IRN", "TUR")] <= base[("IRN", "TUR")]
