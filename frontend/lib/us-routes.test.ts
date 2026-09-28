// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { filterUsRoutes, type UsRoute } from "./us-routes";

const place = { name: "X", state: "AZ", country: "USA", lon: -112, lat: 33.4, precision: "city" as const };
const route = (id: string, drug: UsRoute["drug"]): UsRoute => ({
  id, drug, basis: "hidta_assessment", from: place, to: place, precision: "city", period: null,
  source: { id: "s", url: "https://example.gov", publisher: "P", title: "T", year: 2024, locator: "p. 1", quote: "q" },
});

test("US routes follow the drug filter; fentanyl shows under All only", () => {
  const all = [route("a", "meth"), route("b", "fentanyl"), route("c", "cocaine")];
  assert.equal(filterUsRoutes(all, "all").length, 3);
  assert.deepEqual(filterUsRoutes(all, "meth").map((r) => r.id), ["a"]);
  assert.equal(filterUsRoutes(all, "heroin").length, 0);
});
