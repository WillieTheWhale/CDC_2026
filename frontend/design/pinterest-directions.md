<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# TRACE visual direction research

Research date: 2026-09-26. Status: awaiting the owner's selection; no frontend implementation or Figma assets created.

## Current brief

- The owner supersedes the older black-and-amber brief: make a colorful, detailed, efficient map workspace with enough presence for an advisor demonstration.
- Adobe Fonts only, following the owner's final font instruction. Authenticated API access verified (HTTP 200); token stored only in gitignored frontend/.env.local with mode 0600. Do not load Google Fonts.
- Research Pinterest and present image sets before building. Use Figma MCP for subsequent design and asset work.
- Preserve the map, country drilldowns, risk board, time scrubber, observed/predicted distinction, source provenance, and harm-reduction framing.
- Read AGENTS.md, README.md, CONTEXT_LOG, FRONTEND_BRIEF, SYSTEM_DESIGN, BACKEND_BRIEF, DATA_SOURCES, HANDOFF_PROMPT, CDC_RULES, contract changelog/requests, and the API/WebSocket contract. Reviewed the shapes and representative contents of every fixture.
- Pulled main to 6527310: contract v1.0.0 and backend scaffold are now available. The fixtures are illustrative except the World Bank country metadata; their model metrics are not research findings.
- The old untracked research/project-discovery.md concerns an earlier AI-energy proposal and is not the current TRACE brief.

## A — Editorial Atlas (recommended)

Warm ivory and pale blue cartography; vermilion, saffron, and violet analytical marks. Fine rules, compact labels, annotated events, and a map that occupies most of the workspace. Translate the references into interactive country/route selection, not a static infographic.

Best fit: communicating complicated evidence in the advisor presentation while retaining dense analytical detail. Keep strong colors attached to selected measures and stable categories; do not make every panel compete for attention.

1. Five Years of Drought, discovered and inspected on Pinterest: https://www.pinterest.com/pin/70437488874130/
   - Original linked source: https://adventuresinmapping.com/2016/07/12/five-years-of-drought/
   - Image observed on the pin: https://i.pinimg.com/1200x/5d/45/22/5d4522040b4c3ca5a799d8f152dc25cb.jpg
   - Reference for bivariate color, geographic density, and warm background.
2. Los Angeles pollution data visualization, Max Henderson: https://www.pinterest.com/pin/5488830790860904/
   - Original linked source: https://www.behance.net/gallery/13630553/Los-Angeles-pollution-data-visualization
   - Image observed on the pin: https://i.pinimg.com/1200x/86/2a/1b/862a1b4181dd26b0055411f682fcded2.jpg
   - Reference for map annotations, multiscale marks, and editorial hierarchy.

## B — Blue Atlas

Marine and cobalt map surfaces, ice-blue geographic detail, pale docked panels, and coral/citron routes. Use subtle topography as geographic texture and reduce detail as the user zooms out. A global-to-regional transition can provide the presentation's dramatic moment.

Best fit: a map-led demonstration with strong geographic immersion. Contours must remain quiet enough that route and country data remain readable.

1. Blue city map reference: https://www.pinterest.com/pin/794885403023497821/
   - Image observed on the pin: https://i.pinimg.com/736x/ca/55/2b/ca552bb5aace38f05c4329516680e205.jpg
   - Original creator not established; the Pinterest uploader is not assumed to be the author.
2. Blue contour reference: https://www.pinterest.com/pin/107664247338620162/
   - Image observed on the pin: https://i.pinimg.com/736x/af/f2/d1/aff2d100bb10adfd121afdf50d028a3f.jpg
   - Reference for hue and line treatment only, not a complete dashboard design.

## C — Scientific Workspace

Porcelain panels, a lilac map, mint and golden data overlays, sharply aligned numbers, and a persistent country inspector beside the map. Keep tables flat and compact; minimize shadows and improve the references' low-contrast labels.

Best fit: sustained analysis, country comparison, and an advisor looking closely at evidence. For presentation impact, let the map and timeline provide movement rather than adding ornamental UI.

1. Lilac map with green/gold overlays and docked detail panel: https://www.pinterest.com/pin/66498531996320586/
   - Image observed on the pin: https://i.pinimg.com/1200x/5d/e8/16/5de816fe78e97c39e1cf9a23a0dfd2cc.jpg
2. Light green analytical map workspace: https://www.pinterest.com/pin/682013937361822823/
   - Image observed on the pin: https://i.pinimg.com/1200x/a8/f4/4a/a8f44a631512d8e89c6d40259b198ac5.jpg
   - Original creators not established for these two pins.

## Reference handling and next step

These are third-party visual references, not TRACE designs or reusable production assets. The image URLs were observed in Pinterest's rendered pages; images were not downloaded, altered, or posted to the owner's Pinterest account.

Wait for the owner to select A, B, C, or a specific combination before creating the frontend. Keep Adobe token values out of this file and Git. Figma remote MCP is configured, but the prior OAuth callback failed with a missing issuer response, so a successful MCP connection still needs verification before Figma work.
