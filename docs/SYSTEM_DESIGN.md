# TRACE: System Design

A Bloomberg-style terminal for the global drug trade that predicts where the next drug crisis will hit, before it arrives.

- Event: 2026 Carolina Data Challenge (CDC), Graduate track
- Theme: AI for Social Good
- Hard requirement: data must be retrieved programmatically from the World Bank Indicators API. External data is allowed but must be cited.
- Status of this doc: authoritative spec. If code and this doc disagree, raise it; do not silently diverge.

Related docs: [CONTEXT_LOG.md](CONTEXT_LOG.md) (how we got here and why), [DATA_SOURCES.md](DATA_SOURCES.md) (verified codes and links), [BACKEND_BRIEF.md](BACKEND_BRIEF.md), [FRONTEND_BRIEF.md](FRONTEND_BRIEF.md), [CDC_RULES.md](CDC_RULES.md).

---

## 1. Pitch

**One line:** A Bloomberg Terminal for the global drug trade that predicts where the next drug crisis will hit, before it arrives.

**Paragraph:** Trafficking routes for cocaine and crack, heroin, meth, and cannabis constantly shift, and the countries they pass through often inherit the consequences: rising local use, violence, and HIV, usually years before anyone measures it. TRACE combines World Bank development data with UN seizure, price, and cultivation data to map those routes, forecast how they will move next, and score every country on its risk of a new drug crisis. A live AI-classified newswire catches changes before official data is published, and a shock simulator shows what happens when a country bans a crop, legalizes a drug, or cracks down on a port. We validate it on real natural experiments, most dramatically Afghanistan's 2022 opium ban. TRACE turns years of lagging data into an early warning system so help can arrive before the crisis instead of after.

**Why it is social good**
- Protects transit communities that never chose to be on a trafficking route and are hit hardest.
- Shifts the use of drug data from punishment toward prevention and harm reduction (where to send naloxone, treatment, HIV prevention next).
- Turns hindsight into foresight: official drug and health data lags by years.
- Gives policymakers evidence from real experiments (bans, legalization) instead of ideology.
- Ungatekeeps information: the data is public but scattered across UN PDFs and portals; TRACE puts it in one free, open tool for journalists, researchers, NGOs.

**Users:** harm reduction and public health orgs, journalists, policymakers, researchers.

---

## 2. Core hypothesis

"When a trafficking route moves through a country, local harm follows."

TRACE does not assume this; it tests it. Does predicted route exposure today predict rising violence (homicide), HIV incidence, or drug use in that country later, beyond what vulnerability alone predicts? If yes, route forecasts become crisis forecasts. Report the result whichever way it comes out. This is the headline finding.

---

## 3. Scope

- **Drugs:** cocaine (includes crack; UNODC groups them as cocaine-type), heroin/opiates, methamphetamine, cannabis. Fentanyl appears only in the live wire and US context, not the route model.
- **Geography:** all World Bank economies (about 217). Exclude aggregates (`region.value == "Aggregates"`).
- **Years:** about 2011 to 2024 for routes; live data layered on top.
- **Natural experiment 1 (showcase):** Afghanistan's 2022 opium poppy ban. Afghan opium production fell about 95 percent in 2023; Myanmar became the top producer. Afghan cultivation was about 232,000 ha in 2022 vs 12,800 ha in 2024. Prices stayed roughly five times the pre-ban average.
- **Natural experiment 2:** cannabis legalization (Uruguay 2013, Canada 2018, US states). The UNODC WDR annex includes a cannabis regulation table with dates.

---

## 4. Product: six screens

| Screen | What it does | Tier |
|---|---|---|
| Route Map | Dark world map, glowing arcs per drug, thickness by volume, timeline scrubber 2011 to latest, "Predict" toggle for next year, emerging corridors pulse | Must |
| Country Screen | `COL <GO>`: routes in and out, prices, World Bank vulnerability profile, harm reduction services, risk score and its drivers | Must |
| Spillover Risk Board | Every country ranked by crisis risk, three columns: Exposure, Vulnerability, Protection | Must |
| Shock Simulator | Plain-English scenario ("Colombia cuts coca 50%"); network rewires; risk scores update | Should |
| Live Wire | Jev-classified breaking news, pins drop on map, anomalies flagged | Should |
| Market Board | Price tickers per drug per country with year-over-year change | Nice |

