// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// Published SQLite source observations; independent of modeled API fixtures.
// With NEXT_PUBLIC_API_URL set, Health and Markets read only the live evidence API
// (/api/evidence/*); this packaged snapshot is the no-API / API-failure fallback.

import { API_BASE } from "./api";
import {
  fetchAllEvidenceValues,
  fetchAllMarketObservations,
  fetchEvidenceHealth,
  fetchEvidenceOverdose,
  fetchEvidenceValue,
  fetchMarketObservationCountries,
  fetchResearchModel,
  healthIsComplete,
  mapHealth,
  mapMarketObservation,
  mapMarketValue,
  mapOverdoseRow,
  type ApiEvidenceValueSummary,
  type ApiMarketObservation,
} from "./evidence-api";

export type ObservedDomain =
  | "prevalence"
  | "pwid"
  | "treatment_contacts"
  | "treatment_coverage"
  | "market_price"
  | "market_derived";

export interface ObservedSource {
  title: string;
  publisher: string;
  url: string;
  publicationYear: number | null;
  caveat?: string | null;
}

export interface ObservedRecord {
  id: string;
  domain: ObservedDomain;
  iso3: string;
  year: number | null;
  yearText?: string | null;
  metric: string;
  value: number | null;
  unit: string;
  sourceId: string;
  sourceUrl: string;
  publicationYear: number | null;
  substance?: string | null;
  form?: string | null;
  marketLevel?: string | null;
  basis?: string | null;
  publisherEstimate?: boolean;
  population?: string | null;
  ageGroup?: string | null;
  sex?: string | null;
  referencePeriod?: string | null;
  lower?: number | null;
  upper?: number | null;
  status?: string | null;
  /** Source wording for status (e.g. SDG nature label); shown when present. */
  statusLabel?: string | null;
  substanceDetail?: string | null;
  /** /api/evidence/value/{id} key when the value is drillable. */
  evidenceValueId?: string;
  label?: string | null;
  method?: string | null;
  attribution?: string | null;
  geographicCoverage?: string | null;
  denominator?: string | null;
  injectingDefinition?: string | null;
  sampleSize?: string | null;
  reference?: string | null;
  caveat?: string | null;
  sourceRow?: { sheet?: string; rowNo: number; cellNo?: number | null };
  observationId?: number;
  derivedId?: number;
  originalValue?: number | null;
  originalUnit?: string | null;
  originalText?: string | null;
  originalLower?: number | null;
  originalUpper?: number | null;
  formula?: string;
  inputs?: Record<string, number>;
  inputObservationIds?: number[];
}

export interface ResearchInput {
  role: string;
  sourceTable: string;
  sourceKey: string;
  sourceId: string | null;
  sourceUrl: string | null;
  publicationYear: number | null;
  observationYear: number | null;
  value: number | null;
  unit: string | null;
  transform: string | null;
}

export interface ResearchValue {
  metricId: string;
  metricKey: string;
  iso3: string;
  drug: string | null;
  year: number | null;
  value: number;
  unit: string;
  version: number;
  label: string;
  formula: string;
  selectionRule: string;
  interpretation: string;
  supportCount: number;
  qualityFlags: string;
  firstPublicationYear: number | null;
  lastPublicationYear: number | null;
  inputs: ResearchInput[];
}

export interface ResearchSample {
  sampleId: string;
  metricId: string;
  iso3: string;
  seizureYear: number;
  outcomeYear: number;
  log1pSeizureKg: number;
  homicidePer100k: number;
}

export interface ObservedCountry {
  iso3: string;
  observations: ObservedRecord[];
  researchValues: ResearchValue[];
  researchSamples: ResearchSample[];
}

export interface EvidenceClaim {
  claimId: string;
  claimType: string;
  drug: string | null;
  geographyFrom: string | null;
  geographyTo: string | null;
  geographyScope: string;
  observationStartYear: number | null;
  observationEndYear: number | null;
  policyEffectiveDate: string | null;
  publicationYear: number;
  claim: string;
  originalExcerpt: string;
  sourceLocator: string;
  evidenceBasis: string;
  caveat: string;
  sourceId: string;
  sourceUrl: string;
}

export interface ResearchModelResult {
  modelKey: string;
  specification: string;
  outcome: string;
  predictor: string;
  coefficient: number | null;
  standardError: number | null;
  pValue: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  n: number;
  countries: number;
  firstPredictorYear: number | null;
  lastPredictorYear: number | null;
  clusterCount: number;
  rSquared: number | null;
  caveat: string;
  computedAt: string;
}

