// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Published SQLite source observations; independent of modeled API fixtures.

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
