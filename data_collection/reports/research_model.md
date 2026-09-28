<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Cocaine seizures and next-year homicide: retrospective association

The preselected fixed-effects model estimated a coefficient of **0.01949 homicide deaths per 100,000** for a one-unit change in log(1 + reported cocaine-seizure kg). The country-clustered standard error is 0.1184; 95% interval [-0.2126, 0.2515], p = 0.8692. This is an association, not an effect of trafficking.

The complete-case sample has 1,428 country-years from 144 countries; seizure observation years 2006–2022, with homicide measured in the following year. The model includes a separate intercept for each country and seizure year. Standard errors are clustered by country; R² = 0.903. No missing outcome or seizure value is imputed. All matched observations and their source row links are in `research_regression_samples` → `research_values` → `research_value_inputs`.

## Interpretation

Retrospective, ecological, noncausal association. Seizures reflect enforcement/reporting, not trade volume or route exposure; homicide is general-population, not drug-attributed. Latest available UNODC annex editions and 2026 World Bank retrieval may revise past years.

The source editions were downloaded together in 2026. Some older seizure years come from later revised editions, so the model is not a point-in-time forecast test. Country and year effects remove fixed country differences and common annual shifts, but cannot account for time-varying enforcement, reporting, policy or confounding. We cannot infer that seizures cause a change in homicide, nor that the measured seizures describe an origin-to-destination route.

## Method

`homicide_per_100k ~ log1p_seizure_kg + C(iso3) + C(seizure_year)`

The model uses ordinary least squares with country and calendar-year indicator variables, and a country-clustered sandwich covariance matrix, implemented with statsmodels. There is one preselected predictor and one outcome; no model search or multiple-testing selection was used for this report.

Sources: [UNODC World Drug Report annex](https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html) and [World Bank Indicators API](https://api.worldbank.org/v2/indicator/VC.IHR.PSRC.P5?format=json). Exact request URLs and publication years are stored for each contributing input row.
