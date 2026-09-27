// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// Estimated local flows: a labelled, map-only layer built by
// `uv run trace estimate-flows` (backend/trace_backend/model/estimated_flows.py).
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
  generation: 1 | 2;
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
}
interface EstimatedFile {
  meta: { note: string };
  data: {
    year: number;
    mode: string;
    drugs: Drug[];
    cities: [string, string, number, number, number][];
    flows: [number, 1 | 2, number, number, number, number][];
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

export const ARROW_ICON = {
  url:
    "data:image/svg+xml;charset=utf-8," +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">' +
        '<path d="M32 4 L58 40 L41 40 L41 60 L23 60 L23 40 L6 40 Z" fill="#fff"/></svg>',
    ),
  width: 64,
  height: 64,
  anchorY: 32,
  mask: true,
};

// Slope-field view: sum glyph vectors in a regular lon/lat grid and draw one
// arrow per cell (direction = net flow, size = magnitude, color = dominant
// drug), like wind arrows on a weather map.
export interface FieldArrow {
  position: [number, number];
  bearing: number;
  magnitude: number; // 0-1 relative to the strongest cell
  drug: Drug;
  flows: EstimatedFlow[];
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
    .map((c) => ({
      position: [c.lon / c.w, c.lat / c.w] as [number, number],
      bearing: ((Math.atan2(c.vx, c.vy) / rad) + 360) % 360,
      magnitude: Math.hypot(c.vx, c.vy),
      drug: [...c.drugs.entries()].sort((a, b) => b[1] - a[1])[0][0],
      flows: [...c.flows]
        .sort((a, b) => b.strength - a.strength)
        .filter(
          (f, i, all) =>
            all.findIndex((g) => g.from.name === f.from.name && g.to.name === f.to.name) === i,
        )
        .slice(0, 3),
    }));
  const peak = Math.max(1e-9, ...raw.map((a) => a.magnitude));
  return raw
    .map((a) => ({ ...a, magnitude: Math.sqrt(a.magnitude / peak) }))
    .filter((a) => a.magnitude > 0.04);
}
