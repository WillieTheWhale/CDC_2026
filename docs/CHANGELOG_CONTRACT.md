# Contract Changelog

Every change to `contracts/` gets a dated line here so the frontend knows to pull.

| Date | Change | Breaking? |
|---|---|---|
| 2026-09-26 | v1.0.0 created: `openapi.yaml` (12 endpoints, envelope `{meta,data}`), `websocket.md`, 15 fixtures in `contracts/fixtures/` | n/a (initial) |
| 2026-09-26 | Fixtures regenerated from real pipeline output via the live API (`uv run trace export --fixtures`): real routes 2011-2024, 2025 predictions, risk board, COL profile, simulate, metrics, Live Wire. Shapes unchanged. Live Wire fixtures are replayed synthetic headlines (`sample.trace.local`) because GDELT is unavailable (see BLOCKERS.md). | No |
