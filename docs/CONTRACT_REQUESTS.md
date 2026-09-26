# Contract Requests (frontend to backend)

Frontend: add a row when you need a field or endpoint changed. Backend: resolve it, update the contract, and log it in CHANGELOG_CONTRACT.md.

| Date | Requested by | Endpoint | Request | Status |
|---|---|---|---|---|
| 2026-09-26 | Owner via ChatGPT data-collection task | Backend storage (no API shape change) | Owner selected SQLite as the canonical collected-data DB, superseding the earlier DuckDB plan. See `data_collection/README.md`; use the published `trace.sqlite` snapshot and its provenance/coverage tables, keep JSON for API exports only, and adapt backend DB access accordingly. Full source histories are retained; do not backfill later survey editions into earlier years. | Collection in progress; backend adapter migration requested |
| 2026-09-26 | Owner via ChatGPT data-collection task | Backend SQLite adapter (no API shape change) | Verified 37-table SQLite snapshot: `data_collection/snapshot.json`, GitHub release `data-2026-09-26-v1`; run `python3 data_collection/manage.py download`. Preserve raw observation years, edition/provenance fields and nulls. Existing DuckDB adapter must be migrated before pointing `TRACE_DB_PATH` at this file; derive route/model features separately and retain API shapes. | Collection complete; backend integration requested |

- 2026-09-26 — Frontend integration: regenerated `simulate.json` reports a Colombia baseline score of 68.1, while the same-year `risk.json` and `country_COL.json` report 64.5. Please align baseline normalization/model metadata or document why scenario and saved-profile baselines differ. The frontend preserves both values and explicitly identifies the different baseline. No contract or backend files changed.
