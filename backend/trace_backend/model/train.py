# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T5: PPML gravity baseline, LightGBM hurdle, SHAP drivers, 2019 backtest, Afghan ban test.

Outputs: DuckDB `predictions`, `afghan_ban`; models in data/processed/models/; data/processed/metrics.json.

Metric definitions (test = target years 2020-2024, models trained on target years <= 2019):
- AUC: P(edge active next year) vs realised activity, all candidate corridors.
- Spearman: predicted vs realised next-year kg over corridors active in t or t+1.
- precision@20: per test year, of the 20 established corridors (active, share >= 0.2%) with the highest
  predicted growth, the share that actually grew by >= 10%; averaged over years.
"""
from __future__ import annotations

import json
import logging

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from .. import config, db
from . import features as F
from . import shocks as SH
from .gravity import GravityPPML
from .hurdle import HurdleModel

log = logging.getLogger(__name__)
MODELS = config.PROCESSED / "models"
METRICS = config.PROCESSED / "metrics.json"
SEA = {"MMR", "LAO", "THA"}


def update_metrics(section: str, payload) -> dict:
    config.ensure_dirs()
    m = json.loads(METRICS.read_text(encoding="utf-8")) if METRICS.exists() else {}
    m[section] = payload
    m["model_version"] = config.MODEL_VERSION
    METRICS.write_text(json.dumps(m, indent=2, default=float), encoding="utf-8")
    return m


def _r(x, n=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def scores(df: pd.DataFrame, pred_kg: np.ndarray, proba: np.ndarray | None) -> dict:
    y_act = df["active_next"].astype(int).values
    auc = roc_auc_score(y_act, proba if proba is not None else pred_kg) if len(set(y_act)) > 1 else np.nan
    uni = (df["lag_active"] == 1) | (df["active_next"] == 1)
    sp = spearmanr(pred_kg[uni.values], df.loc[uni, "kg_next"]).statistic if uni.sum() > 2 else np.nan
    precs = []
    for _, g in df.assign(pred=pred_kg).groupby("year"):
        est = g[(g["lag_active"] == 1) & (g["lag_share"] >= 0.002) & (g["kg"] > 0)]
        if len(est) < 20:
            continue
        growth = np.log1p(est["pred"]) - np.log1p(est["kg"])
        top = est.loc[growth.nlargest(20).index]
        precs.append(float((top["kg_next"] > top["kg"] * 1.10).mean()))
    return {"auc": _r(auc), "spearman": _r(sp), "precision_at_20": _r(np.mean(precs) if precs else np.nan),
            "n": int(len(df))}


def backtest(X: pd.DataFrame) -> tuple[dict, HurdleModel, pd.DataFrame]:
    lab = X.dropna(subset=["kg_next"])
    train = lab[lab["year"] + 1 <= config.BACKTEST_TRAIN_THROUGH]
    test = lab[lab["year"] + 1 > config.BACKTEST_TRAIN_THROUGH].reset_index(drop=True)
    hm = HurdleModel().fit(train)
    grav = GravityPPML().fit(train)
    p_h, k_h = hm.predict_proba(test), hm.predict_kg(test)
    k_g = grav.predict_kg(test)
    out = {"train_through": config.BACKTEST_TRAIN_THROUGH,
           "test_years": sorted((test["year"] + 1).astype(int).unique().tolist()),
           "train_rows": int(len(train)),
           "hurdle": scores(test, k_h, p_h), "gravity_baseline": scores(test, k_g, None),
           "persistence_baseline": scores(test, test["kg"].values, test["lag_log_kg"].values),
           "per_drug": {}, "per_year": {}}
    for d, g in test.groupby("drug"):
        i = g.index.values
        out["per_drug"][d] = scores(g, k_h[i], p_h[i])
    for y, g in test.groupby("year"):
        i = g.index.values
        out["per_year"][str(int(y) + 1)] = scores(g, k_h[i], p_h[i])
    out["top_features"] = hm.top_features(test.sample(min(len(test), 3000), random_state=0))
    out["gravity_coefficients"] = grav.summary()
    return out, hm, test


def afghan_ban(X_all: pd.DataFrame, ctx: SH.Context, inputs: dict) -> dict:
    """Train through 2021, inject a 95% cut in Afghan opium at the 2022 state, forecast 2023."""
    lab = X_all.dropna(subset=["kg_next"])
    hm = HurdleModel().fit(lab[lab["year"] + 1 <= config.AFGHAN_TRAIN_THROUGH])
    shock = SH.Shock("cultivation", "AFG", 0.05, "heroin")
    ref = 2022
    shocked_edges = SH.apply_to_edges(ctx, ref, [shock])
    Xs = F.build(shocked_edges, inputs)
    Xs = Xs[(Xs["year"] == ref) & (Xs["drug"] == "heroin")].reset_index(drop=True)
    Xb = X_all[(X_all["year"] == ref) & (X_all["drug"] == "heroin")].reset_index(drop=True)
    Xs["pred_kg"] = hm.predict_kg(Xs)
    Xb["pred_kg"] = hm.predict_kg(Xb)
    e = ctx.edges[ctx.edges["drug"] == "heroin"]
    act = e[e["year"] == ref + 1].set_index(["from_iso3", "to_iso3"])["kg"]
    before = e[e["year"] == ref].set_index(["from_iso3", "to_iso3"])["kg"]
    key = ["from_iso3", "to_iso3"]
    res = Xs[key + ["pred_kg"]].merge(Xb[key + ["pred_kg"]], on=key, suffixes=("", "_noshock"))
    res["before"] = before.reindex(pd.MultiIndex.from_frame(res[key])).values
    res["actual"] = act.reindex(pd.MultiIndex.from_frame(res[key])).values
    top = pd.concat([res.nlargest(10, "before"), res[res["from_iso3"].isin(SEA)].nlargest(5, "before")])
    top = top.drop_duplicates(key).reset_index(drop=True)
    mx = max(before.max(), 1.0)
    norm = lambda v: float(np.clip(np.log1p(max(v, 0)) / np.log1p(mx), 0, 1))  # noqa: E731
    top["dir_pred"] = np.sign(top["pred_kg"] - top["before"])
    top["dir_act"] = np.sign(top["actual"] - top["before"])
    top["correct"] = top["dir_pred"] == top["dir_act"]
    sp = spearmanr(np.log1p(top["pred_kg"]) - np.log1p(top["before"]),
                   np.log1p(top["actual"]) - np.log1p(top["before"])).statistic

    def sea_share(frame, col):
        tot = frame[col].sum()
        return float(frame.loc[frame["from_iso3"].isin(SEA), col].sum() / tot) if tot else None

    share_before, share_pred, share_act = sea_share(res, "before"), sea_share(res, "pred_kg"), sea_share(res, "actual")
    share_noshock = sea_share(res, "pred_kg_noshock")
    cult = db.read_table("cultivation")
    series = []
    for iso3, lbl in (("AFG", "Afghanistan"), ("MMR", "Myanmar")):
        c = cult[(cult["iso3"] == iso3) & (cult["crop"] == "opium_poppy") & (cult["year"] >= 2015)]
        series.append({"id": f"{iso3.lower()}_cultivation", "label": f"{lbl} opium poppy cultivation", "unit": "ha",
                       "points": [{"year": int(y), "value": _r(v, 0)} for y, v in zip(c["year"], c["hectares"],
                                                                                    strict=True)]})
        series.append({"id": f"{iso3.lower()}_production", "label": f"{lbl} potential opium production",
                       "unit": "tonnes",
                       "points": [{"year": int(y), "value": _r(v, 0)} for y, v in zip(c["year"], c["production_t"],
                                                                                    strict=True)]})
    sh_pts = []
    for y, g in e[e["year"] >= 2015].groupby("year"):
        tot = g["kg"].sum()
        sh_pts.append({"year": int(y), "value": _r(g.loc[g["from_iso3"].isin(SEA), "kg"].sum() / tot if tot else None)})
    series.append({"id": "sea_share", "label": "Share of heroin corridor volume leaving Myanmar, Laos, Thailand",
                   "unit": "share", "points": sh_pts})
    n_ok, n = int(top["correct"].sum()), len(top)
    verdict = (f"Trained only on data through {config.AFGHAN_TRAIN_THROUGH}, the model given a 95% cut in Afghan opium "
               f"predicted the direction of change on {n_ok} of {n} major heroin corridors for {ref + 1}. "
               f"The Southeast Asian share of heroin corridor volume was {share_before:.0%} in {ref}; the model "
               f"predicted {share_pred:.0%} (vs {share_noshock:.0%} without the shock) and data later showed "
               f"{share_act:.0%}.")
    out = {
        "title": "Afghanistan 2022 opium ban",
        "summary": ("Train the route model on data through 2021, inject the 2023 collapse in Afghan opium "
                    "cultivation (x0.05) at the 2022 state, forecast 2023 heroin corridors, and compare with "
                    "what 2023 data showed."),
        "ban_year": 2022, "train_through": config.AFGHAN_TRAIN_THROUGH, "shock": shock.to_dict(), "series": series,
        "edges": [{"from": r.from_iso3, "to": r.to_iso3, "drug": "heroin", "before": round(norm(r.before), 4),
                   "predicted": round(norm(r.pred_kg), 4),
                   "actual": None if np.isnan(r.actual) else round(norm(r.actual), 4),
                   "direction_correct": bool(r.correct), "before_kg": _r(r.before, 1), "predicted_kg": _r(r.pred_kg, 1),
                   "actual_kg": _r(r.actual, 1)} for r in top.itertuples()],
        "metrics": {"direction_accuracy": _r(n_ok / n if n else None), "spearman": _r(sp), "n_edges": n,
                    "sea_share_before": _r(share_before), "sea_share_predicted": _r(share_pred),
                    "sea_share_predicted_no_shock": _r(share_noshock), "sea_share_actual": _r(share_act)},
        "verdict": verdict,
    }
    return out


def predict_next(X: pd.DataFrame, hm: HurdleModel, ctx: SH.Context) -> pd.DataFrame:
    last = int(X["year"].max())
    cur = X[X["year"] == last].reset_index(drop=True)
    cur["probability"] = hm.predict_proba(cur)
    cur["kg_pred"] = hm.predict_kg(cur)
    cur["drivers"] = [json.dumps(d) for d in hm.drivers(cur)]
    cur["year_pred"] = last + 1
    mx = cur.groupby("drug")["kg_pred"].transform("max").replace(0, np.nan)
    cur["volume_norm_pred"] = (np.log1p(cur["kg_pred"]) / np.log1p(mx)).fillna(0).clip(0, 1)
    tot = cur.groupby("drug")["kg_pred"].transform("sum").replace(0, np.nan)
    cur["share_pred"] = (cur["kg_pred"] / tot).fillna(0)
    cur["change_pct_pred"] = ((cur["kg_pred"] / cur["kg"].replace(0, np.nan) - 1) * 100).round(1)
    cur["is_emerging_pred"] = (cur["probability"] >= 0.5) & (cur["share_pred"] >= 0.005) & (
        (cur["lag_active"] == 0) | (cur["change_pct_pred"] >= 50))
    conf = ctx.edges[ctx.edges["year"] == last].set_index(["drug", "from_iso3", "to_iso3"])
    idx = pd.MultiIndex.from_frame(cur[["drug", "from_iso3", "to_iso3"]])
    for c in ["confidence", "sig_seizures", "sig_price_gradient", "sig_oc_index", "sig_news", "sig_cultivation",
              "sig_documented"]:
        cur[c] = conf[c].reindex(idx).values
    cols = ["drug", "from_iso3", "to_iso3", "year_pred", "probability", "kg_pred", "volume_norm_pred", "share_pred",
            "change_pct_pred", "is_emerging_pred", "drivers", "kg", "confidence", "sig_seizures",
            "sig_price_gradient", "sig_oc_index", "sig_news", "sig_cultivation", "sig_documented"]
    return cur[cols].rename(columns={"year_pred": "year", "kg": "kg_base"})


def run(refresh: bool = False) -> dict:
    MODELS.mkdir(parents=True, exist_ok=True)
    ctx = SH.Context.load()
    inputs = F.load_inputs()
    X = F.build(ctx.edges, inputs)

    bt, hm_bt, _ = backtest(X)
    log.info("backtest hurdle %s | gravity %s | persistence %s", bt["hurdle"], bt["gravity_baseline"],
             bt["persistence_baseline"])

    ab = afghan_ban(X, ctx, inputs)
    log.info("afghan ban: %s", ab["metrics"])
    db.write_table("afghan_ban", pd.DataFrame([{"json": json.dumps(ab)}]))

    lab = X.dropna(subset=["kg_next"])
    hm = HurdleModel().fit(lab)
    grav = GravityPPML().fit(lab)
    joblib.dump(hm, MODELS / "hurdle.joblib")
    joblib.dump(grav, MODELS / "gravity.joblib")
    preds = predict_next(X, hm, ctx)
    db.write_table("predictions", preds)
    log.info("predictions for %d: %d corridors, %d active (p>=0.5), %d emerging", int(preds["year"].iloc[0]),
             len(preds), int((preds["probability"] >= 0.5).sum()), int(preds["is_emerging_pred"].sum()))

    update_metrics("backtest", bt)
    update_metrics("afghan_ban", {k: ab["metrics"][k] for k in ("direction_accuracy", "spearman")} | {
        "verdict": ab["verdict"], **ab["metrics"]})
    return {"backtest": bt["hurdle"], "afghan": ab["metrics"]}
