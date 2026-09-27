// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// Estimated local flows: a labelled, map-only layer built by
// `uv run trace estimate-flows` (backend/trace_backend/model/estimated_flows.py).
// The build needs city populations (Natural Earth) and GDP per capita that
// /api/routes does not carry, so it cannot be derived from live edges in the
// browser. lib/api.ts asks /api/estimated-flows (same payload) and falls back
// to the snapshot files in public/data/estimated/; `live` records which.
// Arrows follow money (city population x GDP per capita) out of the cities
// that modeled corridors feed. They are never counted in scores or tables.
import type { Drug, Edge } from "./types";

export interface EstimatedCity {
  name: string;
  iso3: string;
  lon: number;
  lat: number;
  intensity: number; // 0-1, darker where many paths cross
}
export interface EstimatedFlow {
  drug: Drug;
  generation: 1 | 2 | 3;
  strength: number; // 0-1 within the drug and year
  km: number;
  from: EstimatedCity;
  to: EstimatedCity;
}
export interface EstimatedLayer {
  year: number;
  mode: string;
  flows: EstimatedFlow[];
  cities: EstimatedCity[];
  note: string;
  live: boolean; // true when served by the API, false for a snapshot file
}
interface EstimatedFile {
  live?: boolean;
  meta: { note: string };
  data: {
    year: number;
    mode: string;
    drugs: Drug[];
    cities: [string, string, number, number, number][];
    flows: [number, 1 | 2 | 3, number, number, number, number][];
  };
}

export function parseEstimated(file: EstimatedFile): EstimatedLayer {
  const { data } = file;
  const cities = data.cities.map(([name, iso3, lon, lat, intensity]) => ({
    name,
    iso3,
    lon,
    lat,
    intensity,
  }));
  return {
    year: data.year,
    mode: data.mode,
    note: file.meta.note,
    live: file.live ?? false,
    cities,
    flows: data.flows.map(([drug, generation, strength, from, to, km]) => ({
      drug: data.drugs[drug],
      generation,
      strength,
      km,
      from: cities[from],
      to: cities[to],
    })),
  };
}

const rad = Math.PI / 180;
function interpolate(
  a: [number, number],
  b: [number, number],
  t: number,
): [number, number] {
  // Great-circle interpolation, so glyphs sit on the same curve the eye expects.
  const [l1, p1, l2, p2] = [a[0] * rad, a[1] * rad, b[0] * rad, b[1] * rad];
  const d =
    2 *
    Math.asin(
      Math.sqrt(
        Math.sin((p2 - p1) / 2) ** 2 +
          Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2,
      ),
    );
  if (d === 0) return a;
  const A = Math.sin((1 - t) * d) / Math.sin(d);
  const B = Math.sin(t * d) / Math.sin(d);
  const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
  const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
  const z = A * Math.sin(p1) + B * Math.sin(p2);
  return [Math.atan2(y, x) / rad, Math.atan2(z, Math.hypot(x, y)) / rad];
}
// Compass bearing from a to b, degrees clockwise from north.
export function bearing(a: [number, number], b: [number, number]) {
  const [l1, p1, l2, p2] = [a[0] * rad, a[1] * rad, b[0] * rad, b[1] * rad];
  const y = Math.sin(l2 - l1) * Math.cos(p2);
  const x =
    Math.cos(p1) * Math.sin(p2) -
    Math.sin(p1) * Math.cos(p2) * Math.cos(l2 - l1);
  return ((Math.atan2(y, x) / rad) + 360) % 360;
}

export interface WindGlyph {
  position: [number, number];
  bearing: number;
  strength: number;
  drug: Drug;
  flow: EstimatedFlow;
}
// Weather-map style: short arrows spaced along each path. Spacing shrinks as
// the map zooms in, so local views stay dense without drawing new data.
export function spacingKm(zoom: number) {
  return Math.max(18, Math.min(420, 900 / 2 ** (zoom - 2)));
}
export function windGlyphs(flows: EstimatedFlow[], zoom: number): WindGlyph[] {
  const step = spacingKm(zoom);
  const out: WindGlyph[] = [];
  for (const flow of flows) {
    const a: [number, number] = [flow.from.lon, flow.from.lat];
    const b: [number, number] = [flow.to.lon, flow.to.lat];
    const n = Math.max(1, Math.floor(flow.km / step));
    for (let i = 0; i < n; i++) {
      const t = (i + 0.5) / n;
      const position = interpolate(a, b, t);
      const ahead = interpolate(a, b, Math.min(1, t + 0.02));
      out.push({
        position,
        bearing: bearing(position, ahead),
        strength: flow.strength,
        drug: flow.drug,
        flow,
      });
    }
  }
  return out;
}

