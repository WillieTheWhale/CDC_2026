# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Structural shock propagation used by the simulator and the Afghan ban test.

A shock edits node inputs for a base year, then the seizure-anchored allocation is re-run:
- cultivation (iso3, multiplier m): production and producer seizures x m. Downstream transit countries
  lose inflow; their volumes are cascaded (2 rounds, elasticity 0.7). Destinations with other suppliers
  substitute automatically because inflow weights are proportional to supplier mass.
- legalization (iso3, drug, value): illicit inflow of that drug into iso3 x (1 - 0.5 value); regulation flag set.
- customs_efficiency (iso3, delta on the 1-5 LPI scale): throughput and route attractiveness through iso3
  x exp(-0.35 delta); the difference is displaced to the upstream origins' other destinations (the
  "balloon effect", shown so neighbours can prepare prevention services).
The hurdle model then forecasts next year from the shocked state.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import db
from . import edges as E

CASCADE_ROUNDS = 2
CASCADE_ELASTICITY = 0.7
LEGAL_INFLOW_CUT = 0.5
CUSTOMS_ROUTE_ELASTICITY = 0.35


@dataclass
class Shock:
    type: str
    iso3: str
    value: float
    drug: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Shock:
        return cls(type=d["type"], iso3=d["iso3"].upper(), value=float(d["value"]), drug=d.get("drug"))

    def to_dict(self) -> dict:
        return {"type": self.type, "iso3": self.iso3, "drug": self.drug, "value": self.value}


@dataclass
class Context:
    edges: pd.DataFrame
    seiz: pd.DataFrame
    prod: pd.DataFrame
    dist: pd.DataFrame
    cands: pd.DataFrame = field(init=False)

    def __post_init__(self):
        self.cands = self.edges[["drug", "from_iso3", "to_iso3", "documented"]].drop_duplicates(
            ["drug", "from_iso3", "to_iso3"]).reset_index(drop=True)

    @classmethod
    def load(cls) -> Context:
        return cls(edges=db.read_table("edges"), seiz=db.read_table("seizures_country"),
                   prod=E.production(db.read_table("cultivation")), dist=db.read_table("model_distances"))


def resolve_drug(shock: Shock, prod: pd.DataFrame) -> list[str]:
    if shock.drug:
        return [shock.drug]
    if shock.type == "legalization":
        return ["cannabis"]
    grown = prod[(prod["iso3"] == shock.iso3) & (prod["prod_kg"] > 0)]["drug"].unique().tolist()
    return grown or ["cocaine", "heroin", "meth", "cannabis"]


