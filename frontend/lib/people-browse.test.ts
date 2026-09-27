// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import test from "node:test";
import { peopleRequestViewport } from "./people-browse";

const bounds: [number, number, number, number] = [-100, -10, -70, 30];

test("Connections browses all tiers without the hidden map viewport", () => {
  assert.deepEqual(peopleRequestViewport({ mode: "graph", searching: false, selectedCountry: null, zoom: 1, bounds }), { zoom: 3, bounds: undefined });
  assert.deepEqual(peopleRequestViewport({ mode: "graph", searching: true, selectedCountry: "USA", zoom: 2, bounds }), { zoom: 3, bounds: undefined });
});

test("Map retains its viewport until a search or country browse expands the scope", () => {
  assert.deepEqual(peopleRequestViewport({ mode: "map", searching: false, selectedCountry: null, zoom: 1, bounds }), { zoom: 1, bounds });
  assert.deepEqual(peopleRequestViewport({ mode: "map", searching: true, selectedCountry: null, zoom: 1, bounds }), { zoom: 3, bounds: undefined });
  assert.deepEqual(peopleRequestViewport({ mode: "unlocated", searching: false, selectedCountry: null, zoom: 1, bounds }), { zoom: 3, bounds: undefined });
});