export interface ObservedOverview {
  snapshot: {
    releaseTag: string;
    databaseSha256: string;
    inputShards: Record<string, string>;
    exportedAt: string;
    kind: "observed-source-export";
  };
  sources: Record<string, ObservedSource>;
  countrySummaries: { iso3: string; counts: Record<string, number> }[];
  marketCatalog: {
    iso3: string;
    substance: string | null;
    form: string | null;
    year: number | null;
    marketLevel: string | null;
    metric: string;
    count: number;
  }[];
  evidenceClaims: EvidenceClaim[];
  researchModelResults: ResearchModelResult[];
  researchDefinitions: {
    metricKey: string;
    version: number;
    label: string;
    unit: string;
    formula: string;
    selectionRule: string;
    interpretation: string;
  }[];
}

export interface ObservedOverdosePoint {
  id: string;
  iso3: "USA";
  period: string;
  periodKind: "12 month-ending";
  indicator: string;
  metricKind: string;
  unit: string;
  reportedValue: number | null;
  predictedValue: number | null;
  percentComplete: number | null;
  percentPending?: number | null;
  suppressed?: boolean;
  status: string;
  footnote: string | null;
  sourceId: string;
  sourceUrl: string;
  publicationYear: number | null;
}

const BASE = "/data/observed-v2";
let overviewPromise: Promise<ObservedOverview> | undefined;
const countryPromises = new Map<string, Promise<ObservedCountry | null>>();
let overdosePromise: Promise<ObservedOverdosePoint[]> | undefined;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}/${path}`);
  if (!response.ok) throw new Error(`Observed data unavailable (${response.status})`);
  return (await response.json()) as T;
}

export function loadObservedOverview(): Promise<ObservedOverview> {
  overviewPromise ??= getJson<ObservedOverview>("overview.json").catch((error) => {
    overviewPromise = undefined;
    throw error;
  });
  return overviewPromise;
}

export function loadObservedCountry(iso3: string): Promise<ObservedCountry | null> {
  const normalized = iso3.toUpperCase();
  if (!/^[A-Z]{3}$/.test(normalized)) return Promise.resolve(null);
  const existing = countryPromises.get(normalized);
  if (existing) return existing;
  const result = fetch(`${BASE}/countries/${normalized}.json`)
    .then(async (response) => {
      if (response.status === 404) return null;
      if (!response.ok) throw new Error(`Country evidence unavailable (${response.status})`);
      return (await response.json()) as ObservedCountry;
    })
    .catch((error) => {
      countryPromises.delete(normalized);
      throw error;
    });
  countryPromises.set(normalized, result);
  return result;
}

export function loadObservedUSOverdose(): Promise<ObservedOverdosePoint[]> {
  overdosePromise ??= getJson<ObservedOverdosePoint[]>("us-overdose.json").catch((error) => {
    overdosePromise = undefined;
    throw error;
  });
  return overdosePromise;
}

// ---------- live evidence API with packaged-snapshot fallback ----------

export type EvidenceOrigin = "api" | "snapshot";
export interface Sourced<T> {
  data: T;
  origin: EvidenceOrigin;
  /** Why the packaged snapshot is shown when an API is configured. */
  fallbackReason?: string;
}

export const EVIDENCE_API_CONFIGURED = Boolean(API_BASE);
const HEALTH_DOMAINS = new Set<ObservedDomain>(["prevalence", "pwid", "treatment_contacts", "treatment_coverage"]);
const healthPromises = new Map<string, Promise<Sourced<ObservedCountry | null>>>();
const marketPromises = new Map<string, Promise<Sourced<ObservedCountry | null>>>();
let marketCountsPromise: Promise<MarketCountryCounts | null> | undefined;
let liveOverdosePromise: Promise<Sourced<ObservedOverdosePoint[]>> | undefined;
let researchModelPromise: ReturnType<typeof fetchResearchModel> | undefined;

function reason(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function emptyCountry(iso3: string): ObservedCountry {
  return { iso3, observations: [], researchValues: [], researchSamples: [] };
}

/**
 * Health rows from the API. `served` names the groups the API returned; an older
 * API without PWID / treatment contacts gets only those groups from the snapshot.
 */
export function combineHealth(
  iso3: string,
  liveRows: ObservedRecord[],
  snapshot: ObservedCountry | null,
  served: Iterable<ObservedDomain> = HEALTH_DOMAINS,
): ObservedCountry | null {
  const live = new Set(served);
  const base = snapshot ?? emptyCountry(iso3);
  const observations = [
    ...liveRows,
    ...base.observations.filter((row) => HEALTH_DOMAINS.has(row.domain) && !live.has(row.domain)),
  ];
  if (!observations.length && !snapshot) return null;
  return { ...base, observations };
}

/** Markets view for one country, entirely from the API: price/purity observations plus matched derivations. */
export function buildMarketCountry(
  iso3: string,
  observations: ApiMarketObservation[],
  values: ApiEvidenceValueSummary[],
): ObservedCountry | null {
  const rows = [
    ...observations.filter((row) => row.iso3 === iso3).map(mapMarketObservation),
    ...values.filter((value) => value.kind === "market" && value.iso3 === iso3).map(mapMarketValue),
  ];
  return rows.length ? { ...emptyCountry(iso3), observations: rows } : null;
}

export function loadHealthEvidence(iso3: string): Promise<Sourced<ObservedCountry | null>> {
  const normalized = iso3.toUpperCase();
  if (!API_BASE || !/^[A-Z]{3}$/.test(normalized))
    return loadObservedCountry(normalized).then((data) => ({ data, origin: "snapshot" as const }));
  const existing = healthPromises.get(normalized);
  if (existing) return existing;
  const result = fetchEvidenceHealth(API_BASE, normalized)
    .then(async (health): Promise<Sourced<ObservedCountry | null>> => {
      if (healthIsComplete(health))
        return { data: health ? combineHealth(normalized, mapHealth(health), null) : null, origin: "api" };
      // Older API without PWID / treatment contacts: fill only those groups from the snapshot.
      const snapshot = await loadObservedCountry(normalized).catch(() => null);
      return {
        data: combineHealth(normalized, mapHealth(health!), snapshot, ["prevalence", "treatment_coverage"]),
        origin: "api",
      };
    })
    .catch(async (error: unknown): Promise<Sourced<ObservedCountry | null>> => {
      healthPromises.delete(normalized);
      return { data: await loadObservedCountry(normalized), origin: "snapshot", fallbackReason: reason(error) };
    });
  healthPromises.set(normalized, result);
  return result;
}

export interface MarketCountryCounts {
  /** Price/purity observations + matched derivations per country. */
  byCountry: Map<string, { observations: number; derived: number }>;
  totals: { observations: number; derived: number };
}

/** Per-country market counts from the API (country list and header); null without an API or on failure. */
export function loadMarketCountryCounts(): Promise<MarketCountryCounts | null> {
  if (!API_BASE) return Promise.resolve(null);
  marketCountsPromise ??= fetchMarketObservationCountries(API_BASE)
    .then((data) => ({
      byCountry: new Map(data.countries.map((row) => [row.iso3, { observations: row.observations, derived: row.derived }])),
      totals: data.totals,
    }))
    .catch(() => {
      marketCountsPromise = undefined;
      return null;
    });
  return marketCountsPromise;
}

export function loadMarketEvidence(iso3: string): Promise<Sourced<ObservedCountry | null>> {
  const normalized = iso3.toUpperCase();
  if (!API_BASE || !/^[A-Z]{3}$/.test(normalized))
    return loadObservedCountry(normalized).then((data) => ({ data, origin: "snapshot" as const }));
  const existing = marketPromises.get(normalized);
  if (existing) return existing;
  const result = Promise.all([
    fetchAllMarketObservations(API_BASE, { iso3: normalized }),
    fetchAllEvidenceValues(API_BASE, { kind: "market", iso3: normalized }),
  ])
    .then(([live, values]): Sourced<ObservedCountry | null> => ({
      data: buildMarketCountry(normalized, live.observations, values.values),
      origin: "api",
    }))
    .catch(async (error: unknown): Promise<Sourced<ObservedCountry | null>> => {
      marketPromises.delete(normalized);
      return { data: await loadObservedCountry(normalized), origin: "snapshot", fallbackReason: reason(error) };
    });
  marketPromises.set(normalized, result);
  return result;
}

export function loadUSOverdose(): Promise<Sourced<ObservedOverdosePoint[]>> {
  if (!API_BASE) return loadObservedUSOverdose().then((data) => ({ data, origin: "snapshot" as const }));
  liveOverdosePromise ??= fetchEvidenceOverdose(API_BASE, "US")
    .then((body): Sourced<ObservedOverdosePoint[]> => ({
      data: body.rows.map((row) => mapOverdoseRow(row, body.source_url)),
      origin: "api",
    }))
    .catch(async (error: unknown): Promise<Sourced<ObservedOverdosePoint[]>> => {
      liveOverdosePromise = undefined;
      return { data: await loadObservedUSOverdose(), origin: "snapshot", fallbackReason: reason(error) };
    });
  return liveOverdosePromise;
}

/** /api/evidence/value/{id} drilldown; only available with a configured API. */
export function loadEvidenceValue(id: string) {
  if (!API_BASE) return Promise.reject(new Error("Value drilldown needs the live evidence API."));
  return fetchEvidenceValue(API_BASE, id);
}

export function loadResearchModel() {
  if (!API_BASE) return Promise.reject(new Error("Research model needs the live evidence API."));
  researchModelPromise ??= fetchResearchModel(API_BASE).catch((error) => {
    researchModelPromise = undefined;
    throw error;
  });
  return researchModelPromise;
}
