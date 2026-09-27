// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { landAnchor, onLand } from "../scripts/land-anchors.mjs";

const geo = JSON.parse(
  readFileSync(new URL("../public/geo/countries.json", import.meta.url), "utf8"),
);
type Feature = {
  properties: { iso3: string; label_lon: number; label_lat: number };
  geometry: unknown;
};
// The map keys anchors by ISO3 and the last feature wins, so test that one.
const byIso = new Map<string, Feature>(
  geo.features.map((f: Feature) => [f.properties.iso3, f]),
);
const all = (iso3: string): Feature[] =>
  geo.features.filter((f: Feature) => f.properties.iso3 === iso3);

test("every modeled route endpoint is anchored on land", () => {
  const dir = new URL("../public/data/routes/", import.meta.url);
  const ends = new Set<string>();
  for (const name of readdirSync(dir).filter((n) => /-\d{4}\.json$/.test(n))) {
    const body = JSON.parse(readFileSync(new URL(name, dir), "utf8"));
    for (const e of body.data.edges) ends.add(e.from).add(e.to);
  }
  assert.ok(ends.size > 50);
  for (const iso3 of ends) {
    const f = byIso.get(iso3);
    if (!f) continue; // no polygon: the map falls back to the World Bank capital
    const p = f.properties;
    assert.ok(
      all(iso3).some((g) => onLand([p.label_lon, p.label_lat], g.geometry)),
      `${iso3} anchor is at sea`,
    );
  }
});

test("split countries anchor on their mainland, not an overseas islet", () => {
  // France + Clipperton Island, Australia + Ashmore and Cartier, Brazil, Kazakhstan.
  for (const [iso3, name] of [
    ["FRA", "France"],
    ["AUS", "Australia"],
    ["BRA", "Brazil"],
    ["KAZ", "Kazakhstan"],
  ]) {
    const features = all(iso3);
    assert.ok(features.length > 1, `${iso3} is no longer split`);
    const main = features.find((f) => (f.properties as { name?: string }).name === name)!;
    const p = byIso.get(iso3)!.properties;
    assert.ok(onLand([p.label_lon, p.label_lat], main.geometry), `${iso3} anchor is off the mainland`);
  }
});

test("an offshore label point snaps to the country's port", () => {
  const nzl = byIso.get("NZL")!;
  const moved = landAnchor({
    ...nzl,
    properties: { ...nzl.properties, label_lon: 172.787, label_lat: -39.759 },
  });
  assert.equal(moved.label_source, "port: Port of Auckland");
  assert.ok(onLand([moved.label_lon, moved.label_lat], nzl.geometry));
});

test("without a listed port an offshore point snaps to the nearest land", () => {
  const stp = byIso.get("STP")!;
  const moved = landAnchor({
    ...stp,
    properties: { ...stp.properties, label_lon: 7.021, label_lat: 0.9709 },
  });
  assert.equal(moved.label_source, "nearest land");
  assert.ok(onLand([moved.label_lon, moved.label_lat], stp.geometry));
});
