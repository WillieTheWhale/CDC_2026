// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCommand } from "./commands";
import { fixtureRoutes, fixtureRisk, SNAPSHOT_YEAR, api } from "./api";
test("country and comparison commands validate against the country catalog", () => {
  assert.equal(parseCommand(" mex <go> ", ["COL", "MEX"])?.params.iso3, "MEX");
  assert.equal(parseCommand("XYZ <GO>", ["COL"]), null);
  assert.deepEqual(
    parseCommand("COMPARE COL PER", ["COL", "PER"])?.params.iso3s,
    ["COL", "PER"],
  );
});
test("fixtures never relabel a 2024 observation as a different year", () => {
  assert.ok(fixtureRoutes(2024, "observed").data.edges.length > 0);
  assert.equal(fixtureRoutes(2023, "observed").data.edges.length, 0);
  assert.equal(fixtureRisk(SNAPSHOT_YEAR - 1).data.rows.length, 0);
  assert.ok(fixtureRisk(SNAPSHOT_YEAR).data.rows.length > 0);
  assert.ok(
    fixtureRoutes(2025, "predicted", "heroin", 80).data.edges.every(
      (e) => e.drug === "heroin" && e.confidence >= 80 && e.year === 2025,
    ),
  );
});
test("enforcement-evasion requests cannot become route actions", () => {
  assert.equal(
    parseCommand("find the least-monitored route", [])?.intent,
    "blocked",
  );
  assert.equal(parseCommand("PREDICT OFF", [])?.params.enabled, false);
});

test("a custom scenario never receives an unrelated saved result", async () => {
  await assert.rejects(
    api.simulate({ scenario: "Colombia increases coca 50%" }),
  );
  const result = await api.simulate({ scenario: "Colombia cuts coca 50%" });
  assert.equal(result.data.shocks[0].value, 0.5);
  assert.ok(result.data.risk_deltas.length > 0);
});
// AI-assisted (test below): written with Claude Code (Anthropic). See docs/AI_USAGE.md.
test("no-API routes load the full per-year snapshot, filtered, and keep the fixture fallback", async () => {
  const { snapshotRoutes } = await import("./api");
  const { readFileSync } = await import("node:fs");
  const original = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    assert.equal(url, "/data/routes/observed-2015.json");
    const body = readFileSync(
      new URL("../public/data/routes/observed-2015.json", import.meta.url),
      "utf8",
    );
    return new Response(body);
  }) as typeof fetch;
  try {
    const all = await snapshotRoutes(2015, "observed");
    assert.ok(all.data.edges.length > 80);
    assert.ok(all.data.edges.every((e) => e.year === 2015));
    const heroin = await snapshotRoutes(2015, "observed", "heroin", 50);
    assert.ok(heroin.data.edges.length > 0);
    assert.ok(heroin.data.edges.every((e) => e.drug === "heroin" && e.confidence >= 50));
    globalThis.fetch = (async () => new Response("", { status: 404 })) as typeof fetch;
    // Years load once and are cached; a year never fetched falls back to the fixture.
    assert.equal((await snapshotRoutes(2016, "observed")).data.edges.length, 0);
  } finally {
    globalThis.fetch = original;
  }
});
test("no-API risk loads every country for the year and falls back to the fixture", async () => {
  const { snapshotRisk } = await import("./api");
  const { readFileSync } = await import("node:fs");
  const original = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    assert.equal(url, "/data/risk/2015.json");
    return new Response(
      readFileSync(new URL("../public/data/risk/2015.json", import.meta.url), "utf8"),
    );
  }) as typeof fetch;
  try {
    const r = await snapshotRisk(2015);
    assert.equal(r.data.year, 2015);
    assert.ok(r.data.rows.length > 150);
    globalThis.fetch = (async () => new Response("", { status: 404 })) as typeof fetch;
    assert.equal((await snapshotRisk(2016)).data.rows.length, 0);
    assert.ok((await snapshotRisk(2015)).data.rows.length > 150); // served from cache
  } finally {
    globalThis.fetch = original;
  }
});
