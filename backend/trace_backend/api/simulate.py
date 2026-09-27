# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T9: POST /api/simulate (shock simulator) and POST /api/command (command bar).

The simulator shocks the base-year state (structural propagation, model/shocks.py), reruns the LightGBM
hurdle model for the next year, and propagates the change to spillover exposure and risk scores.
Needs the pipeline outputs (DuckDB + models); everything else in the API runs from exported JSON.
"""
from __future__ import annotations

from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config, db
from ..model import features as F
from ..model import shocks as SH
from ..model import spillover as SP
from ..model.edges import production
from ..model.scenario import BLOCK_MSG, BLOCKED, parse_command, parse_llm, parse_rules

router = APIRouter()
TYPES = {"cultivation", "legalization", "customs_efficiency"}


class ShockIn(BaseModel):
    type: str
    iso3: str
    value: float
    drug: str | None = None


class SimulateIn(BaseModel):
    scenario: str | None = None
    shocks: list[ShockIn] | None = None
    year: int | None = None


class CommandIn(BaseModel):
    text: str


def _unprocessable(msg: str):
    raise HTTPException(status_code=422, detail={"code": "invalid_scenario", "message": msg})


class Engine:
    def __init__(self):
        self.ctx = SH.Context.load()
        self.inputs = F.load_inputs()
        self.model = joblib.load(config.PROCESSED / "models" / "hurdle.joblib")
        self.prod = production(db.read_table("cultivation"))
        self.risk = db.read_table("risk_scores")
        self.names = db.read_table("countries").set_index("iso3")["name"].to_dict()
        self.X = F.build(self.ctx.edges, self.inputs)
        # the saved risk board is the source of truth: same scaling, same edges/production world as spillover.run
        meta = db.read_table("risk_meta").iloc[0]
        self.ref_max = float(meta["ref_max"])
        self.world_edges, self.world_prod, _ = SP.exposure_world(
            self.ctx.edges, db.read_table("predictions"), self.prod, int(meta["forecast_year"]))
        years = sorted(self.ctx.edges["year"].unique())
        risk_years = set(self.risk["year"].astype(int))
        self.years = [int(y) + 1 for y in years if int(y) + 1 in risk_years]  # target years we can simulate
        self._base: dict[int, pd.DataFrame] = {}

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        X["p"] = self.model.predict_proba(X)
        X["kg_pred"] = self.model.predict_kg(X)
        return X[["drug", "from_iso3", "to_iso3", "p", "kg_pred", "kg"]]

    def baseline(self, base_year: int) -> pd.DataFrame:
        if base_year not in self._base:
            self._base[base_year] = self.predict(self.X[self.X["year"] == base_year])
        return self._base[base_year]

    def raw(self, pred: pd.DataFrame, target: int, prod: pd.DataFrame,
            totals: tuple[pd.Series, pd.Series]) -> pd.Series:
        """Raw exposure per iso3 for predicted edges, measured against the saved board's denominators."""
        e = pred.drop(columns="kg").rename(columns={"kg_pred": "kg"})[["drug", "from_iso3", "to_iso3", "kg"]].assign(
            year=target)
        return SP.exposure_raw(e, prod, [target], totals).groupby("iso3")["raw"].sum()

    def risk_deltas(self, target: int, raw_b: pd.Series, raw_s: pd.Series) -> pd.DataFrame:
        """Baseline = the saved risk board for `target`; scenario = the saved raw exposure moved by the modelled
        change (x raw_s / raw_b; + raw_s where the modelled baseline is 0), scored with spillover's own scaling and
        formula. For the forecast year raw_b equals the saved raw, so this is raw_s; no change => identical score."""
        r = self.risk[self.risk["year"] == target].set_index("iso3")
        b, s = raw_b.reindex(r.index).fillna(0), raw_s.reindex(r.index).fillna(0)
        saved = r["exposure_raw"]
        scen = (saved * s / b.where(b > 0)).fillna(saved + s - b).clip(lower=0)
        exp_s = SP.exposure_score(scen, self.ref_max).round(1)
        out = pd.DataFrame({"score_b": r["score"], "rank_b": r["rank"],
                            "score_s": SP.risk_score(exp_s, r["vulnerability"], r["protection"])})
        out["rank_s"] = out["score_s"].rank(ascending=False, method="first").astype(int)
        return out

    def run(self, shocks: list[SH.Shock], target: int | None) -> dict:
        target = target or max(self.years)
        if target not in self.years:
            _unprocessable(f"year must be one of {self.years[0]}-{self.years[-1]}")
        base_year = target - 1
        base = self.baseline(base_year)
        edges = SH.apply_to_edges(self.ctx, base_year, shocks)
        sub = edges[edges["year"].isin([base_year - 1, base_year])]
        Xs = F.build(sub, self.inputs)
        Xs = SH.feature_overrides(Xs[Xs["year"] == base_year], shocks)
        scen = self.predict(Xs)
        key = ["drug", "from_iso3", "to_iso3"]
        m = base.merge(scen, on=key, suffixes=("_b", "_s"))
        mx = m.groupby("drug")["kg_pred_b"].transform("max").replace(0, np.nan)
        norm = lambda v: (np.log1p(v.clip(lower=0)) / np.log1p(mx)).fillna(0).clip(0, 1)  # noqa: E731
        m["vb"], m["vs"] = norm(m["kg_pred_b"]), norm(m["kg_pred_s"])
        m["delta_pct"] = ((m["kg_pred_s"] / m["kg_pred_b"].replace(0, np.nan) - 1) * 100).fillna(0)
        m["abs_kg"] = (m["kg_pred_s"] - m["kg_pred_b"]).abs()
        ch = m[(m["delta_pct"].abs() > 1) & (m[["kg_pred_b", "kg_pred_s"]].max(axis=1) > 1)]
        ch = ch.sort_values("abs_kg", ascending=False).head(60)
        edges_changed = [{"from": r.from_iso3, "to": r.to_iso3, "drug": r.drug,
                          "baseline_volume_norm": round(float(r.vb), 4), "scenario_volume_norm": round(float(r.vs), 4),
                          "baseline_kg": round(float(r.kg_pred_b), 1), "scenario_kg": round(float(r.kg_pred_s), 1),
                          "baseline_probability": round(float(r.p_b), 4), "scenario_probability": round(float(r.p_s), 4),
                          "delta_pct": round(float(r.delta_pct), 1)} for r in ch.itertuples()]

        # production and denominators exactly as spillover.run used them for the target year
        prod_b = self.world_prod[self.world_prod["year"] == target]
        prod_s = prod_b.copy()
        for sh in shocks:
            if sh.type == "cultivation":
                for d in SH.resolve_drug(sh, self.prod):
                    prod_s.loc[(prod_s["iso3"] == sh.iso3) & (prod_s["drug"] == d), "prod_kg"] *= max(sh.value, 0)
        tot = SP.exposure_totals(self.world_edges, self.world_prod, target)
        rd = self.risk_deltas(target, self.raw(base, target, prod_b, tot), self.raw(scen, target, prod_s, tot))
        rd = rd.dropna()
        rd["delta"] = (rd["score_s"] - rd["score_b"]).round(1)
        rd = rd[rd["delta"].abs() >= 0.1]
        rd = rd.loc[rd["delta"].abs().sort_values(ascending=False).index].head(40)
        risk_deltas = [{"iso3": i, "name": self.names.get(i, i), "baseline_score": float(r.score_b),
                        "scenario_score": float(r.score_s), "delta": float(r.delta), "baseline_rank": int(r.rank_b),
                        "scenario_rank": int(r.rank_s)} for i, r in rd.iterrows()]
        return {"year": target, "edges_changed": edges_changed, "risk_deltas": risk_deltas,
                "summary": summarize(shocks, m, risk_deltas, self.names)}


