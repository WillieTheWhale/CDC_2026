<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
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

That gap is the problem. Trafficking routes shift constantly, and the countries they pass through inherit
the consequences — rising local use, violence, HIV — usually years before any official statistic records
it. Every dataset that tells you a drug crisis arrived is two to five years old: homicide data through
2023, HIV incidence through 2024, poverty through 2022, drug prevalence through 2021. Harm reduction
arrives after the crisis. Every time.

## What it does

TRACE maps trafficking corridors for cocaine, heroin, methamphetamine and cannabis, forecasts how those
corridors will shift next year, and scores every country on its risk of a new local drug crisis —
combining World Bank development data with UN seizure, price and cultivation data.

Six screens, keyboard-driven:

- **Route Map** — corridor arcs per drug over a dark basemap, year scrubber, observed vs predicted toggle
- **Country Screen** — routes in and out, prices, World Bank vulnerability profile, harm-reduction coverage, risk drivers
- **Spillover Risk Board** — every country ranked across Exposure, Vulnerability and Protection
- **Shock Simulator** — a plain-English scenario rewires the network and updates risk scores
- **Live Wire** — a GDELT newswire classified in real time, with anomalies flagged against the model
- **Market Board** — wholesale and retail price tickers with year-over-year change

It is a harm-reduction and early-warning instrument, not an enforcement one. By design it never shows
where enforcement is weakest or which routes are least watched.

## How we built it

**Data.** The World Bank Indicators API is called programmatically with explicit source IDs — 24 indicators
across 217 economies, 2005–2026, nulls preserved, provenance recorded per value. That layer does five
distinct jobs: market mass for the gravity model, route friction, vulnerability, validation targets, and
detection-bias control. External sources (all cited): UNODC Individual Drug Seizures (~2.3M cases), the
UNODC World Drug Report statistical annex, the Global Organized Crime Index, Harm Reduction International's
Global State of Harm Reduction, CEPII GeoDist, and GDELT.

**Models.** A PPML gravity model as the published baseline, and a LightGBM hurdle model as the main
predictor — a classifier for whether a corridor is active next year, a regressor for volume if it is.
SHAP gives per-corridor drivers in plain language. Every corridor carries a 0–100 confidence score built
from six independent signals.

**AI at runtime.** Jev (TypeSafe's System One model, pinned to `jev-1.13.0`) classifies the newswire into
typed decisions with calibrated confidence — event type, drug, origin, transit, destination, size — rather
than text, and parses command-bar intent. A confident event landing on a corridor the model gave under 10%
probability is flagged as an anomaly: the model announcing its own misses.

**Stack.** Python 3.11, uv, DuckDB, pandas, statsmodels, LightGBM, scikit-learn, SHAP, FastAPI with a
WebSocket Live Wire, APScheduler. Next.js, TypeScript, Tailwind, deck.gl `ArcLayer` over MapLibre, cmdk,
Recharts. Contract-first development: an OpenAPI spec and fixtures were committed before any backend logic
so the frontend could build in parallel.

## Challenges we ran into

- **The public UNODC seizure release has no route fields.** Departure, transit and destination are
  restricted-tier. Rather than invent routes, we built a cited corridor table from UNODC's own published
  route maps and reports, with a citation key per row, and estimated yearly volumes by seizure-anchored
  allocation over real node totals. The route-level loader is written and waiting.
- **Governance indicator codes had been renamed.** The familiar `CC.EST` family is archive-only now; the
  live codes are `GOV_WGI_*.EST` on source 3. We found that by verifying every code against the live API
  rather than trusting documentation.
- **GDELT rate-limited us.** The poller keeps GDELT's spacing and retries; while unavailable, the Live Wire
  replays a labelled sample set, marked as fallback in `/api/meta` and never counted as evidence.
- **Seizures measure enforcement, not trafficking.** Addressed with detection-bias controls and the
  multi-signal confidence score rather than ignored.

## Accomplishments we're proud of

- A held-out backtest: the hurdle model reaches 0.92 AUC on corridor activation against 0.61 for the
  standard economics baseline, trained through 2019 and evaluated on 2020–2024.
- The Afghan ban test: trained through 2021, shocked with the cultivation collapse, the model called 12 of
  14 corridor shifts in the right direction and predicted a Southeast Asia share of 12% against the 14% the
  later data showed.
- Publishing a result that went against us. Our core spillover hypothesis was not supported: route exposure
  alone does not predict later rises in homicide or HIV once vulnerability is controlled for. We committed
  that finding the day we found it. It is why the risk score has three columns, and it is an argument for
  harm reduction over interdiction.

## What we learned

That the hard part of an early-warning system is not the model, it is being honest about evidence. Most of
our engineering time went into confidence scoring, detection-bias controls, and documenting limitations —
and that is what makes the forecasts worth acting on.

## What's next for TRACE

Live Jev key; a fentanyl module; ACLED conflict events; a public read-only API; wastewater and EUDA price
feeds; weekly retraining and per-country alert subscriptions; and a deployment with a harm-reduction
partner in a single transit corridor, measured against real service placement.

---

## Built with
`python` · `duckdb` · `pandas` · `statsmodels` · `lightgbm` · `scikit-learn` · `shap` · `fastapi` ·
`websockets` · `apscheduler` · `nextjs` · `typescript` · `tailwind` · `deck.gl` · `maplibre` · `recharts` ·
`world-bank-api` · `unodc` · `gdelt` · `jev` · `typesafe-ai` · `anthropic` · `uv`

## Data sources (all cited)
World Bank Indicators API (WDI source 2, WGI source 3) · UNODC Drugs Monitoring Platform, Individual Drug
Seizures · UNODC World Drug Report statistical annex · UNODC crop surveys (Afghanistan, Myanmar) · Global
Organized Crime Index (GI-TOC) · Harm Reduction International, Global State of Harm Reduction 2024 · CEPII
GeoDist · GDELT DOC 2.0 · Natural Earth. Full table with codes, freshness and links:
[`docs/DATA_SOURCES.md`](../docs/DATA_SOURCES.md).

## AI usage disclosure (CDC requirement)
Generative AI was used throughout and is cited in two places: an `AI-assisted` header comment in every file
it wrote or substantially edited, and a dated log in [`docs/AI_USAGE.md`](../docs/AI_USAGE.md). Runtime AI:
Jev (TypeSafe AI) for newswire classification and command parsing; Claude (Anthropic) for country briefings
and scenario parsing. Statistical methods cited: Santos Silva & Tenreyro (2006) for PPML; Ke et al. (2017)
for LightGBM; Lundberg & Lee (2017) for SHAP.
