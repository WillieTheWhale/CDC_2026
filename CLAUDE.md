# CLAUDE.md (rules for Claude Code in this repo)

Project: **TRACE**, a drug-trade terminal with spillover-risk early warning, for the 2026 Carolina Data Challenge, Graduate track.

## Read before doing anything
1. `docs/SYSTEM_DESIGN.md` (authoritative spec)
2. `docs/CONTEXT_LOG.md` (decisions and why)
3. `docs/DATA_SOURCES.md` (verified World Bank codes, gotchas, external sources)
4. `docs/BACKEND_BRIEF.md` (your task list, in order)
5. `skills/world-bank-indicators-api/SKILL.md` before any World Bank API call

## Your role
You are the **backend** agent. You may edit `backend/`, `contracts/`, `docs/`, and root config files. **Never edit `frontend/`**; a teammate's ChatGPT Astra agent owns it and pulls from `main` in parallel.

## Workflow
- `git pull --rebase origin main` before starting work and before every push.
- Push straight to `main`. Small, frequent, working commits with clear messages.
- Contract first: `contracts/` must exist and be pushed before other backend logic. Never change a response shape silently; contract changes get their own commit, updated fixtures, and an entry in `docs/CHANGELOG_CONTRACT.md`.
- After each milestone, update the status table in `README.md`.

## Hard requirements
- **World Bank API is mandatory and must be called programmatically.** Use explicit `source` IDs, paginate, keep nulls, record provenance. Governance codes are `GOV_WGI_*.EST` with `source=3`; refugees are `SM.POP.RHCR.EA/EO`.
- **Cite AI use (CDC rule).** Put this header at the top of every file you create or substantially edit:
  `# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.`
  (use the right comment syntax per language) and append a dated line to `docs/AI_USAGE.md` each session.
- **Cite external data** in `docs/DATA_SOURCES.md` and in API `meta` responses.
- **Never commit secrets or raw data.** `.env` stays local; `backend/data/raw/`, `backend/data/processed/`, and `*.duckdb` are gitignored.
- **Jev has no key yet.** Build the Live Wire behind a `JevClassifier` interface with a mock; real client reads `TYPESAFE_API_KEY`, pinned to `jev-1.13.0`.

## Design boundary (non-negotiable)
TRACE is a harm-reduction and early-warning tool. Never build features, fields, rankings, or queries that show where enforcement is weakest, which routes are least monitored, or how to avoid detection. Show where flows and harms are, framed around prevention.

## Ask first
Deleting data, force pushing, rewriting history, changing the project scope, or anything that costs money.