def summarize(shocks, m: pd.DataFrame, rd: list[dict], names: dict) -> str:
    parts = []
    for sh in shocks:
        nm = names.get(sh.iso3, sh.iso3)
        if sh.type == "cultivation":
            parts.append(f"{nm} illicit crop output x{sh.value:g}")
        elif sh.type == "legalization":
            parts.append(f"{nm} {'regulates' if sh.value >= 0.5 else 're-criminalises'} {sh.drug or 'cannabis'}")
        else:
            parts.append(f"{nm} customs efficiency {sh.value:+g}")
    txt = "Scenario: " + "; ".join(parts) + "."
    for d, g in m.groupby("drug"):
        b, s = g["kg_pred_b"].sum(), g["kg_pred_s"].sum()
        if b > 0 and abs(s / b - 1) > 0.01:
            txt += f" Total {d} corridor volume {(s / b - 1) * 100:+.0f}%."
    down = m[m["kg_pred_s"] < m["kg_pred_b"]].nlargest(1, "abs_kg")
    up = m[m["kg_pred_s"] > m["kg_pred_b"]].nlargest(1, "abs_kg")
    if len(down):
        r = down.iloc[0]
        txt += f" Largest drop: {r.drug} {r.from_iso3}->{r.to_iso3} ({r.delta_pct:+.0f}%)."
    if len(up):
        r = up.iloc[0]
        txt += f" Largest gain: {r.drug} {r.from_iso3}->{r.to_iso3} ({r.delta_pct:+.0f}%)."
    rise = [x for x in rd if x["delta"] > 0][:3]
    if rise:
        txt += " Spillover risk rises most in " + ", ".join(x["name"] for x in rise) + "; prevention services there first."
    return txt


