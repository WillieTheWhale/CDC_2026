<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# TRACE methods, explained feature by feature (presenter guide)

Every equation, constant, threshold and result below is taken from the code on `main` and from the live API
(`/api/metrics`, 2026-09-27). File paths point to where each piece lives, so any number can be checked.

For each feature you get:
- **Say it:** a plain-English version you can say on stage.
- **Method:** the exact equation.
- **Variables:** what goes in, and where it comes from.
- **Decisions:** the thresholds and rules that choose what the audience sees.
- **Result:** measured performance, where there is one.
- **If asked:** likely judge questions, with answers.

---

## 0. The whole system in 30 seconds

> TRACE turns public data into four things. First, a map of drug routes between countries, estimated from real
> seizure totals. Second, a machine-learning forecast of which routes will be active next year. Third, a risk
> score for every country, combining how much drug traffic passes through it, how vulnerable its population is,
> and how much harm-reduction protection it has. Fourth, tools that stress-test all of this: a shock simulator,
> a natural-experiment test on Afghanistan's opium ban, and a live AI newswire that flags events the model did
> not expect.

**Pipeline** (`uv run trace pipeline`, under a minute):

```
World Bank API (24 indicators) ─┐
UNODC seizures, cultivation,    ├─► route network (edges.py) ─► route forecast (hurdle.py) ─► risk score (spillover.py)
  prices (WDR annex)            │        │ confidence score          │ SHAP drivers                │ hypothesis test
GI-TOC OC Index, HRI, CEPII  ───┘        ▼                           ▼                             ▼
                                   Atlas map arcs            Predict toggle, Scenarios      Risk board, Country screen
```

**The World Bank data plays five roles** (the Graduate-track requirement). If you removed it, the model
would lose all of these:

| Role | Indicators (code, API source) | Used in |
|---|---|---|
| Market size (gravity "mass") | GDP `NY.GDP.MKTP.CD`, population `SP.POP.TOTL`, GDP per capita PPP `NY.GDP.PCAP.PP.KD` (source 2) | Gravity baseline, hurdle features, estimated local flows |
| Route friction and attraction | Rule of law `GOV_WGI_RL.EST`, control of corruption `GOV_WGI_CC.EST`, government effectiveness `GOV_WGI_GE.EST`, political stability `GOV_WGI_PV.EST` (source 3), container ports `IS.SHP.GOOD.TU`, air passengers `IS.AIR.PSGR`, trade openness `NE.TRD.GNFS.ZS`, logistics `LP.LPI.OVRL.XQ` | Hurdle features |
| Vulnerability | Youth unemployment `SL.UEM.1524.ZS`, youth NEET `SL.UEM.NEET.ZS`, poverty `SI.POV.DDAY`, Gini `SI.POV.GINI`, health spending `SH.XPD.CHEX.PC.CD`, account ownership `FX.OWN.TOTL.ZS`, rule of law, control of corruption | Risk score |
| Outcomes (validation) | Homicide `VC.IHR.PSRC.P5`, HIV incidence `SH.HIV.INCD.ZS`, battle deaths `VC.BTL.DETH` | Hypothesis test, conflict feature |
| Detection-bias control | Customs efficiency `LP.LPI.CUST.XQ`, rule of law | Fitted as controls, **never shown** (design boundary) |

---

## 1. Route network: the arcs on the Atlas (`backend/trace_backend/model/edges.py`)

**Say it:**
> The public UN seizure data tells us how much of each drug every country seizes, but not where it came from.
> So we take 234 corridors documented in UN and EU reports, plus land-border neighbours of the big seizure
> hubs. Each country's seized amount is then split across the routes that could feed it, like a gravity model
> from trade economics: bigger sources and shorter distances get more. A route only gets volume if both ends
> support it.

**Method.** This is a seizure-anchored gravity allocation, run for each drug and year.

1. **Candidate routes.**
   - Documented corridors get prior `1.0`.
   - Land-border pairs that touch one of the drug's 25 biggest seizure countries, where both countries report
     seizures of that drug in at least 3 years, get prior `0.15`.
   - A neighbour candidate that reverses a documented corridor is dropped.
