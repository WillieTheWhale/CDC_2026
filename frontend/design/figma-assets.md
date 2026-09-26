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

Map colors adapt the source legend: neutral sand for unscored countries, then ochre/orange/coral/violet for increasing country exposure. Dots are cartographic samples, not geographically precise observations. Country boundaries: Natural Earth, public domain (https://www.naturalearthdata.com/). Source GeoJSON from the Natural Earth maintainer repository, simplified to required identity/label properties.

Adobe kit `jzx3gtq` contains Forma DJR Text, Display and Mono, scoped to localhost and 127.0.0.1. No private Adobe token is in this file, public assets, or client code.

The signal ring, carrier and core are also exported separately as `signal-ring.svg` (34×34), `signal-carrier.svg` (16×16), and `signal-core.svg` (7×7). Their positions and native dimensions match Figma nodes 2:37–2:39. `components/figma-motion.tsx` consumes the assets and exported motion values. MapLibre markers share the equivalent sampled CSS keyframes. Browser verification confirmed all six beacon images loaded, correct dimensions, changing ring transforms, and changing route stroke-dasharray values.
