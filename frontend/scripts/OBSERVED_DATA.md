<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Observed SQLite export

The canonical historical database is the published [`data-2026-09-26-v2` SQLite release](https://github.com/WillieTheWhale/CDC_2026/releases/tag/data-2026-09-26-v2). This frontend keeps a read-only JSON export of the four source shards that add drug-specific health, market, research and cited context records. These are observed or publisher-estimated records, separate from the route, risk and scenario model API and fixtures. The exporter uses Python's standard library and checks the pinned SHA-256 and byte size of each input before reading it.

From the repository root, download and export with:

```sh
mkdir -p /tmp/trace-observed-v2
gh release download data-2026-09-26-v2 --repo WillieTheWhale/CDC_2026 \
  --dir /tmp/trace-observed-v2 --clobber \
  --pattern health.sqlite --pattern markets.sqlite \
  --pattern research.sqlite --pattern evidence.sqlite
python3 frontend/scripts/export-observed-v2.py \
  --health /tmp/trace-observed-v2/health.sqlite \
  --markets /tmp/trace-observed-v2/markets.sqlite \
  --research /tmp/trace-observed-v2/research.sqlite \
  --evidence /tmp/trace-observed-v2/evidence.sqlite
TRACE_SHARDS_DIR=/tmp/trace-observed-v2 python3 frontend/scripts/test-observed-v2.py
```

The output defaults to `frontend/public/data/observed-v2/`. `overview.json` holds source metadata, coverage summaries, eight claims and the research model result. `countries/ISO3.json` holds source observations and their coordinates, all derived research inputs, and model sample rows for one country. `us-overdose.json` contains US national provisional 12-month-ending CDC periods, including suppressed NULLs. The frontend loads these files on demand through `frontend/lib/observed-data.ts`. Each refresh overwrites these generated files and prunes country JSON files absent from the verified input. After the checks, the temporary downloads can be removed.

If the restored canonical `data_collection/work/trace.sqlite` is available, pass its path to all four `--health`, `--markets`, `--research`, and `--evidence` arguments. The exporter then verifies the full database against the release manifest's SHA-256 and byte count. It does not turn national seizure locations into observed country-pair routes. Raw source worksheets remain in the SQLite release; the JSON contains only the fields needed by the frontend.
