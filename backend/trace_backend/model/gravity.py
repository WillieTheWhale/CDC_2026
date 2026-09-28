# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""PPML gravity baseline (Santos Silva and Tenreyro 2006, "The Log of Gravity").

kg_{t+1} ~ Poisson( exp( b0 + drug FE + b1 log GDP_o + b2 log GDP_d + b3 log Pop_o + b4 log Pop_d
                         + b5 log dist + b6 contig + b7 price gap ) ), estimated by Poisson GLM with robust SEs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .features import gravity_columns

SCALE = 1000.0  # fit in tonnes for numerical stability


def _design(df: pd.DataFrame) -> pd.DataFrame:
    X = df[gravity_columns()].astype(float).copy()
    for d in ("heroin", "meth", "cannabis"):
        X[f"fe_{d}"] = (df["drug"] == d).astype(float)
    return sm.add_constant(X, has_constant="add")


class GravityPPML:
    def fit(self, df: pd.DataFrame) -> GravityPPML:
        y = df["kg_next"].values / SCALE
        self.res = sm.GLM(y, _design(df), family=sm.families.Poisson()).fit(cov_type="HC1", maxiter=200)
        return self

    def predict_kg(self, df: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.res.predict(_design(df))) * SCALE

    def summary(self) -> dict:
        return {k: {"coef": round(float(v), 4), "p": round(float(self.res.pvalues[k]), 4)}
                for k, v in self.res.params.items()}
