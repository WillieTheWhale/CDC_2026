// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// Route arcs join one representative point per country. Natural Earth's label
// point sometimes sits offshore (New Zealand between its islands, Trinidad and
// Tobago in the Gulf of Paria), which draws an arrow ending in the sea. Keep
// every anchor on land: if the label point is outside the country's own
// polygons, use the country's main seaport; if there is none (or it also
// tests as offshore at 1:10m), use the nearest point on the country's coast.
//
// Run directly to patch public/geo/countries.json in place:
//   node scripts/land-anchors.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Main container/cargo seaports, [lon, lat]. Used only when a label point is at sea.
export const PORTS = {
  NZL: ["Port of Auckland", 174.7766, -36.8431],
  TTO: ["Port of Spain", -61.5167, 10.6517],
  JAM: ["Port of Kingston", -76.8199, 17.9714],
  DOM: ["Port of Santo Domingo", -69.8833, 18.4719],
  HTI: ["Port-au-Prince", -72.3451, 18.5559],
  BHS: ["Nassau", -77.3431, 25.0786],
  CUB: ["Port of Havana", -82.3486, 23.1403],
  PHL: ["Port of Manila", 120.9580, 14.5921],
  IDN: ["Tanjung Priok, Jakarta", 106.8833, -6.1000],
  JPN: ["Port of Tokyo", 139.7900, 35.6200],
  GBR: ["Port of Felixstowe", 1.3200, 51.9550],
  IRL: ["Dublin Port", -6.2000, 53.3480],
  LKA: ["Port of Colombo", 79.8450, 6.9480],
  MDV: ["Malé", 73.5093, 4.1755],
  CPV: ["Port of Praia", -23.5050, 14.9130],
  FJI: ["Port of Suva", 178.4250, -18.1330],
  PNG: ["Port Moresby", 147.1500, -9.4780],
  MLT: ["Port of Valletta", 14.5140, 35.8970],
  CYP: ["Port of Limassol", 33.0200, 34.6500],
  GNB: ["Port of Bissau", -15.5800, 11.8580],
  CHL: ["Port of San Antonio", -71.6150, -33.5930],
  NOR: ["Port of Oslo", 10.7460, 59.9050],
  GRC: ["Port of Piraeus", 23.6280, 37.9420],
  MYS: ["Port Klang", 101.3930, 3.0000],
};

function ringContains([x, y], ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}

function polygons(geometry) {
  if (geometry.type === "Polygon") return [geometry.coordinates];
  if (geometry.type === "MultiPolygon") return geometry.coordinates;
  return [];
}

export function onLand(point, geometry) {
  return polygons(geometry).some(
    ([outer, ...holes]) =>
      ringContains(point, outer) && !holes.some((h) => ringContains(point, h)),
  );
}

// Nearest point on any outer ring, then nudged a hair toward the ring's next
// vertices until it tests as inside, so the arrowhead sits on the coast.
function nearestCoast([x, y], geometry) {
  let best = null;
  let bestD = Infinity;
  for (const [outer] of polygons(geometry)) {
    for (let i = 0; i < outer.length - 1; i++) {
      const [ax, ay] = outer[i];
      const [bx, by] = outer[i + 1];
      const dx = bx - ax;
      const dy = by - ay;
      const len = dx * dx + dy * dy;
      const t = len ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len)) : 0;
      const px = ax + t * dx;
      const py = ay + t * dy;
      const d = (px - x) ** 2 + (py - y) ** 2;
      if (d < bestD) {
        bestD = d;
        best = { point: [px, py], ring: outer };
      }
    }
  }
  if (!best) return null;
  const [px, py] = best.point;
  // Step toward the ring's centroid until the point is inside the country.
  const n = best.ring.length;
  const cx = best.ring.reduce((s, v) => s + v[0], 0) / n;
  const cy = best.ring.reduce((s, v) => s + v[1], 0) / n;
  for (const f of [0.002, 0.01, 0.03, 0.1]) {
    const q = [px + (cx - px) * f, py + (cy - py) * f];
    if (onLand(q, geometry)) return q;
  }
  return best.point;
}

const round = (v) => Math.round(v * 1e5) / 1e5;

// Returns the properties to use for a feature, with label_source recording why.
export function landAnchor(feature) {
  const p = feature.properties;
  const g = feature.geometry;
  const label = [p.label_lon, p.label_lat];
  if (typeof label[0] !== "number" || !g) return { ...p };
  if (onLand(label, g)) return { ...p, label_source: "natural-earth" };
  const port = PORTS[p.iso3];
  if (port) {
    const at = [port[1], port[2]];
    const point = onLand(at, g) ? at : nearestCoast(at, g);
    if (point)
      return {
        ...p,
        label_lon: round(point[0]),
        label_lat: round(point[1]),
        label_source: `port: ${port[0]}`,
      };
  }
  const coast = nearestCoast(label, g);
  if (!coast) return { ...p };
  return {
    ...p,
    label_lon: round(coast[0]),
    label_lat: round(coast[1]),
    label_source: "nearest land",
  };
}

export function anchorAll(world) {
  const moved = [];
  for (const feature of world.features) {
    const before = [feature.properties.label_lon, feature.properties.label_lat];
    feature.properties = landAnchor(feature);
    if (
      before[0] !== feature.properties.label_lon ||
      before[1] !== feature.properties.label_lat
    )
      moved.push({
        iso3: feature.properties.iso3,
        from: before,
        to: [feature.properties.label_lon, feature.properties.label_lat],
        source: feature.properties.label_source,
      });
  }
  return moved;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const file = new URL("../public/geo/countries.json", import.meta.url);
  const world = JSON.parse(readFileSync(file, "utf8"));
  const moved = anchorAll(world);
  writeFileSync(file, JSON.stringify(world));
  for (const m of moved)
    console.log(`${m.iso3}: ${m.from.join(", ")} -> ${m.to.join(", ")} (${m.source})`);
  console.log(`Kept ${world.features.length - moved.length} label points; moved ${moved.length} off the sea.`);
}