// Country color by modeled drug volume: kg entering or leaving the country on
// the modeled corridors shown (already filtered by drug and confidence),
// banded 0-5 on a log scale relative to the largest country that year.
export function volumeBands(edges: Edge[]): Map<string, number> {
  const kg = new Map<string, number>();
  for (const e of edges) {
    kg.set(e.from, (kg.get(e.from) ?? 0) + (e.kg ?? 0));
    kg.set(e.to, (kg.get(e.to) ?? 0) + (e.kg ?? 0));
  }
  const max = Math.max(0, ...kg.values());
  const bands = new Map<string, number>();
  if (max <= 0) return bands;
  for (const [iso3, v] of kg)
    bands.set(
      iso3,
      v <= 0 ? 0 : Math.max(1, Math.min(5, Math.ceil((5 * Math.log1p(v)) / Math.log1p(max)))),
    );
  return bands;
}

// Slope-field view: sum glyph vectors in a regular lon/lat grid and draw one
// arrow per cell (direction = net flow, size = magnitude, color = dominant
// drug), like wind arrows on a weather map.
export interface FieldArrow {
  position: [number, number];
  bearing: number;
  magnitude: number; // 0-1 relative to the strongest cell
  drug: Drug;
  flows: EstimatedFlow[];
  turn?: number;
}
export function fieldArrows(glyphs: WindGlyph[], cellDeg: number): FieldArrow[] {
  const cells = new Map<
    string,
    { vx: number; vy: number; lon: number; lat: number; w: number; drugs: Map<Drug, number>; flows: Set<EstimatedFlow> }
  >();
  for (const g of glyphs) {
    const key = `${Math.floor(g.position[0] / cellDeg)}:${Math.floor(g.position[1] / cellDeg)}`;
    let c = cells.get(key);
    if (!c) {
      c = { vx: 0, vy: 0, lon: 0, lat: 0, w: 0, drugs: new Map(), flows: new Set() };
      cells.set(key, c);
    }
    const r = g.bearing * rad;
    c.vx += g.strength * Math.sin(r);
    c.vy += g.strength * Math.cos(r);
    c.lon += g.position[0] * g.strength;
    c.lat += g.position[1] * g.strength;
    c.w += g.strength;
    c.drugs.set(g.drug, (c.drugs.get(g.drug) ?? 0) + g.strength);
    c.flows.add(g.flow);
  }
  const raw = [...cells.values()]
    .filter((c) => c.w > 0)
    .map((c) => {
      const position: [number, number] = [c.lon / c.w, c.lat / c.w];
      const net = ((Math.atan2(c.vx, c.vy) / rad) + 360) % 360;
      // Point at the city the strongest flow here is heading to; bend from the
      // path's own direction toward it (arrows converge on cities, tips stay off them).
      const main = [...c.flows].sort((a, b) => b.strength - a.strength)[0];
      const aim = bearing(position, [main.to.lon, main.to.lat]);
      const turn = Math.max(-35, Math.min(35, 2 * ((((aim - net + 540) % 360) - 180))));
      return {
        position,
        bearing: aim,
        turn,
        magnitude: Math.hypot(c.vx, c.vy),
      drug: [...c.drugs.entries()].sort((a, b) => b[1] - a[1])[0][0],
      flows: [...c.flows]
        .sort((a, b) => b.strength - a.strength)
        .filter(
          (f, i, all) =>
            all.findIndex((g) => g.from.name === f.from.name && g.to.name === f.to.name) === i,
        )
        .slice(0, 3),
      };
    });
  const peak = Math.max(1e-9, ...raw.map((a) => a.magnitude));
  return raw
    .map((a) => ({ ...a, magnitude: Math.sqrt(a.magnitude / peak) }))
    .filter((a) => a.magnitude > 0.03);
}

