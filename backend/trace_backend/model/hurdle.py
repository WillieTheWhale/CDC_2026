# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""LightGBM hurdle model (Ke et al. 2017): (a) P(edge active next year), (b) log volume if active.

Expected volume = P(active) * expm1(predicted log volume). SHAP (Lundberg and Lee 2017) explains each edge.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

from .features import HIDDEN_DRIVERS, LAG_FEATS, feature_columns, label

CLF_PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=20, subsample=0.8,
                  subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=7)
REG_PARAMS = dict(n_estimators=500, learning_rate=0.03, num_leaves=31, min_child_samples=15, subsample=0.8,
                  subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=7)


class HurdleModel:
    def __init__(self):
        self.cols = feature_columns()

    def fit(self, df: pd.DataFrame) -> HurdleModel:
        X = df[self.cols]
        self.clf = lgb.LGBMClassifier(**CLF_PARAMS).fit(X, df["active_next"].astype(int))
        act = df["active_next"].astype(bool)
        self.reg = lgb.LGBMRegressor(**REG_PARAMS).fit(X[act], np.log1p(df.loc[act, "kg_next"]))
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return self.clf.predict_proba(df[self.cols])[:, 1]

    def predict_log_kg(self, df: pd.DataFrame) -> np.ndarray:
        return self.reg.predict(df[self.cols])

    def predict_kg(self, df: pd.DataFrame) -> np.ndarray:
        return self.predict_proba(df) * np.expm1(np.clip(self.predict_log_kg(df), 0, None))

    # ------------------------------------------------------------------ SHAP
    def shap_values(self, df: pd.DataFrame) -> np.ndarray:
        """SHAP on the volume model (log-kg scale)."""
        ex = shap.TreeExplainer(self.reg)
        return np.asarray(ex.shap_values(df[self.cols]))

    def drivers(self, df: pd.DataFrame, k: int = 3) -> list[list[dict]]:
        """Top-k SHAP drivers per row beyond last year's volume; detection-bias controls never shown."""
        sv = self.shap_values(df)
        show = [i for i, c in enumerate(self.cols) if c not in LAG_FEATS | HIDDEN_DRIVERS | {"drug_code"}]
        out = []
        for row in sv:
            idx = sorted(show, key=lambda i: -abs(row[i]))[:k]
            out.append([{"feature": self.cols[i], "label": label(self.cols[i]), "contribution": round(float(row[i]), 4),
                         "direction": "up" if row[i] > 0 else "down"} for i in idx])
        return out

    def top_features(self, df: pd.DataFrame, k: int = 10) -> list[dict]:
        sv = np.abs(self.shap_values(df)).mean(axis=0)
        order = [i for i in np.argsort(-sv) if self.cols[i] not in HIDDEN_DRIVERS and self.cols[i] != "drug_code"]
        return [{"feature": self.cols[i], "label": label(self.cols[i]), "mean_abs_shap": round(float(sv[i]), 4)}
                for i in order[:k]]
