<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# TRACE backend

Python 3.11 data pipeline, models, and FastAPI server for TRACE (2026 Carolina Data Challenge, Graduate track).
The API contract is [`../contracts/openapi.yaml`](../contracts/openapi.yaml) and [`../contracts/websocket.md`](../contracts/websocket.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.11 itself.

```bash
cd backend
uv sync
```

Optional: copy `../.env.example` to `../.env`. Nothing is required; every key has a fallback.

| Variable | Effect |
|---|---|
| `TYPESAFE_API_KEY` | Enables the real Jev classifier (`uv sync --extra jev`, pinned `JEV_MODEL=jev-1.13.0`). Empty = mock classifier. |
| `ANTHROPIC_API_KEY` | Plain-English scenario parsing falls back to Claude (`claude-opus-5`, structured output) when the rule parser finds no shock (`uv sync --extra llm`). |
| `GDELT_POLL_MINUTES` | Live Wire poll interval (default 15). |
| `TRACE_DB_PATH` | DuckDB location (default `backend/data/trace.duckdb`). |
| `CORS_ORIGINS` | Comma-separated allowed origins (default `http://localhost:3000`; `*.vercel.app` is always allowed). |

## One command: the whole pipeline

```bash
uv run trace pipeline
```

This downloads and caches every source (about 250 MB of raw files, gitignored), builds DuckDB, trains the models, runs the backtests and experiments, scores risk, and exports API JSON. It takes about 2 minutes once raw files are cached. Add `--refresh` to re-download. Stages can be run one at a time:

| Stage | Command | Output |
|---|---|---|
| World Bank ingest | `uv run trace wb` | `countries`, `wb_indicators` (long, nulls kept), `wb_panel`, `data/processed/wb_manifest.json` |
| External ingest | `uv run trace ingest` | UNODC IDS cases, WDR annex seizures/cultivation/prices/cannabis regulation, OC Index, HRI, CEPII, corridor seed, `ingest_manifest.json` |
| Edges | `uv run trace edges` | `edges` (corridor x drug x year, kg estimate, 0-100 confidence) |
| Models | `uv run trace models` | PPML gravity, LightGBM hurdle, SHAP, 2019 backtest, Afghan ban test, `predictions`, `data/processed/metrics.json` |
| Risk | `uv run trace risk` | `risk_scores` for every country and year (2011-2025), hypothesis test in `metrics.json` |
| Export | `uv run trace export [--fixtures]` | `data/processed/api/*.json`; `--fixtures` also regenerates `contracts/fixtures/` and `tests/data/api_sample/` from the live API |

## Run the API

```bash
uv run trace serve            # http://127.0.0.1:8000, docs at /docs
uv run trace serve --host 0.0.0.0 --port 8000
```

The API serves precomputed JSON, so the demo never waits on a model. Only `POST /api/simulate` runs a model, in about 1 second. Endpoints: `/api/meta`, `/api/countries`, `/api/routes`, `/api/country/{iso3}`, `/api/risk`, `/api/prices`, `POST /api/simulate`, `/api/experiments/afghan-ban`, `/api/metrics`, `/api/livewire`, `WS /ws/livewire`, `POST /api/command`.

Frontend: set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

To deploy (Render or Railway): run `uv run trace pipeline` during build, then start with `uv run trace serve --host 0.0.0.0 --port $PORT`. The simulator needs `data/trace.duckdb` and `data/processed/models/`. Every other endpoint needs only `data/processed/api/`.

## Tests

```bash
uv run pytest        # 98 tests
uv run ruff check .
```

`tests/test_api_*.py` call every endpoint and validate each response against `contracts/openapi.yaml`. They cover success paths, 404/422 error shapes, the WebSocket frames, and a check that every contract path is served. They use the real export when present, or the committed 20-country sample in `tests/data/api_sample/` otherwise. Simulator tests skip when the pipeline has not run.

## How it works (short)

1. **World Bank (required core).** 24 indicators from `docs/DATA_SOURCES.md`, all economies, 2005-2026. The client uses `format=json`, an explicit `source` (2 = WDI, 3 = WGI), reads every page, keeps nulls, retries with backoff, catches JSON error bodies returned with HTTP 200, and caches raw pages on disk. Provenance per indicator (API URL, retrieved_at, lastupdated, rows) is in `wb_manifest.json`. API responses carry `{code, source_id, year, value}`.
2. **Route network.** The public UNODC IDS release has no departure, transit, or destination fields (see `docs/BLOCKERS.md`). Edges are therefore 234 documented corridors (cited in `trace_backend/seed/`) plus land-border neighbours of seizure hubs. Yearly volumes come from seizure-anchored gravity allocation over real national seizure totals (WDR annex 7.1; calibrated IDS backcast for 2011-2014) and cultivation (annex 6.x). `kg` is seizure-scale, not total trafficked volume.
3. **Confidence (0-100).** 30 seizures at both ends, 20 price gradient, 20 OC Index market score >= 5 at both ends, 10 live news, 10 cultivation at origin, 10 documented corridor.
4. **Models.** PPML gravity baseline (GDP, population, distance, border, price gap, drug fixed effects). LightGBM hurdle: P(active next year) times volume if active, using lagged volume, node seizures, cultivation, price gap, OC Index, World Bank governance, logistics, gravity, and conflict for both ends. SHAP drivers exclude last year's volume and the customs detection-bias control.
5. **Shocks.** Cultivation, legalization, and customs shocks edit the base-year state. The allocation re-runs, cascades downstream (elasticity 0.7 = partial substitution) and displaces volume to alternative destinations, and then the hurdle model forecasts the next year.
6. **Spillover risk.** 0.45 exposure (harm-weighted route volume) + 0.35 vulnerability (World Bank percentiles) + 0.20 (100 - protection from HRI services).

## Results (from `data/processed/metrics.json`)

| Test | Result |
|---|---|
| Backtest (train on targets through 2019, test 2020-2024, 3,380 corridor-years) | Hurdle: AUC **0.924**, Spearman **0.666**, precision@20 **0.50**. Gravity PPML: 0.611 / 0.501 / 0.37. Persistence: 0.857 / 0.649 / 0.42 |
| Afghan ban (train through 2021, inject a 95% opium cut at the 2022 state, forecast 2023) | Direction correct on **12 of 14** major heroin corridors (Spearman 0.43). Southeast Asian share of heroin corridor volume: 5.3% in 2022, **12.7% predicted** (5.1% without the shock), **14.1% actual** |
| Spillover hypothesis (exposure predicts a 20%+ rise in homicide or HIV within 3 years, beyond vulnerability) | **Not supported.** Exposure level is associated with *lower* odds (OR 0.90 per 10 points, p = 1.3e-05). Exposure change: OR 0.96, p = 0.60. CV AUC 0.686 without exposure vs 0.700 with it. A likely reason: seizure-anchored exposure also tracks enforcement capacity. Reported as is, per SYSTEM_DESIGN section 2 |
| Live Wire mock classifier (100 synthetic headlines, provisional labels) | is_event 0.81, event_type 0.80, drug 0.89, origin 0.89, destination 0.52, size 0.96. An upper bound: the rules and labels were written together. Re-run on team-labelled GDELT articles and with Jev |

## Known limits

- Corridor volumes are model estimates anchored on seizures. Seizures measure enforcement as well as trafficking.
- HRI protection is the 2024 snapshot, applied to every year.
- GDELT is rate-limiting this network, so the Live Wire replays synthetic sample headlines (`sample.trace.local`, never counted as route evidence). It switches to live GDELT automatically when requests succeed.
- Design boundary: customs efficiency (`LP.LPI.CUST.XQ`) is a model control only. It is never shown as a driver, a profile value, or a ranking. The command bar refuses questions about weak enforcement or avoiding detection.

## Layout

```
trace_backend/
  wb/        World Bank client, indicator registry, ingest
  ingest/    unodc_ids, unodc_annex, ocindex, hri, cepii, country names, orchestrator
  model/     edges, features, gravity, hurdle, train, shocks, spillover, scenario (parsers)
  jev/       JevClassifier interface, mock, real client, labelled eval set
  api/       FastAPI app, store, livewire (REST + WS), simulate + command
  export/    API JSON export, fixture regeneration
  seed/      cited corridor table
tests/       98 tests (unit, contract validation, WebSocket)
```