@lru_cache(maxsize=1)
def engine() -> Engine:
    return Engine()


def validate_shocks(raw: list[dict]) -> list[SH.Shock]:
    from .app import store
    valid = set(store().country_index)
    out = []
    for s in raw:
        sh = SH.Shock.from_dict(s)
        if sh.type not in TYPES:
            _unprocessable(f"unknown shock type {sh.type}")
        if sh.iso3 not in valid:
            _unprocessable(f"unknown country {sh.iso3}")
        if sh.drug not in (None, *config.DRUGS):
            _unprocessable(f"unknown drug {sh.drug}")
        if sh.type == "cultivation" and not 0 <= sh.value <= 10:
            _unprocessable("cultivation multiplier must be between 0 and 10")
        if sh.type == "legalization" and not 0 <= sh.value <= 1:
            _unprocessable("legalization value must be 0 or 1")
        if sh.type == "customs_efficiency" and not -4 <= sh.value <= 4:
            _unprocessable("customs delta must be between -4 and 4")
        out.append(sh)
    return out


@router.post("/api/simulate")
def simulate(body: SimulateIn):
    from .app import envelope
    if body.scenario and BLOCKED.search(body.scenario):
        _unprocessable(BLOCK_MSG)
    if body.shocks:
        raw, parsed_by = [s.model_dump() for s in body.shocks], "structured"
    elif body.scenario:
        raw, parsed_by = parse_rules(body.scenario), "rules"
        if not raw:
            raw, parsed_by = parse_llm(body.scenario), "llm"
    else:
        raw, parsed_by = [], "structured"
    if not raw:
        _unprocessable("Could not find a shock. Try 'Colombia cuts coca 50%', 'Mexico legalizes cannabis', "
                       "or 'SHOCK AFG CULTIVATION -95%'.")
    shocks = validate_shocks(raw)
    res = engine().run(shocks, body.year)
    warnings = ["Scenario effects are model estimates under documented assumptions, not forecasts of policy outcomes."]
    if any(s.type == "customs_efficiency" for s in shocks):
        warnings.append("Displacement is shown so neighbouring countries can prepare prevention and treatment "
                        "services; TRACE does not rank enforcement weakness.")
    data = {"scenario": body.scenario, "parsed_by": parsed_by, "shocks": [s.to_dict() for s in shocks], **res,
            "warnings": warnings}
    return envelope(data, "unodc_wdr_annex", "unodc_ids", "unodc_routes", "wb_wdi", "wb_wgi", "hri_gshr")


@router.post("/api/command")
def command(body: CommandIn):
    from .app import envelope
    return envelope(parse_command(body.text))
