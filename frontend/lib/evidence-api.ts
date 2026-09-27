// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// Live evidence API (/api/evidence/*) client and mappers into the observed-data
// shapes the Health and Markets views already render. Pure mappers are exported
// for tests; fetchers take the API base explicitly so tests never touch env.

import type { ObservedOverdosePoint, ObservedRecord } from "./observed-data";

// ---------- API shapes (contracts/openapi.yaml, Evidence* schemas) ----------

export interface ApiMeta {
  generated_at?: string;
  model_version?: string;
  sources?: { id: string; name: string; url: string; citation: string }[];
  notes?: string[];
  total?: number;
  next_cursor?: string | null;
}

export interface ApiEvidenceValueSummary {
  id: string;
  kind: "research" | "market";
  metric_key: string;
  label: string;
  iso3: string | null;
  drug: string | null;
  year: number | null;
  value: number;
  unit: string;
  // Additive (evidence v2.1): market provenance; null for research values.
  form?: string | null;
  market_level?: string | null;
  source_publication_year?: number | null;
  source_id?: string | null;
  source_url?: string | null;
  formula_expression?: string | null;
  market_inputs?: Record<string, number> | null;
  input_observation_ids?: number[] | null;
}

export interface ApiEvidenceCell {
  col_no: number;
  value_text: string | null;
  value_number: number | null;
  value_type: string | null;
  italic: boolean;
}

export interface ApiEvidenceInput {
  role: string;
  source_table: string;
  source_key: string;
  source_id?: string | null;
  source_url: string | null;
  source_title?: string | null;
  source_checksum?: string | null;
  publication_year: number | null;
  observation_year: number | null;
  input_value: number | null;
  input_unit: string | null;
  transform: string | null;
  source_row?: {
    source_id: string;
    sheet: string;
    row_no: number;
    observation: Record<string, unknown> | null;
    cells: ApiEvidenceCell[];
  } | null;
  world_bank?: {
    indicator_code: string;
    source_id: number;
    iso3: string;
    year: number;
    lastupdated: string | null;
    lastupdated_note?: string;
    download_url: string;
    request_id: string;
    retrieved_at?: string | null;
    sha256?: string | null;
  };
  edition?: number;
  editions?: { edition: number; kg: number | null; source_id: string }[];
  revised_between_editions?: boolean;
  revision_label?: string | null;
}

export interface ApiEvidenceValue extends ApiEvidenceValueSummary {
  numerator?: number | null;
  denominator?: number | null;
  formula: {
    expression: string;
    version: number | null;
    selection_rule: string | null;
    interpretation: string | null;
  };
  support_count: number;
  support_count_basis: string;
  observation_year: number | null;
  source_publication_year: number | null;
  first_publication_year?: number | null;
  last_publication_year?: number | null;
  source_title: string | null;
  source_url: string | null;
  source_key: string | null;
  quality_flags: string[];
  caveat: string | null;
  revision_label: string | null;
  inputs: ApiEvidenceInput[];
  market: {
    substance: string;
    form: string | null;
    market_level: string | null;
    source: {
      source_id: string;
      url: string | null;
      edition: number | null;
      sha256: string | null;
      retrieved_at?: string | null;
      citation?: string | null;
      license_note?: string | null;
    };
  } | null;
  regression_sample: {
    sample_id: string;
    seizure_year: number;
    outcome_year: number;
    log1p_seizure_kg: number;
    homicide_per_100k: number;
  } | null;
}

interface ApiHealthSource {
  source_id: string;
  title: string | null;
  publisher?: string | null;
  url: string | null;
  edition_year: number | null;
}

export interface ApiPrevalenceRow {
  substance: string;
  substance_detail?: string | null;
  year: number | null;
  year_text?: string | null;
  reference_period: string;
  population: string;
  age_group: string | null;
  sex: string | null;
  value_pct: number | null;
  low_pct: number | null;
  high_pct: number | null;
  estimate_status: string;
  estimate_label: string;
  method: string | null;
  attribution?: string | null;
  adjustment_note?: string | null;
  notes?: string | null;
  source: ApiHealthSource;
  source_row: { sheet: string; row_no: number; cell_no: number };
}

