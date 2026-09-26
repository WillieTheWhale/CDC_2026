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

The signal ring has Figma manual scale tracks from 0.65 to 1.6 and opacity from 0.65 to 0 over 2.4 seconds. The route uses Figma's Path draw preset over 1.2 seconds. `get_motion_context` was used to inspect the beacon motion. The frontend implements the authored 2.4-second loop and a 1.2-second route reveal; prefers-reduced-motion disables decorative motion. Figma's generated motion snippet rounded the track to two seconds, so the authored duration was preserved.

Map colors adapt the source legend: neutral sand for unscored countries, then ochre/orange/coral/violet for increasing country exposure. Dots are cartographic samples, not geographically precise observations. Country boundaries: Natural Earth, public domain (https://www.naturalearthdata.com/). Source GeoJSON from the Natural Earth maintainer repository, simplified to required identity/label properties.

Adobe kit `jzx3gtq` contains Forma DJR Text, Display and Mono, scoped to localhost and 127.0.0.1. No private Adobe token is in this file, public assets, or client code.
