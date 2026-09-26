# AI Usage Log (CDC citation requirement)

CDC rules allow generative AI tools but require citing where they are used. Every AI-written file also carries a header comment. Append one line per session: date, tool, who ran it, what it produced.

| Date | Tool | Operator | What it produced |
|---|---|---|---|
| 2026-09-26 | Claude (Anthropic), claude.ai | Markandeya | Project ideation, data source research and verification, TRACE spec and all files in `docs/`, `CLAUDE.md`, `AGENTS.md`, repo config |
| 2026-09-26 | Claude Code (Anthropic), Opus 5.5 | Markandeya | Backend T0-T9: API contract and fixtures, `backend/` pipeline (World Bank ingest, external ingest, edges, gravity + LightGBM hurdle models, SHAP, backtests, spillover risk, API, Live Wire, simulator), tests, docs updates |
| 2026-09-26 | Claude Code (Anthropic), Opus 5 | Adrian | `deck/` pitch deck: content, renderer, repo-driven build script, cue cards, Q&A prep, Devpost copy |

## Runtime AI used by the product
| Component | Model | Purpose |
|---|---|---|
| Live Wire classifier | Jev (TypeSafe AI), pinned `jev-1.13.0`; mock until key is available | Classify news events into typed fields |
| Command bar parsing | Rule parser today (Jev planned) | Map free text to command intents; refuses design-boundary requests |
| Country briefings | none (template) | Briefings come from a deterministic data template (`export/build.py::briefing`); no LLM at runtime |
| Scenario parsing | Rules first; Claude (`claude-opus-5`, structured output) only as a fallback when `ANTHROPIC_API_KEY` is set | Plain English to structured shocks (`model/scenario.py`) |

## Statistical methods to cite in the writeup
- PPML gravity model: Santos Silva and Tenreyro (2006), "The Log of Gravity", Review of Economics and Statistics.
- LightGBM: Ke et al. (2017), NeurIPS.
- SHAP: Lundberg and Lee (2017), NeurIPS.

## Backend build details (Claude Code session, 2026-09-26)
- Every backend file carries the header `# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.` JSON fixtures and data files cannot hold comments; `contracts/README.md`, `backend/trace_backend/seed/README.md`, and the `_about` field of `jev/data/labeled_eval.json` cover them.
- `backend/trace_backend/seed/corridors.csv` was compiled by Claude Code from UNODC and EUDA publications (cited per row). The team should spot-check it.
- `backend/trace_backend/jev/data/labeled_eval.json`: 100 **synthetic** headlines with provisional labels drafted by Claude Code. They are not real articles. Replace or verify them with team hand-labels before quoting classifier accuracy.
- Methods implemented with AI help and cited in the code: PPML gravity (Santos Silva and Tenreyro 2006), LightGBM (Ke et al. 2017), SHAP TreeExplainer (Lundberg and Lee 2017), nested logistic regression with a likelihood-ratio test, grouped cross-validation (scikit-learn, statsmodels).

- 2026-09-26 — ChatGPT (OpenAI), operated by William: explicitly authorized three data-collection subagents plus coordinator to retrieve full-history World Bank and external source observations into SQLite, preserve provenance/missingness, audit temporal coverage, write reproducible collectors and tests, publish database snapshots, and document the SQLite handoff. User instruction supersedes the old frontend-only assignment for this separate `data_collection/` task.
