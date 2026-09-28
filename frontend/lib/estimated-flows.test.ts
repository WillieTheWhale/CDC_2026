// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import {
  ESTIMATE_BASIS,
  arrowAlpha,
  bearing,
  feedLabel,
  fieldArrows,
  flowLine,
  parseEstimated,
  pickLabel,
  placeLabel,
  placementOrder,
  routeSteps,
  routeText,
  spacingKm,
  volumeBands,
  waveLabel,
  windGlyphs,
} from "./estimated-flows";
import type { EstimatedFlow } from "./estimated-flows";
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
  const from = { name: "A", iso3: "AAA", country: "Aland", lon: 0, lat: 0, intensity: 1 };
  const to = { name: "B", iso3: "BBB", country: "Bland", lon: 2.7, lat: 0, intensity: 1 };
  const east: EstimatedFlow = {
    drug: "cocaine",
    generation: 1,
    strength: 1,
    km: 300,
    from,
    to,
    corridors: [],
    path: [from, to],
    pick: "top",
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

test("hover lists the hovered path first, then the biggest paths nearby", async () => {
  const { nearestBigPaths } = await import("./estimated-flows");
  const f = layer.flows[0];
  // Hover where the map actually draws one of this flow's arrows (on its great-circle path).
  const mid = windGlyphs([f], 6)[0].position;
  const near = nearestBigPaths(mid, layer.flows, 3, 300, f);
  assert.equal(near.length, 3);
  const score = (p: (typeof near)[number]) => p.flow.strength / (1 + p.distanceKm / 150);
  // The hovered arrow's own path (distance ~0) always comes first, whatever its strength ...
  assert.equal(`${near[0].flow.from.name}>${near[0].flow.to.name}`, `${f.from.name}>${f.to.name}`);
  assert.ok(near[0].distanceKm < 25);
  // ... then the biggest paths nearby, strongest first.
  for (let i = 2; i < near.length; i++) assert.ok(score(near[i - 1]) >= score(near[i]));
  assert.ok(near.every((p) => p.distanceKm <= 4000 && p.drugs.length >= 1));
  const keys = near.map((p) => `${p.flow.from.name}${p.flow.to.name}`);
  assert.equal(new Set(keys).size, 3);
});

test("each arrow carries its feeding corridors, chain, wave and country names", () => {
  assert.ok(layer.corridors.length > 50);
  for (const c of layer.corridors) {
    assert.equal(c.id, `${c.drug}:${c.from}:${c.to}`);
    assert.equal(c.entry.iso3, c.to); // entry city lies in the destination country
    assert.ok(c.fromName && c.toName && c.confidence >= 0 && c.confidence <= 100);
  }
  const named = layer.cities.filter((c) => c.country !== c.iso3).length;
  assert.ok(named / layer.cities.length > 0.95, `${named}/${layer.cities.length} cities have a country name`);
  for (const f of layer.flows) {
    assert.ok(f.corridors.length >= 1 && f.corridors.length <= 4);
    assert.ok(f.corridors.every((c) => c.drug === f.drug));
    assert.equal(f.path.at(-1), f.to);
    assert.equal(f.path.at(-2), f.from);
    if (f.pick === "departure") assert.equal(f.path.length, 2);
    else {
      assert.equal(f.path.length, f.generation + 1); // one step per wave
      assert.ok(f.corridors.every((c) => c.entry === f.path[0]));
    }
  }
  const picks = new Set(layer.flows.map((f) => f.pick));
  assert.ok(picks.has("top") && picks.has("country_quota"));
});

test("every corridor country in the layer has an arrow of that drug", () => {
  const touched = new Set(layer.flows.flatMap((f) => [`${f.drug}:${f.from.iso3}`, `${f.drug}:${f.to.iso3}`]));
  const withCity = new Set(layer.cities.map((c) => c.iso3));
  const missing = layer.corridors
    .flatMap((c) => [`${c.drug}:${c.from}`, `${c.drug}:${c.to}`])
    .filter((k) => withCity.has(k.split(":")[1]) && !touched.has(k));
  assert.deepEqual([...new Set(missing)], []);
});

test("older files without details still parse", () => {
  const raw = JSON.parse(readFileSync(new URL("observed-2024.json", dir), "utf8"));
  const { countries, corridors, picks, details, ...data } = raw.data;
  void [countries, corridors, picks, details];
  const old = parseEstimated({ ...raw, data });
  assert.equal(old.flows.length, layer.flows.length);
  const f = old.flows[0];
  assert.deepEqual(f.path, [f.from, f.to]);
  assert.equal(f.pick, "top");
  assert.deepEqual(f.corridors, []);
  assert.match(flowLine(f), /fed by modeled corridors$/);
});

test("hover line: drug · from → to · strength · km · feeding corridor", () => {
  const f = layer.flows.find((x) => x.generation === 2 && x.from.country !== x.from.name)!;
  const line = flowLine(f);
  assert.match(
    line,
    /^(Cocaine|Heroin|Methamphetamine|Cannabis) · .+, .+ → .+, .+ · strength \d\.\d\d · \d+ km · fed by modeled corridor .+ → .+ \(\d+% confidence\)( \+\d+ more)?$/,
  );
  assert.ok(line.includes(`${f.from.name}, ${f.from.country} → ${f.to.name}, ${f.to.country}`));
  assert.ok(line.includes(`strength ${f.strength.toFixed(2)}`) && line.includes(`${f.km} km`));
  assert.ok(line.includes(`${f.corridors[0].fromName} → ${f.corridors[0].toName}`));
  assert.ok(flowLine(f, ["cannabis", "heroin"]).startsWith("Cannabis, Heroin · "));
  assert.match(ESTIMATE_BASIS, /not observed/i);
  assert.equal(placeLabel({ name: "Singapore", country: "Singapore" }), "Singapore");
});

test("route details: corridor origin → entry city → onward cities, with legs", () => {
  const f = layer.flows.find((x) => x.generation === 3 && x.pick !== "departure")!;
  const steps = routeSteps(f, layer.flows);
  assert.deepEqual(
    steps.map((s) => s.kind),
    ["origin", "entry", "onward", "onward", "onward"],
  );
  assert.equal(steps[0].label, f.corridors[0].fromName);
  assert.equal(steps[1].city, f.path[0]);
  const last = steps.at(-1)!;
  assert.equal(last.city, f.to);
  assert.equal(last.km, f.km);
  assert.equal(last.strength, f.strength);
  assert.equal(last.generation, 3);
  // Earlier legs resolve to the layer's own arrows (wave 1 and 2 of the same chain).
  assert.deepEqual(steps.slice(2).map((s) => s.generation), [1, 2, 3]);
  assert.ok(steps.slice(2).every((s) => typeof s.strength === "number" && s.km! > 0));
  assert.equal(routeText(f), steps.map((s) => s.label).join(" → "));
  assert.match(waveLabel(f), /step 3/);
  assert.ok(pickLabel[f.pick].length > 10);
  assert.match(feedLabel(f), /^fed by modeled corridor /);
});

test("departure and coverage picks explain themselves", () => {
  const dep = layer.flows.find((x) => x.pick === "departure");
  if (dep) {
    assert.match(feedLabel(dep), /^leaves along modeled corridor /);
    assert.equal(routeSteps(dep)[0].label, dep.path[0].country);
    assert.ok(dep.corridors.every((c) => c.from === dep.from.iso3));
  }
  assert.match(pickLabel.coverage, /coverage/i);
});

test("rendering: opacity grows with strength; each country's lead arrow is placed first", () => {
  assert.ok(arrowAlpha(0) < arrowAlpha(0.5) && arrowAlpha(0.5) < arrowAlpha(1));
  assert.ok(arrowAlpha(0) >= 90 && arrowAlpha(1) <= 255);
  const z = 4;
  const arrows = fieldArrows(windGlyphs(layer.flows, z + 1), (spacingKm(z) * 1.1) / 111);
  const order = placementOrder(arrows);
  assert.equal(order.length, arrows.length);
  const leads = new Set(arrows.map((a) => a.flows[0].to.iso3)).size;
  const head = order.slice(0, leads).map((a) => a.flows[0].to.iso3);
  assert.equal(new Set(head).size, leads);
  for (const a of arrows) assert.ok(a.strength >= 0 && a.strength <= 1);
});
