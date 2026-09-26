// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
export type PersonStatus = "convicted" | "charged" | "sanctioned" | "reported";

export interface PeopleSource {
  url: string;
  title: string;
  publisher: string;
  language: string;
  publishedAt?: string;
  claim: string;
}

export interface PersonRegion {
  iso3: string;
  label: string;
}

export interface PersonPhoto {
  url: string;
  credit: string;
  license: string;
  sourceUrl: string;
}

export interface Person {
  id: string;
  name: string;
  aliases?: string[];
  status: PersonStatus;
  statusAsOf?: string;
  roleLabel?: string;
  prominence: 1 | 2 | 3;
  organizationIds: string[];
  regions: PersonRegion[];
  drugs: string[];
  photo?: PersonPhoto;
  sources: PeopleSource[];
}

export interface Organization {
  id: string;
  name: string;
  aliases?: string[];
  regions: string[];
  sources: PeopleSource[];
}

export interface Connection {
  id: string;
  fromId: string;
  toId: string;
  type: string;
  label: string;
  sources: PeopleSource[];
}

export interface PeopleDataset {
  organizations: Organization[];
  people: Person[];
  connections: Connection[];
}

export interface PeopleCountry {
  iso3: string;
  name: string;
  lat: number | null;
  lon: number | null;
}

export type PeopleLoadResult =
  | { status: "ready"; dataset: PeopleDataset; source: "fixtures" | "api" }
  | { status: "unavailable"; reason: string };
