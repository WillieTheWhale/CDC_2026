# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T4: route network `edges` (year, drug, from, to) with estimated volume and a 0-100 confidence score.

Method (see docs/BLOCKERS.md for why route fields are not observed directly):

1. Candidate corridors = documented corridors (corridors_seed, prior 1.0)
   + neighbour candidates: land-border pairs touching a seizure hub for that drug where both ends
   report seizures of the drug in at least 3 years (prior 0.15). The model can light these up.
2. Node volumes: S = seizures (kg, WDR annex 7.1 + calibrated IDS backcast);
   P = production at origin (coca ha x 7 kg/ha cocaine; opium tonnes / 10 heroin-equivalent).
3. Seizure-anchored gravity allocation per drug-year:
     inflow  F_in(i->j)  = S_j        * w(i->j) / sum_k w(k->j),  w = prior * sqrt(S_i + P_i) * decay(dist)
     outflow F_out(i->j) = (S_i+P_i)  * v(i->j) / sum_k v(i->k),  v = prior * sqrt(S_j) * decay(dist)
     kg(i->j) = min(F_in, F_out)   (both ends must support the flow; inflow <= S_j, outflow <= S_i+P_i)
   If a UNODC IDS release with route fields is present (`ids_hops`), observed hop kg replaces the estimate.
4. Confidence = 30 seizures + 20 price gradient + 20 OC Index + 10 news + 10 cultivation + 10 documented.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .. import config, db

log = logging.getLogger(__name__)
COCA_KG_PER_HA = 7.0          # approx. cocaine HCl per hectare of coca (UNODC GRC 2023 order of magnitude)
OPIUM_T_TO_HEROIN_KG = 100.0  # 1 t opium -> 100 kg heroin-equivalent (10:1)
OPIUM_KG_PER_HA = 25.0        # fallback yield where production is missing
DECAY_KM = {"cocaine": 9000.0, "heroin": 3500.0, "meth": 3500.0, "cannabis": 1500.0}
PRIOR_DOC, PRIOR_NEIGHBOUR = 1.0, 0.15
ACTIVE_SHARE = 0.001          # edge active when >= 0.1% of that drug's allocated volume in the year
N_HUBS = 25
OC_COL = {"cocaine": "cocaine", "heroin": "heroin", "meth": "synthetic", "cannabis": "cannabis"}
CROP = {"cocaine": "coca", "heroin": "opium_poppy"}
WEIGHTS = {"seizures": 30, "price_gradient": 20, "oc_index": 20, "news": 10, "cultivation": 10, "documented": 10}


def production(cult: pd.DataFrame) -> pd.DataFrame:
    """Production at origin in kg drug-equivalent, per iso3-year-drug."""
    c = cult.copy()
    coca = c[c["crop"] == "coca"].assign(drug="cocaine", prod_kg=lambda d: d["hectares"] * COCA_KG_PER_HA)
    op = c[c["crop"] == "opium_poppy"].copy()
    op["prod_kg"] = np.where(op["production_t"].notna(), op["production_t"] * OPIUM_T_TO_HEROIN_KG,
                             op["hectares"] * OPIUM_KG_PER_HA * OPIUM_T_TO_HEROIN_KG / 1000)
    op["drug"] = "heroin"
    out = pd.concat([coca, op])[["iso3", "year", "drug", "prod_kg"]].dropna()
    return out.groupby(["iso3", "year", "drug"], as_index=False)["prod_kg"].sum()


def candidates(seiz: pd.DataFrame, seed: pd.DataFrame, dist: pd.DataFrame) -> pd.DataFrame:
    rows = [seed.assign(documented=True)[["drug", "from_iso3", "to_iso3", "documented"]]]
    contig = dist[dist["contig"] == 1][["from_iso3", "to_iso3"]]
    for drug in config.DRUGS:
        s = seiz[seiz["drug"] == drug]
        years_present = s[s["kg"] > 0].groupby("iso3")["year"].nunique()
        present = set(years_present[years_present >= 3].index)
        hubs = set(s.groupby("iso3")["kg"].sum().nlargest(N_HUBS).index)
        c = contig[(contig["from_iso3"].isin(hubs) | contig["to_iso3"].isin(hubs))
                   & contig["from_iso3"].isin(present) & contig["to_iso3"].isin(present)]
        rows.append(c.assign(drug=drug, documented=False))
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values("documented", ascending=False).drop_duplicates(["drug", "from_iso3", "to_iso3"])
    # a neighbour candidate that reverses a documented corridor would split its volume: drop it
    doc_rev = set(zip(seed["drug"], seed["to_iso3"], seed["from_iso3"], strict=True))
    rev = [(d, f, t) in doc_rev for d, f, t in zip(out["drug"], out["from_iso3"], out["to_iso3"], strict=True)]
    out = out[out["documented"] | ~pd.Series(rev, index=out.index)]
    return out.reset_index(drop=True)


