// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  COVERAGE_NATURE,
  coverageNatureLabel,
  fetchAllEvidenceValues,
  fetchAllMarketObservations,
  fetchEvidenceHealth,
  healthIsComplete,
  mapHealth,
  mapMarketObservation,
  mapMarketValue,
  mapOverdoseRow,
  marketUnitLabel,
  MARKET_DERIVED_CAVEAT,
  PWID_ESTIMATE_LABEL,
  type ApiEvidenceValueSummary,
  type ApiHealth,
  type ApiMarketObservation,
  type ApiOverdose,
  type ApiOverdoseRow,
} from "./evidence-api";
import { buildMarketCountry, combineHealth, type ObservedCountry, type ObservedRecord } from "./observed-data";

const fixture = <T>(name: string): T =>
  JSON.parse(readFileSync(new URL(`../../contracts/fixtures/${name}`, import.meta.url), "utf8")).data as T;

test("health fixture maps prevalence and labels coverage M vs C", () => {
  const health = fixture<ApiHealth>("evidence_health.json");
  const rows = mapHealth(health);
  const coverage = rows.filter((row) => row.domain === "treatment_coverage");
  assert.equal(rows.filter((row) => row.domain === "prevalence").length, health.prevalence.rows.length);
  assert.deepEqual(coverage.map((row) => coverageNatureLabel(row.status)), [COVERAGE_NATURE.M, COVERAGE_NATURE.C]);
  for (const row of rows) {
    assert.ok(row.sourceUrl, "every row keeps its source link");
    if (row.domain === "prevalence" || row.domain === "treatment_coverage") assert.equal(row.unit, "%");
  }
  const first = health.prevalence.rows[0];
  const mapped = rows[0];
  assert.equal(mapped.referencePeriod, first.reference_period);
  assert.equal(mapped.population, first.population);
  assert.equal(mapped.statusLabel, first.estimate_label);
  assert.equal(mapped.sourceRow?.rowNo, first.source_row.row_no);
});

test("overdose rows keep suppressed values unavailable, never zero", () => {
  const overdose = fixture<ApiOverdose>("evidence_overdose.json");
  const mapped = overdose.rows.map((row) => mapOverdoseRow(row, overdose.source_url));
  assert.equal(mapped[0].reportedValue, overdose.rows[0].reported_value);
  const suppressed: ApiOverdoseRow = { ...overdose.rows[0], suppressed: true, reported_value: null, predicted_value: null };
  const point = mapOverdoseRow(suppressed, overdose.source_url);
  assert.equal(point.reportedValue, null);
  assert.equal(point.predictedValue, null);
  assert.equal(point.suppressed, true);
  assert.match(point.status, /suppressed/);
});

test("blank source units read as not stated, not as a known unit", () => {
  assert.equal(marketUnitLabel("source unit unavailable", "price"), "USD · quantity unit not stated in source");
  assert.equal(marketUnitLabel("", "purity"), "unit not stated in source");
  assert.equal(marketUnitLabel(null), "unit not stated in source");
  assert.equal(marketUnitLabel("usd_per_pure_gram", "purity_adjusted_price_usd_per_pure_g"), "USD/pure g");
  assert.equal(marketUnitLabel("Pound", "price"), "Pound");
});

test("health fixture maps PWID (labelled estimates) and treatment contacts (counts)", () => {
  const health = fixture<ApiHealth>("evidence_health.json");
  assert.ok(healthIsComplete(health));
  const rows = mapHealth(health);
  const pwid = rows.filter((row) => row.domain === "pwid");
  const contacts = rows.filter((row) => row.domain === "treatment_contacts");
  assert.equal(pwid.length, health.pwid!.rows.length);
  assert.equal(contacts.length, health.treatment!.rows.length);
  assert.ok(pwid.length && contacts.length);
  for (const row of pwid) {
    assert.ok(row.statusLabel, "every PWID row carries an estimate label");
    assert.ok(row.sourceRow?.sheet && row.publicationYear);
  }
  for (const row of contacts) {
    assert.equal(row.unit, "persons treated");
    assert.match(row.caveat ?? "", /overlap/);
  }
  const first = health.pwid!.rows[0];
  const indirect = mapHealth({
    ...health,
    pwid: { ...health.pwid!, rows: [{ ...first, indirect_estimate: true, indirect_label: "Indirect estimate (x)" }] },
  }).find((row) => row.domain === "pwid")!;
  assert.equal(indirect.statusLabel, "Indirect estimate (x)");
  assert.equal(pwid[0].statusLabel, first.indirect_estimate ? first.indirect_label : PWID_ESTIMATE_LABEL);
});

const snapshot: ObservedCountry = {
  iso3: "MEX",
  researchValues: [],
  researchSamples: [],
  observations: [
    { id: "pwid:1", domain: "pwid", iso3: "MEX", year: 2016, metric: "people_who_inject_drugs", value: 0.1, unit: "percent_of_general_population", sourceId: "health:unodc_4_1", sourceUrl: "u", publicationYear: 2026 },
    { id: "prevalence:old", domain: "prevalence", iso3: "MEX", year: 2016, metric: "Cannabis", value: 2, unit: "%", sourceId: "health:unodc_1_2", sourceUrl: "u", publicationYear: 2026 },
    { id: "market_price:1", domain: "market_price", iso3: "MEX", year: 2021, metric: "price", value: 1, unit: "usd_per_gram", sourceId: "market:prices", sourceUrl: "u", publicationYear: 2026 },
  ] as ObservedRecord[],
};

