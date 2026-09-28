// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// Connected mode: route evidence pages in from the API; estimated flows use
// /api/estimated-flows when served and fall back to the snapshot files.
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import page from "../../contracts/fixtures/route_evidence.json";

process.env.NEXT_PUBLIC_API_URL = "https://api.example.test/";
const calls: string[] = [];
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
globalThis.fetch = (async (input: string | URL | Request) => {
  const url = String(input);
  calls.push(url);
  if (url.startsWith("https://api.example.test/api/route-evidence?")) {
    const cursor = new URL(url).searchParams.get("cursor");
    return cursor
      ? json({ ...page, meta: { ...page.meta, next_cursor: null }, data: page.data.slice(3) })
      : json({ ...page, meta: { ...page.meta, next_cursor: "page-2" }, data: page.data.slice(0, 3) });
  }
  if (url.startsWith("https://api.example.test/api/estimated-flows")) return json({ error: {} }, 404);
  if (url.startsWith("/data/estimated/"))
    return new Response(readFileSync(new URL(`../public${url}`, import.meta.url)));
  return json({}, 500);
}) as typeof fetch;

test("connected mode pages through /api/route-evidence instead of the fixture", async () => {
  const { routeEvidence } = await import("./api");
  const records = await routeEvidence();
  assert.deepEqual(records.map((r) => r.id), page.data.map((r) => r.id));
  const pages = calls.filter((u) => u.includes("/api/route-evidence?"));
  assert.equal(pages.length, 2);
  assert.match(pages[0], /limit=250/);
  assert.match(pages[1], /cursor=page-2/);
  await routeEvidence(); // cached: no refetch
  assert.equal(calls.filter((u) => u.includes("/api/route-evidence?")).length, 2);
});

test("estimated flows fall back to the snapshot until the API serves them", async () => {
  const { estimatedFlows } = await import("./api");
  const layer = await estimatedFlows(2024, "observed");
  assert.equal(layer.live, false);
  assert.equal(layer.year, 2024);
  assert.ok(layer.flows.length > 500);
  await estimatedFlows(2023, "observed");
  // A 404 is remembered: later years skip the endpoint.
  assert.equal(calls.filter((u) => u.includes("/api/estimated-flows")).length, 1);
});
