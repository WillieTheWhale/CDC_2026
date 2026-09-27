# Contract Changelog

Every change to `contracts/` gets a dated line here so the frontend knows to pull.

| Date | Change | Breaking? |
|---|---|---|
| 2026-09-26 | v1.0.0 created: `openapi.yaml` (12 endpoints, envelope `{meta,data}`), `websocket.md`, 15 fixtures in `contracts/fixtures/` | n/a (initial) |
| 2026-09-26 | Fixtures regenerated from real pipeline output via the live API (`uv run trace export --fixtures`): real routes 2011-2024, 2025 predictions, risk board, COL profile, simulate, metrics, Live Wire. Shapes unchanged. Live Wire fixtures are replayed synthetic headlines (`sample.trace.local`) because GDELT is unavailable (see BLOCKERS.md). | No |
| 2026-09-26 | Fixtures regenerated after the SQLite v2 migration: observed years now 2006-2024, risk years 2008-2025, HRI protection per edition (`harm_reduction.year` = edition in force). Shapes unchanged. | No |
| 2026-09-26 | Fixtures regenerated: `simulate.json` baseline scores now equal `risk.json` (baseline fix); Live Wire fixtures classified by Reflex v0.2 (`classifier: "reflex-0.2.0"`). Shapes unchanged. | No |
| 2026-09-26 | Added People endpoints: `GET /api/people` (search, zoom tier, bbox, country, cursor paging; `meta.total`, `meta.next_cursor`), `GET /api/people/countries`, `GET /api/people/network` (`meta.total_connections`), `GET /api/people/{person_id}`. Schemas `Person`, `PersonRegion` (country-level only), `PersonEvent`, `Organization`, `Connection`, `PeopleSource`. Fixtures `people.json`, `people_countries.json`, `people_network.json`, `person.json`. Semantics match `frontend/lib/people-query.ts`. | No (additive) |
