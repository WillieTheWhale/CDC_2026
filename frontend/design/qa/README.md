<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Frontend verification — 2026-09-26

The connected browser was used for interaction, screenshots, and visual iteration. The requested tool named Razor is not exposed in the available tool inventory; clarification remains pending. This is browser verification, not a claim of a Razor run.

## Evidence

| Requirement | Current evidence |
|---|---|
| Reference-led colorful world atlas | `atlas-desktop.jpg` and `atlas-mobile.jpg`: warm ivory, orange/violet dot geography, compact panels, no decorative eyebrow labels. Owner reference inspected directly. |
| Figma-authored identity and animation | `../figma-assets.md` records the live Figma file, nodes, exports, and MCP motion context. The route node 2:49 screenshot was successfully retrieved again during final verification. The UI uses the exported path geometry and pulse tracks. |
| Adobe typography | Published Forma DJR Text/Display/Mono kit loads; browser `document.fonts.check` passed at desktop and mobile widths. No private Adobe token is needed by the client. |
| Map interactions | Physical country click selected Brazil; direct corridor click selected ECU → DEU with 80% confidence and three drivers. Zoom, pan, reset, drug filters, confidence cutoff, and layer toggles exercised. Fixed MapLibre's single-world constraint so zoom-out and world fit work. |
| Timeline | Keyboard year selection reached 2023 with explicit empty observations; reset restored the 2025 snapshot. Play advanced to the final year and stopped; immediate pause from 2011 stopped playback. No unavailable years are fabricated. |
| Country evidence | `COL <GO>` opened the 2025 Colombia profile, score 64.5, harm-reduction coverage, source/year citations, and World Bank API links. Other countries retain available risk summaries and clearly report missing detailed snapshots. |
| Risk and comparison | Forty rows, country filter, numeric sorting, trend sparklines, and `COMPARE COL PER` exercised. Comparison showed 64.5 and 73.1. Desktop panel dragging works; narrow panels stack. |
| Scenarios | Saved Colombia 50% cultivation scenario displayed 25 changed routes and 20 risk deltas. View on map updated corridor volumes. A baseline discrepancy is visibly disclosed and logged in `docs/CONTRACT_REQUESTS.md`. Unsupported custom scenarios show an API-required error. |
| Livewire | Replay rotates the saved synthetic events. Selecting a story opens its details and pins a Figma beacon on the map. Synthetic sources remain labeled in either data mode. WebSocket reconnect and frame parsing are implemented, but a real live server session was not exercised in this browser run. |
| Markets | Fifty-seven series; drug/market filters verified. Fifteen null year-over-year values render as unavailable rather than NaN. |
| Experiment | `experiment-desktop.jpg`: Afghanistan and Myanmar cultivation series selected by ID, correct hectares and 2015–2025 range. Before/predicted/actual corridor values and saved metrics render. The unsupported spillover hypothesis is preserved verbatim. |
| Keyboard and mobile | 390×844 has no horizontal page overflow. Named search control opens commands. Selection scrolls country details into view; closing returns scroll position to zero. Modal focus trapping, Escape, and focus restoration checked. |
| Data boundary | `npm test`: six tests pass for commands, refusal boundary, snapshot-year honesty, exact saved-scenario matching, live request parameters/envelopes, and POST/error behavior. Live tests intercept fetch; they are not backend end-to-end tests. |
| Runtime/build | TypeScript check passed. Production build passed after final map fixes. A new mobile browser tab produced no warning/error logs. The earlier hot-refresh style-loading error was corrected by guarding map style access. |

## Screenshots

These JPEGs are native browser viewport captures, not generated mockups or stitched full-page captures:

- `atlas-desktop.jpg` — 1440×960.
- `atlas-mobile.jpg` — 390×844.
- `experiment-desktop.jpg` — 1440×960.

`scripts/save-browser-shot.mjs` receives captured bytes through a local form on 127.0.0.1:8766. It does not automate the browser or send images to an external service.

## Remaining verification limits

- Razor-specific execution remains unverified because no such tool is available in this session.
- Reduced-motion behavior is implemented in Motion, CSS, and map transitions; an OS-level reduced-motion toggle was not exercised.
- Full live-backend integration and a deployed Adobe domain remain separate from this snapshot frontend delivery. Setup is in `../../README.md`.
