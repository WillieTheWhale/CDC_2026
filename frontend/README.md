<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# TRACE frontend

An interactive research atlas with country drilldowns, route evidence, risk comparisons, scenarios, a newswire, markets, and the Afghanistan experiment. A white and cool-blue map carries fine country-exposure textures and colored country links. Figma supplies the identity, legend, signal beacon, and route animation; Adobe Forma DJR supplies the typography.

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

The default is a saved snapshot of the backend output. Available route snapshots are 2024 observed and 2025 predicted; country risk and Colombia's detailed profile use 2025. Other years and profiles show an explicit unavailable state. News fixtures are synthetic and labeled as such. A saved Colombia cultivation scenario is available; custom scenarios require the model API. Experiment results, including the unsupported spillover hypothesis, are shown as supplied by the backend.

To connect the API, add this public endpoint to `.env.local` without replacing existing private credentials:

```dotenv
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Restart the dev server or rebuild for deployment because Next embeds public environment values at build time. REST requests and the `/ws/livewire` WebSocket use the same base URL. Configure backend `CORS_ORIGINS` to include the frontend origin, such as `http://127.0.0.1:3000`. A connected API failure stays an error; it never silently switches to the saved snapshot. See `../backend/README.md` for API setup. The separate SQLite collection is awaiting backend integration and is not read directly by the browser.

## Interface

- Click a country or a corridor to inspect it; pan, zoom, and reset the map.
- Filter by drug, confidence, year, and observed/forecast mode. The timeline supports playback.
- Use ⌘K or Ctrl+K for `COL <GO>`, `HEROIN ROUTES`, `RISK TOP 20`, `COMPARE COL PER`, `YEAR 2023`, or `PREDICT ON`.
- Drag the two lower panel handles on desktop. On narrow screens the panels stack and selected details scroll into view.
- Open Data sources for provenance, observation years, retrieval dates, and limitations.

## Design and verification

- Figma: https://www.figma.com/design/pGB5GIz2RsLKBPNjnyHpdg
- Asset and motion details: `design/figma-assets.md`.
- Browser checks and screenshots: `design/qa/README.md`.
- Adobe kit `jzx3gtq` is configured for localhost and 127.0.0.1. Add the deployed domain to the Adobe web project before deployment. The published CSS is public; the private API token belongs only in ignored environment configuration.
- Native Figma motion is implemented using Motion and equivalent map-marker CSS, with reduced-motion guards. Natural Earth 1:10m boundaries are bundled locally. OpenFreeMap/OpenStreetMap vector tiles add cities, roads, and buildings through zoom 18. Fine screen-space texture encodes six country-exposure bands and fades by zoom 6; it never represents subnational observations. Country links connect representative country coordinates, not observed travel paths. Rebuild geography with `node scripts/build-geography.mjs`.

The browser's WebGL support is required for the map. Country search and tabular views remain usable if WebGL is unavailable. Keep the harm-prevention framing and visible data provenance when connecting new data.