**Command bar examples:** `HEROIN ROUTES`, `MEX <GO>`, `RISK TOP 20`, `SHOCK AFG CULTIVATION -95%`, `NEWS COCAINE`, `COMPARE COL PER`

**Aesthetic:** terminal. Amber and green on black, monospace (IBM Plex Mono or JetBrains Mono), dense draggable panels.

**Design boundary (non-negotiable):** TRACE shows where flows and harms are, never where enforcement is weak. No "least-monitored route", "weakest customs", or "safest path" features, rankings, or queries. Every output is framed around harm and prevention.

---

## 5. Data

Full verified list with codes, sources, freshness, and links: [DATA_SOURCES.md](DATA_SOURCES.md).

### How the World Bank data does real work (graduate-track defense)
1. **Gravity-model mass:** GDP, population, purchasing power define market size.
2. **Route friction and attraction:** governance, customs efficiency, port and air traffic, trade openness explain why flows pass through one country instead of a neighbor.
3. **Vulnerability:** youth unemployment, NEET, poverty, inequality, health spending determine how badly a route's arrival hurts.
4. **Outcomes for validation:** homicide, HIV incidence, refugee flows are what the spillover hypothesis is tested against.
5. **Detection-bias control:** customs efficiency and rule of law let the model separate "more drugs flowing" from "better at catching them".

Remove the World Bank data and the model has no market sizes, no friction, and no vulnerability.

### Known data limits (say them out loud)
- Seizures measure enforcement, not trafficking. Controlled for via (5) and the multi-signal edge confidence score.
- The drug trade is cash-based. We never rely on transactions; we follow physical, price, and harm traces, plus official currency seizure data (CBP).
- UNODC route origins are "last provenance", not necessarily production country.
- World Bank data lags 1 to 5 years depending on series (see DATA_SOURCES.md).

---

## 6. Pipeline and models