2. **Node mass.** `S` = kg seized, from UNODC WDR annex 7.1 (editions 2012, 2015, 2020 and 2026; the latest
   edition wins for each country-year). `P` = production:
   - Cocaine: `coca hectares × 7 kg/ha`.
   - Heroin: `opium tonnes × 100 kg` (10:1 heroin-equivalent). If only hectares exist: `hectares × 25 kg/ha
     opium × 0.1`.
3. **Distance decay.** `decay = exp(−distance / L) × (1 + 0.5 × shared_border)`.
   - `L` is 9,000 km for cocaine, 3,500 km for heroin and meth, and 1,500 km for cannabis.
   - `L` is multiplied by 3 for documented corridors.
4. **Two-sided allocation.**

   ```
   inflow  F_in(i→j)  = S_j        × w(i→j) / Σ_k w(k→j),   w = prior × √(S_i + P_i) × decay
   outflow F_out(i→j) = (S_i + P_i) × v(i→j) / Σ_k v(i→k),   v = prior × √S_j       × decay
   kg(i→j) = min(F_in, F_out)        ← both ends must support the flow
   ```

**Variables:** seizures at both ends, production at the origin, great-circle distance (CEPII GeoDist),
shared border (CEPII), and the documented-corridor flag.

**Decisions (what is displayed):**

| Quantity | Rule |
|---|---|
| `share` | `kg / total kg of that drug that year` |
| `active` | share ≥ **0.1%** |
| `volume_norm` (arc thickness) | `log(1+kg) / log(1+max kg for that drug-year)`, in 0–1 |
| `is_emerging` (pulsing arc) | active, share ≥ 0.5%, and (not active two years earlier, or kg grew ≥ 1.5× over two years). Never flagged in the first two data years |
| `change_pct` | `(kg / last year's kg − 1) × 100` |

**If asked:**
- *"Isn't this just seizures?"* Yes: `kg` is seizure-scale, not the total trafficked. We say so in the
  API notes. That's why every route also has an independent confidence score (section 2).
- *"Why the square root?"* It dampens huge producers so they don't take every route. Mass matters, but with
  diminishing returns.

---

## 2. Edge confidence score, 0–100 (`edges.py → signals`)

**Say it:**
> Every route gets an evidence score: how many independent kinds of evidence agree it's real. Seizures at both
> ends, prices rising along the route, organised-crime market scores, cultivation at the origin, a published
> source, and live news.

**Method:** a sum of weighted yes/no signals:

| Signal | Points | True when |
|---|---|---|
| Seizures | 30 | origin has seizures or production **and** the destination has seizures |
| Price gradient | 20 | destination price (USD/g, nearest year within 4 years) > origin price |
| OC Index | 20 | the GI-TOC market score for that drug is ≥ 5 at **both** ends (nearest edition within 10 years) |
| Cultivation | 10 | the origin grows coca (cocaine) or opium poppy (heroin) |
| Documented | 10 | the corridor is in a cited UNODC/EUDA report |
| News | 10 | the Live Wire saw a real (not replay) event on this route in the last 30 days. Added live by the API, capped at 100 |

**If asked:** *"Why these weights?"* They're set by hand, not learned. Seizures get the most points because
they're the direct physical trace; news gets the least because it's the noisiest. We present the score as an
evidence count, not a probability.

---

## 3. Route forecast: the "Predict" toggle (`hurdle.py`, `features.py`, `train.py`)

**Say it:**
> To forecast next year, we use a two-part machine-learning model called a hurdle model. Part one asks: will
> this route be active next year? Part two asks: if so, how big? We multiply the two. We tested it honestly: we
> trained only on data up to 2019 and forecast 2020 to 2024. It beat both a classic trade-economics gravity
> model and a "same as last year" baseline.

**Method:** a LightGBM hurdle model (gradient-boosted trees).

```
P(active next year)   = LightGBM classifier  (400 trees, learning rate 0.03, 31 leaves)
log(1 + kg next year) = LightGBM regressor   (500 trees, trained only on routes that were active)
expected kg           = P(active) × (exp(predicted log kg) − 1)
```

