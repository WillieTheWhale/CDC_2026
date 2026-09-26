# TRACE

**A Bloomberg-style terminal for the global drug trade that predicts where the next drug crisis will hit, before it arrives.**

2026 Carolina Data Challenge, Graduate track (World Bank Indicators API). Theme: AI for Social Good.

TRACE maps trafficking routes for cocaine and crack, heroin, meth, and cannabis; forecasts how those routes will shift; and scores every country on its risk of a new local drug crisis, combining World Bank development data with UN seizure, price, and cultivation data. A live AI-classified newswire (Jev) catches changes before official data is published. Built for harm reduction and early warning, not enforcement.

## Start here
| If you are | Read |
|---|---|
| Anyone | [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md), [docs/CONTEXT_LOG.md](docs/CONTEXT_LOG.md) |
| Backend (Claude Code) | [CLAUDE.md](CLAUDE.md), [docs/BACKEND_BRIEF.md](docs/BACKEND_BRIEF.md) |
| Frontend (ChatGPT Astra) | [AGENTS.md](AGENTS.md), [docs/FRONTEND_BRIEF.md](docs/FRONTEND_BRIEF.md) |
| Data questions | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md), [skills/world-bank-indicators-api/SKILL.md](skills/world-bank-indicators-api/SKILL.md) |
| Handoff prompts | [docs/HANDOFF_PROMPT.md](docs/HANDOFF_PROMPT.md) |
| Rules and rubric | [docs/CDC_RULES.md](docs/CDC_RULES.md), [docs/AI_USAGE.md](docs/AI_USAGE.md) |

## Layout
```
docs/        shared specs and logs
contracts/   API contract and fixtures (the frontend/backend seam)
backend/     Python data pipeline, models, FastAPI (Claude Code)
frontend/    Next.js terminal UI (ChatGPT Astra)
skills/      World Bank Indicators API skill
```

## Status
| Milestone | Owner | Status |
|---|---|---|
| Spec, docs, handoff | planning session | done |
| T0 API contract + fixtures | backend | done (`contracts/`) |
| T1 backend scaffold | backend | done (uv, Python 3.11, `trace` CLI) |
| T2 World Bank ingest | backend | done (24 indicators, 217 economies, 2005-2026, `wb_manifest.json`) |
| T3 external ingest (UNODC, OC Index, HRI, CEPII) | backend | not started |
| T4 edges + confidence | backend | not started |
| T5 route models + backtest + Afghan ban test | backend | not started |
| T6 spillover risk | backend | not started |
| T7 export + API | backend | not started |
| T8 Live Wire (mock Jev) | backend | not started |
| T9 shock simulator | backend | not started |
| Frontend shell + map | frontend | not started |
| Country Screen + Risk Board | frontend | not started |
| Simulator, Live Wire, Market Board | frontend | not started |

## Data and AI citations
All sources: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). All AI use: [docs/AI_USAGE.md](docs/AI_USAGE.md).
