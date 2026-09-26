# AGENTS.md (rules for ChatGPT Astra / Codex-style agents)

Project: **TRACE**, a Bloomberg-terminal-style tool for the global drug trade that predicts where the next drug crisis will hit. 2026 Carolina Data Challenge, Graduate track, theme AI for Social Good.

## Read before doing anything
1. `docs/FRONTEND_BRIEF.md` (your task list, stack, look and feel)
2. `docs/SYSTEM_DESIGN.md` (full spec; sections 1, 4, 7, 11 matter most for you)
3. `contracts/` (API shapes and fixtures; your source of truth for data)
4. `docs/CDC_RULES.md`

## Your role
You are the **frontend** agent. You may edit **only `frontend/`** (plus appending lines to `docs/AI_USAGE.md` and `docs/CONTRACT_REQUESTS.md`). Never edit `backend/`, `contracts/`, or other docs. A Claude Code agent owns the backend and pushes to `main` in parallel.

## Workflow
- `git pull --rebase origin main` before starting and before every push. Pull often: the backend updates contracts and fixtures during the week.
- Push straight to `main` in small commits. `npm run build` must pass first.
- Build against `contracts/fixtures/` until `NEXT_PUBLIC_API_URL` is set; keep a single data layer that switches between fixtures and the live API.
- Need a different response shape? Do not work around it silently. Add a request to `docs/CONTRACT_REQUESTS.md` and keep going with the current shape.

## Hard requirements
- **Cite AI use (CDC rule, disqualification risk).** Header comment at the top of every file you create or substantially edit:
  `// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.`
  and append a dated line to `docs/AI_USAGE.md` each session.
- Show data provenance (source and year) next to World Bank numbers, and include a visible Data Sources panel.
- Never commit secrets. Use `frontend/.env.local` (gitignored).

## Design boundary (non-negotiable)
TRACE is a harm-reduction and early-warning tool. Never add views, sorts, filters, or labels that show where enforcement is weakest, which routes are least watched, or how to avoid detection. Frame everything around harm and prevention.
