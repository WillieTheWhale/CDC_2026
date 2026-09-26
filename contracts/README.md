<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# contracts/

The seam between `backend/` and `frontend/`. Source of truth for every response shape.

- [`openapi.yaml`](openapi.yaml): REST endpoints (OpenAPI 3.1). Every response is `{ "meta": ResponseMeta, "data": ... }`.
- [`websocket.md`](websocket.md): `WS /ws/livewire` frames.
- [`fixtures/`](fixtures/): one realistic example per endpoint. The frontend reads these until `NEXT_PUBLIC_API_URL` is set.

| Fixture | Endpoint | Schema |
|---|---|---|
| `meta.json` | `GET /api/meta` | `MetaResponse` |
| `countries.json` | `GET /api/countries` | `CountriesResponse` (pulled live from the World Bank `/country` API) |
| `routes_observed.json` | `GET /api/routes?mode=observed` | `RoutesResponse` |
| `routes_predicted.json` | `GET /api/routes?mode=predicted` | `RoutesResponse` |
| `country_COL.json` | `GET /api/country/COL` | `CountryResponse` |
| `risk.json` | `GET /api/risk` | `RiskResponse` |
| `prices.json` | `GET /api/prices` | `PricesResponse` |
| `simulate_request.json` / `simulate.json` | `POST /api/simulate` | `SimulateRequest` / `SimulateResponse` |
| `afghan_ban.json` | `GET /api/experiments/afghan-ban` | `AfghanBanResponse` |
| `metrics.json` | `GET /api/metrics` | `MetricsResponse` |
| `livewire.json` | `GET /api/livewire` | `LivewireResponse` |
| `ws_livewire.json` | `WS /ws/livewire` | frames per `websocket.md` |
| `command_request.json` / `command.json` | `POST /api/command` | `CommandRequest` / `CommandResponse` |

Validate fixtures: `cd backend && uv run python -m trace_backend.contract`.

Fixtures from T0 are illustrative (plausible numbers, real codes). Once the pipeline has run, fixtures are regenerated from real output with `uv run trace export --fixtures`; the shapes do not change.