**Variables.** There are 46 features per route-year: 20 route-level features, plus 13 World Bank features
for each end.
- **History:** last year's log kg, log kg two years ago, share, active flag, growth.
- **Geography:** log distance, shared border, common language, documented corridor.
- **Node signals:** log seizures and seizure growth at origin and destination, log production at origin,
  price gap `log(price_dest / price_origin)`, OC Index at both ends, cannabis legal status at both ends
  (from the WDR regulation table).
- **World Bank, both ends:** log GDP, log population, GDP per capita PPP, rule of law, control of
  corruption, government effectiveness, political stability, log port TEU, log air passengers, trade % GDP,
  LPI overall, LPI customs (control only), log battle deaths.

**Explanations (the "drivers" on each route).** SHAP values on the volume model (Lundberg and Lee 2017). The
UI shows the top 3 by absolute size. It excludes last year's volume (too obvious to be useful) and the customs
control (design boundary).

**Baselines:**
- **PPML gravity** (Santos Silva and Tenreyro 2006):
  `kg_next ~ Poisson(exp(b0 + drug FE + log GDP_o + log GDP_d + log Pop_o + log Pop_d + log dist + border +
  price gap))`, with robust (HC1) standard errors.
- **Persistence:** next year = this year.

**Result.** Backtest trained on target years ≤ 2019 (8,242 route-years) and tested on 2020–2024 (3,170):

| Model | AUC (will the route be active?) | Spearman (volume ranking) | Precision@20 (top growth calls) |
|---|---|---|---|
| **Hurdle (ours)** | **0.881** | **0.578** | **0.48** |
| Gravity PPML | 0.583 | 0.378 | 0.34 |
| Persistence | 0.815 | 0.477 | 0.42 |

Per drug, the AUC is meth 0.96, heroin 0.92, cannabis 0.89 and cocaine 0.79. The biggest drivers are
history (last year's volume, the year before, share), then seizures at the origin.

**Decisions:**
- **Predicted "emerging":** P ≥ 0.5, predicted share ≥ 0.5%, and (inactive last year, or predicted growth
  ≥ +50%).
- **The final model** is retrained on all labelled years before forecasting 2025.

**Metric definitions** (for the Q&A):
- **AUC:** the chance a randomly chosen active route is ranked above an inactive one (0.5 = coin flip).
- **Spearman:** rank correlation between predicted and actual volumes, over routes active in either year.
- **Precision@20:** of the 20 established routes with the highest predicted growth each year, the share that
  actually grew ≥ 10%.

**If asked:**
- *"Most of the power is last year's volume, isn't it?"* History is the largest driver, which is why
  "persistence" is the honest baseline to beat. We beat it on all three metrics.
- *"Why not deep learning?"* About 11,000 labelled rows of tabular data. Boosted trees are the standard
  strong choice for that, and SHAP explains them exactly.

---

## 4. Estimated local flows: the faint wind-style arrows (`model/estimated_flows.py`, `/api/estimated-flows`)

**Say it:**
> The route model works country to country, so zoomed in, the map would be empty. The faint arrows are
> clearly labelled estimates of how drugs spread from where a route arrives to nearby cities: they follow
> population and money, and fade with distance. They are never used in any score.

**Method:**
1. **Entry city.** Each modeled route delivers into an entry city: the city in the destination country, among
   its 15 richest, that maximises `money / (km from origin + 300)²`. Here `money = population × GDP per capita
   PPP`. The squared distance was adopted on 2026-09-27 after the US validation (section 5).
   Its supply is `volume_norm × confidence / 100`.
2. **Arrow score.** Every city of 150k+ people draws one arrow from the source that maximises:

   ```
   arrow score = supply × (money_target / max money) / (1 + km / 400)²,   25 km ≤ km ≤ 1,500 km
   ```

3. **Waves.** There are three waves. Each keeps its strongest arrows: 300, then 240, then 200 per drug and
   year, each wave at half the strength of the one before. Every country in reach also keeps its best 2
   targets, so poorer regions are not crowded out.
4. **City intensity** (shading) = the modeled supply plus the estimated strength passing through each city.

**Variables:** Natural Earth city population and location, World Bank GDP per capita PPP, the modeled routes'
volume and confidence, and great-circle distance. No enforcement variable.

**If asked:** *"Are these real routes?"* No. They're placement estimates, labelled "estimated", and never
counted. Section 5 shows we tested them against real US data.

---

## 5. US documented routes and the validation (`seed/us_routes.csv`, `/api/us-routes`, `docs/US_ROUTES_VALIDATION.md`)

**Say it:**
> For the United States we added 203 routes that official US reports state in words, from the Justice
> Department's National Drug Intelligence Center and HIDTA threat assessments. Every one comes with the page
> number and an exact quote. We then used them to test our own model, and to improve it.

**Method:**
- Rows come from 14 NDIC HIDTA Drug Market Analyses (2009/2011) and the 2026 Atlanta-Carolinas HIDTA
  assessment. Each quote was checked word for word against the PDF page.
- **Placement:** a Natural Earth city if the source names one, otherwise the state's label point. Foreign
  origins go on the country anchor.

**Validation.** We scored each contiguous state on whether the documents name it as a destination (AUC), with
a population-only baseline and bootstrap confidence intervals:
- **Before the fix:** neither the arrows nor the classifier-driven arrows beat population. The model entered
  the US through New York and Los Angeles, while the documents say distribution starts on the Southwest border.
- **The fix** (squared distance for the entry city) raised cannabis state AUC from 0.76 to 0.87, now above
  population (0.79). The bootstrap 95% CI of the gain is +0.05 to +0.21.
- **Country level:** the classifier's predicted US inflows (Mexico 0.99, Canada 0.97, Jamaica 0.76 for
  cannabis) match the documented foreign origins. The only miss is the Bahamas.

