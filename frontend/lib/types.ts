// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
export type Drug = "cocaine" | "heroin" | "meth" | "cannabis";
export type Mode = "observed" | "predicted";
export type View =
  "atlas" | "risk" | "health" | "people" | "livewire" | "scenarios" | "markets" | "experiment";
export interface Source {
  id: string;
  name: string;
  url: string;
  [key: string]: unknown;
}
export interface Meta {
  generated_at: string;
  model_version: string;
  sources: Source[];
  notes?: string[] | string;
}
export interface Envelope<T> {
  meta: Meta;
  data: T;
}
export interface Country {
  iso3: string;
  iso2: string | null;
  /** Display name (lib/country-names); the API sends the World Bank name. */
  name: string;
  /** World Bank economy name, kept for citations (set by lib/api). */
  formal_name?: string;
  region: string;
  income_group: string;
  capital: string | null;
  lat: number | null;
  lon: number | null;
}
export interface Edge {
  id: string;
  from: string;
  to: string;
  drug: Drug;
  year: number;
  volume_norm: number;
  kg: number | null;
  cases: number | null;
  confidence: number;
  is_emerging: boolean;
  probability: number | null;
  change_pct: number | null;
  signals: Record<string, boolean>;
  drivers: {
    feature: string;
    label: string;
    contribution: number;
    direction: string;
  }[];
  /** /api/route-evidence ids supporting this drug/from/to (API only; absent in snapshots). */
  evidence_ids?: string[];
  /** How `kg` was obtained; always allocated_seizure_scale today. */
  kg_basis?: "allocated_seizure_scale" | "direct_pair_observation";
}
export interface Routes {
  year: number;
  mode: Mode;
  drug: Drug | null;
  edges: Edge[];
}
export interface RiskRow {
  iso3: string;
  name: string;
  formal_name?: string;
  region: string;
  exposure: number;
  vulnerability: number;
  protection: number;
  score: number;
  rank: number;
  tier: string;
  /** Null in the first modeled year (no previous year), per contracts/openapi.yaml. */
  delta_1y: number | null;
  top_drug: string | null;
  trend: { year: number; score: number }[];
}
export interface Risk {
  year: number;
  weights: { exposure: number; vulnerability: number; protection: number };
  rows: RiskRow[];
}
export interface LiveEvent {
  id: string;
  published_at: string;
  title: string;
  url: string;
  source_domain: string;
  language: string;
  event_type: string;
  drug: string;
  origin: string | null;
  transit: string | null;
  destination: string | null;
  size: string;
  is_event: number;
  route_mentioned: number;
  confidence: number;
  is_anomaly: boolean;
  anomaly_reason: string | null;
  edge_probability: number | null;
  classifier: string;
  lat: number | null;
  lon: number | null;
}
export interface Price {
  iso3: string;
  name: string;
  drug: string;
  level: string;
  unit: string;
  points: { year: number; value: number; purity_pct: number | null }[];
  latest: number;
  yoy_change_pct: number | null;
  source: string;
}
export interface CommandAction {
  intent: string;
  params: Record<string, unknown>;
  message?: string;
}
export interface SimulationRequest {
  scenario?: string;
  year?: number;
  shocks?: { type: string; iso3: string; drug: string; value: number }[];
}
