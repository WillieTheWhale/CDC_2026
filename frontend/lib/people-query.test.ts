// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import { parsePeopleQuery, queryCountryCounts, queryPeople, queryPersonNetwork } from "./people-query";
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
  assert.deepEqual(lowZoom.data.people.map((person) => person.id), ["person-10002"]);
  const first = queryPeople(dataset, countries, { search: "", zoom: 3, limit: 2 });
  assert.throws(() => queryPeople(dataset, countries, { search: "other", zoom: 3, limit: 2, cursor: first.meta.next_cursor! }), /cursor/);
});

test("zoom tiers reveal prominence 1, then 2, then 3", () => {
  const tiered: PeopleDataset = {
    organizations: [], connections: [],
    people: [makePerson(1, "USA", 1), makePerson(2, "USA", 2), makePerson(3, "USA", 3)],
  };
  for (const [zoom, expected] of [
    [1, ["person-0001"]],
    [2, ["person-0001", "person-0002"]],
    [3, ["person-0001", "person-0002", "person-0003"]],
  ] as const) {
    const page = queryPeople(tiered, countries, { search: "", zoom, limit: 10 });
    assert.deepEqual(page.data.people.map((person) => person.id), expected);
    assert.equal(page.meta.total, expected.length);
  }
});

test("name search is global across low prominence and outside the map viewport", () => {
  const bounds: [number, number, number, number] = [-130, 20, -60, 55];
  const page = queryPeople(dataset, countries, { search: "Person 10002", zoom: 1, bbox: bounds, limit: 1 });
  assert.equal(page.meta.total, 1);
  assert.equal(page.data.people[0].id, "person-10002");
  const otherZoom = queryPeople(dataset, countries, { search: "Person 10002", zoom: 3, limit: 1 });
  assert.deepEqual(otherZoom.data.people.map((person) => person.id), page.data.people.map((person) => person.id));
});

test("unlocated records page across all tiers without a map or country match", () => {
  const first = makePerson(1, "USA", 1);
  const second = makePerson(2, "USA", 3);
  const third = makePerson(3, "USA", 2);
  first.regions = [];
  second.regions = [];
  const data: PeopleDataset = { people: [third, second, first], organizations: [], connections: [] };
  const filter = parsePeopleQuery(new URLSearchParams("unlocated=1&zoom=1&limit=1"));
  const page = queryPeople(data, countries, filter);
  assert.equal(page.meta.total, 2);
  assert.equal(page.data.people[0].id, first.id);
  const next = queryPeople(data, countries, { ...filter, cursor: page.meta.next_cursor! });
  assert.deepEqual(next.data.people.map((person) => person.id), [second.id]);
  assert.equal(next.meta.next_cursor, null);
  assert.throws(() => queryPeople(data, countries, { ...filter, unlocated: false, cursor: page.meta.next_cursor! }), /cursor/);
  assert.throws(() => parsePeopleQuery(new URLSearchParams("unlocated=1&bbox=-130,20,-60,55")), /cannot be combined/);
  assert.throws(() => parsePeopleQuery(new URLSearchParams("unlocated=1&country=USA")), /cannot be combined/);
  assert.deepEqual(queryPeople(data, countries, parsePeopleQuery(new URLSearchParams("bbox=-130,20,-60,55&zoom=3"))).data.people.map((person) => person.id), [third.id]);
});

test("country counts use all records while zoom visibility and country pagination stay distinct", () => {
  assert.deepEqual(queryCountryCounts(dataset, "", 1), [
    { iso3: "FJI", total: 1, visible: 1 },
    { iso3: "USA", total: 10002, visible: 0 },
  ]);
  const mixed: PeopleDataset = {
    organizations: [], connections: [],
    people: [makePerson(1, "USA", 1), makePerson(2, "USA", 2), makePerson(3, "USA", 3), makePerson(4, "FJI", 3)],
  };
  mixed.people[0].regions.push({ iso3: "USA", label: "United States" });
  assert.deepEqual(queryCountryCounts(mixed, "", 1), [
    { iso3: "FJI", total: 1, visible: 0 },
    { iso3: "USA", total: 3, visible: 1 },
  ]);
  assert.deepEqual(queryCountryCounts(mixed, "Person 0003", 1), [{ iso3: "USA", total: 1, visible: 1 }]);
  const first = queryPeople(mixed, countries, { search: "", zoom: 1, country: "USA", limit: 2, bbox: [170, -30, 190, 0] });
  assert.equal(first.meta.total, 3);
  assert.deepEqual(first.data.people.map((person) => person.id), ["person-0001", "person-0002"]);
  const second = queryPeople(mixed, countries, { search: "", zoom: 1, country: "USA", limit: 2, cursor: first.meta.next_cursor! });
  assert.deepEqual(second.data.people.map((person) => person.id), ["person-0003"]);
  assert.throws(() => queryPeople(mixed, countries, { search: "", zoom: 1, country: "FJI", limit: 2, cursor: first.meta.next_cursor! }), /cursor/);
  assert.throws(() => parsePeopleQuery(new URLSearchParams("country=US")), /country/);
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
