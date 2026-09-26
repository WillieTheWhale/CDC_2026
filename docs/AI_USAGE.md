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
- 2026-09-26 — ChatGPT Sol (OpenAI), operated by William: collected and verified UNODC, OC Index, HRI and CEPII source histories in SQLite; merged three shards; audited 1990–2024 observed coverage and source estimates; built reproducible tests, provenance reports and release tooling. Published measurements are source data, not AI-generated.
- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: verified Figma MCP and Adobe Fonts API access and synchronized local main with origin/main; no application code generated.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: read TRACE context and the new API contract, browsed Pinterest, and curated three visual reference directions in frontend/design/pinterest-directions.md for owner selection; no frontend implementation generated.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: added the owner's frequent-commit rule to AGENTS.md and verified authenticated Adobe Fonts API access; credential stored only in a gitignored local environment file.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: created a plain localhost page containing the six Pinterest reference images at the owner's request.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: built the TRACE Next.js frontend against the shared API fixtures, created dot/legend/pulse/route assets and animation studies using Figma MCP, integrated Adobe Forma fonts, and generated cartographic dots from public-domain Natural Earth boundaries. Interface values and evaluation results are labeled illustrative; no model research findings were generated. Added adapter/command tests and began browser verification.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: refined the projected map dot grid, added emerging-route pulse markers, improved modal keyboard focus and independent API failure handling, and formatted frontend source for review. Verified production build and three focused tests.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: integrated regenerated pipeline fixtures, handled nullable price changes and snapshot years, preserved the unsupported spillover finding, improved source links and scenario comparison, and implemented Figma path/pulse motion from MCP context with reduced-motion support. Production build and four focused tests pass; desktop interaction checks cover commands, country evidence, risk sorting, scenarios, layers, and news pins.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: corrected cultivation-series selection after fixture regeneration, added status freshness and mobile return-to-map behavior, labeled synthetic news in both data modes, improved navigation accessibility, and added isolated live-adapter request/error tests.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: completed desktop/mobile browser interaction checks and native screenshots, fixed world-fit/zoom constraints and stale map tooltips, guarded hot-refresh style loading, documented setup and verification limits, and verified the production build. Razor was unavailable; no Razor execution is claimed.
2026-09-26 — ChatGPT (OpenAI, Codex Sol) designed the TRACE historical research questions, evidence-lineage schema, reproducible SQLite analyses, source caveat documentation, and validation/release workflow. All findings require checking against cited observed datasets; no source measurement is AI-generated.
2026-09-26 — ChatGPT (OpenAI, Codex Sol) collected and normalized UNODC price/purity workbook rows, built exact-product market ratios and purity-adjusted descriptive prices with source-cell lineage, documented failed EUDA CSV retrieval, and tested the market shard; original numeric source measurements were not AI-generated.
2026-09-26 — ChatGPT (OpenAI, Codex Sol) collected UNODC drug-specific prevalence, injecting-related infections and treatment observations; UN SDG 3.5.1 treatment coverage; and CDC provisional rolling-year overdose records into a source-linked SQLite shard. AI assisted code, normalization, verification and documentation; all numeric observations come from cited official sources.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: revised the frontend after owner review, removed decorative copy and beige surfaces, created four drug keys and an exposure legend with Figma MCP, replaced coarse map points with 1px country-exposure textures and detailed OpenFreeMap/Natural Earth cartography, and rebuilt the experiment with shared-scale connected marks and statistical tables. Country-level measurements remain explicitly distinguished from detailed geographic context.

- 2026-09-26 — ChatGPT (OpenAI), operated by William Keffer: browser-tested revised world and Bogotá street views, removed aggregate country links at local zoom, aligned experiment chart axes, improved numeric contrast, replaced filled history charts with observed-point line plots, fixed mobile experiment overflow, and saved native desktop/mobile screenshots. The owner clarified that “Razor” meant browser; that verification blocker is resolved.
