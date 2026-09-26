<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# TRACE historical SQLite collection

**Backend handoff, 2026-09-26:** the project owner explicitly selected **SQLite as the canonical collected-data database**, superseding the older DuckDB storage plan. Use `data_collection/work/trace.sqlite` after collection or snapshot download. Do not recollect these data into a separate JSON or DuckDB source of truth. JSON remains appropriate for API response exports. Existing backend code still uses DuckDB; changing its adapter and model-specific SQL is an integration task for the backend owner, not something this collection silently accomplishes.

This folder is owned by the data-collection task. Backend and frontend implementations are left to their current agents. Three collectors write separate SQLite shards; the coordinator merges completed shards with one writer. Download caches, working databases, and temporary files stay outside Git. The verified compressed snapshot is published as a GitHub release asset, with a versioned download manifest committed here.

## History policy

Store every available year for each chosen series. Do not discard older observations merely because another predictor began later. Preserve nulls, original units and country names, observation/edition years, source URLs, retrieval times, and source metadata. Never invent early observations by carrying later surveys backwards. The candidate long-history spine is **1990–2024 (35 calendar years)**: World Bank market-size and public-health series and UNODC published national price series span those years. The early price series cover far fewer countries and include source-provided estimates. Individual country, drug and indicator coverage differs, so the [coverage report](reports/coverage.md) gives observed annual denominators. Seizures and edition-based context enter only in their actual years. This archive is not a balanced or imputed model matrix.

The 24 World Bank variables in `backend/trace_backend/wb/indicators.py` define the core variable set. UNODC seizures, prices and cultivation; GI-TOC editions; HRI service observations; and CEPII geography supplement it. Live news and optional stretch datasets are separate from this historical collection.

## Collector ownership

| Collector | Output shard | Main tables |
| --- | --- | --- |
| `world_bank.py` | `work/world_bank.sqlite` | `countries`, `wb_indicators`, metadata and coverage |
| `unodc.py` | `work/unodc.sqlite` | case-level seizures, national totals, prices, cultivation, original source records |
| `context_sources.py` | `work/context.sqlite` | OC Index editions, harm-reduction services, geographic distances, original source records |

Collection code records failures explicitly. No synthetic fixture values, fabricated routes, or modeled backcasts belong in this archive. Public UNODC IDS does not expose origin/transit/destination fields; country-of-seizure observations must not be presented as directly observed routes.

API requests use caching, pagination validation, timeouts and bounded retries. World Bank calls use explicit source IDs and preserve missing observations. A request delay is a conservative client setting, not a claim about a published universal quota.

## Using the database

Run these commands from the repository root. The snapshot downloader uses only Python's standard library, checks the compressed and uncompressed SHA-256 hashes, checks SQLite integrity and foreign keys, and atomically installs the database. An interrupted or corrupt download leaves the previous database intact.

```sh
python3 data_collection/manage.py download
python3 data_collection/manage.py inspect
```

The [snapshot manifest](snapshot.json) records the release URL, SHA-256 hashes, integrity checks, and table counts. To reproduce the original collection instead:

```sh
uv sync --project backend
python3 data_collection/world_bank.py
backend/.venv/bin/python data_collection/unodc.py
backend/.venv/bin/python data_collection/context_sources.py
python3 data_collection/manage.py merge
backend/.venv/bin/python -m pytest data_collection/tests -q
```

Collectors can run concurrently because each owns one shard. Run `merge` only after all three have finished successfully. The merger rejects conflicting table/index names and verifies each shard before replacing the canonical file. It preserves source table schemas, constraints and indexes, and records input checksums in `collection_shards`.

Read with standard SQLite, for example:

```python
import sqlite3
from pathlib import Path

path = Path("data_collection/work/trace.sqlite").resolve()
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as con:
    rows = con.execute("""
        SELECT iso3, year, code, source_id, value, lastupdated
        FROM wb_indicators
        WHERE iso3 = ? AND code = ? AND value IS NOT NULL
        ORDER BY year
    """, ("COL", "SP.POP.TOTL")).fetchall()
```

The existing backend `TRACE_DB_PATH` setting alone is **not** a migration: its adapter still opens DuckDB, whose file format and some SQL differ. The backend owner must adapt that code before directing it to this SQLite file. Preserve the public API contract and compute derived model panels separately from the observational archive.

## Provenance and attribution

See the individual reports under `reports/` for official source citations, units, coverage and limitations. Source licenses and third-party terms remain applicable. AI-assisted collection code and analysis are cited in `docs/AI_USAGE.md`; raw published measurements are not AI-generated.
