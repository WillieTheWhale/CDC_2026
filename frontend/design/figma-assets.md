<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Figma source and motion

Design file: https://www.figma.com/design/pGB5GIz2RsLKBPNjnyHpdg

Created using the Figma MCP Plugin API and exported through `download_assets`:

| Asset | Node | Local export |
|---|---|---|
| TRACE dot mark | 2:2 | public/figma/trace-mark.svg |
| Seven-color exposure legend | 2:14 | public/figma/exposure-legend.svg |
| Emerging signal beacon | 2:36 | public/figma/signal-beacon.svg |
| Route draw study | 2:49 | public/figma/route-study.svg |

The signal ring has Figma manual scale tracks from 0.65 to 1.6 and opacity from 0.65 to 0 over 2.4 seconds. The route uses Figma's Path draw preset over 1.2 seconds. `get_motion_context` was used to inspect the beacon motion. The frontend now implements the authoritative `get_motion_context` output: a two-second pulse loop and a route path draw lasting 1.2 seconds with a 0.8-second hold. The React path uses the actual exported vector geometry; it is not a clipped static image. `prefers-reduced-motion` disables both loops.

Map colors use white/cool-blue geography and orange/coral/violet country-exposure bands. Fine 1px texture marks encode exposure density and fade at local scales; they are not observation coordinates. Country boundaries: Natural Earth, public domain (https://www.naturalearthdata.com/). Source GeoJSON from the Natural Earth maintainer repository, simplified to required identity/label properties.

Adobe kit `jzx3gtq` contains Forma DJR Text, Display and Mono, scoped to localhost and 127.0.0.1. No private Adobe token is in this file, public assets, or client code.

The signal ring, carrier and core are also exported separately as `signal-ring.svg` (34×34), `signal-carrier.svg` (16×16), and `signal-core.svg` (7×7). Their positions and native dimensions match Figma nodes 2:37–2:39. `components/figma-motion.tsx` consumes the assets and exported motion values. MapLibre markers share the equivalent sampled CSS keyframes. Browser verification confirmed all six beacon images loaded, correct dimensions, changing ring transforms, and changing route stroke-dasharray values.

## Cartographic revision — 2026-09-26

Figma MCP created and exported the revised keys in frame **4:2**: cocaine **4:4**, heroin **4:6**, meth **4:8**, cannabis **4:10**, and exposure strip **4:12**. Their distinct 24×14 line geometries replace the generic dot filters. Local files are `key-cocaine.svg`, `key-heroin.svg`, `key-meth.svg`, `key-cannabis.svg`, and `exposure-strip.svg`.

Country geometry is Natural Earth 1:10m, with all source vertices preserved at five decimal places. OpenFreeMap Positron vector cartography supplies OpenStreetMap roads, buildings, and labels. `public/geo/basemap.json` applies a cool palette and preserves attribution; see https://openfreemap.org/quick_start/. Screen-space halftone density/color uses six equal exposure bands across 0–100 and fades to zero by zoom 6. Country route anchors remain representative country coordinates.
