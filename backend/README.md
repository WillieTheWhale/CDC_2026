<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# TRACE backend

Python 3.11 data pipeline, models, and FastAPI server for TRACE (2026 Carolina Data Challenge, Graduate track).
The API contract is [`../contracts/openapi.yaml`](../contracts/openapi.yaml) and [`../contracts/websocket.md`](../contracts/websocket.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.11 itself.

```bash
python3 data_collection/manage.py download   # canonical SQLite archive (v2, ~1.2 GB, checksum-verified)
cd backend
uv sync
```

**Storage (migrated from DuckDB on 2026-09-26).** The canonical data is the SQLite archive built by `data_collection/` (`data_collection/work/trace.sqlite`, release `data-2026-09-26-v2`). The backend opens it read-only and attaches it as `archive`. Everything the pipeline derives goes into a separate `backend/data/derived.sqlite`: model inputs, edges, predictions and risk scores. Both files are gitignored. On Windows the downloader's final rename can fail with a file lock after a successful extract (see `docs/BLOCKERS.md`); if so, verify `trace.sqlite.part` against the `sha256` in `data_collection/snapshot.json` and rename it.

Optional: copy `../.env.example` to `../.env`. Nothing is required; every key has a fallback.

| Variable | Effect |
|---|---|
| `TYPESAFE_API_KEY` | Enables the real Jev classifier (`uv sync --extra jev`, pinned `JEV_MODEL=jev-1.13.0`). Empty = mock classifier. |
| `ANTHROPIC_API_KEY` | Plain-English scenario parsing falls back to Claude (`claude-opus-5`, structured output) when the rule parser finds no shock (`uv sync --extra llm`). |
| `GDELT_POLL_MINUTES` | Live Wire poll interval (default 15). |
| `TRACE_ARCHIVE_PATH` | Canonical SQLite archive (default `data_collection/work/trace.sqlite`). |
| `TRACE_DB_PATH` | Derived SQLite for model tables (default `backend/data/derived.sqlite`). |
| `CORS_ORIGINS` | Comma-separated allowed origins (default `http://localhost:3000`; `*.vercel.app` is always allowed). |

## One command: the whole pipeline

```bash
uv run trace pipeline
```

This reads the SQLite archive, derives model inputs, trains the models, runs the backtests and experiments, scores risk, and exports API JSON. It takes under a minute. Stages can be run one at a time:

| Stage | Command | Output |
|---|---|---|
| Prepare | `uv run trace prepare` | From the archive: `wb_panel`, `seizures_country` (latest annex edition per country-year, 2006-2024), `model_distances`, `model_prices`, `model_protection` (HRI per edition, 2008-2024), `model_cannabis_regulation`, `corridors_seed`, and the provenance manifests |
| Edges | `uv run trace edges` | `edges` (corridor x drug x year, kg estimate, 0-100 confidence) |
| Models | `uv run trace models` | PPML gravity, LightGBM hurdle, SHAP, 2019 backtest, Afghan ban test, `predictions`, `data/processed/metrics.json` |
| Risk | `uv run trace risk` | `risk_scores` for every country and year (2008-2025; starts with the first HRI edition), hypothesis test in `metrics.json` |
| Export | `uv run trace export [--fixtures] [--route-snapshots]` | `data/processed/api/*.json`; `--fixtures` also regenerates `contracts/fixtures/` and `tests/data/api_sample/` from the live API; `--route-snapshots` writes every year's full routes and risk (contract-validated) to `frontend/public/data/routes/` and `risk/` for the frontend's no-API mode |

## Run the API

```bash
uv run trace serve            # http://127.0.0.1:8000, docs at /docs
uv run trace serve --host 0.0.0.0 --port 8000
```

The API serves precomputed JSON, so the demo never waits on a model. Only `POST /api/simulate` runs a model, in about 1 second. Endpoints: `/api/meta`, `/api/countries`, `/api/routes`, `/api/country/{iso3}`, `/api/risk`, `/api/prices`, `POST /api/simulate`, `/api/experiments/afghan-ban`, `/api/metrics`, `/api/livewire`, `WS /ws/livewire`, `POST /api/command`, and People: `/api/people`, `/api/people/countries`, `/api/people/network`, `/api/people/{person_id}` (reads the curated `frontend/data/people/manifest.json`, or `TRACE_PEOPLE_MANIFEST`; with `TRACE_PEOPLE_REMOTE=1`, as on Vercel, it re-reads GitHub main every `TRACE_PEOPLE_REFRESH_SECONDS`, default 600). Route evidence: `/api/route-evidence`, `/sources`, `/{evidence_id}`. Evidence drilldown: `/api/evidence/values`, `/api/evidence/value/{value_id}`, `/api/evidence/health/{iso3}`, `/api/evidence/overdose`, `/api/evidence/research-model`.

Frontend: set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

**Live API (Vercel):** https://trace-api-six.vercel.app (docs at `/docs`). **Live website:** https://trace-atlas-gules.vercel.app. It is deployed from the repo root with `vercel deploy --prod`; the project `trace-atlas` has root directory `frontend/`, and `.vercelignore` uploads only `frontend/` and `contracts/`. For the deployed frontend, set `NEXT_PUBLIC_API_URL=https://trace-api-six.vercel.app`. CORS allows `localhost:3000` and any `*.vercel.app` origin.

To redeploy: `.venv/Scripts/python scripts/build_vercel.py`, then `cd .vercel_deploy && vercel deploy --prod`. The build script stages a self-contained package (about 264 MB, of which 137 MB is the Reflex ONNX model; the Linux Python dependencies add about 406 MB, so the function needs Vercel large functions, `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`): the code, `data/processed/api/`, the route model, and a slim SQLite that holds the derived tables plus `countries` and `cultivation`. It leaves out the 1.2 GB archive. On Vercel the Live Wire replays its backlog without polling GDELT and classifies with Reflex through the torch-free ONNX backend (`TRACE_CLASSIFIER=reflex`, `TRACE_REFLEX_BACKEND=onnx` in the generated `app.py`; onnxruntime and tokenizers in its requirements). The ONNX model loads on the first Live Wire read, never on another endpoint's cold start. If it cannot load, the wire falls back to the keyword mock, logs an error and says so in the GDELT source note of `/api/meta` (`livewire_classifier` becomes `mock`). Build the ONNX files first (see Reflex below); `build_vercel.py --no-reflex` deploys the mock instead. LightGBM needs `libgomp.so.1`, which the runtime lacks, so the simulator loads scikit-learn's bundled copy on first use; onnxruntime does not need it.

To deploy elsewhere (Render or Railway): run `uv run trace pipeline` during build, then start with `uv run trace serve --host 0.0.0.0 --port $PORT`. The simulator needs `data/derived.sqlite`, the archive tables `countries` and `cultivation`, and `data/processed/models/`. Every other endpoint needs only `data/processed/api/`.

## Tests

```bash
uv run pytest        # 103 tests
uv run ruff check .
```

`tests/test_api_*.py` call every endpoint and validate each response against `contracts/openapi.yaml`. They cover success paths, 404/422 error shapes, the WebSocket frames, and a check that every contract path is served. They use the real export when present, or the committed 20-country sample in `tests/data/api_sample/` otherwise. Simulator tests skip when the pipeline has not run.

## How it works (short)

1. **World Bank (required core).** 24 indicators from `docs/DATA_SOURCES.md`, all economies, 1960-2025 in the archive (models use 2000 onward). They are pulled programmatically by `data_collection/world_bank.py`. The backend's own client in `trace_backend/wb/` follows the same rules. It uses `format=json`, an explicit `source` (2 = WDI, 3 = WGI), reads every page, keeps nulls, retries with backoff, catches JSON error bodies returned with HTTP 200, and caches raw pages on disk. Provenance per indicator (API URL, retrieved_at, lastupdated, rows) is in `wb_manifest.json`. API responses carry `{code, source_id, year, value}`.
2. **Route network.** The public UNODC IDS release has no departure, transit, or destination fields (see `docs/BLOCKERS.md`). Edges are therefore 234 documented corridors (cited in `trace_backend/seed/`) plus land-border neighbours of seizure hubs. Yearly volumes come from seizure-anchored gravity allocation over real national seizure totals and cultivation. Seizures come from WDR annex editions 2012, 2015, 2020 and 2026 (2006-2024, latest edition per country-year, no backcast); cultivation comes from annex 6.x. `kg` is seizure-scale, not total trafficked volume.
3. **Confidence (0-100).** 30 seizures at both ends, 20 price gradient, 20 OC Index market score >= 5 at both ends, 10 live news, 10 cultivation at origin, 10 documented corridor.
4. **Models.** PPML gravity baseline (GDP, population, distance, border, price gap, drug fixed effects). LightGBM hurdle: P(active next year) times volume if active, using lagged volume, node seizures, cultivation, price gap, OC Index, World Bank governance, logistics, gravity, and conflict for both ends. SHAP drivers exclude last year's volume and the customs detection-bias control.
5. **Shocks.** Cultivation, legalization, and customs shocks edit the base-year state. The allocation re-runs, cascades downstream (elasticity 0.7 = partial substitution) and displaces volume to alternative destinations, and then the hurdle model forecasts the next year.
6. **Spillover risk.** 0.45 exposure (harm-weighted route volume) + 0.35 vulnerability (World Bank percentiles) + 0.20 (100 - protection). Protection comes from the HRI edition in force that year (2008-2024), scored over the services that edition reports.

## Results (from `data/processed/metrics.json`)

| Test | Result |
|---|---|
| Backtest (train on targets 2007-2019, 8,242 corridor-years; test 2020-2024, 3,170) | Hurdle: AUC **0.881**, Spearman **0.578**, precision@20 **0.48**. Gravity PPML: 0.583 / 0.378 / 0.34. Persistence: 0.815 / 0.477 / 0.42 |
| Afghan ban (train through 2021, inject a 95% opium cut at the 2022 state, forecast 2023) | Direction correct on **9 of 13** major heroin corridors (Spearman 0.38). Southeast Asian share of heroin corridor volume: 4.9% in 2022, **13.9% predicted** (4.5% without the shock), **13.4% actual** |
| Spillover hypothesis (exposure predicts a 20%+ rise in homicide or HIV within 3 years, beyond vulnerability) | **Not supported** (n = 4,186). Exposure level is associated with *lower* odds (OR 0.90 per 10 points, p < 1e-5), driven by homicide (OR 0.86); HIV shows no effect (p = 0.78). Exposure change: OR 0.97, p = 0.56. CV AUC 0.705 without exposure vs 0.712 with it. A likely reason: seizure-anchored exposure also tracks enforcement capacity. Reported as is, per SYSTEM_DESIGN section 2 |
| Live Wire mock classifier (100 synthetic headlines, provisional labels) | is_event 0.81, event_type 0.80, drug 0.89, origin 0.89, destination 0.52, size 0.96. An upper bound: the rules and labels were written together. Re-run on team-labelled GDELT articles and with Jev |

## Known limits

- Corridor volumes are model estimates anchored on seizures. Seizures measure enforcement as well as trafficking.
- HRI protection uses the edition in force each year. Risk scores therefore start in 2008, and fields an edition did not track are left out of that year's score rather than counted as missing services.
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

### Earlier DuckDB run vs the SQLite archive
The first build (DuckDB, annex 2015-2024 plus an IDS backcast to 2011) scored hurdle AUC 0.924, Afghan direction 12 of 14, and SEA share 12.7% predicted vs 14.1% actual. The archive run trains on real seizures from 2006 with no backcast, and has more test-period corridors (634 candidates). AUC is lower (0.881 vs 0.924) but still well above both baselines. The Afghan share forecast is closer (13.9% vs 13.4% actual), while fewer individual corridor directions are right (9 of 13). The archive numbers above are the current ones.

## Reflex: TRACE's own System One model

Reflex re-implements the documented behaviour of TypeSafe's Jev (typed Choice/Score/Noul answers with calibrated probabilities) on an open NLI encoder. Its spec, the Parity Scale and results are in [`docs/REFLEX_SPEC.md`](../docs/REFLEX_SPEC.md).

```bash
uv sync --extra reflex                 # torch, transformers, datasets
uv run trace reflex-download           # published v0.2 weights (GitHub release reflex-v0.2.0, SHA-256 verified)
uv run trace reflex-data               # build open-dataset + UNODC-record splits
uv run trace reflex-train              # CPU training (hours on a laptop)
uv run trace reflex-eval --model-dir data/reflex/model
```

To train on a GPU with the Google Colab CLI (Linux, macOS or WSL, signed in with `gcloud auth application-default login`), follow the steps in `scripts/colab_reflex.py`. Both versions trained and evaluated in about 7 minutes on a T4, using 0.41 compute units. The Live Wire uses Reflex automatically when `data/reflex/model/reflex.json` exists. `TRACE_CLASSIFIER=mock|reflex|jev` forces a choice.

**Production runtime (ONNX, no torch).** `Reflex.load()` uses onnxruntime + tokenizers when `TRACE_REFLEX_BACKEND=onnx` or when torch is not installed (extra `reflex-onnx`). The ONNX files live in `data/reflex/onnx/` (gitignored: `model.emb8.onnx`, `tokenizer.json`, `reflex.json`); the Vercel build copies the default variant into the package's `data/reflex/model/`. Rebuild and check them with:

```bash
uv pip install onnx onnxruntime                                # export-time only (torch comes from the reflex extra)
.venv/Scripts/python scripts/export_reflex_onnx.py             # default emb8; --variant all also writes fp32, int8-ffn, int8
.venv/Scripts/python scripts/reflex_onnx_parity.py             # parity with torch -> trace_backend/reflex/results/onnx_parity.json
```

### Reflex service (live classifier)

Deploy order: build the ONNX files once (`scripts/export_reflex_onnx.py`), then the Reflex service
(`scripts/build_vercel_reflex.py`, then `cd .vercel_reflex && vercel deploy --prod`, project `trace-reflex`), then the API
(`scripts/build_vercel.py --reflex-url https://trace-reflex.vercel.app`). The API bundle stays about 120 MB and
never loads torch or onnxruntime.

