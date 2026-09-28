<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# Do TRACE's predictions agree with the cited US route data?

Checked 2026-09-27 with `uv run python backend/scripts/validate_us_routes.py` against the live API
(https://trace-api-six.vercel.app). Ground truth: the 203 cited route rows in
`backend/trace_backend/seed/us_routes.csv` (NDIC HIDTA Drug Market Analyses 2009/2011, AC HIDTA 2026).

## What was compared

| Predictor | What it is | Level it can answer |
|---|---|---|
| **EST-2011** | Route-based estimated local flows (the proximity/"follow the money" arrows) built from observed 2011 edges | city, state |
| **EST-2025** | The same arrow layer built from the **classifier's** predicted 2025 edges (LightGBM hurdle model behind Scenarios) | city, state |
| **Classifier** | Hurdle model P(edge active), country to country | country only |
| **POP** | Baseline: state (or city) population, Natural Earth `pop_max` | city, state |

The classifier's inputs are national (seizure lags, GDP, governance, distance between countries), so on
its own it gives every US city and state the same number. It can be tested per state only through
the arrow layer it drives (EST-2025). **Per county cannot be tested:** no TRACE output is at county
level, and the documents give counties only as origins (South Texas Table 1).

Scores per drug over the 48 contiguous states: AUC = how well the score separates states the documents
name as destinations from the rest (0.5 = chance); rho = Spearman with the number of documented
inbound rows; P@10 = share of the top-10 states that are documented destinations.

## Results

| Drug (documented dest. states) | EST-2011 AUC / rho / P@10 | EST-2025 (classifier) | POP baseline |
|---|---|---|---|
| Cannabis (31) | 0.76 / 0.31 / 0.8 | 0.78 / 0.34 / 0.8 | **0.79 / 0.39 / 0.9** |
| Cocaine (12) | 0.63 / 0.17 / 0.4 | 0.64 / 0.19 / 0.4 | **0.69 / 0.27 / 0.5** |
| Heroin (13) | 0.68 / 0.31 / 0.4 | 0.69 / 0.33 / 0.4 | **0.69 / 0.33 / 0.5** |
| Meth (14) | 0.62 / 0.19 / 0.4 | 0.64 / 0.22 / 0.5 | **0.71 / 0.34 / 0.5** |

City level (documented destination cities among the 201 US cities in the arrow layer), AUC:
cannabis 0.58 / 0.60 / **0.77**, cocaine 0.64 / 0.67 / **0.77**, meth 0.57 / 0.58 / **0.74**
(EST-2011 / EST-2025 / POP; heroin has only 2 documented cities).

Bootstrap 95% CI (2,000 resamples of states):
- EST-2025 minus EST-2011: cannabis [-0.00, +0.05], cocaine [-0.01, +0.03], heroin [-0.01, +0.04], meth [-0.02, +0.06].
- EST-2011 minus POP: cannabis [-0.14, +0.07], meth [-0.18, -0.02] (significantly worse).

## Findings

1. **Neither prediction beats population.** Both arrow layers reach 41-43 of 48 states, so "reached a
   documented state" is uninformative. Their ranking of states and cities is no better than city size,
   and is significantly worse for meth.
2. **Classifier vs route heuristic: the classifier-driven arrows are slightly better on every drug**
   (+0.01 to +0.03 AUC), but every confidence interval includes zero. The data cannot tell them apart.
3. **The largest disagreement is where US distribution starts.** The documents put most domestic
   origins on the Southwest border (cannabis 82% of rows from TX/AZ/NM/CA, heroin 62%, meth 52%,
   cocaine 45%) plus hubs such as St. Louis. The arrow layer lands every modeled inflow in **New York
   and Los Angeles** (cannabis: 29% of outgoing arrow strength from border states, New York 49%). The
   cause is the entry-city rule: it picks the richest city facing the route, and New York wins on money.
4. **At country level the classifier agrees with the documents.** The foreign origins the documents
   name are Mexico, Canada, Jamaica and Bahamas for cannabis, and Mexico for cocaine, heroin and meth.
   The classifier predicts Mexico (P 0.99), Canada (0.97) and Jamaica (0.76) for cannabis, and Mexico
   for the other drugs (0.89-0.99). It misses only the Bahamas, which is not a modeled edge. It also
   predicts South American cocaine origins the US reports do not name, because they describe the last
   hop before the US.

## Caveats

- **Old ground truth:** the documents describe 2008-2011, and EST-2025 is a 2025 prediction.
- **Skewed positives:** South Texas Table 1 contributes 71 cannabis rows, so Texas dominates the
  documented origins. Documented destinations follow where HIDTA reports exist, which also tracks
  population.
- **Missing rows:** only drug-specific sentences were extracted, so absence from the documents is not
  evidence of absence.

## Change adopted: squared distance in the entry-city rule (2026-09-27)

The entry city of each modeled edge now maximises money / (km + 300)^2 instead of money / (km + 300). This is
the same squared decay the arrow waves already use, and only route geometry changes (no enforcement variable).
It was tested A/B on identical inputs: live API edges plus World Bank GDP per capita PPP fetched on the day. The
local rebuild is close to, but not byte-identical with, the deployed layer.

| State AUC (2011 edges) | before | after | POP |
|---|---|---|---|
| Cannabis | 0.76 | **0.87** | 0.79 |
| Cocaine | 0.63 | 0.66 | 0.69 |
| Heroin | 0.68 | 0.73 | 0.69 |
| Meth | 0.62 | 0.71 | 0.71 |

- **City-level AUC (before → after):** cannabis 0.58 → 0.83, cocaine 0.63 → 0.66, heroin 0.66 → 0.77,
  meth 0.57 → 0.77.
- **Confidence:** the bootstrap 95% CI of the gain is [+0.05, +0.21] for cannabis. For the other drugs the gain
  is positive but the CI includes zero.
- **Global effect:** 15 of 170 edges worldwide change entry city in 2011.
  - Mexico to US: Los Angeles → Houston.
  - Jamaica to US: New York → Miami.
  - Netherlands to Germany: Frankfurt → Essen.
  - Tajikistan to Kyrgyzstan: Bishkek → Osh.
  - Myanmar to China: Shanghai → Chongqing.
  - Colombia to Ecuador: Guayaquil → Quito. This one looks worse, since Guayaquil is the known cocaine port.
- **Unchanged:** New York still receives the Canadian and Caribbean cannabis edges, so the border-share gap in
  finding 3 narrows only a little.
- **Deployment:** the deployed API picks this up on its next deploy (`backend/scripts/build_vercel.py`). The
  frontend snapshot files in `frontend/public/data/estimated/` are offline fallbacks; regenerate them with
  `uv run trace estimate-flows` where the archive is available.
