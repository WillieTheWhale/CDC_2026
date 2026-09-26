<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Frontend verification — 2026-09-26

The connected browser was used for interaction, screenshots, and visual iteration. The owner clarified that “Razor” meant browser.

## Evidence

| Requirement | Current evidence |
|---|---|
| Reference-led colorful world atlas | `atlas-revision-world.jpg` and `atlas-revision-mobile.jpg`: white/cool-blue geography, fine exposure texture, distinct Figma drug keys, compact functional labels. |
| Figma-authored identity and animation | `../figma-assets.md` records the live Figma file, nodes, exports, and MCP motion context. The route node 2:49 screenshot was successfully retrieved again during final verification. The UI uses the exported path geometry and pulse tracks. |
| Adobe typography | Published Forma DJR Text/Display/Mono kit loads; browser `document.fonts.check` passed at desktop and mobile widths. No private Adobe token is needed by the client. |
| Map interactions | Physical country click selected Brazil; direct corridor click selected ECU → DEU with 80% confidence and three drivers. Zoom, pan, reset, drug filters, confidence cutoff, and layer toggles exercised. Fixed MapLibre's single-world constraint so zoom-out and world fit work. |
| Timeline | Keyboard year selection reached 2023 with explicit empty observations; reset restored the 2025 snapshot. Play advanced to the final year and stopped; immediate pause from 2011 stopped playback. No unavailable years are fabricated. |
| Country evidence | `COL <GO>` opened the 2025 Colombia profile, score 64.5, harm-reduction coverage, source/year citations, and World Bank API links. Other countries retain available risk summaries and clearly report missing detailed snapshots. |
| Risk and comparison | Forty rows, country filter, numeric sorting, trend sparklines, and `COMPARE COL PER` exercised. Comparison showed 64.5 and 73.1. Desktop panel dragging works; narrow panels stack. |
| Scenarios | Saved Colombia 50% cultivation scenario displayed 25 changed routes and 20 risk deltas. View on map updated corridor volumes. A baseline discrepancy is visibly disclosed and logged in `docs/CONTRACT_REQUESTS.md`. Unsupported custom scenarios show an API-required error. |
| Livewire | Replay rotates the saved synthetic events. Selecting a story opens its details and pins a Figma beacon on the map. Synthetic sources remain labeled in either data mode. WebSocket reconnect and frame parsing are implemented, but a real live server session was not exercised in this browser run. |
| Markets | Fifty-seven series; drug/market filters verified. Fifteen null year-over-year values render as unavailable rather than NaN. |
| Experiment | `experiment-revision.jpg` and `spillover-revision.jpg`: shared hectares chart, shared-axis connected marks and exact before/forecast/observed columns. Statistical results use a plain table, including scientific-notation p-values and the unsupported finding. Myanmar origin filtering returns four rows. |
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

- Reduced-motion behavior is implemented in Motion, CSS, and map transitions; an OS-level reduced-motion toggle was not exercised.
- Full live-backend integration and a deployed Adobe domain remain separate from this snapshot frontend delivery. Setup is in `../../README.md`.

## Owner-requested revision verification

- Browser verified Natural Earth 1:10m coastlines and OpenFreeMap roads/buildings through zoom 14.7 in Bogotá. `atlas-revision-streets.jpg` shows named streets and building footprints. Country textures, links and representative hub markers fade out by local zoom; the exposure legend hides with them. No subnational drug observations are inferred.
- The four drug selectors use newly authored Figma line keys, with selection underlines and accessible pressed state. Removed network counts, slogans, decorative experiment cards, colored hypothesis background and accent bar.
- Cultivation and risk histories use actual observation marks joined by straight segments, without filled chart backgrounds. Experiment connected marks share an aligned numeric scale across all 14 rows.
- At 390×844, Atlas and Experiment both have document width 390px. Charts fit 354px content width; corridor/backtest/hypothesis tables scroll inside their own containers. Fixed a grid intrinsic-width overflow found during this check.
- Browser warning/error logs were empty for the desktop detailed-map and mobile checks. Production build and the six adapter/command tests pass.
- Revision captures: `atlas-revision-world.jpg`, `atlas-revision-streets.jpg`, `experiment-revision.jpg`, `spillover-revision.jpg`, `atlas-revision-mobile.jpg`, `experiment-revision-mobile.jpg`. Earlier screenshots remain as historical evidence.

## SQLite source archive integration check

On 2026-09-26, the production `npm run build` passed, all six npm tests passed, and three active observed-export integrity tests passed. One optional source-shard count test was skipped after checksum-audited temporary copies were removed. This check did not add new screenshots.

Browser checks confirmed that Pakistan opens country health evidence beyond the Colombia model-profile fixture; health rows retain modeled versus country-reported treatment status, ranged reference years, denominator and method detail. The US CDC view selected the exact synthetic-opioid indicator and revealed earlier 12-month-ending periods through “Show earlier periods.” Germany's market view showed the purity-adjusted price formula `10.92 / (11.8 / 100) = 92.53` with both contributing source rows. The research view displayed the retrospective coefficient 0.0195, p-value 0.869, 1,428 observations across 144 countries, and source-pair dates. Published policy context appeared in Scenarios, and the v2 archive appeared in Data sources.

At 390px wide, Health, Markets and Experiment had no horizontal page overflow. A fresh production browser session logged no warnings or errors. These checks cover the saved frontend and source export, not live backend SQLite migration or prospective model validation.
