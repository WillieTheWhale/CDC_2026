# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Fit the preregistered retrospective fixed-effects association."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parent
SPEC = "homicide_per_100k ~ log1p_seizure_kg + C(iso3) + C(seizure_year)"
CAVEAT = (
    "Retrospective, ecological, noncausal association. Seizures reflect enforcement/reporting, "
    "not trade volume or route exposure; homicide is general-population, not drug-attributed. "
    "Latest available UNODC annex editions and 2026 World Bank retrieval may revise past years."
)


def run(db: Path, report: Path) -> dict:
    with sqlite3.connect(db) as con:
        df = pd.read_sql_query("SELECT iso3,seizure_year,log1p_seizure_kg,homicide_per_100k "
                               "FROM research_regression_samples", con)
        if len(df) < 100 or df.iso3.nunique() < 20:
            raise ValueError("Insufficient matched observations for fixed-effects model")
        fitted = smf.ols(SPEC, data=df).fit(cov_type="cluster", cov_kwds={"groups": df.iso3})
        key = "log1p_seizure_kg"
        interval = fitted.conf_int().loc[key]
        result = {
            "model_key": "cocaine_seizure_next_homicide_fe_v1",
            "specification": SPEC,
            "outcome": "World Bank general-population homicide rate in year t+1, per 100,000",
            "predictor": "log(1 + latest published UNODC cocaine seizure kg in year t)",
            "coefficient": float(fitted.params[key]),
            "standard_error": float(fitted.bse[key]),
            "p_value": float(fitted.pvalues[key]),
            "ci_low": float(interval.iloc[0]),
            "ci_high": float(interval.iloc[1]),
            "n": int(fitted.nobs),
            "countries": int(df.iso3.nunique()),
            "first_predictor_year": int(df.seizure_year.min()),
            "last_predictor_year": int(df.seizure_year.max()),
            "cluster_count": int(df.iso3.nunique()),
            "r_squared": float(fitted.rsquared),
            "caveat": CAVEAT,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        placeholders = ",".join("?" for _ in result)
        con.execute(f"INSERT OR REPLACE INTO research_model_results VALUES ({placeholders})",
                    tuple(result.values()))
        con.commit()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render(result))
    return result


def render(r: dict) -> str:
    return "\n".join([
        "<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->",
        "# Cocaine seizures and next-year homicide: retrospective association", "",
        "The preselected fixed-effects model estimated a coefficient of "
        f"**{r['coefficient']:.4g} homicide deaths per 100,000** for a one-unit change in "
        "log(1 + reported cocaine-seizure kg). The country-clustered standard error is "
        f"{r['standard_error']:.4g}; 95% interval [{r['ci_low']:.4g}, {r['ci_high']:.4g}], "
        f"p = {r['p_value']:.4g}. This is an association, not an effect of trafficking.", "",
        f"The complete-case sample has {r['n']:,} country-years from {r['countries']} countries; "
        f"seizure observation years {r['first_predictor_year']}–{r['last_predictor_year']}, "
        "with homicide measured in the following year. The model includes a separate intercept "
        "for each country and seizure year. Standard errors are clustered by country; "
        f"R² = {r['r_squared']:.3f}. No missing outcome or seizure value is imputed. "
        "All matched observations and their source row links are in `research_regression_samples` "
        "→ `research_values` → `research_value_inputs`.", "",
        "## Interpretation", "", r["caveat"], "",
        "The source editions were downloaded together in 2026. Some older seizure years come "
        "from later revised editions, so the model is not a point-in-time forecast test. "
        "Country and year effects remove fixed country differences and common annual shifts, "
        "but cannot account for time-varying enforcement, reporting, policy or confounding. "
        "We cannot infer that seizures cause a change in homicide, nor that the measured seizures "
        "describe an origin-to-destination route.", "",
        "## Method", "", f"`{r['specification']}`", "",
        "The model uses ordinary least squares with country and calendar-year indicator variables, "
        "and a country-clustered sandwich covariance matrix, implemented with statsmodels. "
        "There is one preselected predictor and one outcome; no model search or multiple-testing "
        "selection was used for this report.", "",
        "Sources: [UNODC World Drug Report annex](https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html) "
        "and [World Bank Indicators API](https://api.worldbank.org/v2/indicator/VC.IHR.PSRC.P5?format=json). "
        "Exact request URLs and publication years are stored for each contributing input row.", "",
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "work/research.sqlite")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/research_model.md")
    args = parser.parse_args()
    print(json.dumps(run(**vars(args)), indent=2))
