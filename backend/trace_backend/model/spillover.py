# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T6: Spillover Risk Score per country-year, and the core hypothesis test.

Exposure (0-100): harm-weighted route volume touching the country. For each drug, the country's inbound
  corridor volume + 0.5 x outbound volume + 0.5 x domestic production, as a share of that drug's yearly
  total, weighted by HARM_WEIGHTS, log-scaled on a fixed scale so years are comparable. Observed edges for
  2011-2024; model-predicted edges for the forecast year.
Vulnerability (0-100): mean percentile (within year) of World Bank youth unemployment, youth NEET, poverty,
  Gini, low health spending, weak rule of law, weak control of corruption, low account ownership.
Protection (0-100): Harm Reduction International 2024 services (NSP 25, OAT 25, naloxone 20, DCR 10,
  prison programmes 10, harm reduction in national policy 10). No HRI record = 0 (no evidence of services).
Score = 0.45 exposure + 0.35 vulnerability + 0.20 (100 - protection).

Hypothesis (SYSTEM_DESIGN section 2): does exposure at year t predict a significant rise in homicide or
HIV incidence within 3 years, beyond vulnerability (and the baseline outcome level)? Nested logistic models,
likelihood-ratio test, and country-grouped cross-validated AUC.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import chi2
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .. import config, db
from ..wb.indicators import BY_FEATURE
from .train import update_metrics

log = logging.getLogger(__name__)
WEIGHTS = {"exposure": 0.45, "vulnerability": 0.35, "protection": 0.20}
EPS = 1e-4
# (feature, higher_is_worse)
VULN = [("youth_unemployment", True), ("youth_neet", True), ("poverty", True), ("gini", True),
        ("health_exp_pc", False), ("rule_of_law", False), ("control_corruption", False),
        ("account_ownership", False)]
PROT = {"nsp": 25, "oat": 25, "naloxone": 20, "dcr": 10, "prison_programs": 10, "policy": 10}
PROT_LABELS = {"nsp": "Needle and syringe programmes", "oat": "Opioid agonist therapy",
               "naloxone": "Take-home naloxone", "dcr": "Drug consumption rooms",
               "prison_programs": "Prison harm reduction programmes", "policy": "Harm reduction in national policy"}
TIERS = [(70, "critical"), (58, "high"), (46, "elevated"), (34, "moderate"), (-1, "low")]


def tier(score: float) -> str:
    return next(t for th, t in TIERS if score >= th)


def exposure_raw(edges: pd.DataFrame, prod: pd.DataFrame, years: list[int],
                 totals: tuple[pd.Series, pd.Series] | None = None) -> pd.DataFrame:
    """Per iso3-year-drug: harm-weighted share of that drug's flows touching the country.

    `totals` = (flow totals, production totals) indexed by (drug, year) overrides the denominators, so a
    scenario is measured against the baseline world (absolute declines stay declines)."""
    e = edges[edges["year"].isin(years)]
    tot = e.groupby(["drug", "year"])["kg"].sum().rename("tot") if totals is None else totals[0].rename("tot")
    inflow = e.groupby(["to_iso3", "year", "drug"])["kg"].sum().rename("inbound")
    outflow = e.groupby(["from_iso3", "year", "drug"])["kg"].sum().rename("outbound")
    inflow.index.names = outflow.index.names = ["iso3", "year", "drug"]
    df = pd.concat([inflow, outflow], axis=1).fillna(0).reset_index()
    p = prod[prod["year"].isin(years)].set_index(["iso3", "year", "drug"])["prod_kg"]
    df = df.merge(p.rename("production").reset_index(), on=["iso3", "year", "drug"], how="outer").fillna(0)
    df = df.join(tot, on=["drug", "year"])
    ptot = prod.groupby(["drug", "year"])["prod_kg"].sum() if totals is None else totals[1]
    df["ptot"] = [ptot.get((d, y), np.nan) for d, y in zip(df["drug"], df["year"], strict=True)]
    df["s_in"] = df["inbound"] / df["tot"]
    df["s_out"] = 0.5 * df["outbound"] / df["tot"]
    df["s_prod"] = (0.5 * df["production"] / df["ptot"]).fillna(0)
    df["raw"] = (df["s_in"] + df["s_out"] + df["s_prod"]) * df["drug"].map(config.HARM_WEIGHTS)
    return df


def exposure_score(raw_total: pd.Series, ref_max: float) -> pd.Series:
    return (100 * np.log1p(raw_total / EPS) / np.log1p(ref_max / EPS)).clip(0, 100)


