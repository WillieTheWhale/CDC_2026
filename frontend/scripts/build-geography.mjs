// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Preserve Natural Earth's 1:10m geometry; strip unused properties only.
// The screen-space exposure texture is generated in atlas-map.tsx, not here.
import { writeFileSync } from "node:fs";
const source =
  "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson";
const response = await fetch(source);
if (!response.ok) throw new Error(`Natural Earth: ${response.status}`);
const world = await response.json();
const round = (coordinates) =>
  coordinates.map((v) =>
    Array.isArray(v) ? round(v) : Math.round(v * 1e5) / 1e5,
  );
const aliases = { KOS: "XKX", SDS: "SSD" };
for (const feature of world.features) {
  const p = feature.properties;
  const code = p.ISO_A3_EH && p.ISO_A3_EH !== "-99" ? p.ISO_A3_EH : p.ADM0_A3;
  feature.properties = {
    iso3: aliases[code] ?? code,
    name: p.NAME_EN ?? p.NAME,
    label_lon: p.LABEL_X,
    label_lat: p.LABEL_Y,
  };
  feature.geometry.coordinates = round(feature.geometry.coordinates);
}
world.metadata = {
  ai_assisted: "ChatGPT (OpenAI). See docs/AI_USAGE.md.",
  source,
  license: "Natural Earth public domain",
  scale: "1:10m",
};
writeFileSync(
  new URL("../public/geo/countries.json", import.meta.url),
  JSON.stringify(world),
);
console.log(`Saved ${world.features.length} detailed country polygons.`);