**If asked:** *"Your model was wrong?"* It was wrong at one step. We found that with independent data, fixed
it, and measured the fix. That's the point of validating.

---

## 6. Spillover risk: the Risk board and Country screen (`model/spillover.py`)

**Say it:**
> Every country gets a crisis-risk score out of 100 from three parts. Exposure is how much drug traffic flows
> through it, weighted by how harmful each drug is. Vulnerability is how exposed its people are: youth
> unemployment, poverty, inequality, weak health spending. Protection is the harm-reduction services that
> already exist. High exposure, high vulnerability and low protection is where help should go first.

**Method:**

```
per drug:  raw_d = [ inbound/total + 0.5 × outbound/total + 0.5 × production/total production ] × harm weight
harm weights: heroin 1.3, meth 1.1, cocaine 1.0, cannabis 0.3
Exposure  = 100 × log(1 + Σ_d raw_d / 0.0001) / log(1 + max raw / 0.0001)        (fixed scale across years)

Vulnerability = mean of within-year percentiles (0–100, higher = worse) of: youth unemployment, youth NEET,
  poverty, Gini, low health spending, weak rule of law, weak control of corruption, low account ownership.
  Needs ≥ 2 indicators; otherwise the region median, otherwise 50.

Protection = 100 × points earned / points the HRI edition reports:
  needle-syringe programmes 25, opioid agonist therapy 25, naloxone 20, drug consumption rooms 10,
  prison programmes 10, harm reduction in national policy 10. The edition in force that year is used;
  no HRI record = 0.

Risk score = 0.45 × Exposure + 0.35 × Vulnerability + 0.20 × (100 − Protection)
Tiers: ≥ 70 critical, ≥ 58 high, ≥ 46 elevated, ≥ 34 moderate, otherwise low
```

- **Years:** scores cover 2008 (the first HRI edition) to 2025. 2025 uses the forecast routes.
- **Drill-down:** the Country screen shows each component's contribution. Every World Bank value carries its
  code, source and year.

**If asked:**
- *"Why 0.45/0.35/0.20?"* It's a transparent, hand-set weighting: exposure is the early-warning signal, and
  protection only reduces risk. They're stated in the UI and configurable (`config.RISK_WEIGHTS`). They were
  not fitted.
