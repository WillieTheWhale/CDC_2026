<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# TRACE historical SQLite collection

**Backend handoff, 2026-09-26:** the project owner explicitly selected **SQLite as the canonical collected-data database**, superseding the older DuckDB storage plan. Use `data_collection/work/trace.sqlite` after collection or snapshot download. Do not recollect these data into a separate JSON or DuckDB source of truth. JSON remains appropriate for API response exports. Existing backend code still uses DuckDB; changing its adapter and model-specific SQL is an integration task for the backend owner, not something this collection silently accomplishes.

This folder is owned by the data-collection task. Backend and frontend implementations are left to their current agents. Three collectors write separate SQLite shards; the coordinator merges completed shards with one writer. Download caches, working databases, and temporary files stay outside Git. A verified compressed snapshot and checksum will be published as a GitHub release asset, with a versioned download manifest committed here.

## History policy

Store every available year for each chosen series. Do not discard older observations merely because another predictor began later. Preserve nulls, original units and country names, observation/edition years, source URLs, retrieval times, and source metadata. Never invent early observations by carrying later surveys backwards. The coverage report distinguishes full historical storage, a candidate longitudinal analysis window, and sparse contemporary supplements. The database is an observational archive, not a balanced or imputed model matrix.

The 24 World Bank variables in `backend/trace_backend/wb/indicators.py` define the core variable set. UNODC seizures, prices and cultivation; GI-TOC editions; HRI service observations; and CEPII geography supplement it. Live news and optional stretch datasets are separate from this historical collection.

## Collector ownership

| Collector | Output shard | Main tables |
| --- | --- | --- |
| `world_bank.py` | `work/world_bank.sqlite` | `countries`, `wb_indicators`, metadata and coverage |
| `unodc.py` | `work/unodc.sqlite` | case-level seizures, national totals, prices, cultivation, original source records |
| `context_sources.py` | `work/context.sqlite` | OC Index editions, harm-reduction services, geographic distances, original source records |

Collection code records failures explicitly. No synthetic fixture values, fabricated routes, or modeled backcasts belong in this archive. Public UNODC IDS does not expose origin/transit/destination fields; country-of-seizure observations must not be presented as directly observed routes.

API requests use caching, pagination validation, timeouts and bounded retries. World Bank calls use explicit source IDs and preserve missing observations. A request delay is a conservative client setting, not a claim about a published universal quota.

## Provenance and attribution

See the individual reports under `reports/` for official source citations, units, coverage and limitations. Source licenses and third-party terms remain applicable. AI-assisted collection code and analysis are cited in `docs/AI_USAGE.md`; raw published measurements are not AI-generated.
