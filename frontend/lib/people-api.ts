// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type {
  Connection,
  Organization,
  PeopleDataset,
  PeopleLoadResult,
  PeopleSource,
  PersonEvent,
  Person,
  PersonRegion,
} from "./people-types";

const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
export interface PeopleQuery {
  search?: string;
  country?: string;
  zoom?: 1 | 2 | 3;
  bounds?: [west: number, south: number, east: number, north: number];
  limit?: number;
  cursor?: string;
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

function validatedRegions(values: unknown, sources: PeopleSource[]): PersonRegion[] {
  const sourceUrls = new Set(sources.map((source) => source.url));
  if (!Array.isArray(values)) return [];
  return values.filter((region): region is PersonRegion =>
    region && typeof region.iso3 === "string" && /^[A-Z]{3}$/.test(region.iso3) &&
    typeof region.label === "string" && region.label.trim().length > 0,
  ).map((region) => {
    const evidence = region.evidence;
    const validEvidence = evidence && typeof evidence.claim === "string" && evidence.claim.trim() &&
      typeof evidence.sourceUrl === "string" && sourceUrls.has(evidence.sourceUrl) &&
      (evidence.period === undefined || typeof evidence.period === "string" && evidence.period.trim());
    return { ...region, evidence: validEvidence ? evidence : undefined };
  });
}

function validEvent(value: unknown): value is PersonEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<PersonEvent>;
  return typeof event.id === "string" && event.id.trim().length > 0 &&
    typeof event.occurredAt === "string" && /^\d{4}-\d{2}-\d{2}$/.test(event.occurredAt) &&
    !Number.isNaN(Date.parse(`${event.occurredAt}T00:00:00Z`)) &&
    ["arrest", "charge", "conviction", "sentence", "sanction", "development"].includes(event.type ?? "") &&
    typeof event.title === "string" && event.title.trim().length > 0 &&
    typeof event.summary === "string" && event.summary.trim().length > 0 &&
    sourceIsCitable(event.source);
}

export function normalizeDataset(input: unknown): PeopleDataset {
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
      regions: validatedRegions(person.regions, validatedSources(person.sources)),
      organizationIds: person.organizationIds.filter((id) => organizationIds.has(id)),
      events: Array.isArray(person.events) ? person.events.filter(validEvent)
        .sort((a, b) => b.occurredAt.localeCompare(a.occurredAt)) : [],
      photo: person.photo && validHttpUrl(person.photo.url) &&
        validHttpUrl(person.photo.sourceUrl) &&
        (!person.photo.licenseUrl || validHttpUrl(person.photo.licenseUrl)) &&
        person.sources.some((source) => source.url === person.photo?.sourceUrl) &&
        typeof person.photo.credit === "string" && person.photo.credit.trim() &&
        typeof person.photo.license === "string" && person.photo.license.trim()
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

async function fetchPeople(path: string): Promise<{ dataset: PeopleDataset; total: number | null; nextCursor: string | null; totalConnections: number | null }> {
  const response = await fetch(`${apiBase ?? ""}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`People API returned ${response.status}`);
  const body = await response.json() as { data?: unknown; meta?: { total?: unknown; next_cursor?: unknown; total_connections?: unknown }; total?: unknown; next_cursor?: unknown };
  if (!body.data) throw new Error("People API response is missing data");
  const dataset = normalizeDataset(body.data);
  const rawTotal = body.meta?.total ?? body.total;
  const rawCursor = body.meta?.next_cursor ?? body.next_cursor;
  return {
    dataset,
    total: typeof rawTotal === "number" && Number.isSafeInteger(rawTotal) && rawTotal >= dataset.people.length ? rawTotal : null,
    nextCursor: typeof rawCursor === "string" && rawCursor.length ? rawCursor : null,
    totalConnections: typeof body.meta?.total_connections === "number" && Number.isSafeInteger(body.meta.total_connections) && body.meta.total_connections >= dataset.connections.length ? body.meta.total_connections : null,
  };
}

export async function loadPeople(options: PeopleQuery = {}): Promise<PeopleLoadResult> {
  try {
    const query = new URLSearchParams({ limit: String(options.limit ?? 100), zoom: String(options.zoom ?? 1) });
    if (options.search?.trim()) query.set("search", options.search.trim());
    if (options.country) query.set("country", options.country);
    if (options.bounds) query.set("bbox", options.bounds.join(","));
    if (options.cursor) query.set("cursor", options.cursor);
    return { status: "ready", source: apiBase ? "api" : "fixtures", ...await fetchPeople(`/api/people?${query}`) };
  } catch (error) {
    return {
      status: "unavailable",
      reason: error instanceof Error ? error.message : "People data is unavailable.",
    };
  }
}

export async function loadPeopleCountryCounts(search = "", zoom: 1 | 2 | 3 = 3): Promise<{ iso3: string; total: number; visible: number }[] | null> {
  try {
    const query = new URLSearchParams({ zoom: String(zoom) });
    if (search.trim()) query.set("search", search.trim());
    const response = await fetch(`${apiBase ?? ""}/api/people/countries?${query}`, { cache: "no-store" });
    if (!response.ok) return null;
    const body = await response.json() as { data?: unknown };
    if (!Array.isArray(body.data)) return null;
    return body.data.filter((row): row is { iso3: string; total: number; visible: number } =>
      row && typeof row.iso3 === "string" && /^[A-Z]{3}$/.test(row.iso3) &&
      Number.isSafeInteger(row.total) && row.total >= 0 &&
      Number.isSafeInteger(row.visible) && row.visible >= 0 && row.visible <= row.total);
  } catch { return null; }
}

export async function loadPersonNetwork(personId: string): Promise<PeopleLoadResult> {
  try {
    return {
      status: "ready",
      source: apiBase ? "api" : "fixtures",
      ...await fetchPeople(`/api/people/network?person_id=${encodeURIComponent(personId)}`),
    };
  } catch (error) {
    return { status: "unavailable", reason: error instanceof Error ? error.message : "Connection evidence is unavailable." };
  }
}
