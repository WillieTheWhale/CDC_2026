// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import countries from "../../contracts/fixtures/countries.json";
import { routeEvidence, routeEvidenceSourceById } from "./route-evidence";

test("published links have traceable country-scale evidence and valid endpoints", () => {
  const knownCountries = new Set(countries.data.map((country) => country.iso3));
  const ids = new Set<string>();
  for (const route of routeEvidence) {
    assert.ok(!ids.has(route.id), `duplicate ${route.id}`);
    ids.add(route.id);
    assert.ok(knownCountries.has(route.from), `unknown origin ${route.from}`);
    assert.ok(knownCountries.has(route.to), `unknown destination ${route.to}`);
    assert.notEqual(route.from, route.to);
    assert.equal(route.geometryPrecision, "country pair");
    assert.ok(route.sourceLocator.length > 5);
    const source = routeEvidenceSourceById.get(route.sourceId);
    assert.ok(source, `missing source ${route.sourceId}`);
    assert.match(source.url, /^https:\/\//);
    if (route.period) {
      assert.ok(route.period[0] <= route.period[1]);
      assert.ok(route.period[1] <= source.publicationYear);
    }
  }
  assert.ok(routeEvidence.some((route) => route.from === "PAK" && route.to === "IND"));
  assert.ok(routeEvidence.some((route) => route.from === "MOZ" && route.to === "ZAF"));
  assert.ok(routeEvidence.some((route) => route.from === "MMR" && route.to === "LAO"));
});
