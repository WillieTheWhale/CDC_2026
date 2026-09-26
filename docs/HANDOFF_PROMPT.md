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
