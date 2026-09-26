# Backend Brief (Claude Code)

Owner: Markandeya, via Claude Code on his machine. Work in `backend/`, `contracts/`, and `docs/`. Never edit `frontend/`.

Read first: [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md), [DATA_SOURCES.md](DATA_SOURCES.md), [CONTEXT_LOG.md](CONTEXT_LOG.md), `skills/world-bank-indicators-api/SKILL.md`.

## Task order

### T0. Contract (do this first, push immediately)
Write `contracts/openapi.yaml`, `contracts/websocket.md`, and one realistic fixture per endpoint in `contracts/fixtures/`. Use real country codes and plausible numbers (for example cocaine COL to ECU to ESP/NLD/BEL, heroin AFG to IRN/PAK to TUR to Balkans, MMR opium into Southeast Asia, meth MEX to USA, MMR to THA/LAO). Push, then add a line to `docs/CHANGELOG_CONTRACT.md`.

Proposed endpoints (refine, but keep names stable once pushed):

| Method and path | Purpose |
|---|---|
| `GET /api/meta` | Available years, drugs, model version, data freshness per source |
| `GET /api/countries` | iso3, name, region, income group, lat, lon |
| `GET /api/routes?drug=&year=&mode=observed\|predicted` | Edges: from, to, drug, year, volume_norm, kg, cases, confidence, is_emerging, drivers (predicted only) |
| `GET /api/country/{iso3}?year=` | Profile: World Bank indicators (with code, source, year, value), routes in/out, prices, OC Index scores, harm reduction services, risk breakdown |
| `GET /api/risk?year=&limit=` | Ranked list: iso3, exposure, vulnerability, protection, score, rank, trend |
| `GET /api/prices?drug=&iso3=` | Price series (retail, wholesale, USD per gram) |
| `POST /api/simulate` | Body: scenario text or structured shocks. Returns changed edges and risk deltas |
| `GET /api/experiments/afghan-ban` | Before/after series, predicted vs actual edges, metrics |
| `GET /api/metrics` | Backtest metrics (AUC, Spearman, precision@20), Jev accuracy |
| `GET /api/livewire?since=` | Recent classified events (REST fallback) |
| `WS /ws/livewire` | Pushes classified events and anomaly flags |
| `POST /api/command` | Free-text command bar input to structured intent |

Every numeric World Bank value in responses carries provenance: `{ "code", "source_id", "year", "value" }`.

### T1. Project scaffold
`backend/` with uv, Python 3.11, `pyproject.toml`, `ruff`, `pytest`. Layout:
```
backend/
  trace/
    wb/          World Bank client (pagination, retries, caching, provenance)
    ingest/      unodc_ids.py, unodc_annex.py, ocindex.py, hri.py, cepii.py, cbp.py, gdelt.py
    model/       edges.py, gravity.py, hurdle.py, spillover.py, simulate.py
    jev/         classifier interface, mock, real client
    api/         FastAPI app, routers, websocket
    export/      precompute JSON for the frontend
  data/          raw/ (gitignored), processed/ (gitignored), trace.duckdb (gitignored)
  tests/
```

### T2. World Bank ingest
- Client per the skill: explicit `source`, paginate every page, keep nulls, keep `lastupdated`, bounded retries, on-disk cache.
- Pull every indicator in DATA_SOURCES.md for all economies, years 2005 to latest, into long table `wb_indicators`.
- Pull `/country` into `countries`, drop aggregates.
- Write a provenance file `data/processed/wb_manifest.json` (code, source, retrieved_at, API URL, rows).

### T3. External ingest
UNODC IDS (verify download access first; if a login is required, stop and tell Markandeya), WDR 2026 annex tables, GI-TOC OC Index, HRI table, CEPII GeoDist. Keep raw files out of git; write download scripts so anyone can reproduce.

### T4. Edges and confidence
Build `edges` from IDS hops; normalize volume within drug; compute confidence per SYSTEM_DESIGN.md section 6.

### T5. Models
PPML gravity baseline, LightGBM hurdle, SHAP drivers, backtest (train through 2019, test 2020 to 2024), Afghan ban test. Save metrics to `backend/data/processed/metrics.json`.

### T6. Spillover risk
Exposure, vulnerability, protection, combined score; hypothesis test (does exposure add predictive power beyond vulnerability?).

### T7. Export and API
Precompute JSON matching the contract exactly; FastAPI serves it. Add a test that validates every response against `contracts/openapi.yaml`.

### T8. Live Wire
GDELT poll every 15 minutes, dedupe, classify via `JevClassifier` interface. `MockJevClassifier` (keyword + simple rules) is used until `TYPESAFE_API_KEY` exists. Real client pinned to `jev-1.13.0`. Dates come from GDELT, never Jev. Anomaly = confident event on an edge the model gave under 10 percent probability.

### T9. Shock simulator
Structured shocks first (cultivation multiplier, legalization flag, customs efficiency delta); plain-English parsing via LLM second.

## Rules
- Commit small, push to `main` often, `git pull --rebase` first.
- Never commit secrets or raw data. Check `.gitignore` before adding files.
- AI citation header in every file you write, and a line in `docs/AI_USAGE.md` per session.
- Never break the contract silently. Contract changes: own commit, fixtures updated, CHANGELOG_CONTRACT.md entry.
- Design boundary: no feature, field, or ranking that shows where enforcement is weak.
- Ask Markandeya before anything destructive (deleting data, force push, rewriting history).
