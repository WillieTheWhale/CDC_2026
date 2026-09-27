// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import countries from "../../contracts/fixtures/countries.json";
import apiPage from "../../contracts/fixtures/route_evidence.json";
import {
  evidenceForEdge,
  fixtureRouteEvidence,
  indexRouteEvidence,
  kgBasisNote,
  pairTypeLabel,
  type RouteEvidence,
} from "./route-evidence";

test("no-API fixture pairs have traceable country-scale evidence and valid endpoints", () => {
  const knownCountries = new Set(countries.data.map((country) => country.iso3));
  const ids = new Set<string>();
  assert.equal(fixtureRouteEvidence.length, 51);
  for (const route of fixtureRouteEvidence) {
    assert.ok(!ids.has(route.id), `duplicate ${route.id}`);
    ids.add(route.id);
    assert.equal(route.pair_type, "direct_reported_pair");
    assert.ok(route.from && knownCountries.has(route.from), `unknown origin ${route.from}`);
    assert.ok(route.to && knownCountries.has(route.to), `unknown destination ${route.to}`);
    assert.notEqual(route.from, route.to);
    assert.equal(route.geometry_precision, "country pair");
    assert.ok(route.source_locator.length > 5);
    assert.ok(route.source, `missing source for ${route.id}`);
    assert.match(route.source.url, /^https:\/\//);
    assert.deepEqual(route.supports_edge_ids, [`${route.drug}:${route.from}:${route.to}`]);
    if (route.period) {
      assert.ok(route.period[0] <= route.period[1]);
      assert.ok(route.period[1] <= route.source.publication_year);
    }
  }
  assert.ok(fixtureRouteEvidence.some((route) => route.from === "PAK" && route.to === "IND"));
  assert.ok(fixtureRouteEvidence.some((route) => route.from === "MOZ" && route.to === "ZAF"));
  assert.ok(fixtureRouteEvidence.some((route) => route.from === "MMR" && route.to === "LAO"));
});

test("fixture records match the /api/route-evidence record shape", () => {
  const apiRecord = apiPage.data[0];
  const fixture = fixtureRouteEvidence.find((r) => r.id === apiRecord.id);
  assert.ok(fixture, `fixture lacks ${apiRecord.id}`);
  assert.deepEqual(Object.keys(fixture).sort(), Object.keys(apiRecord).sort());
  assert.equal(fixture.caveat, apiRecord.caveat);
  assert.deepEqual(fixture.source, apiRecord.source);
});

const interpreted: RouteEvidence = {
  id: "cocaine:COL:ECU:trace-corridors",
  drug: "cocaine",
  from: "COL",
  to: "ECU",
  geography_from: null,
  geography_to: null,
  pair_type: "interpreted_corridor",
  basis: "regional route map and report text (TRACE transcription)",
  period: [2021, 2024],
  source: { id: "trace-corridors", publisher: "TRACE", title: "TRACE documented corridors", publication_year: 2026, url: "https://example.org/corridors.csv" },
  source_locator: "seed/corridors.csv row cocaine,COL,ECU",
  citations: [{ key: "WDR2026-7.3.1", publisher: "UNODC", title: "WDR 2026 annex 7.3.1", publication_year: 2026, url: "https://example.org/wdr" }],
  original_excerpt: null,
  geometry_precision: "country pair interpreted from regional map/text",
  caveat: "Indicative, not verbatim.",
  supports_edge_ids: ["cocaine:COL:ECU"],
};
const narrative: RouteEvidence = {
  ...interpreted,
  id: "cocaine:claim:andean:wdr2026_cocaine",
  from: null,
  to: null,
  geography_from: "Colombia and Ecuador",
  geography_to: "North America and Europe",
  pair_type: "narrative_context",
  source: { ...interpreted.source, id: "wdr2026_cocaine", publisher: "UNODC" },
  citations: [],
  supports_edge_ids: [],
};

test("index separates the three pair types; narrative context is never drawable", () => {
  const index = indexRouteEvidence([narrative, interpreted, ...fixtureRouteEvidence]);
  assert.equal(index.direct.length, 51);
  assert.deepEqual(index.interpreted.map((r) => r.id), [interpreted.id]);
  assert.deepEqual(index.narrative.map((r) => r.id), [narrative.id]);
  assert.ok([...index.direct, ...index.interpreted].every((r) => r.from && r.to));
  // Stable order: direct pairs, interpreted corridors, narrative context.
  assert.equal(index.all[0].pair_type, "direct_reported_pair");
  assert.equal(index.all.at(-1)!.pair_type, "narrative_context");
  const layers = new Map(index.sources.map((s) => [s.id, s.layer]));
  assert.equal(layers.get("trace-corridors"), "interpreted_corridor");
  assert.equal(layers.get("wdr2026_cocaine"), "narrative_context");
  assert.match(pairTypeLabel.interpreted_corridor, /TRACE transcription/);
});

test("a selected edge links to its evidence by evidence_ids, else by supports_edge_ids", () => {
  const index = indexRouteEvidence([interpreted, ...fixtureRouteEvidence]);
  const direct = "cocaine:COL:ECU:unodc-cocaine-2023";
  // API edge: order follows evidence_ids; unknown ids are dropped.
  assert.deepEqual(
    evidenceForEdge(index, { id: "cocaine:COL:ECU", evidence_ids: [direct, interpreted.id, "missing"] }).map((r) => r.id),
    [direct, interpreted.id],
  );
  // Snapshot edge without ids: records that support it, direct pairs first.
  assert.deepEqual(
    evidenceForEdge(index, { id: "cocaine:COL:ECU" }).map((r) => r.id),
    [direct, interpreted.id],
  );
  assert.deepEqual(evidenceForEdge(index, { id: "meth:USA:CAN" }), []);
});

test("kg basis wording never presents kg as an observed pair volume", () => {
  assert.match(kgBasisNote("allocated_seizure_scale"), /allocated from national seizure totals; not an observed pair volume/);
  assert.match(kgBasisNote(undefined), /not an observed pair volume/);
});
