# Handoff prompts

## For Claude Code (backend, Markandeya's machine)

Open Claude Code in `C:\Users\yalam\CDC_2026` and paste:

```
Pull the latest main first (git pull --rebase origin main). Then read, in order:
CLAUDE.md, docs/SYSTEM_DESIGN.md, docs/CONTEXT_LOG.md, docs/DATA_SOURCES.md,
docs/BACKEND_BRIEF.md, and skills/world-bank-indicators-api/SKILL.md.

You are the backend agent for TRACE. Work through docs/BACKEND_BRIEF.md in order,
starting with T0 (the API contract and fixtures), and push it to main as soon as it's
done, because my teammate's frontend agent is waiting on it. Then continue with T1
onward, committing and pushing after each working step.

Use a task list, run tests before pushing, and update the status table in README.md
after each milestone. Follow every rule in CLAUDE.md, especially: never edit frontend/,
cite AI use, never commit secrets or raw data, and respect the design boundary.
If the UNODC download needs a login, or anything is ambiguous or destructive, stop
and ask me.
```

### Autonomous version (/goal)

```
/goal Build the entire TRACE backend, end to end, and push it to main.

Setup: git pull --rebase origin main, then read CLAUDE.md, docs/SYSTEM_DESIGN.md,
docs/CONTEXT_LOG.md, docs/DATA_SOURCES.md, docs/BACKEND_BRIEF.md, and
skills/world-bank-indicators-api/SKILL.md. Those docs are the spec; follow them.

Work through every task in docs/BACKEND_BRIEF.md (T0 through T9) in order without
stopping to check in. Push T0 (contract + fixtures) the moment it's done, because the
frontend agent is building against it. After each task: run tests, commit, pull
--rebase, push to main, and update the README status table.

Blockers never stop the run. Work around them and log them in docs/BLOCKERS.md:
- UNODC IDS download needs a login: build the edge table from the WDR annex, published
  UNODC route tables, and the OC Index instead, keep the IDS loader ready, and note it.
- No Jev key: use the MockJevClassifier behind the interface (already the plan).
- Any source unreachable: cache what you can, use a documented fallback, keep going.

Done when all of these are true:
1. contracts/openapi.yaml, websocket.md, and fixtures for every endpoint are on main.
2. The World Bank data (every indicator in DATA_SOURCES.md) is pulled programmatically
   into DuckDB with a provenance manifest.
3. The edge table, gravity baseline, LightGBM hurdle model, SHAP drivers, 2019 backtest,
   and Afghan ban test all run from one command, with results in metrics.json.
4. Spillover risk scores exist for every country and year, with the hypothesis test result.
5. FastAPI serves every contract endpoint from precomputed JSON, the Live Wire WebSocket
   streams (mock Jev), and /api/simulate works for structured shocks.
6. A test validates every endpoint response against the OpenAPI contract, and all tests pass.
7. backend/README.md explains setup, the one-command pipeline, and how to run the API.
8. docs/AI_USAGE.md, docs/DATA_SOURCES.md, and the README status table are current.

Never edit frontend/, never commit secrets or raw data, cite AI use in every file, and
respect the design boundary in CLAUDE.md. The only reasons to stop and ask me: a
destructive action (deleting data, force push, history rewrite), spending money, or
changing project scope.
```

## For ChatGPT Astra (frontend, teammate's machine)

Clone `https://github.com/WillieTheWhale/CDC_2026`, then use as the goal:

```
Build the TRACE frontend described in docs/FRONTEND_BRIEF.md and docs/SYSTEM_DESIGN.md.
Read AGENTS.md first and follow every rule in it. Work only inside frontend/.
Use contracts/openapi.yaml and contracts/fixtures/ as the data source until
NEXT_PUBLIC_API_URL is set. If contracts/ doesn't exist yet, scaffold the shell and
map first, then git pull again. The backend pushes it first.

Done when: all screens in the brief render from fixtures; the command bar handles
the listed commands; the route map animates by year with the observed/predicted
toggle; the Country Screen and Risk Board work; npm run build passes; and every file
has the AI citation header. Pull from main often and push small commits straight to
main.
```
