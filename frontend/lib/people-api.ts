// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import fixtureManifest from "../data/people/manifest.json";
import type {
  Connection,
  Organization,
  PeopleDataset,
  PeopleLoadResult,
  PeopleSource,
  Person,
} from "./people-types";

const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
export interface PeopleQuery {
  search?: string;
  zoom?: 1 | 2 | 3;
  bounds?: [west: number, south: number, east: number, north: number];
  limit?: number;
}

function validHttpUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function sourceIsCitable(value: unknown): value is PeopleSource {
  if (!value || typeof value !== "object") return false;
  const source = value as Partial<PeopleSource>;
  return (
    validHttpUrl(source.url) &&
    typeof source.title === "string" && source.title.trim().length > 0 &&
    typeof source.publisher === "string" && source.publisher.trim().length > 0 &&
    typeof source.language === "string" && source.language.trim().length > 0 &&
    typeof source.claim === "string" && source.claim.trim().length > 0
  );
}

function validatedSources(values: unknown): PeopleSource[] {
  return Array.isArray(values) ? values.filter(sourceIsCitable) : [];
}

function normalizeDataset(input: unknown): PeopleDataset {
  if (!input || typeof input !== "object") {
    return { organizations: [], people: [], connections: [] };
  }
  const raw = input as Partial<PeopleDataset>;
  const organizations = (Array.isArray(raw.organizations) ? raw.organizations : [])
    .filter((item): item is Organization => Boolean(
      item && typeof item.id === "string" && typeof item.name === "string" &&
      Array.isArray(item.regions) &&
      validatedSources(item.sources).length,
    ));
  const organizationIds = new Set(organizations.map((item) => item.id));
  const people = (Array.isArray(raw.people) ? raw.people : [])
    .filter((item): item is Person => Boolean(
      item && typeof item.id === "string" && typeof item.name === "string" &&
      validatedSources(item.sources).length &&
      Array.isArray(item.organizationIds) && Array.isArray(item.regions) &&
      ["convicted", "charged", "sanctioned", "reported"].includes(item.status) &&
      [1, 2, 3].includes(item.prominence),
    ))
    .map((person) => ({
      ...person,
      sources: validatedSources(person.sources),
      organizationIds: person.organizationIds.filter((id) => organizationIds.has(id)),
      photo: person.photo && validHttpUrl(person.photo.url) &&
        validHttpUrl(person.photo.sourceUrl) &&
        person.sources.some((source) => source.url === person.photo?.sourceUrl) &&
        person.photo.credit.trim() && person.photo.license.trim()
        ? person.photo
        : undefined,
    }));
  const personIds = new Set(people.map((item) => item.id));
  const connections = (Array.isArray(raw.connections) ? raw.connections : [])
    .filter((item): item is Connection => Boolean(
      item && typeof item.id === "string" && personIds.has(item.fromId) &&
      personIds.has(item.toId) && validatedSources(item.sources).length &&
      typeof item.label === "string" && item.label.trim().length > 0,
    ))
    .map((connection) => ({ ...connection, sources: validatedSources(connection.sources) }));

  return {
    organizations: organizations.map((item) => ({ ...item, sources: validatedSources(item.sources) })),
    people,
    connections,
  };
}

async function fetchPeople(path: string): Promise<PeopleDataset> {
  const response = await fetch(`${apiBase}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`People API returned ${response.status}`);
  const body = await response.json() as { data?: unknown };
  if (!body.data) throw new Error("People API response is missing data");
  return normalizeDataset(body.data);
}

export async function loadPeople(options: PeopleQuery = {}): Promise<PeopleLoadResult> {
  try {
    if (!apiBase) {
      return {
        status: "ready",
        source: "fixtures",
        dataset: normalizeDataset(fixtureManifest),
      };
    }
    const query = new URLSearchParams({ limit: String(options.limit ?? 250), zoom: String(options.zoom ?? 1) });
    if (options.search?.trim()) query.set("search", options.search.trim());
    if (options.bounds) query.set("bbox", options.bounds.join(","));
    return { status: "ready", source: "api", dataset: await fetchPeople(`/api/people?${query}`) };
  } catch (error) {
    return {
      status: "unavailable",
      reason: error instanceof Error ? error.message : "People data is unavailable.",
    };
  }
}

export async function loadPersonNetwork(personId: string): Promise<PeopleLoadResult> {
  if (!apiBase) return loadPeople();
  try {
    return {
      status: "ready",
      source: "api",
      dataset: await fetchPeople(`/api/people/network?person_id=${encodeURIComponent(personId)}&limit=49`),
    };
  } catch (error) {
    return { status: "unavailable", reason: error instanceof Error ? error.message : "Connection evidence is unavailable." };
  }
}