def vulnerability(panel: pd.DataFrame, countries: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    p = panel[panel["year"].isin(years)].copy()
    comps = []
    for f, worse in VULN:
        r = p.groupby("year")[f].rank(pct=True)
        p[f"v_{f}"] = (r if worse else 1 - r) * 100
        comps.append(f"v_{f}")
    n = p[comps].notna().sum(axis=1)
    p["vulnerability"] = p[comps].mean(axis=1).where(n >= 2)
    p = p.merge(countries[["iso3", "region"]], on="iso3", how="left")
    reg_med = p.groupby(["region", "year"])["vulnerability"].transform("median")
    p["vuln_imputed"] = p["vulnerability"].isna()
    p["vulnerability"] = p["vulnerability"].fillna(reg_med).fillna(50.0)
    return p


def protection(hri: pd.DataFrame) -> pd.DataFrame:
    h = hri.copy()
    h["protection"] = sum(PROT[k] * h[k].fillna(False).astype(bool).astype(int) for k in PROT)
    return h


def _auc_cv(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> float:
    pred = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(X.iloc[tr], y[tr])
        pred[te] = m.predict_proba(X.iloc[te])[:, 1]
    return float(roc_auc_score(y, pred))


def hypothesis(scores: pd.DataFrame, panel: pd.DataFrame) -> dict:
    scores = scores.sort_values(["iso3", "year"]).copy()
    scores["exposure_change"] = scores.groupby("iso3")["exposure"].diff(2)
    rows = []
    for outcome, feat, rel, abs_min in (("homicide", "homicide_rate", 1.2, 1.0), ("hiv", "hiv_incidence", 1.2, 0.05)):
        raw = panel.pivot_table(index="iso3", columns="year", values=feat)
        # observed (not forward-filled) values only
        imp = panel.pivot_table(index="iso3", columns="year", values=f"{feat}_imputed")
        raw = raw.where(~imp.astype(bool))
        for r in scores.itertuples():
            y0 = r.year
            if r.iso3 not in raw.index or y0 not in raw.columns or pd.isna(raw.at[r.iso3, y0]):
                continue
            fut = [raw.at[r.iso3, y] for y in (y0 + 1, y0 + 2, y0 + 3) if y in raw.columns]
            fut = [v for v in fut if pd.notna(v)]
            if not fut:
                continue
            base = raw.at[r.iso3, y0]
            rise = int(max(fut) >= base * rel and max(fut) - base >= abs_min)
            rows.append({"outcome": outcome, "iso3": r.iso3, "year": y0, "y": rise, "exposure": r.exposure,
                         "exposure_change": r.exposure_change, "vulnerability": r.vulnerability,
                         "baseline": np.log1p(base)})
    d = pd.DataFrame(rows)
    res = _fit(d.drop(columns="exposure_change"), "exposure")
    chg = _fit(d.drop(columns="exposure").rename(columns={"exposure_change": "exposure"}), "exposure")
    c = res.get("combined", {})
    cc = chg.get("combined", {})
    supported = bool(c and c["lr_p_value"] < 0.05 and c["exposure_coef"] > 0)
    if c:
        direction = "raises" if c["exposure_coef"] > 0 else "lowers"
        stmt = (f"Route exposure {direction} the odds of a 20%+ rise in homicide or HIV incidence within 3 years "
                f"(odds ratio {c['exposure_odds_ratio_per_10pts']:.2f} per 10 exposure points, LR test "
                f"p = {c['lr_p_value']:.3g}, n = {c['n']}). Cross-validated AUC {c['auc_vulnerability_only']:.3f} "
                f"(vulnerability + baseline) vs {c['auc_with_exposure']:.3f} (+ exposure). "
                + ("The hypothesis is supported." if supported else "The hypothesis is not supported."))
        if cc:
            stmt += (f" Secondary test (2-year change in exposure, i.e. a route moving in): odds ratio "
                     f"{cc['exposure_odds_ratio_per_10pts']:.2f} per 10 points, p = {cc['lr_p_value']:.3g}.")
    else:
        stmt = "Not enough outcome data to test the hypothesis."
    return {
        "hypothesis": ("Route exposure at year t predicts a significant rise in homicide or HIV incidence within "
                       "3 years, beyond vulnerability and the baseline outcome level."),
        "outcome": "homicide rate or HIV incidence (15-49) up >= 20% (and >= 1 per 100k / 0.05 per 1,000) within 3 years",
        "n": c.get("n", 0), "auc_vulnerability_only": c.get("auc_vulnerability_only"),
        "auc_with_exposure": c.get("auc_with_exposure"), "exposure_coef": c.get("exposure_coef"),
        "lr_p_value": c.get("lr_p_value"), "supported": supported, "statement": stmt,
        "by_outcome": {k: v for k, v in res.items() if k != "combined"},
        "secondary_exposure_change": chg,
        "method": ("Nested logistic regressions (statsmodels), likelihood-ratio test for the exposure term; AUC from "
                   "5-fold cross-validation grouped by country. Observed (not forward-filled) World Bank outcomes. "
                   "Primary predictor: exposure level at t; secondary: change in exposure from t-2 to t."),
    }


def _logit(y: pd.Series, X: pd.DataFrame):
    """Newton first; fall back to L-BFGS when the Hessian is singular (e.g. quasi-separation)."""
    try:
        return sm.Logit(y, sm.add_constant(X)).fit(disp=0)
    except np.linalg.LinAlgError:
        return sm.Logit(y, sm.add_constant(X)).fit(method="lbfgs", disp=0, maxiter=500)


def _fit(d: pd.DataFrame, xname: str) -> dict:
    res = {}
    for name, g in list(d.groupby("outcome")) + [("combined", d)]:
        g = g.dropna()
        if g["y"].nunique() < 2 or len(g) < 50:
            continue
        Xv = g[["vulnerability", "baseline"]].assign(hiv=(g["outcome"] == "hiv").astype(int)) if name == "combined" \
            else g[["vulnerability", "baseline"]]
        Xe = Xv.assign(exposure=g["exposure"])
        m0 = _logit(g["y"], Xv)
        m1 = _logit(g["y"], Xe)
        lr = 2 * (m1.llf - m0.llf)
        res[name] = {"n": int(len(g)), "positives": int(g["y"].sum()),
                     "auc_vulnerability_only": round(_auc_cv(Xv, g["y"].values, g["iso3"].values), 4),
                     "auc_with_exposure": round(_auc_cv(Xe, g["y"].values, g["iso3"].values), 4),
                     "exposure_coef": round(float(m1.params["exposure"]), 5),
                     "exposure_odds_ratio_per_10pts": round(float(np.exp(10 * m1.params["exposure"])), 4),
                     "lr_p_value": round(float(chi2.sf(lr, 1)), 6)}
    return res


def run(refresh: bool = False) -> dict:
    countries = db.read_table("countries")
    panel = db.read_table("wb_panel")
    edges = db.read_table("edges")
    preds = db.read_table("predictions")
    from .edges import production
    prod = production(db.read_table("cultivation"))
    hri = protection(db.read_table("harm_reduction"))
    obs_years = sorted(edges["year"].unique().tolist())
    fut_year = int(preds["year"].iloc[0])
    years = obs_years + [fut_year]

    pe = preds.rename(columns={"kg_pred": "kg"})[["drug", "from_iso3", "to_iso3", "kg"]].assign(year=fut_year)
    fut_prod = prod[prod["year"] == fut_year]
    if fut_prod.empty:
        fut_prod = prod[prod["year"] == prod["year"].max()].assign(year=fut_year)
    prod_all = pd.concat([prod[prod["year"] < fut_year], fut_prod], ignore_index=True)
    all_edges = pd.concat([edges[["drug", "from_iso3", "to_iso3", "kg", "year"]], pe], ignore_index=True)
    ex = exposure_raw(all_edges, prod_all, years)
    tot = ex.groupby(["iso3", "year"])["raw"].sum()
    ref_max = float(tot.max())

    grid = pd.MultiIndex.from_product([countries["iso3"], years], names=["iso3", "year"]).to_frame(index=False)
    grid["exposure_raw"] = tot.reindex(pd.MultiIndex.from_frame(grid[["iso3", "year"]])).fillna(0).values
    grid["exposure"] = exposure_score(grid["exposure_raw"], ref_max).round(1)

    # vulnerability: forecast year uses the latest panel year
    pyears = [min(y, int(panel["year"].max())) for y in years]
    vul = vulnerability(panel, countries, sorted(set(pyears)))
    vmap = vul.set_index(["iso3", "year"])
    grid["panel_year"] = [min(y, int(panel["year"].max())) for y in grid["year"]]
    grid["vulnerability"] = vmap["vulnerability"].reindex(pd.MultiIndex.from_frame(
        grid[["iso3", "panel_year"]])).fillna(50).round(1).values
    grid["protection"] = grid["iso3"].map(hri.set_index("iso3")["protection"]).fillna(0).astype(float)
    grid["score"] = (WEIGHTS["exposure"] * grid["exposure"] + WEIGHTS["vulnerability"] * grid["vulnerability"]
                     + WEIGHTS["protection"] * (100 - grid["protection"])).round(1)
    grid["rank"] = grid.groupby("year")["score"].rank(ascending=False, method="first").astype(int)
    grid["tier"] = grid["score"].map(tier)
    grid = grid.sort_values(["iso3", "year"])
    grid["delta_1y"] = grid.groupby("iso3")["score"].diff().round(1)
    by_drug = ex.pivot_table(index=["iso3", "year"], columns="drug", values="raw", aggfunc="sum").fillna(0)
    top = by_drug.idxmax(axis=1).where(by_drug.max(axis=1) > 0)
    grid["top_drug"] = top.reindex(pd.MultiIndex.from_frame(grid[["iso3", "year"]])).values

    # details (JSON) for country profiles
    exi = ex.set_index(["iso3", "year", "drug"])
    vuli = vul.set_index(["iso3", "year"])
    hrii = hri.set_index("iso3")
    details = []
    for r in grid.itertuples():
        exp_by_drug, exp_det = {}, []
        for d in config.DRUGS:
            if (r.iso3, r.year, d) in exi.index:
                x = exi.loc[(r.iso3, r.year, d)]
                pts = float(exposure_score(pd.Series([x["raw"]]), ref_max).iloc[0])
                exp_by_drug[d] = round(float(x["raw"] / max(r.exposure_raw, 1e-12)) * 100, 1) if r.exposure_raw else 0.0
                for comp, lbl in (("inbound", "Inbound + transit"), ("outbound", "Outbound"),
                                  ("production", "Domestic production")):
                    if x[comp] > 0:
                        exp_det.append({"feature": f"{comp}_{d}", "label": f"{lbl} {d} (kg est.)",
                                        "value": round(float(x[comp]), 1),
                                        "contribution": round(pts * float(x[{"inbound": "s_in", "outbound": "s_out",
                                                                               "production": "s_prod"}[comp]] /
                                                                           max(x["s_in"] + x["s_out"] + x["s_prod"],
                                                                               1e-12)), 2)})
        vul_det = []
        if (r.iso3, r.panel_year) in vuli.index:
            v = vuli.loc[(r.iso3, r.panel_year)]
            present = [f for f, _ in VULN if pd.notna(v.get(f"v_{f}"))]
            for f in present:
                ind = BY_FEATURE[f]
                val = v.get(f)
                vul_det.append({"feature": f, "label": ind.label, "value": None if pd.isna(val) else round(float(val), 3),
                                "contribution": round(float(v[f"v_{f}"]) / len(present), 2),
                                "provenance": {"code": ind.code, "source_id": ind.source_id,
                                               "year": int(r.panel_year),
                                               "value": None if pd.isna(val) else round(float(val), 3),
                                               "imputed": bool(v.get(f"{f}_imputed"))}})
        prot_det = []
        if r.iso3 in hrii.index:
            h = hrii.loc[r.iso3]
            for k, w in PROT.items():
                val = h.get(k)
                prot_det.append({"feature": k, "label": PROT_LABELS[k],
                                 "value": None if val is None or pd.isna(val) else int(bool(val)),
                                 "contribution": float(w if val is True else 0)})
        details.append(json.dumps({"exposure_by_drug": exp_by_drug, "exposure_detail": exp_det,
                                   "vulnerability_detail": vul_det, "protection_detail": prot_det}))
    grid["details"] = details
    grid["is_forecast"] = grid["year"] == fut_year
    db.write_table("risk_scores", grid)

    obs = grid[~grid["is_forecast"]]
    hyp = hypothesis(obs[obs["year"] <= int(panel["year"].max()) - 1], panel)
    hyp["weights"] = WEIGHTS
    update_metrics("spillover", hyp)
    latest = grid[grid["year"] == fut_year].nsmallest(10, "rank")[["iso3", "score", "exposure", "vulnerability",
                                                                  "protection", "tier"]]
    log.info("risk_scores: %d country-years; tiers %s\nTop %d:\n%s", len(grid),
             grid[grid["year"] == fut_year]["tier"].value_counts().to_dict(), fut_year, latest.to_string(index=False))
    log.info("hypothesis: %s", hyp["statement"])
    return {"rows": len(grid), "hypothesis_supported": hyp["supported"]}
