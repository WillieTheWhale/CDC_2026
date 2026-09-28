# Context Log: how TRACE was chosen

This is the handoff record of the planning session (2026-09-26) that produced TRACE. It captures every decision, what was tried and rejected, and why, so any agent or teammate picking up the project has the full reasoning. The spec itself lives in [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

## 1. The challenge

- 2026 Carolina Data Challenge (UNC), theme **AI for Social Good**.
- Five tracks, one dataset each: Popular Culture (Music and Mental Health survey, easy), Social Science (Open Data Index for Schools, medium), Natural Science (NOAA Storm Events, medium), Business (CFPB complaints, medium), **Graduate (World Bank Indicators API, hard)**.
- We chose **Graduate**. Requirement: the project must retrieve data programmatically using the World Bank Indicators API. Prizes: AirPods Pro 2 (1st), Dell dock (2nd).
- Full rules, rubric, and AI citation requirement: [CDC_RULES.md](CDC_RULES.md).

## 2. What the team wanted (the filter every idea went through)

Stated preferences, in the order they came up:
1. Nothing boring (the example given was "chips").
2. Integrate **Jev** (TypeSafe AI's new non-LLM decision model) meaningfully. Jev is one tool among many; any other tools are fine.
3. Something **cool and niche** that other teams would not think of.
4. Not "dashboardy", not basic, not predictable.
5. Live tracking of something.
6. Open-sourcing / **ungatekeeping information**.
7. Something a **common person** can use.
8. **Genuinely interactive.**
9. Touching a real, sensitive, close-to-home topic.
10. Must still clearly pass the rubric (fun wrappers without analysis were rejected).

## 3. Ideas explored and why they were not chosen

| Idea | Outcome |
|---|---|
| Breakout Countries (growth forecasting), Hunger Early Warning, Shock Radar, Remittance Navigator, Ask the World (indicator search) | "Too dashboardy, basic, predictable" |
| Tender Watch (red flags in 418k World Bank procurement notices) | Liked as niche, but not chosen |
| Ghost Numbers (statistic revision forensics), Shadow Price Index | Not chosen |
| Live politician/news fact-checker (Community Notes style) | Came from a friend; team liked it as "cool and funny". Later evolved into a browser extension idea. Not chosen as final |
| UN Brag-o-Meter, Campaign Receipts, Viral Claim Checker | Same family as above |
| Game ("Run a Country"), path planner over development space, data documentary | Rejected: would not pass the rubric / "weird" |
| Development GPS, Twin Earths (synthetic control), Who Does AI Fail audit | Rejected as "weird" |
| Teen mental health and social media | Explored; data is thin in World Bank (no age-specific mental health data) |
| The Rights Gap (Women, Business and the Law index vs outcomes) + Rights Ticker | Good social justice fit, not chosen |
| Earth Engine (learned world model with Jev agents) | Rejected: "not cool" |
| Debt vs Doctors, Aid Report Card, Missing Data Watch, Fee Watch | Tracking/ungatekeeping family, not chosen |
| Stat-Check browser extension, Another Life (life simulator with real odds) | Common-person tools, not chosen |
| 210 ideas across all 21 World Bank topics | Brainstorm; led to exploring drug data |
| Suicide data ideas | Data exists (`SH.STA.SUIC.P5`, 2000-2021, 185 countries) but team decided it was not the right topic |
| Child protection / child marriage ideas | Explored at population level only; not chosen |
| **Drug trafficking terminal** | **Chosen.** Became TRACE |

## 4. How TRACE evolved

1. Question: does the World Bank have drug data? Answer: only alcohol and tobacco. Illegal drug data comes from UNODC and others (external data is allowed if cited).
2. Idea: a Bloomberg Terminal for drug trafficking routes.
3. Question: is there enough data to predict and map routes? Answer: yes for mapping (UNODC IDS lists departure, transit, destination per seizure; UNODC builds its own route maps this way), partly for prediction. Caveat: seizures measure enforcement, which became a strength (detection-bias control and evidence scores).
4. Concern: "the drug trade is cash." Resolution: never rely on transactions; follow physical traces (seizures, cultivation, wastewater), price gradients, laundering fingerprints, court/news text, and harm outcomes; combine into a per-route confidence score.
5. Scope clarified to the "real" illegal street drugs, not prescriptions: **cocaine/crack, heroin, meth, cannabis**. Crack is counted under cocaine (UNODC groups them).
6. Reframed from "where are drugs going" to **"where will the harm show up next"**: transit countries inherit drug crises; predicting route shifts predicts crises. This is what makes it AI for Social Good.
7. Named **TRACE**. Natural experiments chosen: Afghan opium ban (2022) and cannabis legalization.
8. External data expanded: Global Organized Crime Index, Harm Reduction International, CBP, CDC overdose, ACLED, EUDA, etc.
9. Full spec written and every World Bank code verified live (two renamed code families found; see DATA_SOURCES.md).

## 5. Decisions (binding unless the team changes them)

| Decision | Value |
|---|---|
| Track | Graduate (World Bank API required) |
| Project | TRACE, drug trade terminal with spillover-risk early warning |
| Drugs | cocaine (incl. crack), heroin, meth, cannabis |
| Framing | harm reduction and prevention, not enforcement |
| Safety boundary | never show where enforcement is weak; no least-watched-route features |
| Deadline | later this week (exact date to confirm) |
| Git flow | push straight to `main`, small frequent commits, `git pull --rebase` first |
| Split | backend by Claude Code on Markandeya's machine (`C:\Users\yalam\CDC_2026`); frontend by teammate using ChatGPT Astra |
| Ownership | backend agent edits `backend/`, `contracts/`, `docs/`; frontend agent edits `frontend/` only |
| Contract first | `contracts/openapi.yaml` + fixtures before backend logic |
| Jev key | none yet (waitlisted); build Live Wire with a mock classifier behind an interface |
| AI citation | required by CDC rules; comment every AI-written file and log in `docs/AI_USAGE.md` |
| Secrets | `.env` only, never committed; `.env.example` lists names |

## 6. Open items

- Confirm exact submission deadline and presentation time.
- ~~Verify the UNODC IDS public download~~ Done 2026-09-26: no login needed, but the public release has no route fields (see BLOCKERS.md).
- Get a Jev key (console.typesafe.ai waitlist, or Vercel AI Gateway).
- Confirm with CDC organizers that using external AI APIs (Jev, Claude) at runtime is fine (rules allow generative AI tools with citation).
- Pick deploy targets (Vercel + Railway/Render proposed).

## 7. About Jev (researched 2026-09-26)

- Made by TypeSafe AI (San Francisco, founded 2024, CEO Diogo Almeida, ex-OpenAI RLHF/InstructGPT). Early access launched 2026-09-15 with a US$40M seed led by DCVC.
- "System One model": returns typed decisions with probabilities and calibrated confidence, not text. Trained with RLCD (reinforcement learning for calibrated decisions).
- Question types: `Choice` (up to 255 options), `Score` (2 to 10 ordered levels, fractional result), `Noul` (probability of yes).
- 70 to 500 ms; $0.042 per million input tokens, output free; 64k context for state plus questions.
- Python: `pip install typesafe-sdk`; `from typesafe_sdk import Choice, Noul, Score, TypeSafeClient`; `client.system_one(state=..., questions={...})`; answers in `response.answers[name]` with `.choice/.score/.noul/.confidence/.probabilities`.
- Known weaknesses (TypeSafe's own "jaggedness" page): reads instructions literally, cannot count or do arithmetic, treats dates as text, context rot with irrelevant state, state is not treated as adversarial, does not generate text.
- Rate limits for jev-1.13: 250k tokens/s, 1,200 requests/min. Pin `jev-1.13.0`.
- Benchmarks are self-reported by TypeSafe and unreproduced; validate on our own labels.
- Guide used: https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e
