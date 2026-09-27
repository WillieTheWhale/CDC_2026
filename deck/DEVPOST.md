<!-- AI-assisted: written with Claude Code (Anthropic) and maintained with Codex (OpenAI). See docs/AI_USAGE.md. -->
# Devpost submission copy

Paste-ready. Numbers here track `README.md`; re-check them against the status table before submitting.

---

## Project name
**TRACE**

## Tagline
A Bloomberg terminal for the global drug trade that predicts where the next drug crisis will hit,
before it arrives.

## Track
Graduate — World Bank Indicators API. Theme: AI for Social Good.

---

## Inspiration

Afghanistan grew about 80% of the world's illicit opium. In April 2022 a single decree cut its production
by 95% in one season — 6,200 tonnes in 2022, 333 tonnes in 2023, with cultivation falling from 233,000
hectares to 10,800. The drugs did not stop. Some of the shortfall was absorbed by an estimated 12,000
tonnes of stockpile, Myanmar became the leading producer again, and more than 9,000 hectares of poppy
appeared in Pakistan's Balochistan — a province no UN survey covers. For three years, nobody could tell
the countries on the new routes that they were coming.

That gap is the problem. Trafficking routes shift constantly. In our cross-sectional analysis, surveyed
route countries have 3.5× the cocaine-use prevalence of off-route countries and 2.5× the homicide rate of
destination-only countries. Those are associations, not causal effects: our prospective spillover test did
not find added homicide or HIV signal once vulnerability was controlled. Every dataset that tells you a
drug crisis arrived is two to five years old: homicide data through
2023, HIV incidence through 2024, poverty through 2022, drug prevalence through 2021. Harm reduction
arrives after the crisis. Every time.

## What it does

TRACE maps trafficking corridors for cocaine, heroin, methamphetamine and cannabis, forecasts how those
corridors will shift next year, and scores every country on its risk of a new local drug crisis —
combining World Bank development data with UN seizure, price and cultivation data.

Core screens, keyboard-driven:

- **Route Map** — every modeled year with smooth playback, observed vs predicted routes, and a clearly labelled estimated local-flow overlay
- **Country Screen** — routes in and out, prices, World Bank vulnerability profile, harm-reduction coverage, risk drivers
- **Spillover Risk Board** — every country ranked across Exposure, Vulnerability and Protection
- **Shock Simulator** — a plain-English scenario rewires the network and updates risk scores
- **Live Wire** — a GDELT newswire classified in real time, with anomalies flagged against the model
- **Market Board** — wholesale and retail price tickers with year-over-year change
- **Health Evidence** — service coverage, legal context and dated public-health indicators with source provenance
- **People** — a source-bounded research appendix for documented public claims, event histories and connections

It is a harm-reduction and early-warning instrument, not an enforcement one. By design it never shows
where enforcement is weakest or which routes are least watched. The People appendix is not an input to
forecasting or risk scores: it exposes only cited public records, preserves allegation/charge/conviction
distinctions, keeps geography at country level, and contains no live positions, private addresses or travel
patterns.

## How we built it

**Data.** The World Bank Indicators API is called programmatically with explicit source IDs — 24 indicators
across 217 economies, with history from 1960–2025, nulls preserved and provenance recorded per value in a
checksum-verified, read-only SQLite v2 archive. That layer does five
distinct jobs: market mass for the gravity model, route friction, vulnerability, validation targets, and
detection-bias control. External sources (all cited): UNODC Individual Drug Seizures (~2.3M cases), the
UNODC World Drug Report statistical annex, the Global Organized Crime Index, Harm Reduction International's
Global State of Harm Reduction, CEPII GeoDist, and GDELT. Live evidence endpoints trace research and
derived market values to formulas, exact input rows, source editions and original URLs; they also expose
source-published price/purity rows, PWID estimates, treatment contacts and overdose records with their
method and status labels. Route edges likewise carry evidence IDs and identify kilograms as allocated
seizure scale.

**Models.** A PPML gravity model as the published baseline, and a LightGBM hurdle model as the main
predictor — a classifier for whether a corridor is active next year, a regressor for volume if it is.
SHAP gives per-corridor drivers in plain language. Every corridor carries a 0–100 confidence score built
from six independent signals.

**AI at runtime.** Reflex is TRACE's open, locally trained System One model: a 70M-parameter NLI
cross-encoder that scores each supplied option, answers seven typed questions per article in one batch,
trains with log-loss, and temperature-scales Choice, Score and Noul separately. It copies no TypeSafe code
or weights; it implements the published Jev interface and calibration objective. Live Wire uses Jev when
a key is configured, otherwise Reflex when local trained weights are present, and otherwise a clearly
identified keyword fallback. Reflex v0.2's downloadable release includes its weights and evaluation, with
0.020 in-distribution calibration error. It is now also tested on 92 real published headlines it never
trained on, where grounding guardrails hold every country and drug to what the text actually says: 0
hallucinated entities out of 107, and calibration error 0.052 on the events that reach the wire. Over all
rows confidence remains a routing signal rather than a field-validated probability. A confident event on a corridor the
forecast gave under 10% probability is flagged as an anomaly: the model announcing its own misses.

**Stack.** Python 3.11, uv, SQLite, pandas, statsmodels, LightGBM, scikit-learn, SHAP, FastAPI with a
WebSocket Live Wire, APScheduler. Next.js, TypeScript, Tailwind, deck.gl `ArcLayer` over MapLibre, cmdk,
Recharts. Contract-first development: an OpenAPI spec and fixtures were committed before any backend logic
so the frontend could build in parallel.

## Challenges we ran into

