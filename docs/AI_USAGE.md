# AI Usage Log (CDC citation requirement)

CDC rules allow generative AI tools but require citing where they are used. Every AI-written file also carries a header comment. Append one line per session: date, tool, who ran it, what it produced.

| Date | Tool | Operator | What it produced |
|---|---|---|---|
| 2026-09-26 | Claude (Anthropic), claude.ai | Markandeya | Project ideation, data source research and verification, TRACE spec and all files in `docs/`, `CLAUDE.md`, `AGENTS.md`, repo config |
| 2026-09-26 | Claude Code (Anthropic), Opus 5.5 | Markandeya | Backend T0-T9: API contract and fixtures, `backend/` pipeline (World Bank ingest, external ingest, edges, gravity + LightGBM hurdle models, SHAP, backtests, spillover risk, API, Live Wire, simulator), tests, docs updates |

## Runtime AI used by the product
| Component | Model | Purpose |
|---|---|---|
| Live Wire classifier | Jev (TypeSafe AI), pinned `jev-1.13.0`; mock until key is available | Classify news events into typed fields |
| Command bar parsing | Jev | Map free text to command intents |
| Country briefings, scenario parsing | Claude (Anthropic) | Short text briefings; plain English to structured shocks |

## Statistical methods to cite in the writeup
- PPML gravity model: Santos Silva and Tenreyro (2006), "The Log of Gravity", Review of Economics and Statistics.
- LightGBM: Ke et al. (2017), NeurIPS.
- SHAP: Lundberg and Lee (2017), NeurIPS.
