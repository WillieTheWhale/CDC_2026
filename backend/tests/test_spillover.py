# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Spillover risk components and the hypothesis test machinery."""
import numpy as np
import pandas as pd

from trace_backend.model import spillover as S


def test_tiers_are_ordered():
    assert S.tier(90) == "critical" and S.tier(60) == "high" and S.tier(50) == "elevated"
    assert S.tier(40) == "moderate" and S.tier(5) == "low"


def test_exposure_score_monotone_and_bounded():
    s = S.exposure_score(pd.Series([0, 1e-4, 1e-2, 0.5, 2.0]), ref_max=0.5)
    assert s.is_monotonic_increasing and s.iloc[0] == 0 and s.max() == 100


def test_protection_points():
    hri = pd.DataFrame([{"iso3": "A", "nsp": True, "oat": True, "naloxone": True, "dcr": True,
                         "prison_programs": True, "policy": True},
                        {"iso3": "B", "nsp": None, "oat": False, "naloxone": None, "dcr": None,
                         "prison_programs": None, "policy": None}])
    p = S.protection(hri).set_index("iso3")["protection"]
    assert p["A"] == 100 and p["B"] == 0


def test_hypothesis_detects_a_real_effect():
    rng = np.random.default_rng(1)
    rows, panel = [], []
    for i in range(160):
        iso3 = f"C{i:03d}"
        exp_ = rng.uniform(0, 100)
        for y in range(2010, 2021):
            rows.append({"iso3": iso3, "year": y, "exposure": exp_, "vulnerability": rng.uniform(0, 100)})
        h = 5.0
        for y in range(2010, 2021):
            # homicide trends up where exposure is high
            h *= 1 + (0.12 if exp_ > 60 else -0.02) + rng.normal(0, 0.05)
            panel.append({"iso3": iso3, "year": y, "homicide_rate": h, "homicide_rate_imputed": False,
                          "hiv_incidence": 0.1 + rng.uniform(0, 0.2), "hiv_incidence_imputed": False})
    res = S.hypothesis(pd.DataFrame(rows), pd.DataFrame(panel))
    assert res["supported"] and res["exposure_coef"] > 0
    assert res["auc_with_exposure"] > res["auc_vulnerability_only"]
