// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import countries from "../../contracts/fixtures/countries.json";
import { displayCountryName, displayCountryText, displayNameMap, withDisplayName } from "./country-names";
import { parseEstimated } from "./estimated-flows";

test("World Bank names map to common display names", () => {
  const cases: [string, string][] = [
    ["Venezuela, RB", "Venezuela"],
    ["Egypt, Arab Rep.", "Egypt"],
    ["Korea, Rep.", "South Korea"],
    ["Korea, Dem. People's Rep.", "North Korea"],
    ["Iran, Islamic Rep.", "Iran"],
    ["Congo, Dem. Rep.", "DR Congo"],
    ["Congo, Rep.", "Republic of the Congo"],
    ["Yemen, Rep.", "Yemen"],
    ["Bahamas, The", "Bahamas"],
    ["Gambia, The", "Gambia"],
    ["Micronesia, Fed. Sts.", "Micronesia"],
    ["Hong Kong SAR, China", "Hong Kong"],
    ["Lao PDR", "Laos"],
  ];
  for (const [formal, shown] of cases) assert.equal(displayCountryName(formal), shown, formal);
  // Plain names and unknown values pass through.
  assert.equal(displayCountryName("Colombia", "COL"), "Colombia");
  assert.equal(displayCountryName("Atlantis"), "Atlantis");
  // A bare code (layers without a name for it) resolves by ISO3.
  assert.equal(displayCountryName("VEN", "VEN"), "Venezuela");
  assert.equal(displayCountryName(null, "KOR"), "South Korea");
  assert.equal(displayCountryName(undefined, "COL"), "COL");
});

test("no display name in the country catalog keeps World Bank comma or abbreviation style", () => {
  const shown = (countries.data as { iso3: string; name: string }[]).map((c) => displayCountryName(c.name, c.iso3));
  const leftovers = shown.filter((n) => /, (The|Rep\.|RB|Arab|Islamic|Dem\.|Fed\.)|SAR, China| PDR$/.test(n));
  assert.deepEqual(leftovers, []);
});

test("withDisplayName keeps the formal name for citations and is idempotent", () => {
  const row = withDisplayName({ iso3: "VEN", name: "Venezuela, RB", score: 50 });
  assert.equal(row.name, "Venezuela");
  assert.equal(row.formal_name, "Venezuela, RB");
  assert.equal(row.score, 50);
  const again = withDisplayName(row);
  assert.equal(again.name, "Venezuela");
  assert.equal(again.formal_name, "Venezuela, RB");
  assert.deepEqual(displayNameMap({ EGY: "Egypt, Arab Rep.", COL: "Colombia" }), { EGY: "Egypt", COL: "Colombia" });
});

test("estimated-flow layers show display names for cities and corridors", () => {
  const layer = parseEstimated({
    meta: { note: "" },
    data: {
      year: 2024,
      mode: "observed",
      drugs: ["cocaine"],
      cities: [
        ["Caracas", "VEN", -66.9, 10.5, 0.5],
        ["Cairo", "EGY", 31.2, 30.0, 0.5],
        ["Pyongyang", "PRK", 125.7, 39.0, 0.1],
      ],
      flows: [[0, 1, 0.5, 0, 1, 900]],
      countries: { VEN: "Venezuela, RB", EGY: "Egypt, Arab Rep." },
      corridors: [["cocaine:VEN:EGY", 0, "VEN", "EGY", 60, 0.4, 1]],
      picks: ["top"],
      details: [[[0], [0, 1], 0]],
    },
  });
  assert.equal(layer.cities[0].country, "Venezuela");
  assert.equal(layer.cities[1].country, "Egypt");
  assert.equal(layer.cities[2].country, "North Korea"); // no name in the file: by ISO3
  assert.equal(layer.corridors[0].fromName, "Venezuela");
  assert.equal(layer.corridors[0].toName, "Egypt");
});

test("free text replaces World Bank names, longest first", () => {
  assert.equal(
    displayCountryText("Spillover risk rises most in Venezuela, RB, Korea, Dem. People's Rep., Korea, Rep.; prevention there first."),
    "Spillover risk rises most in Venezuela, North Korea, South Korea; prevention there first.",
  );
  assert.equal(displayCountryText("Lao PDR and Egypt, Arab Rep."), "Laos and Egypt");
  assert.equal(displayCountryText("Colombia ranks #20"), "Colombia ranks #20");
  assert.equal(displayCountryText(null), null);
});
