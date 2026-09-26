# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Feature matrix for route prediction: one row per (drug, from, to, year t), target = year t+1.

World Bank features (gravity mass, governance, logistics, conflict) come from `wb_panel`, joined for both
ends of the corridor. `lpi_customs_*` is a detection-bias control only: it is used for fitting but never
shown as a driver or exposed by the API (design boundary).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import db

WB_BOTH = ["gdp", "population", "gdp_pc_ppp", "rule_of_law", "control_corruption", "gov_effectiveness",
           "political_stability", "port_teu", "air_passengers", "trade_gdp", "lpi_overall", "lpi_customs",
           "battle_deaths"]
LOG_FEATS = {"gdp", "population", "port_teu", "air_passengers", "battle_deaths"}
HIDDEN_DRIVERS = {"lpi_customs_from", "lpi_customs_to"}  # detection-bias controls, never displayed
LAG_FEATS = {"lag_log_kg", "lag2_log_kg", "lag_share", "lag_active", "log_growth"}

LABELS = {
    "lag_log_kg": "Last year's volume on this corridor", "lag2_log_kg": "Volume two years ago",
    "lag_share": "Corridor share of the drug's flows", "lag_active": "Corridor active last year",
    "log_growth": "Recent growth on the corridor", "log_dist": "Distance", "contig": "Shared border",
    "comlang": "Common official language", "documented": "Documented UNODC/EUDA corridor",
    "log_seiz_from": "Seizures at origin", "log_seiz_to": "Seizures at destination",
    "seiz_growth_from": "Seizure growth at origin", "seiz_growth_to": "Seizure growth at destination",
    "log_prod_from": "Cultivation / production upstream", "price_gap": "Price gap destination vs origin",
    "oc_from": "Drug market score at origin (OC Index)", "oc_to": "Drug market score at destination (OC Index)",
    "legal_to": "Destination cannabis regulation", "legal_from": "Origin cannabis regulation",
    "drug_code": "Drug",
}
_WB_LABELS = {"gdp": "market size (GDP)", "population": "population", "gdp_pc_ppp": "income per capita",
              "rule_of_law": "governance (rule of law)", "control_corruption": "governance (control of corruption)",
              "gov_effectiveness": "government effectiveness", "political_stability": "political stability",
              "port_teu": "container port capacity", "air_passengers": "air passenger traffic",
              "trade_gdp": "trade openness", "lpi_overall": "logistics performance", "lpi_customs": "customs (control)",
              "battle_deaths": "armed conflict"}
for _f, _l in _WB_LABELS.items():
    LABELS[f"{_f}_from"] = f"Origin {_l}"
    LABELS[f"{_f}_to"] = f"Destination {_l}"

DRUG_CODE = {"cocaine": 0, "heroin": 1, "meth": 2, "cannabis": 3}


def feature_columns() -> list[str]:
    base = ["drug_code", "lag_log_kg", "lag2_log_kg", "lag_share", "lag_active", "log_growth", "log_dist", "contig",
            "comlang", "documented", "log_seiz_from", "log_seiz_to", "seiz_growth_from", "seiz_growth_to",
            "log_prod_from", "price_gap", "oc_from", "oc_to", "legal_to", "legal_from"]
    return base + [f"{f}_{s}" for f in WB_BOTH for s in ("from", "to")]


def gravity_columns() -> list[str]:
    return ["log_gdp_from", "log_gdp_to", "log_pop_from", "log_pop_to", "log_dist", "contig", "price_gap0",
            "price_missing"]


def load_inputs() -> dict[str, pd.DataFrame]:
    return {"panel": db.read_table("wb_panel"), "dist": db.read_table("model_distances"),
            "reg": db.read_table("model_cannabis_regulation")}


def build(edges: pd.DataFrame, inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Features at year t and targets at t+1 (NaN when t+1 is not in `edges`)."""
    e = edges.sort_values(["drug", "from_iso3", "to_iso3", "year"]).copy()
    key = ["drug", "from_iso3", "to_iso3"]
    g = e.groupby(key)
    e["lag_log_kg"] = np.log1p(e["kg"])
    e["lag2_log_kg"] = np.log1p(g["kg"].shift(1))
    e["lag_share"] = e["share"]
    e["lag_active"] = e["active"].astype(int)
    e["log_growth"] = e["lag_log_kg"] - e["lag2_log_kg"]
    e["log_seiz_from"] = np.log1p(e["S_from"])
    e["log_seiz_to"] = np.log1p(e["S_to"])
    e["seiz_growth_from"] = e["log_seiz_from"] - np.log1p(g["S_from"].shift(1))
    e["seiz_growth_to"] = e["log_seiz_to"] - np.log1p(g["S_to"].shift(1))
    e["log_prod_from"] = np.log1p(e["P_from"])
    e["price_gap"] = np.log(e["price_to"] / e["price_from"])
    e["log_dist"] = np.log(e["dist"])
    e["documented"] = e["documented"].astype(int)
    e["drug_code"] = e["drug"].map(DRUG_CODE)
    # targets
    e["kg_next"] = g["kg"].shift(-1)
    e["active_next"] = g["active"].shift(-1)
    e["year_next"] = g["year"].shift(-1)
    e.loc[e["year_next"] != e["year"] + 1, ["kg_next", "active_next"]] = np.nan

    d = inputs["dist"].set_index(["from_iso3", "to_iso3"])["comlang_off"]
    e["comlang"] = d.reindex(pd.MultiIndex.from_arrays([e["from_iso3"], e["to_iso3"]])).fillna(0).values

    p = inputs["panel"].set_index(["iso3", "year"])
    for side, col in (("from", "from_iso3"), ("to", "to_iso3")):
        idx = pd.MultiIndex.from_arrays([e[col], e["year"]])
        for f in WB_BOTH:
            v = p[f].reindex(idx).values if f in p else np.nan
            e[f"{f}_{side}"] = np.log1p(v) if f in LOG_FEATS else v

    reg = inputs["reg"].dropna(subset=["year_effective"]).set_index("iso3")["year_effective"]
    for side, col in (("from", "from_iso3"), ("to", "to_iso3")):
        start = e[col].map(reg)
        e[f"legal_{side}"] = ((e["drug"] == "cannabis") & start.notna() & (e["year"] >= start)).astype(int)

    # gravity baseline terms (PPML)
    e["log_gdp_from"] = e["gdp_from"].fillna(e["gdp_from"].median())
    e["log_gdp_to"] = e["gdp_to"].fillna(e["gdp_to"].median())
    e["log_pop_from"] = e["population_from"].fillna(e["population_from"].median())
    e["log_pop_to"] = e["population_to"].fillna(e["population_to"].median())
    e["price_missing"] = e["price_gap"].isna().astype(int)
    e["price_gap0"] = e["price_gap"].fillna(0)
    return e.reset_index(drop=True)


def label(feature: str) -> str:
    return LABELS.get(feature, feature.replace("_", " "))
