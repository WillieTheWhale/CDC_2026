// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
import type { Feature, FeatureCollection, Geometry, Position } from "geojson";

export type Anchor = { lat: number; lon: number };
type Ring = Position[];
type Polygon = Ring[];

// Route arcs join one representative point per country. Natural Earth tags
// several features with the same ISO3 (France and Clipperton Island, Australia
// and Ashmore Reef, Brazil and Brazilian Island), and some label points fall
// just offshore at 1:10m (New Zealand, Trinidad and Tobago). Either way an arc
// ends in open water although the data is a country-level corridor. Anchors
// therefore come from each country's largest feature and are kept on its land.

const polygons = (geometry: Geometry | null): Polygon[] =>
  geometry?.type === "Polygon"
    ? [geometry.coordinates]
    : geometry?.type === "MultiPolygon"
      ? geometry.coordinates
      : [];

// Shoelace area with a cosine correction so high-latitude islands do not
// outweigh a mainland in plate carrée degrees.
function ringArea(ring: Ring) {
  let area = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const cos = Math.cos((((ring[i][1] + ring[j][1]) / 2) * Math.PI) / 180);
    area += (ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1]) * cos;
  }
  return Math.abs(area / 2);
}

function inRing([x, y]: Position, ring: Ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i],
      [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}

export const inPolygon = (point: Position, [outer, ...holes]: Polygon) =>
  inRing(point, outer) && !holes.some((hole) => inRing(point, hole));

function edgeDistance([x, y]: Position, polygon: Polygon) {
  let best = Infinity;
  for (const ring of polygon)
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [ax, ay] = ring[j],
        [bx, by] = ring[i];
      const dx = bx - ax,
        dy = by - ay;
      const t = dx || dy
        ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        : 0;
      best = Math.min(best, Math.hypot(x - ax - t * dx, y - ay - t * dy));
    }
  return best;
}

// Approximate pole of inaccessibility: the interior point farthest from the
// coast, found by a coarse grid search refined twice around the best cell.
export function interiorPoint(polygon: Polygon): Position {
  const xs = polygon[0].map((p) => p[0]),
    ys = polygon[0].map((p) => p[1]);
  let [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  let best: Position = polygon[0][0],
    bestDistance = -1;
  for (let pass = 0; pass < 3; pass++) {
    const steps = 24,
      sx = (maxX - minX) / steps,
      sy = (maxY - minY) / steps;
    for (let i = 0; i <= steps; i++)
      for (let j = 0; j <= steps; j++) {
        const point = [minX + i * sx, minY + j * sy];
        if (!inPolygon(point, polygon)) continue;
        const distance = edgeDistance(point, polygon);
        if (distance > bestDistance) [best, bestDistance] = [point, distance];
      }
    [minX, maxX, minY, maxY] = [best[0] - sx, best[0] + sx, best[1] - sy, best[1] + sy];
  }
  return best;
}

const featureArea = (feature: Feature) =>
  polygons(feature.geometry).reduce((sum, polygon) => sum + ringArea(polygon[0]), 0);

export function countryAnchor(feature: Feature): Anchor | null {
  const parts = polygons(feature.geometry)
    .map((polygon) => ({ polygon, area: ringArea(polygon[0]) }))
    .sort((a, b) => b.area - a.area);
  if (!parts.length) return null;
  const { label_lon, label_lat } = feature.properties ?? {};
  if (typeof label_lon === "number" && typeof label_lat === "number") {
    // Keep the curated label when it sits on a substantial landmass (Sumatra
    // for Indonesia, Luzon-scale islands for the Philippines).
    const home = parts.find(({ polygon }) => inPolygon([label_lon, label_lat], polygon));
    if (home && home.area >= parts[0].area * 0.1) return { lon: label_lon, lat: label_lat };
  }
  const [lon, lat] = interiorPoint(parts[0].polygon);
  return { lon, lat };
}

export function countryAnchors(geo: FeatureCollection<Geometry>) {
  const largest = new Map<string, { feature: Feature; area: number }>();
  for (const feature of geo.features) {
    const iso3 = feature.properties?.iso3;
    if (typeof iso3 !== "string") continue;
    const area = featureArea(feature);
    if (area > (largest.get(iso3)?.area ?? -1)) largest.set(iso3, { feature, area });
  }
  const anchors = new Map<string, Anchor>();
  for (const [iso3, { feature }] of largest) {
    const anchor = countryAnchor(feature);
    if (anchor) anchors.set(iso3, anchor);
  }
  return anchors;
}