// Curved arrow outline for one field arrow, in lon/lat, sized in screen
// pixels at `zoom`. The arrow bends toward its main flow's destination city
// (at least a gentle default bend), with a tapered shaft and a soft head.
export function curvedArrow(
  arrow: FieldArrow,
  zoom: number,
  lengthPx: number,
  widthPx: number,
): [number, number][] {
  const [lon0, lat0] = arrow.position;
  const degPerPx = 360 / (512 * 2 ** zoom);
  const kx = degPerPx / Math.max(0.2, Math.cos(lat0 * rad));
  const ky = degPerPx;
  let turn = Math.max(-40, Math.min(40, arrow.turn ?? 0));
  if (Math.abs(turn) < 14) turn = turn < 0 ? -14 : 14;
  // Centerline: heading swings from (bearing - turn) to `bearing`, so the
  // head points straight at the target city.
  const n = 10;
  const step = lengthPx / n;
  const pts: { x: number; y: number; h: number }[] = [];
  let x = 0,
    y = 0;
  for (let i = 0; i <= n; i++) {
    const h = (arrow.bearing - turn + (turn * i) / n) * rad;
    pts.push({ x, y, h });
    x += step * Math.sin(h);
    y += step * Math.cos(h);
  }
  // Center the shape on the cell position.
  const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
  const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
  const at = (p: { x: number; y: number }, off: number, h: number): [number, number] => [
    lon0 + (p.x - cx + off * Math.cos(h)) * kx,
    lat0 + (p.y - cy - off * Math.sin(h)) * ky,
  ];
  const headStart = 7; // last 3 segments form the head
  const left: [number, number][] = [];
  const right: [number, number][] = [];
  for (let i = 0; i <= headStart; i++) {
    const w = (widthPx / 2) * (0.35 + (0.65 * i) / headStart);
    left.push(at(pts[i], -w, pts[i].h));
    right.push(at(pts[i], w, pts[i].h));
  }
  const base = pts[headStart];
  const tip = pts[n];
  return [
    ...left,
    at(base, -widthPx * 1.25, base.h),
    at(tip, 0, tip.h),
    at(base, widthPx * 1.25, base.h),
    ...right.reverse(),
  ];
}

export const arrowLength = (magnitude: number) => 20 + magnitude * 22;
export const arrowWidth = (magnitude: number) => 3.5 + magnitude * 4.5;

// Web Mercator "world pixels" at a zoom level (512 px tiles, as MapLibre).
function worldPx([lon, lat]: [number, number], zoom: number): [number, number] {
  const size = 512 * 2 ** zoom;
  const s = Math.sin(Math.max(-85, Math.min(85, lat)) * rad);
  return [((lon + 180) / 360) * size, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * size];
}
function segmentDistance(a: number[], b: number[], c: number[], d: number[]) {
  const pt = (p: number[], q: number[], r: number[]) => {
    const dx = r[0] - q[0], dy = r[1] - q[1];
    const len = dx * dx + dy * dy;
    const t = len ? Math.max(0, Math.min(1, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / len)) : 0;
    return Math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dy);
  };
  const cross = (p: number[], q: number[], r: number[]) =>
    (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  const intersect =
    cross(a, b, c) * cross(a, b, d) < 0 && cross(c, d, a) * cross(c, d, b) < 0;
  return intersect ? 0 : Math.min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b));
}
export interface PlacedArrow extends FieldArrow {
  polygon: [number, number][];
}
// Greedy placement, strongest first: an arrow is kept only if its body (a
// capsule from tail to tip, plus a small gap) touches no arrow already kept,
// and its head stays off the city it points at.
export function placeArrows(arrows: FieldArrow[], zoom: number, gapPx = 3): PlacedArrow[] {
  const cell = 48;
  const grid = new Map<string, { a: number[]; b: number[]; r: number }[]>();
  const out: PlacedArrow[] = [];
  for (const arrow of [...arrows].sort((x, y) => y.magnitude - x.magnitude)) {
    const length = arrowLength(arrow.magnitude);
    const width = arrowWidth(arrow.magnitude);
    const polygon = curvedArrow(arrow, zoom, length, width);
    const tip = worldPx(polygon[Math.floor(polygon.length / 2)], zoom);
    const tail = worldPx(
      [(polygon[0][0] + polygon.at(-1)![0]) / 2, (polygon[0][1] + polygon.at(-1)![1]) / 2],
      zoom,
    );
    const city = arrow.flows[0] && worldPx([arrow.flows[0].to.lon, arrow.flows[0].to.lat], zoom);
    if (city && Math.hypot(tip[0] - city[0], tip[1] - city[1]) < 6) continue;
    const r = width * 1.25;
    const cx = Math.floor((tip[0] + tail[0]) / 2 / cell);
    const cy = Math.floor((tip[1] + tail[1]) / 2 / cell);
    let clash = false;
    for (let dx = -2; dx <= 2 && !clash; dx++)
      for (let dy = -2; dy <= 2 && !clash; dy++)
        for (const o of grid.get(`${cx + dx}:${cy + dy}`) ?? [])
          if (segmentDistance(tail, tip, o.a, o.b) < r + o.r + gapPx) {
            clash = true;
            break;
          }
    if (clash) continue;
    const key = `${cx}:${cy}`;
    grid.set(key, [...(grid.get(key) ?? []), { a: tail, b: tip, r }]);
    out.push({ ...arrow, polygon });
  }
  return out;
}