def allocate(cands: pd.DataFrame, seiz: pd.DataFrame, prod: pd.DataFrame, dist: pd.DataFrame,
             years: list[int], prior_mult: dict[str, float] | None = None) -> pd.DataFrame:
    """Seizure-anchored allocation. `prior_mult` (iso3 -> factor) rescales route attractiveness through a
    country (used by the shock simulator for customs shifts)."""
    d = dist.set_index(["from_iso3", "to_iso3"])[["dist", "contig"]]
    base = cands.join(d, on=["from_iso3", "to_iso3"])
    base["dist"] = base["dist"].fillna(base["dist"].median())
    base["contig"] = base["contig"].fillna(0)
    base["prior"] = np.where(base["documented"], PRIOR_DOC, PRIOR_NEIGHBOUR)
    if prior_mult:
        base["prior"] *= base["from_iso3"].map(prior_mult).fillna(1.0) * base["to_iso3"].map(prior_mult).fillna(1.0)
    L = base["drug"].map(DECAY_KM) * np.where(base["documented"], 3.0, 1.0)
    base["decay"] = np.exp(-base["dist"] / L) * (1 + 0.5 * base["contig"])
    S = seiz.set_index(["iso3", "year", "drug"])["kg"]
    P = prod.set_index(["iso3", "year", "drug"])["prod_kg"] if len(prod) else pd.Series(dtype=float)
    frames = []
    for y in years:
        e = base.copy()
        e["year"] = y
        ki = pd.MultiIndex.from_arrays([e["from_iso3"], e["year"], e["drug"]])
        kj = pd.MultiIndex.from_arrays([e["to_iso3"], e["year"], e["drug"]])
        e["S_from"] = S.reindex(ki).fillna(0).values
        e["S_to"] = S.reindex(kj).fillna(0).values
        e["P_from"] = P.reindex(ki).fillna(0).values if len(P) else 0.0
        e["M_from"] = e["S_from"] + e["P_from"]
        e["w_in"] = e["prior"] * np.sqrt(e["M_from"]) * e["decay"]
        e["w_out"] = e["prior"] * np.sqrt(e["S_to"]) * e["decay"]
        sin = e.groupby(["drug", "to_iso3"])["w_in"].transform("sum").replace(0, np.nan)
        sout = e.groupby(["drug", "from_iso3"])["w_out"].transform("sum").replace(0, np.nan)
        f_in = (e["S_to"] * e["w_in"] / sin).fillna(0)
        f_out = (e["M_from"] * e["w_out"] / sout).fillna(0)
        e["kg"] = np.minimum(f_in, f_out)
        frames.append(e)
    return pd.concat(frames, ignore_index=True)


def _nearest_by_year(df: pd.DataFrame, keys: list[str], value: str, years: list[int], max_gap: int = 4):
    """For each key and target year, the value from the nearest available year within max_gap."""
    out = []
    for k, g in df.groupby(keys):
        g = g.sort_values("year")
        ys, vs = g["year"].values, g[value].values
        for y in years:
            i = np.argmin(np.abs(ys - y))
            if abs(ys[i] - y) <= max_gap:
                out.append((*((k,) if not isinstance(k, tuple) else k), y, vs[i]))
    return pd.DataFrame(out, columns=[*keys, "year", value])


def signals(e: pd.DataFrame, prices: pd.DataFrame, oc: pd.DataFrame, cult: pd.DataFrame,
            years: list[int]) -> pd.DataFrame:
    e = e.copy()
    e["sig_seizures"] = (e["S_from"] + e["P_from"] > 0) & (e["S_to"] > 0)
    # price gradient: destination price above origin (same level preferred; wholesale origin vs retail dest ok)
    pr = prices.groupby(["iso3", "drug", "year"], as_index=False)["usd_g"].median()
    pn = _nearest_by_year(pr, ["iso3", "drug"], "usd_g", years).set_index(["iso3", "drug", "year"])["usd_g"]
    pf = pn.reindex(pd.MultiIndex.from_arrays([e["from_iso3"], e["drug"], e["year"]])).values
    pt = pn.reindex(pd.MultiIndex.from_arrays([e["to_iso3"], e["drug"], e["year"]])).values
    e["price_from"], e["price_to"] = pf, pt
    e["sig_price_gradient"] = np.nan_to_num(pt, nan=0) > np.nan_to_num(pf, nan=np.inf)
    # OC Index: drug market score >= 5 at both ends (nearest edition)
    ocl = oc.melt(id_vars=["iso3", "edition"], value_vars=list(set(OC_COL.values())), var_name="market",
                  value_name="score").rename(columns={"edition": "year"})
    on = _nearest_by_year(ocl.dropna(), ["iso3", "market"], "score", years, max_gap=10).set_index(
        ["iso3", "market", "year"])["score"]
    mk = e["drug"].map(OC_COL)
    e["oc_from"] = on.reindex(pd.MultiIndex.from_arrays([e["from_iso3"], mk, e["year"]])).values
    e["oc_to"] = on.reindex(pd.MultiIndex.from_arrays([e["to_iso3"], mk, e["year"]])).values
    e["sig_oc_index"] = (np.nan_to_num(e["oc_from"]) >= 5) & (np.nan_to_num(e["oc_to"]) >= 5)
    # cultivation at origin (cocaine: coca; heroin: opium poppy)
    cu = cult[cult["hectares"].fillna(0) > 0]
    grow = set(zip(cu["iso3"], cu["crop"], strict=True))
    e["sig_cultivation"] = [(f, CROP.get(d)) in grow for f, d in zip(e["from_iso3"], e["drug"], strict=True)]
    e["sig_news"] = False  # set from live events at export time
    e["sig_documented"] = e["documented"].astype(bool)
    e["confidence"] = sum(WEIGHTS[k] * e[f"sig_{k}"].astype(int) for k in WEIGHTS)
    return e


