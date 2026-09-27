// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import { parsePeopleQuery, queryPeople, queryPersonNetwork } from "./people-query";
import type { PeopleCountry, PeopleDataset, Person } from "./people-types";

const source = { url: "https://www.justice.gov/example", title: "Record", publisher: "DOJ", language: "en", claim: "Named in source" };
const makePerson = (index: number, region = "USA", prominence: 1 | 2 | 3 = 3): Person => ({
  id: `person-${String(index).padStart(4, "0")}`,
  name: `Person ${String(index).padStart(4, "0")}`,
  aliases: index === 3 ? ["Known Alias"] : [],
  status: "reported", prominence, organizationIds: ["org"], regions: [{ iso3: region, label: region }], drugs: [], sources: [source],
});
const people = Array.from({ length: 10003 }, (_, index) => makePerson(index));
people[10002] = makePerson(10002, "FJI", 1);
const dataset: PeopleDataset = {
  people,
  organizations: [{ id: "org", name: "Source named organization", regions: [], sources: [source] }],
  connections: [{ id: "edge", fromId: people[0].id, toId: people[1].id, type: "reported", label: "Source reported connection", sources: [source] }],
};
const countries: PeopleCountry[] = [
  { iso3: "USA", name: "United States", lat: 38.9, lon: -77 },
  { iso3: "FJI", name: "Fiji", lat: -18.1, lon: 178.4 },
];

test("keyset pagination reaches every record in stable order without duplicate IDs", () => {
  let cursor: string | undefined;
  const ids: string[] = [];
  do {
    const page = queryPeople(dataset, countries, { search: "", zoom: 3, limit: 250, cursor });
    assert.equal(page.meta.total, 10003);
    assert.ok(page.data.people.length <= 250);
    ids.push(...page.data.people.map((person) => person.id));
    cursor = page.meta.next_cursor ?? undefined;
  } while (cursor);
  assert.equal(ids.length, 10003);
  assert.equal(new Set(ids).size, 10003);
  assert.deepEqual(ids, [...ids].sort());
});

test("search, zoom, wrapped bbox and cursor filter binding", () => {
  const alias = queryPeople(dataset, countries, { search: "known alias", zoom: 3, limit: 10 });
  assert.deepEqual(alias.data.people.map((person) => person.id), ["person-0003"]);
  const pacific = queryPeople(dataset, countries, { search: "", zoom: 3, limit: 10, bbox: [170, -30, 190, 0] });
  assert.deepEqual(pacific.data.people.map((person) => person.id), ["person-10002"]);
  const lowZoom = queryPeople(dataset, countries, { search: "", zoom: 1, limit: 10, bbox: [170, -30, 190, 0] });
  assert.equal(lowZoom.meta.total, 0);
  const first = queryPeople(dataset, countries, { search: "", zoom: 3, limit: 2 });
  assert.throws(() => queryPeople(dataset, countries, { search: "other", zoom: 3, limit: 2, cursor: first.meta.next_cursor! }), /cursor/);
});

test("invalid boundaries are rejected and page edges only reference included people", () => {
  assert.throws(() => parsePeopleQuery(new URLSearchParams("limit=251")), /limit/);
  assert.throws(() => parsePeopleQuery(new URLSearchParams("bbox=0,30,20,10")), /bbox/);
  const page = queryPeople(dataset, countries, { search: "", zoom: 3, limit: 1 });
  assert.equal(page.data.connections.length, 0);
  const network = queryPersonNetwork(dataset, people[0].id)!;
  assert.deepEqual(network.data.people.map((person) => person.id), [people[0].id, people[1].id]);
  assert.deepEqual(network.data.connections.map((connection) => connection.id), ["edge"]);
  assert.equal(network.totalConnections, 1);
  assert.equal(queryPersonNetwork(dataset, "missing"), null);
});

test("high-degree ego responses are bounded and report the full claim count", () => {
  const manyEdges = Array.from({ length: 75 }, (_, index) => ({
    id: `edge-${String(index).padStart(3, "0")}`,
    fromId: people[0].id,
    toId: people[index + 1].id,
    type: "reported", label: "Source reported connection", sources: [source],
  }));
  const network = queryPersonNetwork({ ...dataset, connections: manyEdges.reverse() }, people[0].id)!;
  assert.equal(network.totalConnections, 75);
  assert.equal(network.data.connections.length, 48);
  assert.equal(network.data.people.length, 49);
  assert.deepEqual(network.data.connections.map((edge) => edge.id), manyEdges.reverse().slice(0, 48).map((edge) => edge.id));
});
