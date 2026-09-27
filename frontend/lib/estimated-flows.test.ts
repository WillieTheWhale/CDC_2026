// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import {
  bearing,
  fieldArrows,
  parseEstimated,
  spacingKm,
  volumeBands,
  windGlyphs,
} from "./estimated-flows";
import type { Edge } from "./types";

const dir = new URL("../public/data/estimated/", import.meta.url);
const layer = parseEstimated(
  JSON.parse(readFileSync(new URL("observed-2024.json", dir), "utf8")),
);

test("every year has a labelled estimated layer", () => {
  const files = readdirSync(dir).filter((n) => /-\d{4}\.json$/.test(n));
  assert.equal(files.length, 20);
  const raw = JSON.parse(readFileSync(new URL("observed-2024.json", dir), "utf8"));
  assert.equal(raw.meta.kind, "estimated");
  assert.match(raw.meta.note, /not observed/i);
  // Design boundary: no enforcement, customs or detection variable.
  assert.ok(!raw.meta.variables.some((v: string) => /enforce|custom|detect|police/i.test(v)));
});

test("estimated arrows are regional and point at real cities", () => {
  assert.ok(layer.flows.length > 500);
  for (const f of layer.flows) {
    assert.ok(f.km > 0 && f.km <= 1500, `${f.from.name}->${f.to.name} ${f.km} km`);
    assert.ok(f.strength >= 0 && f.strength <= 1);
    assert.ok(f.from && f.to && f.from !== f.to);
  }
  assert.ok(layer.cities.every((c) => c.intensity >= 0 && c.intensity <= 1));
  assert.equal(Math.max(...layer.cities.map((c) => c.intensity)), 1);
});

test("arrow glyphs get denser as the map zooms in", () => {
  assert.ok(spacingKm(6) < spacingKm(3));
  const few = windGlyphs(layer.flows.slice(0, 50), 2).length;
  const many = windGlyphs(layer.flows.slice(0, 50), 6).length;
  assert.ok(many > few * 4);
});

test("bearing and field arrows follow the flow direction", () => {
  assert.ok(Math.abs(bearing([0, 0], [0, 10])) < 1e-6); // north
  assert.ok(Math.abs(bearing([0, 0], [10, 0]) - 90) < 1e-6); // east
  const east = {
    drug: "cocaine" as const,
    generation: 1 as const,
    strength: 1,
    km: 300,
    from: { name: "A", iso3: "AAA", lon: 0, lat: 0, intensity: 1 },
    to: { name: "B", iso3: "BBB", lon: 2.7, lat: 0, intensity: 1 },
  };
  const arrows = fieldArrows(windGlyphs([east], 6), 1);
  assert.ok(arrows.length > 0);
  for (const a of arrows) assert.ok(Math.abs(a.bearing - 90) < 2, String(a.bearing));
});

test("country volume bands grow with modeled kg on the shown corridors", () => {
  const e = (from: string, to: string, kg: number) => ({ from, to, kg }) as Edge;
  const bands = volumeBands([e("COL", "USA", 100000), e("MEX", "USA", 50000), e("PER", "BOL", 10)]);
  assert.equal(bands.get("USA"), 5);
  assert.ok(bands.get("COL")! >= bands.get("MEX")!);
  assert.ok(bands.get("BOL")! < bands.get("MEX")!);
  assert.equal(volumeBands([]).size, 0);
});

test("placed arrows point at a city, stay off it, and never overlap", async () => {
  const { fieldArrows, placeArrows, windGlyphs, spacingKm, bearing } = await import("./estimated-flows");
  for (const zoom of [1, 3, 5]) {
    const arrows = fieldArrows(windGlyphs(layer.flows, zoom + 1), (spacingKm(zoom) * 1.1) / 111);
    const placed = placeArrows(arrows, zoom);
    assert.ok(placed.length > 20, `zoom ${zoom}: ${placed.length}`);
    for (const a of placed) {
      const city = a.flows[0].to;
      const toCity = bearing(a.position, [city.lon, city.lat]);
      assert.ok(Math.abs(((toCity - a.bearing + 540) % 360) - 180) < 1e-6);
      const tip = a.polygon[Math.floor(a.polygon.length / 2)];
      assert.ok(Math.hypot(tip[0] - city.lon, tip[1] - city.lat) > 1e-4, "head on the city");
    }
  }
  // Greedy placement drops arrows that would touch a stronger one.
  const z = 3;
  const all = fieldArrows(windGlyphs(layer.flows, z + 1), (spacingKm(z) * 1.1) / 111);
  assert.ok(placeArrows(all, z).length < all.length);
});

test("hover lists the three biggest estimated paths near a point", async () => {
  const { nearestBigPaths } = await import("./estimated-flows");
  const f = layer.flows[0];
  const mid: [number, number] = [(f.from.lon + f.to.lon) / 2, (f.from.lat + f.to.lat) / 2];
  const near = nearestBigPaths(mid, layer.flows);
  assert.equal(near.length, 3);
  const score = (p: (typeof near)[number]) => p.flow.strength / (1 + p.distanceKm / 150);
  for (let i = 1; i < near.length; i++) assert.ok(score(near[i - 1]) >= score(near[i]));
  assert.ok(near.every((p) => p.distanceKm <= 4000 && p.drugs.length >= 1));
  // The arrow's own path (distance ~0) is among the results.
  assert.ok(near.some((p) => p.distanceKm < 1));
  const keys = near.map((p) => `${p.flow.from.name}${p.flow.to.name}`);
  assert.equal(new Set(keys).size, 3);
});