def scenario_year(ctx: Context, year: int, shocks: list[Shock]) -> pd.DataFrame:
    """Return the edge rows for `year` after applying shocks (same columns as the allocation output).

    Node factors: a shocked node's throughput changes by factor f (cultivation: m; customs: exp(-0.35 delta);
    legalization: 1 - 0.5 v). Downstream non-producer nodes get f_j = (sum_i inflow_share_ij * f_i) ** 0.7
    (0.7 = partial substitution from other suppliers), propagated CASCADE_ROUNDS hops along the base network.
    Customs shifts also displace the lost (or gained) volume to the upstream origins' other destinations.
    """
    S = ctx.seiz[ctx.seiz["year"] == year].copy()
    P = ctx.prod[ctx.prod["year"] == year].copy()
    base = E.allocate(ctx.cands, S, P, ctx.dist, [year])
    Sk = S.set_index(["iso3", "drug"])["kg"].astype(float).copy()
    Pk = P.set_index(["iso3", "drug"])["prod_kg"].astype(float).copy() if len(P) else pd.Series(dtype=float)
    factor: dict[tuple[str, str], float] = {}
    prior_mult: dict[str, float] = {}
    displaced: dict[tuple[str, str], float] = {}

    for sh in shocks:
        for d in resolve_drug(sh, ctx.prod):
            if sh.type == "cultivation":
                f = max(float(sh.value), 0.0)
            elif sh.type == "legalization":
                f = max(1 - LEGAL_INFLOW_CUT * float(sh.value), 0.0)
            elif sh.type == "customs_efficiency":
                f = float(np.exp(-CUSTOMS_ROUTE_ELASTICITY * float(sh.value)))
            else:
                continue
            factor[(sh.iso3, d)] = factor.get((sh.iso3, d), 1.0) * f
            if sh.type == "customs_efficiency":
                into = base[(base["to_iso3"] == sh.iso3) & (base["drug"] == d)]
                for r in into.itertuples():
                    lost = r.kg * (1 - f)
                    alt = base[(base["from_iso3"] == r.from_iso3) & (base["drug"] == d)
                               & (base["to_iso3"] != sh.iso3) & (base["kg"] > 0)]
                    if alt["kg"].sum() > 0:
                        for a in alt.itertuples():
                            k = (a.to_iso3, d)
                            displaced[k] = displaced.get(k, 0.0) + lost * a.kg / alt["kg"].sum()
        if sh.type == "customs_efficiency":
            prior_mult[sh.iso3] = prior_mult.get(sh.iso3, 1.0) * float(np.exp(-CUSTOMS_ROUTE_ELASTICITY * sh.value))

    shocked = set(factor)
    producers = set(Pk[Pk > 0].index) if len(Pk) else set()
    inflow = base.groupby(["to_iso3", "drug"])["kg"].transform("sum").replace(0, np.nan)
    base = base.assign(in_share=(base["kg"] / inflow).fillna(0))
    for _ in range(CASCADE_ROUNDS):
        f_node = dict(factor)
        for (j, d), g in base[base["kg"] > 0].groupby(["to_iso3", "drug"]):
            if (j, d) in shocked or (j, d) in producers:
                continue
            fi = sum(r.in_share * factor.get((r.from_iso3, d), 1.0) for r in g.itertuples())
            if abs(fi - 1.0) > 1e-9:
                f_node[(j, d)] = max(fi, 0.0) ** CASCADE_ELASTICITY
        factor = f_node

    for k, f in factor.items():
        if k in Sk.index:
            Sk.loc[k] *= f
        if k in Pk.index and k in shocked:
            Pk.loc[k] *= f
    for k, v in displaced.items():
        if k in Sk.index:
            Sk.loc[k] = max(Sk.loc[k] + v, 0.0)
    S2 = Sk.reset_index().assign(year=year)
    P2 = Pk.reset_index().assign(year=year) if len(Pk) else P
    return E.allocate(ctx.cands, S2, P2, ctx.dist, [year], prior_mult or None)


def apply_to_edges(ctx: Context, year: int, shocks: list[Shock]) -> pd.DataFrame:
    """Full edges table with `year` replaced by the shocked allocation (share/active recomputed)."""
    sc = scenario_year(ctx, year, shocks)
    base = ctx.edges[ctx.edges["year"] == year].set_index(["drug", "from_iso3", "to_iso3"])
    sc = sc.set_index(["drug", "from_iso3", "to_iso3"])
    out = base.copy()
    for c in ("kg", "S_from", "S_to", "P_from"):
        out[c] = sc[c].reindex(out.index).fillna(0).values
    out = out.reset_index()
    # shares and scaling use the BASELINE totals so absolute declines stay declines (no share inflation)
    tot = out["drug"].map(base.groupby(level="drug")["kg"].sum()).replace(0, np.nan)
    out["share"] = (out["kg"] / tot).fillna(0)
    mx = out["drug"].map(base.groupby(level="drug")["kg"].max()).replace(0, np.nan)
    out["volume_norm"] = (np.log1p(out["kg"]) / np.log1p(mx)).fillna(0).clip(0, 1)
    out["active"] = out["share"] >= E.ACTIVE_SHARE
    return pd.concat([ctx.edges[ctx.edges["year"] != year], out], ignore_index=True)


def feature_overrides(X: pd.DataFrame, shocks: list[Shock]) -> pd.DataFrame:
    """Apply shock effects that live in features rather than node volumes."""
    X = X.copy()
    for sh in shocks:
        if sh.type == "customs_efficiency":
            for side in ("from", "to"):
                m = X[f"{side}_iso3"] == sh.iso3
                X.loc[m, f"lpi_customs_{side}"] = X.loc[m, f"lpi_customs_{side}"].fillna(2.8) + sh.value
        if sh.type == "legalization":
            for side in ("from", "to"):
                m = (X[f"{side}_iso3"] == sh.iso3) & (X["drug"] == (sh.drug or "cannabis"))
                X.loc[m, f"legal_{side}"] = int(sh.value >= 0.5)
    return X
