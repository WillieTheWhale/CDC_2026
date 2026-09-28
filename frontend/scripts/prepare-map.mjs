// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// MapLibre 6's module worker must resolve its shared module from a stable URL.
import { copyFileSync, mkdirSync } from "node:fs";
const dir = new URL("../public/vendor/maplibre/", import.meta.url);
mkdirSync(dir, { recursive: true });
for (const name of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(
    new URL(`../node_modules/maplibre-gl/dist/${name}`, import.meta.url),
    new URL(name, dir),
  );
}
