# Frontend Brief (ChatGPT Astra)

Owner: teammate, via ChatGPT Astra. Work in `frontend/` only. Never edit `backend/` or `contracts/` (request contract changes by adding a note to `docs/CONTRACT_REQUESTS.md` and telling Markandeya).

Read first: [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) (sections 1, 4, 7, 11), [CDC_RULES.md](CDC_RULES.md), and everything in `contracts/`.

## Data source
- Until the backend is live, read data from `contracts/fixtures/*.json` (copy or import them; do not edit originals).
- When `NEXT_PUBLIC_API_URL` is set, fetch from the real API instead. Build one data layer (`frontend/lib/api.ts`) that switches between fixtures and the API so screens never care which one they get.
- Shapes are defined by `contracts/openapi.yaml`. If the backend has not pushed the contract yet, `git pull` again later; the contract is the backend's first task.

## Stack
Next.js (App Router) + TypeScript + Tailwind. deck.gl `ArcLayer` over MapLibre GL with a dark basemap. react-grid-layout for draggable panels. `cmdk` for the command bar. Recharts for sparklines and tickers. Fonts: IBM Plex Mono or JetBrains Mono.

## Look and feel
Bloomberg terminal: black background, amber (#FFB000) primary text, green for up, red for down, cyan for links and selection. Dense, gridded panels with thin borders and uppercase panel headers. Keyboard first. It should feel like a professional intelligence tool, not a consumer dashboard.

## Screens (build in this order)
1. **Shell:** top command bar, panel grid, status bar (data freshness, model version, clock).
2. **Route Map (must):** arcs per drug with color per drug (cocaine white, heroin red, meth cyan, cannabis green), width by `volume_norm`, opacity by `confidence`. Year scrubber. Toggle observed vs predicted. Emerging corridors pulse. Hover shows from, to, volume, confidence, top drivers.
3. **Country Screen (must):** opened by clicking a country or typing `COL <GO>`. Routes in and out, World Bank indicators with year and source shown, OC Index scores, harm reduction checklist, risk breakdown.
4. **Spillover Risk Board (must):** sortable table: rank, country, exposure, vulnerability, protection, score, trend sparkline. `RISK TOP 20`.
5. **Shock Simulator (should):** text box plus presets (Afghan ban, Colombia coca cut, Mexico cannabis legalization); shows changed arcs and risk deltas.
6. **Live Wire (should):** scrolling feed from `WS /ws/livewire` (fixture replay until live); each item shows type, drug, route, size, confidence; anomalies highlighted; clicking pins it on the map.
7. **Market Board (nice):** price tickers per drug and country with year-over-year change.
8. **Experiment view:** Afghan ban before/after with predicted vs actual arcs, and metrics from `/api/metrics`.

## Commands
`HEROIN ROUTES`, `COCAINE ROUTES`, `MEX <GO>`, `RISK TOP 20`, `SHOCK AFG CULTIVATION -95%`, `NEWS COCAINE`, `COMPARE COL PER`, `YEAR 2023`, `PREDICT ON|OFF`. Parse simple ones locally; send anything else to `POST /api/command`.

## Rules
- `git pull --rebase` before starting and before every push; push straight to `main` in small commits.
- AI citation: a header comment in every file written with AI help, plus a line in `docs/AI_USAGE.md` per session (CDC requirement; missing citations risk disqualification).
- Design boundary: never add views, sorts, or labels that show where enforcement is weakest or which routes are least watched. Frame everything around harm and prevention.
- Show data provenance (source and year) wherever a World Bank number appears; judges will check.
- Always include a visible "Data sources" panel or page.
- `npm run build` must pass before pushing.
