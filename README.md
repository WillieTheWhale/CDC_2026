# TRACE

**A Bloomberg-style terminal for the global drug trade that predicts where the next drug crisis will hit, before it arrives.**

2026 Carolina Data Challenge, Graduate track (World Bank Indicators API). Theme: AI for Social Good.

TRACE maps trafficking routes for cocaine and crack, heroin, meth, and cannabis; forecasts how those routes will shift; and scores every country on its risk of a new local drug crisis, combining World Bank development data with UN seizure, price, and cultivation data. A live AI-classified newswire (Jev) catches changes before official data is published. Built for harm reduction and early warning, not enforcement.

## Start here
| If you are | Read |
|---|---|
| Anyone | [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md), [docs/CONTEXT_LOG.md](docs/CONTEXT_LOG.md) |
| Backend (Claude Code) | [CLAUDE.md](CLAUDE.md), [docs/BACKEND_BRIEF.md](docs/BACKEND_BRIEF.md), [backend/README.md](backend/README.md) (setup, `uv run trace pipeline`, `uv run trace serve`, results) |
| Frontend (ChatGPT Astra) | [AGENTS.md](AGENTS.md), [docs/FRONTEND_BRIEF.md](docs/FRONTEND_BRIEF.md) |
| Data questions | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md), [skills/world-bank-indicators-api/SKILL.md](skills/world-bank-indicators-api/SKILL.md) |
| Handoff prompts | [docs/HANDOFF_PROMPT.md](docs/HANDOFF_PROMPT.md) |
| Blockers and workarounds | [docs/BLOCKERS.md](docs/BLOCKERS.md) |
| Presenting | [deck/README.md](deck/README.md), [deck/CUE_CARDS.md](deck/CUE_CARDS.md), [deck/QA_PREP.md](deck/QA_PREP.md) |
| Rules and rubric | [docs/CDC_RULES.md](docs/CDC_RULES.md), [docs/AI_USAGE.md](docs/AI_USAGE.md) |

## Layout
```
docs/        shared specs and logs
contracts/   API contract and fixtures (the frontend/backend seam)
backend/     Python data pipeline, models, FastAPI (Claude Code)
frontend/    Next.js terminal UI (ChatGPT Astra)
skills/      World Bank Indicators API skill
deck/        judging pitch deck (rebuilds itself from this repo)
```

## Status
| Milestone | Owner | Status |
|---|---|---|
| Spec, docs, handoff | planning session | done |
| T0 API contract + fixtures | backend | done (`contracts/`) |
| T1 backend scaffold | backend | done (uv, Python 3.11, `trace` CLI) |
| T2 World Bank ingest | backend | done; now read from the SQLite v2 archive (24 indicators, 217 economies, 1960-2025) |
| T3 external ingest (UNODC, OC Index, HRI, CEPII) | backend | done (IDS 2.3M cases, WDR annex, OC Index x3, HRI 197 countries, CEPII; see BLOCKERS.md) |
| T4 edges + confidence | backend | done (676 corridors x 2011-2024, seizure-anchored allocation, 6-signal confidence) |
| T5 route models + backtest + Afghan ban test | backend | done, retrained on SQLite archive (hurdle AUC 0.88 vs gravity 0.58; Afghan ban 9/13 corridors, SEA share 5%->14% pred vs 13% actual) |
| T6 spillover risk | backend | done (217 countries x 2008-2025, HRI per edition; hypothesis not supported) |
| SQLite v2 migration | backend | done (archive read-only + `derived.sqlite`; DuckDB removed) |
| Reflex (own System One model) | backend | v0.2 shipped as the Live Wire classifier: 98% event type, 82% destination (mock 52%), ECE 0.02; see [REFLEX_SPEC.md](docs/REFLEX_SPEC.md) |
| T7 export + API | backend | done (precomputed JSON, FastAPI, contract tests) |
| T8 Live Wire (mock Jev) | backend | done (JevClassifier + mock, GDELT poller with replay fallback, REST + WS) |
| T9 shock simulator | backend | done (structured + plain-English shocks, command bar) |
| API deployment | backend | done: live at https://trace-api-six.vercel.app (Vercel; keyword Live Wire classifier, backlog replay) |
| People API | backend | done (`/api/people`, `/countries`, `/network`, `/{person_id}`; parity with the frontend route handlers) |
| Website deployment | backend (deploy only) | live at https://trace-atlas-gules.vercel.app (Vercel project `trace-atlas`, root `frontend/`, `NEXT_PUBLIC_API_URL` = live API) |
| Route evidence API | backend | done (`/api/route-evidence`: 51 direct reported pairs, 234 interpreted corridors, 4 narrative claims; `evidence_ids`/`kg_basis` on route edges) |
| Evidence drilldown API | backend | done (`/api/evidence/*`: 3,995 research and market values traced to formula, inputs and original cells; health and CDC overdose with the required labels) |
| Frontend shell + map | frontend | done: live at https://trace-atlas-gules.vercel.app (atlas map with year slider and 2025 forecast, full-screen mode, drug filters, estimated local flows) |
| Country Screen + Risk Board | frontend | done (risk watchlist and board, country inspector with routes, indicators, harm reduction and briefing) |
| Simulator, Live Wire, Market Board | frontend | done (Scenarios tab with policy dates, Live Wire feed, Markets tab; Experiment tab for the Afghan ban test) |
| People atlas | frontend (People data), backend (API) | done: source-cited people, country-level only, served live from GitHub main every 10 min; countryless browse; legal history and life status |
| Live evidence on the site | backend (frontend edits approved by owner) | done: map route evidence, Health, Markets and research values read the live API (with value drilldowns); static snapshots are only the offline fallback |
| Merged database (`database_new`) | backend | done: `backend/scripts/merge_databases.py` = canonical archive + derived API tables + route-evidence seeds (76 tables); uploaded to the team Drive folder as `database_new.sqlite.gz` + `database_new.json` |
| Map: all years, land anchors, smooth playback, estimated local flows | backend (frontend edits approved by owner) | done: every route year and risk year in snapshot mode; route arrows anchored on land; playback without reloads; labelled estimated-flow arrow layer and volume coloring (`uv run trace estimate-flows`) |
| US documented routes (state/city) | backend | data done: 203 cited route pairs (cocaine, heroin, meth, cannabis) across 32 states from NDIC HIDTA Drug Market Analyses + 2026 AC HIDTA assessment, `uv run trace us-routes`; map layer is on `claude/estimated-flows-preview` |
| Pitch deck | presentation | done (`deck/`, 4:45 + live demo, rebuilds from repo) |

## Headline results (backend, 2026-09-26)
- Data: SQLite v2 archive (`data_collection/`), UNODC seizures 2006-2024, World Bank 1960-2025, HRI editions 2008-2024.
- Route model backtest (train on targets through 2019, test 2020-2024): hurdle AUC 0.88 vs 0.58 for the PPML gravity baseline; Spearman 0.58; precision@20 0.48.
- Afghan opium ban: trained through 2021, the model got the direction right on 9 of 13 major heroin corridors and predicted the Southeast Asian share rising from 5% to 14% (actual 13%).
- Spillover hypothesis: **not supported.** Route exposure did not predict later rises in homicide or HIV beyond vulnerability; if anything it predicted lower odds. Details in [backend/README.md](backend/README.md).

## Data and AI citations
All sources: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). All AI use: [docs/AI_USAGE.md](docs/AI_USAGE.md).