export interface ApiCoverageRow {
  year: number;
  substance_group: string;
  sex: string;
  value_pct: number | null;
  lower_pct: number | null;
  upper_pct: number | null;
  nature_code: "M" | "C";
  nature_label: string;
  modelled: boolean;
  attribution?: string | null;
  footnotes?: string[];
  source: ApiHealthSource;
  source_row_no?: number;
}

export interface ApiPwidRow {
  metric: string;
  metric_label: string;
  geography_name?: string | null;
  year: number | null;
  year_text?: string | null;
  sex: string | null;
  age_group: string | null;
  value: number | null;
  low: number | null;
  high: number | null;
  unit: string;
  denominator?: string | null;
  injecting_definition?: string | null;
  geographic_coverage?: string | null;
  sample_size?: string | null;
  reference?: string | null;
  method: string | null;
  attribution?: string | null;
  notes?: string | null;
  estimate_status: string;
  estimate_label: string;
  indirect_estimate: boolean;
  indirect_label: string | null;
  source: ApiHealthSource;
  source_row: { sheet: string; row_no: number; cell_no: number };
}

export interface ApiTreatmentRow {
  drug_group: string;
  drug: string;
  geography_name?: string | null;
  year: number | null;
  year_text?: string | null;
  sex: string;
  persons_treated: number;
  unit: "persons";
  specified_reference_year?: string | null;
  coverage_note?: string | null;
  source: ApiHealthSource;
  source_row: { sheet: string; row_no: number };
}

export interface ApiHealth {
  iso3: string;
  /** Added in evidence v2.1; absent from older API deployments. */
  pwid?: { total: number; rows: ApiPwidRow[]; label: string; indirect_label?: string };
  treatment?: { total: number; rows: ApiTreatmentRow[]; label: string };
  prevalence: { total: number; rows: ApiPrevalenceRow[]; label: string };
  treatment_coverage: {
    total: number;
    rows: ApiCoverageRow[];
    label: string;
    nature_labels: { M: string; C: string };
  };
}

export interface ApiMarketObservation {
  observation_id: number;
  iso3: string | null;
  country?: string | null;
  year: number | null;
  drug_group?: string | null;
  substance: string | null;
  form: string | null;
  market_level: string;
  measure: "price" | "purity";
  basis: string | null;
  value: number | null;
  /** Null when the source states no unit (never inferred). */
  unit: string | null;
  unit_note: string | null;
  normalized_value?: number | null;
  normalized_unit?: string | null;
  original_value: number | null;
  original_unit: string | null;
  original_text?: string | null;
  minimum?: number | null;
  maximum?: number | null;
  publisher_estimate: boolean;
  status_label: string;
  source: { source_id: string; url: string | null; edition: number | null; citation?: string | null };
  source_row: { sheet: string; row_no: number; col_no: number | null };
}

export interface ApiMarketObservationCountry {
  iso3: string;
  country?: string | null;
  observations: number;
  price: number;
  purity: number;
  first_year?: number | null;
  last_year?: number | null;
  derived: number;
}

export interface ApiMarketObservationCountries {
  countries: ApiMarketObservationCountry[];
  totals: { observations: number; derived: number };
}

export interface ApiOverdoseRow {
  period_end: string;
  end_year: number;
  end_month: number;
  period_kind: string;
  indicator: string;
  metric_kind: string;
  unit: string;
  reported_value: number | null;
  predicted_value: number | null;
  percent_complete: number | null;
  percent_pending_investigation?: number | null;
  suppressed: boolean;
  status: string;
  footnote?: string | null;
  footnote_symbol?: string | null;
}

