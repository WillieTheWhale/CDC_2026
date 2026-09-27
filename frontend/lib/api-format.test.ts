// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { api, formatNumber, SNAPSHOT_YEAR } from "./api";

test("formatNumber uses one magnitude rule for every value", () => {
  // Previously 13,398.6 stayed long-form while 347,600 went compact.
  assert.equal(formatNumber(13398.6), "13.4K");
  assert.equal(formatNumber(347600), "347.6K");
  assert.equal(formatNumber(1_250_000), "1.3M");
  assert.equal(formatNumber(9876.54), "9,876.5");
  assert.equal(formatNumber(-15000), "-15K");
  assert.equal(formatNumber(0), "0");
  assert.equal(formatNumber(null), "—");
  assert.equal(formatNumber(undefined), "—");
  assert.equal(formatNumber(Number.NaN), "—");
});

test("country, risk and price envelopes carry display names and keep the formal name", async () => {
  const countries = (await api.countries()).data;
  const ven = countries.find((c) => c.iso3 === "VEN");
  assert.equal(ven?.name, "Venezuela");
  assert.equal(ven?.formal_name, "Venezuela, RB");
  assert.ok(!countries.some((c) => c.region !== c.region.trim()), "regions are trimmed");
  const risk = (await api.risk(SNAPSHOT_YEAR)).data.rows;
  assert.ok(risk.length > 0);
  assert.ok(!risk.some((r) => /, (RB|Rep\.|The|Arab Rep\.|Islamic Rep\.)$/.test(r.name)));
  assert.ok(risk.every((r) => typeof r.formal_name === "string"));
  const prices = (await api.prices()).data.series;
  assert.ok(prices.every((p) => !/, (RB|Rep\.|The)$/.test(p.name)));
});