### Step 1: Route network
- Each UNODC IDS seizure lists departure, transit, destination. Split into hops (departure to transit, transit to destination; departure to destination if no transit).
- Aggregate into edges: `(year, drug, from_iso3, to_iso3, total_kg, case_count)`.
- Normalize kg within drug (for example, share of that drug's yearly total, or z-score of log kg) so drugs are comparable.
- **Edge confidence (0 to 100):** how many independent signals agree the corridor is active:
  - seizures present on the edge
  - price gradient in the expected direction (cheaper upstream, pricier downstream)
  - Global Organized Crime Index market score for that drug is high on both ends
  - live news hits on that edge
  - cultivation at origin (for cocaine and heroin)

### Step 2: Route prediction model
- **Unit:** plausible `(from, to, drug, year)` pairs: every pair ever observed, plus neighbors of major hubs.
- **Target:** next year's volume on the edge.
- **Baseline:** PPML gravity model (Poisson pseudo-maximum likelihood, standard in trade economics) with GDP, population, distance, shared border, price gap.
- **Main model:** LightGBM hurdle model: (a) classifier for "edge active next year", (b) regressor for volume if active. Features: lagged volume, gravity terms, price gap, cultivation at origin, governance and logistics features, OC Index scores, conflict.
- **Explanations:** SHAP per edge; top drivers shown in the UI ("rising because of weaker rule of law plus new port capacity").
- **Validation:** train through 2019, predict 2020 to 2024. Metrics: AUC for edge appearance, Spearman correlation for volumes, precision@20 for top predicted growth corridors.
- **Afghan ban test:** train through 2021, inject the 2023 cultivation collapse as a shock, check whether heroin flows shift toward Myanmar-linked Southeast Asian routes in the direction later data showed.

### Step 3: Spillover Risk Score (per country-year)
- **Exposure:** predicted inbound plus transit volume, weighted by drug harm.
- **Vulnerability:** World Bank youth unemployment, NEET, poverty, health spending, governance.
- **Protection:** Harm Reduction International services (needle and syringe programs, opioid agonist therapy, naloxone, drug consumption rooms).
- Validation: logistic model predicting "significant rise in homicide rate or HIV incidence within three years" from exposure plus vulnerability. Report whether exposure adds predictive power beyond vulnerability alone.
- Display: Exposure, Vulnerability, Protection as three columns plus a combined score. Countries where all three line up badly are the headline slide.

### Step 4: Shock Simulator
- Scenario edits model inputs (cultivation, legalization flag, customs efficiency shift), reruns route model, propagates to risk scores.
- An LLM parses plain English into structured edits.

---

## 7. Jev (TypeSafe AI "System One" model)

Jev returns typed decisions (not text): `Choice` (one of up to 255 options), `Score` (2 to 10 ordered levels), `Noul` (yes/no probability). 70 to 500 ms per call, questions answered in parallel, input-only billing. Python SDK: `pip install typesafe-sdk`, env var `TYPESAFE_API_KEY`, endpoint `POST https://api.typesafe.ai/v1/systemone`. Weak at counting, arithmetic, and date comparison. Pin the version (`jev-1.13.0`).

**No key yet (waitlisted).** Build the classifier behind an interface with a mock implementation; the real Jev client drops in later. Access options: console.typesafe.ai (waitlist) or Vercel AI Gateway.

### Live Wire classifier
Every 15 minutes pull drug-related articles from GDELT, dedupe, one Jev call per article:
- `is_event` (Noul): describes a specific drug seizure, bust, or policy change
- `event_type` (Choice): seizure, arrest_or_indictment, lab_dismantled, law_or_policy_change, violence, corruption, other
- `drug` (Choice): cocaine, heroin, meth, cannabis, fentanyl, other, unclear
- `origin`, `transit`, `destination` (Choice): about 200 countries plus `not_stated`
- `size` (Score): small, notable, major, record
- `route_mentioned` (Noul)

Rules: hide events under 0.6 confidence; take dates from GDELT metadata, never from Jev; flag an **anomaly** when a confident event lands on an edge the model gave under 10 percent probability.

Other Jev jobs: command bar intent parsing (Choice over command types).

Validation: hand-label 100 articles, report per-field accuracy.

An LLM (Claude or similar) handles country briefings and scenario parsing only.

---

## 8. Tech stack

**Data and models (backend/, Python 3.11, uv)**
- `requests` or `wbgapi` for World Bank (always pass source IDs explicitly; follow `skills/world-bank-indicators-api/SKILL.md`)
- `pandas`, **DuckDB** (single local DB), Parquet snapshots
- `openpyxl` (UNODC Excel), `pdfplumber` (HRI PDF table)
- `statsmodels` (PPML), `lightgbm`, `scikit-learn`, `shap`
- `typesafe-sdk` (Jev, behind an interface), `anthropic` (briefings)

**API (backend/)**
- FastAPI, WebSocket for Live Wire, APScheduler for GDELT polling
- Precomputed JSON for map and risk board so the demo never waits on a model

**Frontend (frontend/, owned by teammate via ChatGPT Astra)**
- Next.js + TypeScript + Tailwind
- deck.gl `ArcLayer` on MapLibre dark basemap
- react-grid-layout (panels), `cmdk` (command bar), Recharts (sparklines, tickers)

**Deploy:** Vercel (frontend), Railway or Render (API). Keep a recorded backup demo video.

**DuckDB tables:** `countries`, `wb_indicators` (long: iso3, year, code, source_id, value, retrieved_at), `seizures_raw`, `edges`, `prices`, `cultivation`, `oc_index`, `harm_reduction`, `predictions`, `risk_scores`, `live_events`

---

## 9. Repo layout and collaboration

```
CDC_2026/
  docs/            shared specs (this file, briefs, context log, data sources, AI usage)
  contracts/       the seam: openapi.yaml, websocket.md, fixtures/*.json
  backend/         Claude Code only
  frontend/        teammate's ChatGPT Astra only
  skills/          World Bank API skill (read before any World Bank call)
  CLAUDE.md        rules for Claude Code
  AGENTS.md        rules for Astra / Codex-style agents
```

- Push straight to `main`, small and frequent commits. Always `git pull --rebase` before starting and before pushing.
- **Contract first.** `contracts/` is written before backend logic so the frontend can build against fixtures on day one. Contract changes are their own commit, update fixtures in the same commit, and are announced in `docs/CHANGELOG_CONTRACT.md`.
- Neither agent edits the other's folder.

**Integration milestones**
1. Contract locked: OpenAPI plus fixtures on main. Frontend starts.
2. Backend serves precomputed JSON from real data. Frontend swaps fixtures for `NEXT_PUBLIC_API_URL`.
3. Live pieces: WebSocket Live Wire, shock simulator.

Integrate at milestone 2, not at the end.

---

## 10. Build plan

Deadline: later this week. Order of work:

| Phase | Backend | Frontend |
|---|---|---|
| 0 | Contract + fixtures + docs pushed | Read docs, scaffold app against fixtures |
| 1 | World Bank pull into DuckDB; UNODC IDS + annex downloads; countries table | Terminal shell, map with static arcs from fixtures |
| 2 | Edge table, OC Index, HRI, CEPII joins | Country Screen, Risk Board |
| 3 | Gravity baseline, LightGBM, backtest | Prediction toggle, timeline scrubber |
| 4 | Spillover score, Afghan ban test, SHAP | Command bar, drivers display |
| 5 | Live Wire (mock Jev), shock simulator | Live Wire panel, simulator UI |
| 6 | Export precomputed JSON, deploy API | Wire to real API, polish, deploy |
| 7 | Results numbers, Devpost AI citations | Rehearse, record backup video |

**Cut order if behind:** Market Board, then Shock Simulator, then Live Wire. Route Map + Country Screen + Risk Board + one validated experiment is a complete project.

---

## 11. The 7-minute demo

1. **Hook (0:45):** "In 2022, one decree in Afghanistan erased most of the world's opium supply. Where did the trade go, and who paid for it?"
2. **Problem (0:45):** transit countries inherit crises; the data arrives years late.
3. **Live terminal (3:00):** `HEROIN ROUTES`, scrub through 2022, watch the network rewire; `RISK TOP 20`; open the top country: exposure, vulnerability, missing harm reduction; run one shock live.
4. **Proof (1:00):** backtest accuracy, Afghan ban test, spillover hypothesis result.
5. **Live Wire (0:45):** stories classified in real time, one anomaly flagged.
6. **Close (0:45):** "Harm reduction usually arrives after the crisis. TRACE lets it arrive before."

Presentation is 7 minutes plus 2 minutes Q&A.

## 12. Q&A prep

- **"Seizures measure enforcement, not trafficking."** Correct; we control for customs efficiency and rule of law, and every corridor has an evidence score from independent signals.
- **"The drug trade is cash."** We never rely on transactions; physical, price, and harm traces, plus official currency seizure data.
- **"Couldn't traffickers use this?"** Built from public UN data they already know better than anyone; shows where harm is heading, not where enforcement is weak; no least-watched-route feature by design.
- **"Is the World Bank data essential?"** Five roles, section 5.
- **"How accurate is Jev?"** Per-field accuracy on 100 hand-labeled articles.

## 13. Rubric map

Rubric: five criteria, 10 points each (50 total). See [CDC_RULES.md](CDC_RULES.md).

| Criterion | Where TRACE earns it |
|---|---|
| Impact and Applicability | Early warning for transit countries; harm reduction targeting |
| Completeness | Working terminal, backtested model, two natural experiments, Jev accuracy |
| Innovation and Creativity | Terminal interface, gravity model applied to trafficking, live AI newswire |
| Visualization | Animated arcs, risk board, rewiring timeline |
| Presentation and Communication | Live command-line demo with a strong narrative arc |