export interface ApiOverdose {
  state: string;
  state_name: string | null;
  label: string;
  indicators: string[];
  source_url: string;
  source_publication_year: null;
  rows: ApiOverdoseRow[];
}

export interface ApiResearchModel {
  model_key: string;
  specification: string;
  outcome: string;
  predictor: string;
  coefficient: number;
  standard_error: number;
  p_value: number;
  ci_low: number;
  ci_high: number;
  n: number;
  countries: number;
  caveat: string;
  interpretation: string;
  metric_key: string;
  sample_rows: number;
}

// ---------- required labels ----------

export const CDC_OVERDOSE_LABEL =
  "12-month-ending provisional; periods overlap, do not sum; drug classes overlap.";
export const RESEARCH_MODEL_LABEL =
  "Retrospective association, not route validation or forecast.";
export const COVERAGE_NATURE: Record<"M" | "C", string> = {
  M: "Officially modelled estimate (M)",
  C: "Country reported (C)",
};

// ---------- fetch helpers ----------

export class EvidenceApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function getEnvelope<T>(base: string, path: string): Promise<{ meta: ApiMeta; data: T }> {
  const response = await fetch(`${base}${path}`, { signal: AbortSignal.timeout(20000) });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new EvidenceApiError(
      detail?.error?.message || detail?.detail || `Evidence API returned ${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as { meta: ApiMeta; data: T };
}

/** Every market or research value matching the filters, following next_cursor. */
export async function fetchAllEvidenceValues(
  base: string,
  filters: { kind?: "market" | "research"; iso3?: string } = {},
): Promise<{ values: ApiEvidenceValueSummary[]; total: number }> {
  const values: ApiEvidenceValueSummary[] = [];
  let cursor: string | null | undefined;
  let total = 0;
  for (let page = 0; page < 40; page++) {
    const params = new URLSearchParams({ limit: "500" });
    if (filters.kind) params.set("kind", filters.kind);
    if (filters.iso3) params.set("iso3", filters.iso3);
    if (cursor) params.set("cursor", cursor);
    const body = await getEnvelope<{ values: ApiEvidenceValueSummary[] }>(base, `/api/evidence/values?${params}`);
    values.push(...body.data.values);
    total = body.meta.total ?? values.length;
    cursor = body.meta.next_cursor;
    if (!cursor) break;
  }
  return { values, total };
}

/** Every published price/purity observation matching the filters, following next_cursor. */
export async function fetchAllMarketObservations(
  base: string,
  filters: { iso3?: string; drug?: string; measure?: "price" | "purity"; market_level?: string; year?: number } = {},
): Promise<{ observations: ApiMarketObservation[]; total: number }> {
  const observations: ApiMarketObservation[] = [];
  let cursor: string | null | undefined;
  let total = 0;
  for (let page = 0; page < 40; page++) {
    const params = new URLSearchParams({ limit: "5000" });
    for (const [key, value] of Object.entries(filters)) if (value != null) params.set(key, String(value));
    if (cursor) params.set("cursor", cursor);
    const body = await getEnvelope<{ observations: ApiMarketObservation[] }>(
      base,
      `/api/evidence/market-observations?${params}`,
    );
    observations.push(...body.data.observations);
    total = body.meta.total ?? observations.length;
    cursor = body.meta.next_cursor;
    if (!cursor) break;
  }
  return { observations, total };
}

export async function fetchMarketObservationCountries(base: string) {
  const body = await getEnvelope<ApiMarketObservationCountries>(base, "/api/evidence/market-observations/countries");
  return body.data;
}

export async function fetchEvidenceValue(base: string, id: string) {
  return getEnvelope<ApiEvidenceValue>(base, `/api/evidence/value/${encodeURIComponent(id)}`);
}

/** Health rows for one country; a 404 means the API holds no rows for it. */
export async function fetchEvidenceHealth(base: string, iso3: string): Promise<ApiHealth | null> {
  try {
    const body = await getEnvelope<ApiHealth>(base, `/api/evidence/health/${iso3}?limit=5000`);
    return body.data;
  } catch (error) {
    if (error instanceof EvidenceApiError && error.status === 404) return null;
    throw error;
  }
}

export async function fetchEvidenceOverdose(base: string, state = "US"): Promise<ApiOverdose> {
  let cursor: string | null | undefined;
  let first: ApiOverdose | null = null;
  for (let page = 0; page < 20; page++) {
    const params = new URLSearchParams({ state, limit: "5000" });
    if (cursor) params.set("cursor", cursor);
    const body = await getEnvelope<ApiOverdose>(base, `/api/evidence/overdose?${params}`);
    if (first) first.rows.push(...body.data.rows);
    else first = body.data;
    cursor = body.meta.next_cursor;
    if (!cursor) break;
  }
  return first!;
}

export async function fetchResearchModel(base: string) {
  return getEnvelope<ApiResearchModel>(base, "/api/evidence/research-model");
}

// ---------- mappers into the view shapes ----------

export function mapPrevalenceRow(iso3: string, row: ApiPrevalenceRow): ObservedRecord {
  const caveat = [row.notes, row.adjustment_note].filter(Boolean).join(" · ") || null;
  return {
    id: `prevalence:${row.source.source_id}:${row.source_row.sheet}:${row.source_row.row_no}:${row.source_row.cell_no}`,
    domain: "prevalence",
    iso3,
    year: row.year,
    yearText: row.year_text ?? null,
    metric: row.substance,
    substance: row.substance,
    substanceDetail: row.substance_detail ?? null,
    value: row.value_pct,
    unit: "%",
    population: row.population,
    ageGroup: row.age_group,
    sex: row.sex,
    referencePeriod: row.reference_period,
    lower: row.low_pct,
    upper: row.high_pct,
    status: row.estimate_status,
    statusLabel: row.estimate_label,
    method: row.method,
    attribution: row.attribution ?? null,
    caveat,
    sourceId: `health:${row.source.source_id}`,
    sourceUrl: row.source.url ?? "",
    publicationYear: row.source.edition_year,
    sourceRow: { sheet: row.source_row.sheet, rowNo: row.source_row.row_no, cellNo: row.source_row.cell_no },
  };
}

export function mapCoverageRow(iso3: string, row: ApiCoverageRow): ObservedRecord {
  const footnotes = (row.footnotes ?? []).filter((note) => note && note.trim());
  return {
    id: `treatment_coverage:${row.source.source_id}:${row.source_row_no ?? `${row.year}:${row.substance_group}:${row.sex}`}`,
    domain: "treatment_coverage",
    iso3,
    year: row.year,
    metric: row.substance_group,
    substance: row.substance_group,
    value: row.value_pct,
    unit: "%",
    sex: row.sex,
    lower: row.lower_pct,
    upper: row.upper_pct,
    status: row.nature_code,
    statusLabel: row.nature_label,
    attribution: row.attribution ?? null,
    caveat: footnotes.length ? `Source footnotes: ${footnotes.join("; ")}` : null,
    sourceId: `health:${row.source.source_id}`,
    sourceUrl: row.source.url ?? "",
    publicationYear: row.source.edition_year,
    sourceRow: row.source_row_no != null ? { rowNo: row.source_row_no } : undefined,
  };
}

export const PWID_ESTIMATE_LABEL = "Source-published estimate";
export const TREATMENT_CONTACTS_CAVEAT = "Primary-drug treatment contacts; group and child drug rows can overlap.";

export function mapPwidRow(iso3: string, row: ApiPwidRow): ObservedRecord {
  return {
    id: `pwid:${row.source.source_id}:${row.source_row.sheet}:${row.source_row.row_no}:${row.source_row.cell_no}`,
    domain: "pwid",
    iso3,
    year: row.year,
    yearText: row.year_text ?? null,
    metric: row.metric,
    label: row.metric_label,
    value: row.value,
    unit: row.unit,
    sex: row.sex,
    ageGroup: row.age_group,
    lower: row.low,
    upper: row.high,
    denominator: row.denominator ?? null,
    status: row.estimate_status,
    // Indirect / model-based source methods are labelled as such, never as a direct count.
    statusLabel: row.indirect_estimate ? (row.indirect_label ?? "Indirect estimate") : PWID_ESTIMATE_LABEL,
    geographicCoverage: row.geographic_coverage ?? null,
    injectingDefinition: row.injecting_definition ?? null,
    sampleSize: row.sample_size ?? null,
    reference: row.reference ?? null,
    attribution: row.attribution ?? null,
    method: row.method,
    caveat: row.notes ?? null,
    sourceId: `health:${row.source.source_id}`,
    sourceUrl: row.source.url ?? "",
    publicationYear: row.source.edition_year,
    sourceRow: { sheet: row.source_row.sheet, rowNo: row.source_row.row_no, cellNo: row.source_row.cell_no },
  };
}

export function mapTreatmentRow(iso3: string, row: ApiTreatmentRow): ObservedRecord {
  const caveat = row.coverage_note
    ? `${TREATMENT_CONTACTS_CAVEAT} Source reporting coverage: ${row.coverage_note}`
    : TREATMENT_CONTACTS_CAVEAT;
  return {
    id: `treatment_contacts:${row.source.source_id}:${row.source_row.sheet}:${row.source_row.row_no}`,
    domain: "treatment_contacts",
    iso3,
    year: row.year,
    yearText: row.year_text ?? null,
    metric: row.drug_group,
    substance: row.drug,
    value: row.persons_treated,
    unit: "persons treated",
    sex: row.sex,
    referencePeriod: row.specified_reference_year ?? null,
    caveat,
    sourceId: `health:${row.source.source_id}`,
    sourceUrl: row.source.url ?? "",
    publicationYear: row.source.edition_year,
    sourceRow: { sheet: row.source_row.sheet, rowNo: row.source_row.row_no },
  };
}

export function mapHealth(health: ApiHealth): ObservedRecord[] {
  return [
    ...health.prevalence.rows.map((row) => mapPrevalenceRow(health.iso3, row)),
    ...(health.pwid?.rows ?? []).map((row) => mapPwidRow(health.iso3, row)),
    ...(health.treatment?.rows ?? []).map((row) => mapTreatmentRow(health.iso3, row)),
    ...health.treatment_coverage.rows.map((row) => mapCoverageRow(health.iso3, row)),
  ];
}

/** True when the API served every health group (v2.1+), so no snapshot rows are needed. */
export function healthIsComplete(health: ApiHealth | null) {
  return health == null || (health.pwid != null && health.treatment != null);
}

export function mapOverdoseRow(row: ApiOverdoseRow, sourceUrl: string, state = "US"): ObservedOverdosePoint {
  return {
    id: `us-overdose:${state}:${row.end_year}:${row.end_month}:${row.indicator}`,
    iso3: "USA",
    period: row.period_end,
    periodKind: "12 month-ending",
    indicator: row.indicator,
    metricKind: row.metric_kind,
    unit: row.unit,
    // Suppressed stays null: never coerced to zero.
    reportedValue: row.suppressed ? null : row.reported_value,
    predictedValue: row.suppressed ? null : row.predicted_value,
    percentComplete: row.percent_complete,
    percentPending: row.percent_pending_investigation ?? null,
    suppressed: row.suppressed,
    status: row.suppressed ? `${row.status}; suppressed/unavailable` : row.status,
    footnote: row.footnote ?? null,
    sourceId: "health:cdc_xkb8_kh2a",
    sourceUrl,
    publicationYear: null,
  };
}

export const MARKET_PRICE_CAVEAT = "Source price or purity observation; not a trade flow.";
export const MARKET_DERIVED_CAVEAT =
  "Matched exact product, year and sale level; nominal values can combine different source samples. Ratio is not a margin or route gradient.";

/** A published price/purity observation from /api/evidence/market-observations. */
export function mapMarketObservation(row: ApiMarketObservation): ObservedRecord {
  return {
    id: `market_price:${row.observation_id}`,
    observationId: row.observation_id,
    domain: "market_price",
    iso3: row.iso3 ?? "",
    year: row.year,
    metric: row.measure,
    substance: row.substance,
    form: row.form,
    marketLevel: row.market_level,
    value: row.value,
    // A blank source unit stays "not stated" (marketUnitLabel); it is never inferred.
    unit: row.unit ?? "source unit unavailable",
    basis: row.basis,
    originalValue: row.original_value,
    originalUnit: row.original_unit,
    originalText: row.original_text ?? null,
    originalLower: row.minimum ?? null,
    originalUpper: row.maximum ?? null,
    publisherEstimate: row.publisher_estimate,
    status: row.publisher_estimate ? "publisher estimate" : "source observation",
    statusLabel: row.status_label,
    sourceId: `market:${row.source.source_id}`,
    sourceUrl: row.source.url ?? "",
    publicationYear: row.source.edition,
    sourceRow: { sheet: row.source_row.sheet, rowNo: row.source_row.row_no, cellNo: row.source_row.col_no },
    caveat: MARKET_PRICE_CAVEAT,
  };
}

/** A market derivation from /api/evidence/values (the v2.1 summary carries form, level, edition and inputs). */
export function mapMarketValue(value: ApiEvidenceValueSummary): ObservedRecord {
  const inputs = value.market_inputs ?? undefined;
  return {
    id: `market_derived:${value.id}`,
    derivedId: Number(value.id),
    evidenceValueId: value.id,
    domain: "market_derived",
    iso3: value.iso3 ?? "",
    year: value.year,
    metric: value.metric_key,
    substance: value.drug,
    value: value.value,
    unit: value.unit,
    label: value.label,
    form: value.form ?? null,
    marketLevel: value.market_level ?? null,
    sourceId: value.source_id ? `market:${value.source_id}` : "market:evidence-api",
    sourceUrl: value.source_url ?? "",
    publicationYear: value.source_publication_year ?? null,
    formula: value.formula_expression ?? undefined,
    inputs,
    inputObservationIds:
      value.input_observation_ids ??
      (inputs
        ? Object.entries(inputs)
            .filter(([key]) => key.endsWith("observation_id"))
            .map(([, id]) => id)
        : undefined),
    status: "descriptive derived value",
    caveat: MARKET_DERIVED_CAVEAT,
  };
}

// ---------- display helpers ----------

const MARKET_UNITS: Record<string, string> = {
  usd_per_gram: "USD/g",
  usd_per_pure_gram: "USD/pure g",
  usd_per_tablet: "USD/tablet",
  usd_per_unit: "USD/unit",
  percent: "%",
  mg_per_tablet: "mg/tablet",
  ratio: "×",
};

/**
 * UNODC 2026 annex 8.1 leaves the Unit cell blank on some rows. The value is
 * still from the Typical_USD column of "Prices in USD", so price rows are USD
 * with the quantity unit not stated; purity rows have no stated unit at all.
 */
export function marketUnitLabel(unit: string | null | undefined, metric?: string | null) {
  const missing = !unit || unit === "source unit unavailable";
  if (missing) return metric === "price" ? "USD · quantity unit not stated in source" : "unit not stated in source";
  return MARKET_UNITS[unit] ?? unit;
}

export function coverageNatureLabel(status: string | null | undefined) {
  if (status === "M" || status === "modeled" || status === "modelled") return COVERAGE_NATURE.M;
  if (status === "C" || status === "country_data" || status === "country_reported") return COVERAGE_NATURE.C;
  return null;
}