test("health: a complete API response needs no snapshot; an older API fills only PWID/contacts", () => {
  const health = fixture<ApiHealth>("evidence_health.json");
  const live = mapHealth(health);
  const full = combineHealth("MEX", live, null)!;
  assert.deepEqual(full.observations.map((row) => row.id), live.map((row) => row.id));
  const legacy = { ...health, pwid: undefined, treatment: undefined };
  assert.equal(healthIsComplete(legacy), false);
  const mixed = combineHealth("MEX", mapHealth(legacy), snapshot, ["prevalence", "treatment_coverage"])!;
  assert.ok(!mixed.observations.some((row) => row.id === "prevalence:old"));
  assert.ok(mixed.observations.some((row) => row.id === "pwid:1"));
  assert.ok(!mixed.observations.some((row) => row.domain === "market_price"));
  assert.equal(combineHealth("ZZZ", [], null), null);
});

test("market observations map source units without inventing them", () => {
  const body = JSON.parse(readFileSync(new URL("../../contracts/fixtures/evidence_market_observations.json", import.meta.url), "utf8"));
  const source = body.data.observations as ApiMarketObservation[];
  const rows = source.map(mapMarketObservation);
  assert.ok(rows.length);
  rows.forEach((row, i) => {
    assert.equal(row.domain, "market_price");
    assert.equal(row.metric, source[i].measure);
    assert.equal(row.publicationYear, source[i].source.edition);
    assert.equal(row.sourceUrl, source[i].source.url);
    assert.equal(row.sourceRow?.cellNo, source[i].source_row.col_no);
  });
  const blank = mapMarketObservation({
    ...source[0],
    unit: null, unit_note: "Unit not stated in source", normalized_unit: null, original_unit: null, measure: "purity",
  });
  assert.equal(marketUnitLabel(blank.unit, blank.metric), "unit not stated in source");
  assert.equal(blank.originalUnit, null);
});

test("market: summary items carry form, level, edition and inputs without the snapshot", () => {
  const values = fixture<{ values: ApiEvidenceValueSummary[] }>("evidence_values.json").values;
  const market = values.find((value) => value.kind === "market")!;
  const mapped = mapMarketValue(market);
  assert.equal(mapped.form, market.form);
  assert.equal(mapped.marketLevel, market.market_level ?? null);
  assert.equal(mapped.publicationYear, market.source_publication_year);
  assert.equal(mapped.sourceUrl, market.source_url);
  assert.equal(mapped.sourceId, "market:" + market.source_id);
  assert.deepEqual(mapped.inputObservationIds, market.input_observation_ids);
  assert.equal(mapped.caveat, MARKET_DERIVED_CAVEAT);
  const obs: ApiMarketObservation = {
    observation_id: market.input_observation_ids![0], iso3: market.iso3, year: market.year, substance: market.drug,
    form: market.form ?? null, market_level: "retail", measure: "price", basis: "typical", value: 5, unit: "usd_per_gram",
    unit_note: null, original_value: 5, original_unit: "USD/g", publisher_estimate: false, status_label: "Source-reported observation",
    source: { source_id: "prices", url: "u", edition: 2026 }, source_row: { sheet: "s", row_no: 2, col_no: 3 },
  };
  const country = buildMarketCountry(market.iso3!, [obs, { ...obs, observation_id: 99, iso3: "ZZZ" }], values)!;
  assert.deepEqual(country.observations.map((row) => row.domain), ["market_price", "market_derived"]);
  assert.equal(buildMarketCountry("ZZZ", [], []), null);
});

test("values pagination follows next_cursor and health 404 means no rows", async () => {
  const original = globalThis.fetch;
  const seen: string[] = [];
  globalThis.fetch = (async (url: string) => {
    seen.push(url);
    if (url.includes("/api/evidence/health/")) return new Response(JSON.stringify({ error: { message: "none" } }), { status: 404 });
    if (url.includes("/api/evidence/market-observations")) {
      const next = url.includes("cursor=") ? null : "c2";
      return new Response(JSON.stringify({ meta: { total: 2, next_cursor: next }, data: { observations: [{ observation_id: next ? 1 : 2 }] } }));
    }
    const page = url.includes("cursor=") ? 2 : 1;
    return new Response(JSON.stringify({
      meta: { total: 2, next_cursor: page === 1 ? "abc" : null },
      data: { values: [{ id: String(page), kind: "market", metric_key: "m", label: "l", iso3: "MEX", drug: null, year: 2021, value: page, unit: "ratio" }] },
    }));
  }) as typeof fetch;
  try {
    const result = await fetchAllEvidenceValues("http://api.test", { kind: "market" });
    assert.deepEqual(result.values.map((value) => value.id), ["1", "2"]);
    assert.equal(seen[0], "http://api.test/api/evidence/values?limit=500&kind=market");
    assert.match(seen[1], /cursor=abc/);
    assert.equal(await fetchEvidenceHealth("http://api.test", "ZZZ"), null);
    const obs = await fetchAllMarketObservations("http://api.test", { iso3: "MEX" });
    assert.deepEqual(obs.observations.map((row) => row.observation_id), [1, 2]);
    assert.match(seen[seen.length - 2], /market-observations\?limit=5000&iso3=MEX$/);
    assert.match(seen[seen.length - 1], /cursor=c2/);
  } finally {
    globalThis.fetch = original;
  }
});
