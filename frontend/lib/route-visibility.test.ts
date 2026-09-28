// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Edge } from "./types";
import { visibleModelRoutes } from "./route-visibility";

const edge = (id: string, from: string, to: string, volume_norm: number): Edge => ({
  id,
  from,
  to,
  drug: "heroin",
  year: 2024,
  volume_norm,
  kg: null,
  cases: null,
  confidence: 80,
  is_emerging: false,
  probability: null,
  change_pct: null,
  signals: {},
  drivers: [],
});

test("world view favors strong corridors while retaining regional flows", () => {
  const countries = new Map([
    ["AAA", { lat: 10, lon: -70 }],
    ["BBB", { lat: 12, lon: -68 }],
    ["CCC", { lat: 14, lon: -66 }],
    ["DDD", { lat: 16, lon: -64 }],
    ["PAK", { lat: 30, lon: 69 }],
    ["IND", { lat: 22, lon: 78 }],
  ]);
  const routes = [
    edge("a", "AAA", "BBB", 1),
    edge("b", "AAA", "CCC", 0.9),
    edge("c", "AAA", "DDD", 0.8),
    edge("d", "PAK", "IND", 0.4),
    edge("e", "IND", "PAK", 0.3),
  ];
  assert.deepEqual(visibleModelRoutes(routes, countries, 1).map((e) => e.id), ["a", "b", "d"]);
  assert.equal(visibleModelRoutes(routes, countries, 4).length, 5);
  assert.equal(visibleModelRoutes(routes, countries, 6).length, 0);
});