- **The public UNODC seizure release has no route fields.** Departure, transit and destination are
  restricted-tier. Rather than invent routes, we built a cited corridor table from UNODC's own published
  route maps and reports, with a citation key per row, and estimated yearly volumes by seizure-anchored
  allocation over real node totals. The route-evidence API now separates directly reported pairs from
  interpreted corridors and regional narrative context, so a judge can open the publication behind an edge.
- **Governance indicator codes had been renamed.** The familiar `CC.EST` family is archive-only now; the
  live codes are `GOV_WGI_*.EST` on source 3. We found that by verifying every code against the live API
  rather than trusting documentation.
- **GDELT rate-limited us.** The poller keeps GDELT's spacing and retries; while unavailable, the Live Wire
  replays a labelled sample set, marked as fallback in `/api/meta` and never counted as evidence.
- **Seizures measure enforcement, not trafficking.** Addressed with detection-bias controls and the
  multi-signal confidence score rather than ignored.
- **The first city-scale arrow rule did not validate as a predictor.** Against 203 cited US drug-route
  pairs, neither the 2011 nor classifier-driven 2025 arrows beat a population baseline. Squaring the
  entry-city distance penalty raised 2011 cannabis state AUC from 0.76 to 0.87 versus a 0.79 population
  baseline, but other gains remain uncertain and some anchors remain implausible. We therefore keep the
  layer labelled estimated and not observed, exclude it from forecasts and risk scores, and show the cited
  US routes as a separate documentary layer.

## Accomplishments we're proud of

- A held-out backtest: the hurdle model reaches 0.88 AUC on corridor activation against 0.58 for the
  standard economics baseline, trained through 2019 and evaluated on 2020–2024.
- The Afghan ban test: trained through 2021 and shocked with the cultivation collapse, the model called 9 of
  13 corridor shifts in the right direction and predicted a Southeast Asia share of 14% against the 13% the
  later data showed. We report that as model output rather than as a measured route shift, and the product
  says so on the screen: its Afghan view shows published cultivation observations and states plainly that
  they do not establish a measured bilateral shift.
- A prespecified test, published with its uncertainty: 0.0195 homicides per 100,000 per unit rise in log
  seizures, 95% interval [-0.213, 0.252], p = 0.869, over 1,428 country-years in 144 countries with country
  and seizure-year fixed effects and clustered standard errors. The interval spans zero and the product
  displays it that way.
- An open Reflex v0.2 release with downloadable weights and full evaluation, shipping as a torch-free ONNX
  runtime with 100% top-choice parity against PyTorch. On the 100-headline synthetic development set it
  reaches 98% event-type accuracy and 82% destination accuracy, versus 80% and 52% for the keyword mock.
  We then built the honest benchmark rather than promising it: 92 real published headlines, hand-labelled
  from the text, each carrying its URL, never trained or tuned on. Grounded, Reflex reads the drug right
  97.8% of the time, the origin 95.7% and the destination 84.8%, and hallucinates nothing at all - 0
  invented entities out of 107, against 5 of 102 without the guardrails and 19 of 88 for the keyword mock.
- Publishing a result that went against us. Our core spillover hypothesis was not supported: route exposure
  alone does not predict later rises in homicide or HIV once vulnerability is controlled for. We committed
  that finding the day we found it. It is why the risk score has three columns, and it is an argument for
  harm reduction over interdiction.

## What we learned

That the hard part of an early-warning system is not the model, it is being honest about evidence. Most of
our engineering time went into confidence scoring, detection-bias controls, and documenting limitations —
and that is what makes the forecasts worth acting on.

## What's next for TRACE

Externally validate Reflex on a larger, independently labelled set; add a fentanyl module; ACLED conflict events;
wastewater and EUDA price
feeds; weekly retraining and per-country alert subscriptions; and a deployment with a harm-reduction
partner in a single transit corridor, measured against real service placement.

---

## Built with
`python` · `sqlite` · `pandas` · `statsmodels` · `lightgbm` · `scikit-learn` · `shap` · `fastapi` ·
`websockets` · `apscheduler` · `pytorch` · `transformers` · `nextjs` · `typescript` · `tailwind` · `deck.gl` ·
`maplibre` · `recharts` ·
`world-bank-api` · `unodc` · `gdelt` · `reflex` · `jev` · `typesafe-ai` · `anthropic` · `uv`

## Data sources (all cited)
World Bank Indicators API (WDI source 2, WGI source 3) · UNODC Drugs Monitoring Platform, Individual Drug
Seizures · UNODC World Drug Report statistical annex · UNODC crop surveys (Afghanistan, Myanmar) · Global
Organized Crime Index (GI-TOC) · Harm Reduction International, Global State editions 2008–2024 · CEPII
GeoDist · GDELT DOC 2.0 · Natural Earth. Full table with codes, freshness and links:
[`docs/DATA_SOURCES.md`](../docs/DATA_SOURCES.md).

## AI usage disclosure (CDC requirement)
Generative AI was used throughout and is cited in two places: an `AI-assisted` header comment in every file
it wrote or substantially edited, and a dated log in [`docs/AI_USAGE.md`](../docs/AI_USAGE.md). Runtime AI:
Reflex (TRACE's open model, built from a DeBERTaV3 NLI cross-encoder) for newswire classification when local
weights are present; Jev and a transparent keyword classifier remain fallbacks; Claude (Anthropic) supports
country briefings
and scenario parsing. Statistical methods cited: Santos Silva & Tenreyro (2006) for PPML; Ke et al. (2017)
for LightGBM; Lundberg & Lee (2017) for SHAP.