- *"Why is cannabis 0.3?"* Lower acute harm (overdose, HIV) per unit than heroin, meth or cocaine.

---

## 7. The core hypothesis test: an honest null result (`spillover.py → hypothesis`)

**Say it:**
> We tested our own premise: when a route moves through a country, does harm follow? We checked whether
> exposure predicts a 20% rise in homicide or HIV within three years, beyond vulnerability. It doesn't. If
> anything, the association goes the other way, probably because seizure-based exposure also measures how
> strong enforcement is. We report that as it is.

**Method:**
- **Outcome:** a country-year is positive if homicide or HIV incidence, within the next 3 years, rises to
  ≥ 1.2× its current level, *and* by ≥ 1 per 100k (homicide) or ≥ 0.05 per 1,000 (HIV). Only observed
  World Bank values count, never forward-filled ones.
- **Nested logistic regressions:** `y ~ vulnerability + log(baseline)` compared with `… + exposure`.
- **Likelihood-ratio test:** `LR = 2(llf₁ − llf₀) ~ χ²(1)`.
- **Out-of-sample check:** cross-validated AUC, with 5 folds **grouped by country** so no country appears in
  both training and test data.

**Result** (n = 4,186 country-years): **not supported.**
- Exposure level: OR 0.90 per 10 points (p ≈ 1e-6), driven by homicide (OR 0.86). HIV: no effect (p = 0.78).
- Exposure change (a route moving in): OR 0.97, p = 0.56.
- AUC 0.705 without exposure vs 0.712 with it.

**A second retrospective check** (`/api/evidence/research-model`): a fixed-effects regression,
`homicide(t+1) ~ log(1 + cocaine seizure kg, t) + country FE + year FE`, with SEs clustered by country.
- Coefficient 0.019 (SE 0.118, p = 0.87), n = 1,428, 144 countries: no association.
- Labelled as ecological and non-causal.

---

## 8. Scenarios: the shock simulator (`model/shocks.py`, `api/simulate.py`, `model/scenario.py`)

**Say it:**
> Type a policy in plain English, like "Colombia cuts coca 50%". TRACE turns it into a structured shock,
> reruns the route allocation, lets the change ripple downstream, re-forecasts next year with the same
> machine-learning model, and shows which routes and which countries' risk scores move.

**Method:**
1. **Parse the text.** Rules come first.
   - "ban" → ×0.05, "halve" → ×0.5, "double" → ×2, a % cut → `1 − pct/100`.
   - Customs "+1" → a +1 shift on the 1–5 LPI scale, and a % converts to `pct/100 × 2`.
   - "legalize" → legalization = 1.
   - If the rules find nothing and an API key is set, Claude parses the text with structured output.
   - Requests about weak enforcement or avoiding detection are refused.
