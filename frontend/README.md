<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# TRACE frontend

An interactive research atlas with country drilldowns, source health evidence, risk comparisons, scenarios, a newswire, markets, and retrospective research. A white and cool-blue map carries fine country-exposure textures and colored country links. Figma supplies the identity, legend, signal beacon, and route animation; Adobe Forma DJR supplies the typography.

## Run

Requires Node.js 20.9 or newer and npm. Run from this directory:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:3000. `predev` and `prebuild` copy the installed MapLibre worker into the ignored public vendor directory. No map API key is needed. Keep this directory inside the repository: the adapter imports the shared contract fixtures from `../contracts/fixtures`.

```sh
npm test
npm run typecheck
npm run build
npm start
```

## Data connection

The default atlas and risk board use a saved backend model snapshot. Without an API, every modeled route (2006-2024 baseline, 2025 forecast) and every country's risk and exposure shading (2008-2025) load per year from `public/data/routes/` and `public/data/risk/`, regenerated with `uv run trace export --route-snapshots` in `../backend`. Colombia's detailed API profile uses 2025; other profiles show an explicit unavailable state. Corridors are modeled country links, not observed seizure routes. News fixtures are synthetic and labeled as such. A saved Colombia cultivation scenario is available; custom scenarios require the model API.

Health, market, source and research panels read compact country exports from the verified 2026-09-26 SQLite v2 archive under `public/data/observed-v2/`. These files preserve observation years, source editions, original populations and units. The browser fetches a country only when needed; the atlas does not wait for this archive. The archive is separate from the model API while the backend SQLite migration is pending. See [`scripts/OBSERVED_DATA.md`](scripts/OBSERVED_DATA.md) to reproduce the export. The published snapshot and coverage limits are documented in `../data_collection/README.md` and `../data_collection/reports/`.

To connect the API, add this public endpoint to `.env.local` without replacing existing private credentials:

```dotenv
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Restart the dev server or rebuild for deployment because Next embeds public environment values at build time. REST requests and the `/ws/livewire` WebSocket use the same base URL. Configure backend `CORS_ORIGINS` to include the frontend origin, such as `http://127.0.0.1:3000`. A connected API failure stays an error; it never silently switches to the saved snapshot. See `../backend/README.md` for API setup. The separate SQLite collection is awaiting backend integration and is not read directly by the browser.

## Interface

- Click a country or a corridor to inspect it; pan, zoom, and reset the map.
- Filter model corridors by drug, confidence, year, and baseline/forecast mode. The timeline supports playback.
- Open Health evidence to select a country and inspect drug use, injecting health, treatment contacts and published SDG treatment coverage with exact population and source labels. The country Evidence tab uses the same archive for countries beyond the saved Colombia profile.
- Use ⌘K or Ctrl+K for `COL <GO>`, `HEROIN ROUTES`, `RISK TOP 20`, `COMPARE COL PER`, `YEAR 2023`, or `PREDICT ON`.
- Drag the two lower panel handles on desktop. On narrow screens the panels stack and selected details scroll into view.
- Open Data sources for provenance, source editions, retrieval dates, and limitations. Officially modeled treatment coverage is marked as such; CDC provisional overdose records use rolling 12-month-ending periods and overlapping drug classes.

## Design and verification

- Figma: https://www.figma.com/design/pGB5GIz2RsLKBPNjnyHpdg
- Asset and motion details: `design/figma-assets.md`.
- Browser checks and screenshots: `design/qa/README.md`.
- Adobe kit `jzx3gtq` is configured for localhost and 127.0.0.1. Add the deployed domain to the Adobe web project before deployment. The published CSS is public; the private API token belongs only in ignored environment configuration.
- Native Figma motion is implemented using Motion and equivalent map-marker CSS, with reduced-motion guards. Natural Earth 1:10m boundaries are bundled locally. OpenFreeMap/OpenStreetMap vector tiles add cities, roads, and buildings through zoom 18. Fine screen-space texture encodes six country-exposure bands. Country textures and links fade by zoom 6; it never represents subnational observations. Country links connect representative country coordinates, not observed travel paths. Rebuild geography with `node scripts/build-geography.mjs`. Route arrows end at each country's label point; `scripts/land-anchors.mjs` keeps those points on land, moving any offshore label point to the country's main seaport or, without one, the nearest coast (`label_source` records which).

The browser's WebGL support is required for the map. Country search and tabular views remain usable if WebGL is unavailable. Keep the harm-prevention framing and visible data provenance when connecting new data.
