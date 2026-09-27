// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import type { FeatureCollection, Geometry, Polygon, MultiPolygon } from "geojson";
import { countryAnchors, inPolygon } from "./country-anchors";

const geo: FeatureCollection<Geometry> = JSON.parse(
  readFileSync(new URL("../public/geo/countries.json", import.meta.url), "utf8"),
);
const anchors = countryAnchors(geo);

test("duplicate ISO3 features resolve to the mainland, not overseas specks", () => {
  const france = anchors.get("FRA")!;
  assert.ok(france.lon > -5 && france.lon < 9 && france.lat > 42 && france.lat < 51);
  const australia = anchors.get("AUS")!;
  assert.ok(australia.lon > 115 && australia.lon < 152 && australia.lat < -20);
  const brazil = anchors.get("BRA")!;
  assert.ok(brazil.lon > -60 && brazil.lat > -20 && brazil.lat < 0);
});

test("every anchor lies on its own country's land", () => {
  const offshore: string[] = [];
  for (const [iso3, anchor] of anchors) {
    const onLand = geo.features.some((feature) => {
      if (feature.properties?.iso3 !== iso3) return false;
      const geometry = feature.geometry as Polygon | MultiPolygon;
      const parts = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
      return parts.some((polygon) => inPolygon([anchor.lon, anchor.lat], polygon));
    });
    if (!onLand) offshore.push(iso3);
  }
  assert.deepEqual(offshore, []);
});
