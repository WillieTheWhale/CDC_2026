// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type { PeopleCountry, PeopleDataset, Person } from "./people-types";

export interface ParsedPeopleQuery {
  search: string;
  zoom: 1 | 2 | 3;
  bbox?: [number, number, number, number];
  limit: number;
  cursor?: string;
}

export interface PeoplePage {
  data: PeopleDataset;
  meta: { total: number; next_cursor: string | null };
}

const fold = (value: string) => value.normalize("NFKC").toLocaleLowerCase("en-US");
const sortKey = (person: Person) => [fold(person.name), person.id] as const;
const compare = (left: Person, right: Person) => {
  const a = sortKey(left);
  const b = sortKey(right);
  return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0;
};

export function parsePeopleQuery(params: URLSearchParams): ParsedPeopleQuery {
  const search = (params.get("search") ?? "").trim();
  if (search.length > 120) throw new Error("search must be 120 characters or fewer");
  const zoomValue = Number(params.get("zoom") ?? "1");
  if (![1, 2, 3].includes(zoomValue)) throw new Error("zoom must be 1, 2, or 3");
  const limitValue = Number(params.get("limit") ?? "100");
  if (!Number.isSafeInteger(limitValue) || limitValue < 1 || limitValue > 250) throw new Error("limit must be from 1 to 250");
  const bboxValue = params.get("bbox");
  let bbox: ParsedPeopleQuery["bbox"];
  if (bboxValue !== null) {
    const parts = bboxValue.split(",").map(Number);
    if (parts.length !== 4 || parts.some((value) => !Number.isFinite(value)) ||
      parts[1] < -90 || parts[1] > 90 || parts[3] < -90 || parts[3] > 90 || parts[1] > parts[3] ||
      parts[2] < parts[0] || parts[2] - parts[0] > 720) throw new Error("bbox must be west,south,east,north");
    bbox = parts as ParsedPeopleQuery["bbox"];
  }
  const cursor = params.get("cursor") ?? undefined;
  if (cursor && cursor.length > 4096) throw new Error("cursor is too long");
  return { search, zoom: zoomValue as 1 | 2 | 3, bbox, limit: limitValue, cursor };
}

function withinBbox(lon: number, lat: number, [west, south, east, north]: [number, number, number, number]) {
  if (lat < south || lat > north) return false;
  if (east - west >= 360) return true;
  const offset = ((lon - west) % 360 + 360) % 360;
  return offset <= east - west;
}

function filterKey(query: ParsedPeopleQuery) {
  return JSON.stringify([fold(query.search), query.zoom, query.bbox ?? null]);
}

function decodeCursor(value: string, key: string): [string, string] {
  try {
    const parsed: unknown = JSON.parse(Buffer.from(value, "base64url").toString("utf8"));
    if (!Array.isArray(parsed) || parsed.length !== 3 || parsed[0] !== key ||
      typeof parsed[1] !== "string" || typeof parsed[2] !== "string") throw new Error();
    return [parsed[1], parsed[2]];
  } catch {
    throw new Error("cursor does not match these filters");
  }
}

export function queryPeople(dataset: PeopleDataset, countries: PeopleCountry[], query: ParsedPeopleQuery): PeoplePage {
  const countryById = new Map(countries.map((country) => [country.iso3, country]));
  const threshold = query.zoom === 1 ? 3 : query.zoom === 2 ? 2 : 1;
  const needle = fold(query.search);
  const filtered = dataset.people.filter((person) =>
    person.prominence >= threshold &&
    (!needle || [person.name, ...(person.aliases ?? [])].some((value) => fold(value).includes(needle))) &&
    (!query.bbox || person.regions.some((region) => {
      const country = countryById.get(region.iso3);
      return country?.lon != null && country.lat != null && withinBbox(country.lon, country.lat, query.bbox!);
    })),
  ).sort(compare);
  const key = filterKey(query);
  let start = 0;
  if (query.cursor) {
    const last = decodeCursor(query.cursor, key);
    start = filtered.findIndex((person) => {
      const current = sortKey(person);
      return current[0] > last[0] || current[0] === last[0] && current[1] > last[1];
    });
    if (start < 0) start = filtered.length;
  }
  const people = filtered.slice(start, start + query.limit);
  const personIds = new Set(people.map((person) => person.id));
  const organizationIds = new Set(people.flatMap((person) => person.organizationIds));
  const last = people.at(-1);
  return {
    data: {
      people,
      organizations: dataset.organizations.filter((organization) => organizationIds.has(organization.id)),
      connections: dataset.connections.filter((connection) => personIds.has(connection.fromId) && personIds.has(connection.toId)),
    },
    meta: {
      total: filtered.length,
      next_cursor: last && start + people.length < filtered.length
        ? Buffer.from(JSON.stringify([key, ...sortKey(last)])).toString("base64url") : null,
    },
  };
}

export function queryPersonNetwork(dataset: PeopleDataset, personId: string): PeopleDataset | null {
  const selected = dataset.people.find((person) => person.id === personId);
  if (!selected) return null;
  const connections = dataset.connections.filter((connection) => connection.fromId === personId || connection.toId === personId);
  const personIds = new Set([personId, ...connections.flatMap((connection) => [connection.fromId, connection.toId])]);
  const people = dataset.people.filter((person) => personIds.has(person.id));
  const organizationIds = new Set(people.flatMap((person) => person.organizationIds));
  return {
    people,
    organizations: dataset.organizations.filter((organization) => organizationIds.has(organization.id)),
    connections,
  };
}
