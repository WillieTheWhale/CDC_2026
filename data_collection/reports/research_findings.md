<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Retrospective TRACE evidence findings

These are observed-source descriptions, not prospective forecasts or causal estimates. Every derived row is clickable through `research_values` → `research_value_inputs` to the source table key, URL, source publication year, observation year, aggregate input and original source-row values. Definitions and formula versions are in `research_metric_definitions`.

## Preselected questions

- UNODC annex edition revisions: 1,642 matched country/drug/year rows with at least two editions and positive oldest kilograms; 456 change and median absolute published revision is 0% across all pairs (0.0767% among changed pairs). This is a revision to reports, not inferred flow.
- Price-comparison feasibility: 2,128 of 3,221 country/drug/year/source keys have positive prices at both levels, but the coarse drug labels can combine different product forms. The candidate ratios are rejected and absent from research_values. Use the 449 exact-product ratios in `market_derived`, which also links to raw workbook cells.
- Cocaine seizure / next-year general-population homicide model sample: 1,428 country-years across 144 countries, seizure years 2006–2022. Run `research_model.py` for the fixed-effects coefficient and uncertainty.

## Interpretation and data limits

The seizure measure is country of seizure, not a route or estimated trade volume. A higher seizure total can reflect enforcement or reporting changes. The homicide outcome covers the general population and is not attributed to drugs. Both sources were retrieved in 2026, and the latest UNODC edition may revise earlier years. Thus the association is retrospective, ecological and noncausal. It cannot validate a live early-warning model.

UNODC price category names may pool forms with different purity. Historical nominal USD/g can move with exchange rates and inflation. Even the stricter market-shard ratio does not resolve all sampling differences. Missing rows are not zero observations.

## Reproduce

```sh
backend/.venv/bin/python data_collection/research.py
backend/.venv/bin/python data_collection/research_model.py
```
