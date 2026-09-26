# Contract Requests (frontend to backend)

Frontend: add a row when you need a field or endpoint changed. Backend: resolve it, update the contract, and log it in CHANGELOG_CONTRACT.md.

| Date | Requested by | Endpoint | Request | Status |
|---|---|---|---|---|
| 2026-09-26 | Owner via ChatGPT data-collection task | Backend storage (no API shape change) | Owner selected SQLite as the canonical collected-data DB, superseding the earlier DuckDB plan. See `data_collection/README.md`; use the published `trace.sqlite` snapshot and its provenance/coverage tables, keep JSON for API exports only, and adapt backend DB access accordingly. Full source histories are retained; do not backfill later survey editions into earlier years. | Collection in progress; backend adapter migration requested |
