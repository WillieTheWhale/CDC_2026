// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Natural Earth public-domain geometry. Dots are an even cartographic sample,
// never subnational observations; values are joined at country level at runtime.
import fs from "node:fs";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
const world = JSON.parse(
  fs.readFileSync(new URL("../public/geo/countries.json", import.meta.url)),
);
const polygons = world.features
  .filter((f) => f.properties.iso3 !== "ATA")
  .map((f) => {
    const coords = f.geometry.coordinates.flat(
      f.geometry.type === "MultiPolygon" ? 2 : 1,
    );
    return {
      f,
      minX: Math.min(...coords.map((p) => p[0])),
      maxX: Math.max(...coords.map((p) => p[0])),
      minY: Math.min(...coords.map((p) => p[1])),
      maxY: Math.max(...coords.map((p) => p[1])),
    };
  });
const dots = [];
for (let row = 0, y = -68; y < 121; y += (1.7 * Math.sqrt(3)) / 2, row++)
  for (let lon = -179 + (row % 2) * 0.85; lon < 180; lon += 1.7) {
    const lat =
      ((2 * Math.atan(Math.exp((y * Math.PI) / 180)) - Math.PI / 2) * 180) /
      Math.PI;
    const item = polygons.find(
      ({ f, minX, maxX, minY, maxY }) =>
        lon >= minX &&
        lon <= maxX &&
        lat >= minY &&
        lat <= maxY &&
        booleanPointInPolygon([lon, lat], f),
    );
    if (item)
      dots.push([+lon.toFixed(3), +lat.toFixed(3), item.f.properties.iso3]);
  }
fs.writeFileSync(
  new URL("../public/geo/dots.json", import.meta.url),
  JSON.stringify(dots),
);
console.log(`Created ${dots.length} cartographic dots.`);
