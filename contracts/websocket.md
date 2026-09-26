<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# WebSocket contract: `WS /ws/livewire`

Pushes classified Live Wire events and anomaly flags. The REST fallback is `GET /api/livewire` (same `LiveEvent` shape, see `openapi.yaml`).

- URL: `ws://<host>/ws/livewire` (e.g. `ws://localhost:8000/ws/livewire`)
- Optional query: `?drug=cocaine` filters events to one Live Wire drug label.
- All frames are JSON text frames with the envelope `{ "type": <string>, "data": <object> }`.
- The server never expects client messages. Clients may send `{"type":"ping"}`; the server replies with `pong`.
- Fixture replay of a full session: [`fixtures/ws_livewire.json`](fixtures/ws_livewire.json) (array of frames in order).

## Frame types

| `type` | When | `data` |
|---|---|---|
| `hello` | Immediately on connect | `{ "classifier": "mock" \| "jev-1.13.0", "poll_minutes": 15, "server_time": ISO8601, "backlog": LiveEvent[] }` (up to the 20 most recent events) |
| `event` | A newly classified event passes the 0.6 confidence threshold | `LiveEvent` |
| `anomaly` | A confident event lands on an edge the route model gave under 10 percent probability | `LiveEvent` with `is_anomaly: true` and `anomaly_reason` set |
| `heartbeat` | Every 20 seconds | `{ "server_time": ISO8601, "next_poll_at": ISO8601, "events_total": int }` |
| `pong` | Reply to a client `ping` | `{ "server_time": ISO8601 }` |

An anomaly is sent as an `anomaly` frame only (not duplicated as `event`).

## LiveEvent

```json
{
  "id": "gdelt-5c1f0e7a",
  "published_at": "2026-09-26T13:45:00Z",
  "title": "Ecuador navy seizes 4.2 tonnes of cocaine bound for Belgium",
  "url": "https://example.org/article",
  "source_domain": "example.org",
  "language": "English",
  "event_type": "seizure",
  "drug": "cocaine",
  "origin": "ECU",
  "transit": null,
  "destination": "BEL",
  "size": "record",
  "is_event": 0.94,
  "route_mentioned": 0.88,
  "confidence": 0.86,
  "is_anomaly": false,
  "anomaly_reason": null,
  "edge_probability": 0.91,
  "classifier": "mock",
  "lat": -1.83,
  "lon": -78.18
}
```

Rules (from SYSTEM_DESIGN section 7):
- `published_at` always comes from GDELT metadata, never from the classifier.
- Events with `confidence < 0.6` are never pushed.
- Until a `TYPESAFE_API_KEY` exists the classifier is `mock` (keyword rules). The real client is pinned to `jev-1.13.0`.
