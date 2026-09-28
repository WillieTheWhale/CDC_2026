// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeDataset } from "./people-api";
import type { PeopleDataset, Person } from "./people-types";

const source = { url: "https://www.justice.gov/example", title: "Case", publisher: "DOJ", language: "en", claim: "Country association" };
const person: Person = {
  id: "person", name: "Example Person", status: "reported", prominence: 1,
  organizationIds: [], drugs: [], sources: [source],
  regions: [
    { iso3: "KEN", label: "Kenya", evidence: { claim: "Cited activity in Kenya", period: "2014", sourceUrl: source.url } },
    { iso3: "AUS", label: "Australia", evidence: { claim: "Uncited activity", sourceUrl: "https://example.com/unrelated" } },
    { iso3: "USA", label: "United States" },
  ],
};

test("region evidence requires an exact citable person source while legacy associations remain visible", () => {
  const dataset: PeopleDataset = { organizations: [], people: [person], connections: [] };
  const regions = normalizeDataset(dataset).people[0].regions;
  assert.equal(regions.length, 3);
  assert.deepEqual(regions[0].evidence, person.regions[0].evidence);
  assert.equal(regions[1].evidence, undefined);
  assert.equal(regions[2].evidence, undefined);
});