def finalize(e: pd.DataFrame) -> pd.DataFrame:
    e = e.sort_values(["drug", "from_iso3", "to_iso3", "year"]).copy()
    tot = e.groupby(["drug", "year"])["kg"].transform("sum").replace(0, np.nan)
    e["share"] = (e["kg"] / tot).fillna(0)
    mx = e.groupby(["drug", "year"])["kg"].transform("max").replace(0, np.nan)
    e["volume_norm"] = (np.log1p(e["kg"]) / np.log1p(mx)).fillna(0).clip(0, 1).round(4)
    e["active"] = e["share"] >= ACTIVE_SHARE
    g = e.groupby(["drug", "from_iso3", "to_iso3"])
    e["kg_prev"] = g["kg"].shift(1)
    e["active_prev2"] = g["active"].shift(2).fillna(False).astype(bool)
    e["kg_prev2"] = g["kg"].shift(2)
    e["change_pct"] = ((e["kg"] / e["kg_prev"] - 1) * 100).replace([np.inf, -np.inf], np.nan).round(1)
    growth2 = (e["kg"] / e["kg_prev2"]).replace([np.inf, -np.inf], np.nan)
    e["is_emerging"] = e["active"] & (e["share"] >= 0.005) & (~e["active_prev2"] | (growth2 >= 1.5))
    # first years have no history: not emerging by construction
    e.loc[e["year"] < config.ROUTE_YEAR_MIN + 2, "is_emerging"] = False
    return e


def run(refresh: bool = False) -> dict:
    seiz = db.read_table("seizures_country")
    cult = db.read_table("cultivation")
    seed = db.read_table("corridors_seed")
    dist = db.read_table("model_distances")
    prices = db.read_table("model_prices")
    oc = db.read_table("oc_index")
    years = list(range(config.ROUTE_YEAR_MIN, int(seiz["year"].max()) + 1))
    prod = production(cult)
    cands = candidates(seiz, seed, dist)
    e = allocate(cands, seiz, prod, dist, years)

    # observed hops from an IDS release with route fields replace the estimate where present
    if db.table_exists("ids_hops"):
        hops = db.read_table("ids_hops")
        if len(hops):
            h = hops.set_index(["drug", "from_iso3", "to_iso3", "year"])["kg"]
            obs = h.reindex(pd.MultiIndex.from_frame(e[["drug", "from_iso3", "to_iso3", "year"]])).values
            e["kg"] = np.where(~np.isnan(obs), obs, e["kg"])
            log.info("applied %d observed IDS hops", int((~np.isnan(obs)).sum()))

    e = signals(e, prices, oc, cult, years)
    e = finalize(e)
    # cases: IDS case count at destination apportioned by the edge's share of destination inflow
    if db.table_exists("seizures_ids"):
        ids = db.read_table("seizures_ids").set_index(["iso3", "year", "drug"])["cases"]
        dest_cases = ids.reindex(pd.MultiIndex.from_arrays([e["to_iso3"], e["year"], e["drug"]])).values
        inflow = e.groupby(["drug", "to_iso3", "year"])["kg"].transform("sum").replace(0, np.nan)
        e["cases"] = np.round(np.nan_to_num(dest_cases) * (e["kg"] / inflow).fillna(0)).astype(int)
    else:
        e["cases"] = 0
    cols = ["year", "drug", "from_iso3", "to_iso3", "kg", "cases", "share", "volume_norm", "active", "is_emerging",
            "change_pct", "documented", "dist", "contig", "S_from", "S_to", "P_from", "price_from", "price_to",
            "oc_from", "oc_to", "sig_seizures", "sig_price_gradient", "sig_oc_index", "sig_news", "sig_cultivation",
            "sig_documented", "confidence"]
    e = e[cols].reset_index(drop=True)
    db.write_table("edges", e)
    summ = e[e["active"]].groupby("drug").agg(active_edges=("kg", "size"), mean_conf=("confidence", "mean"))
    log.info("edges: %d rows, %d candidates; active per drug:\n%s", len(e), len(cands), summ)
    return {"rows": len(e), "candidates": len(cands), "years": [years[0], years[-1]]}