2. **Shock factor for the country's throughput:**
   - Cultivation: `f = multiplier` (applied to production and to the producer's seizures).
   - Legalization: `f = 1 − 0.5 × value` on illicit inflow of that drug, and the legal flag is set.
   - Customs: `f = exp(−0.35 × Δ)`. The lost volume is displaced to the upstream origins' other
     destinations, in proportion to their current volume (the "balloon effect", shown so neighbours can prepare).
3. **Cascade:** 2 rounds downstream. Each non-producing country gets
   `f_j = (Σ_i inflow share_ij × f_i)^0.7`. The 0.7 means partial substitution from other suppliers.
4. **Re-allocate and re-forecast:** re-run the section 1 allocation, apply feature changes (customs score,
   legal flag), then run the hurdle model for next year.
5. **Risk deltas:** `scenario raw exposure = saved raw × scenario/baseline`, re-scored with the section 6
   formula. No change gives exactly the saved score.

**Limits enforced:** cultivation multiplier 0–10, legalization 0 or 1, customs shift ±4.

**If asked:** *"Where does 0.7 come from?"* It's an assumption, not an estimate: it encodes partial
substitution (other suppliers fill part of a gap). The Afghan test (section 9) is how we check the
mechanism.

---

## 9. Experiment: the Afghanistan 2022 opium ban (`train.py → afghan_ban`)

**Say it:**
> In 2022 the Taliban banned opium, and production fell about 95%. We trained the model only on data through
> 2021, applied a 95% cut to Afghan opium, and asked where heroin would go in 2023. It predicted Southeast
> Asia's share of heroin routes would jump from 5% to 14%. The real 2023 data showed 13%. Without the shock,
> the model would have said 4%.

**Method:**
- Hurdle model trained on target years ≤ 2021.
- Shock: `cultivation AFG × 0.05 (heroin)` at the 2022 state.
- Forecast 2023, and compare with the observed 2023 routes.
- Evaluated on 13 routes: the top 10 by 2022 volume plus the top 5 leaving Myanmar, Laos or Thailand
  (overlaps removed).

**Result:**
- **Direction:** correct on **9 of 13** major heroin corridors; Spearman 0.38 on the size of change.
- **Southeast Asian share:** 4.9% before, **13.9% predicted** (4.5% with no shock), **13.4% actual**.

---

## 10. Live Wire: AI-classified news (`api/livewire.py`, `jev/`, `reflex/`)

**Say it:**
> Official drug data arrives years late. So TRACE reads the news: every 15 minutes it pulls drug stories from
> GDELT and classifies each one: is it a real event, which drug, from where, to where, and how big. If a
> confident seizure lands on a route our model said was unlikely, under 10%, it's flagged as an anomaly: an
> early sign that a route is moving.

**Method:** one typed question per field, in the style of Jev.
- `is_event` (yes/no), `event_type` (7 choices), `drug` (7), `origin`/`transit`/`destination` (about 200
  countries or "not stated"), `size` (4 levels), `route_mentioned` (yes/no).
- **Size** is computed from quantities stated in the text, not guessed by the model:
  - Weight: < 100 kg small, 100–1,500 kg notable, ≥ 1,500 kg major.
  - Pills: < 10,000 small, up to 1 million notable, ≥ 1 million major.
  - "Record" wording → record.
- Dates come from GDELT metadata, never from the classifier.

**Decisions:**

| Rule | Threshold |
|---|---|
| Show an event | confidence ≥ 0.6 and P(is_event) ≥ 0.5 |
| Anomaly | event type = seizure, route mentioned, and the model's P(route active) < 0.10 (a route the model never considered counts as 0). Fentanyl is not modeled, so it never triggers one |
| News signal | a real (not replayed) event on a route in the last 30 days → +10 route confidence |

**Classifiers:** there are three behind one interface.
- **Jev** (TypeSafe, pinned `jev-1.13.0`): used once there's an API key.
- **Reflex:** our own re-implementation (section 11). The deployed API runs its torch-free ONNX build; the
  chosen compressed model has 100% top-choice agreement with PyTorch over 150 parity headlines.
- **Keyword mock:** the explicit fallback if Reflex cannot load; `/api/meta` identifies which classifier is live.

The production build pre-classifies the replay backlog, reducing its first read from about 17 seconds to
0.06 seconds. `POST /api/livewire/classify` applies the same grounded classifier to one supplied headline
without storing it.

**Result.** Grounded Reflex on 92 real published headlines it never trained or tuned on (one AI-assisted
annotator; every row retains its URL):

| Field | Accuracy |
|---|---|
| is_event | 0.913 |
| drug | 0.978 |
| origin | 0.957 |
| destination | 0.848 |
| size (28 seizure rows; “not stated” is a label) | 0.929 |

Grounding produced 0 unsupported country/drug entities out of 107 predictions, versus 5 of 102 without
the guardrails and 19 of 88 for the keyword mock. This means the entity is supported by the text, not that
the model necessarily assigned the supported country to the correct route role.

---

## 11. Reflex: our own "System One" classifier (`reflex/`, `docs/REFLEX_SPEC.md`)

**Say it:**
> The commercial model we planned to use had a waitlist, so we built our own version of it, Reflex. It answers
> the same typed questions and now runs in production without PyTorch. On a first real-news benchmark, its
> grounding guardrails invented no country or drug; displayed events had mean confidence 0.857 against 0.840
> precision. It is still a routing signal, not an externally validated field probability.

**Method:**
- A cross-encoder (`nli-deberta-v3-xsmall`) reads (news text, candidate answer) and scores
  `s = logit(entailment) − logit(contradiction)`.
- The probabilities are `softmax(s / T)` over that question's options, with one temperature `T` per question
  type fitted on held-out data (temperature scaling).
- Trained with log-loss on open datasets plus UNODC-record examples, on a Colab T4 (about 7 minutes).

**Result:**
- Held-out accuracy 90.2% (untuned backbone 48.1%).
- Expected calibration error 0.020, which is within the 0.02–0.03 that independent testing reports for Jev.
- Live Wire fields: event type 98%, destination 82% (mock 52%).
- On the 92-headline real-news benchmark, grounded Reflex reaches 97.8% drug, 95.7% origin and 84.8%
  destination accuracy. Displayed-event calibration error is 0.052; over all rows it is 0.19. The set has
  one AI-assisted annotator, so the next step is a larger independently labelled evaluation.

---

## 12. Markets (`export/build.py → price_series`, `/api/evidence/market-observations`)

**Say it:**
> Price tickers per drug and country, from the UN's published price and purity tables. Prices rise along a
> route, which is one of our evidence signals.

**Method:**
- **Price series:** USD per gram by market level (retail or wholesale).
- **Year-over-year change:** `(this year / last year − 1) × 100`, shown only when the two years are
  consecutive.
- **Exact-product derived values:** 449 retail-to-wholesale price ratios and 476 purity-adjusted prices,
  `USD per pure gram = price / purity`.
- **Rejected:** coarse ratios that mixed product forms were thrown out in a feasibility audit.

---

## 13. Health evidence and drilldowns (`api/evidence.py`, `api/route_evidence.py`)

**Say it:**
> Research and derived market values open to their formula, exact input rows and original spreadsheet cells.
> Source-published health and overdose records open to their source, date, method and status labels instead;
> we do not invent a derivation where the source reports an observation or estimate directly.

**Route evidence has three layers, each labelled:**
- `direct_reported_pair`: 51 country pairs a primary source states explicitly.
- `interpreted_corridor`: 234 pairs that are our transcription of UN/EU regional route maps.
- `narrative_context`: 4 multi-regional statements, kept as text.

**Health evidence** comes from UNODC annex data, each value labelled with its type:
- people who inject drugs, and HIV, hepatitis C and hepatitis B among them;
- treatment counts;
- US provisional overdose deaths from the CDC.

The labels say whether a value is modelled or observed, direct or indirect, and whether periods overlap.

---

## 14. People atlas (`frontend/data/people/`, `/api/people`)

**Say it:**
> A source-cited directory of people named in court records, indictments and sanctions. Each person is placed
> at country level only, with their legal status and the date of that status.

**Rules:**
- Every displayed person, status and country link carries a cited source. Most rest on an official action such
  as a court judgment, indictment, sanctions listing or police release; the separately labelled `reported`
  records rely on journalism and are not presented as official findings.
- Status is `convicted`, `charged`, `sanctioned` or `reported`, with an as-of date. A charge is never shown as
  a conviction.
- Countries come from documented conduct, never from where a group operates.
- No precise locations, inferred relationships or unlicensed photos.
- **Prominence tiers (1, 2, 3)** are set from leadership or court-role evidence. Tier 1 shows at world zoom,
  tier 2 at regional zoom, tier 3 up close.

---

## 15. Command bar and the design boundary (`model/scenario.py → parse_command`)

- **Commands:** `HEROIN ROUTES`, `MEX <GO>`, `RISK TOP 20`, `SHOCK AFG CULTIVATION -95%`, `NEWS COCAINE`,
  `COMPARE COL PER`, `YEAR 2023`, `PREDICT ON`. These are parsed by rules, each with a confidence value.
- **Design boundary:** questions like "least watched", "weakest customs", "avoid detection" or "how to
  smuggle" are refused, in the command bar and the simulator, and the US-route loader rejects rows with that wording.
- Customs efficiency is used only as a statistical control, and is never displayed or ranked.

**If asked:** *"Couldn't traffickers use this?"* It's built from public UN data they know better than anyone.
It shows where harm is heading, not where enforcement is weak, and there's no "least-watched route" feature
by design.

---

## 16. Which variables drive which decision (cheat sheet)

| Decision / output | Driven by | Not driven by |
|---|---|---|
| Route exists and how big (arcs) | seizures at both ends, production (coca ha, opium t), distance, shared border, documented flag | news, enforcement |
| Route confidence | seizures, price gradient, OC Index ≥ 5 both ends, cultivation, documented, news (last 30 days) | the model's prediction |
| Will a route be active next year | route history, seizures and growth, production, price gap, OC Index, legal status, World Bank market size, governance, logistics, conflict (both ends) | customs is fitted as a control but never shown |
| Emerging flag | share ≥ 0.5% + new or ≥ 1.5× growth (observed), or P ≥ 0.5 + new or ≥ +50% (predicted) | |
| Estimated arrows | city population × GDP per capita PPP, distance, modeled route volume × confidence | any enforcement variable; never feeds a score |
| Exposure | inbound + ½ outbound + ½ production shares × harm weight | |
| Vulnerability | youth unemployment, NEET, poverty, Gini, health spending, rule of law, corruption control, account ownership (percentiles) | |
| Protection | HRI services: NSP, OAT, naloxone, DCR, prison programmes, national policy | |
| Risk score and tier | 0.45 E + 0.35 V + 0.20 (100 − P); cut-offs 70/58/46/34 | |
| Scenario result | shock type and size, cascade elasticity 0.7, customs elasticity 0.35, legal cut 0.5, then the hurdle model | |
| Live Wire shown / anomaly | confidence ≥ 0.6 / seizure + route mentioned + model P < 0.10 | |

---

## 17. Honest limits (say them before a judge does)

1. **Seizures measure enforcement as well as trafficking.** That's why route volume is "seizure-scale" and
   every route has an independent evidence score. It's also the likely reason the spillover hypothesis failed.
2. **The public UN seizure file has no route fields.** Routes are allocated over documented corridors, not
   observed shipment by shipment.
3. **Several weights are set by hand and stated openly, not fitted:** risk 0.45/0.35/0.20, harm weights,
   confidence points, cascade 0.7.
4. **The first real-news Live Wire benchmark is small and internally labelled:** 92 published headlines,
   one AI-assisted annotator. Grounding guarantees textual support for recognised entities, not the correct
   route role, and confidence remains a routing signal pending larger independent validation.
5. **The US validation uses 2008–2011 reports.** Absence from a report isn't evidence of absence.

---

## 18. Glossary of methods (one line each)

| Term | Meaning |
|---|---|
| Gravity model | Trade flows grow with the size of both economies and shrink with distance |
| PPML | Poisson pseudo-maximum likelihood: the standard way to fit a gravity model with zeros in the data |
| LightGBM | Fast gradient-boosted decision trees for tabular data |
| Hurdle model | Two stages: will it happen (classifier) × how much if it does (regressor) |
| SHAP | Splits each prediction into additive contributions from each feature |
| AUC | Probability a random positive is ranked above a random negative (0.5 = chance, 1 = perfect) |
| Spearman ρ | Correlation of ranks (does the model order things right?) |
| Precision@k | Share of the top-k predictions that turn out right |
| Logistic regression / odds ratio | Models the probability of a yes/no outcome; OR < 1 means lower odds |
| Likelihood-ratio test | Does adding a variable improve the fit more than chance would? |
| Grouped cross-validation | Hold out whole countries, so the test never sees a country the model trained on |
| Fixed effects | Compare each country with itself over time, removing stable country differences |
| Temperature scaling / ECE | Rescale model scores so probabilities match observed frequencies; ECE measures the gap |
| Bootstrap CI | Resample the data many times to see how much a result could vary |
