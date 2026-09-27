// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// US documented routes: cited city/state drug-route pairs from public reports
// (built by `uv run trace us-routes` from backend/trace_backend/seed/us_routes.csv).
import type { Drug } from "./types";

export type UsDrug = Drug | "fentanyl";
export interface UsPlace {
  name: string;
  state: string | null;
  country: string;
  lon: number;
  lat: number;
  precision: "city" | "state" | "country";
}
export interface UsRoute {
  id: string;
  drug: UsDrug;
  basis: "hidta_assessment" | "ndic_market_analysis" | "dea_ndta" | "court_case";
  from: UsPlace;
  to: UsPlace;
  precision: "city" | "state" | "mixed";
  period: [number, number] | null;
  source: { id: string; url: string; publisher: string; title: string; year: number; locator: string; quote: string };
}
export const basisLabel: Record<UsRoute["basis"], string> = {
  hidta_assessment: "HIDTA threat assessment",
  ndic_market_analysis: "NDIC drug market analysis",
  dea_ndta: "DEA National Drug Threat Assessment",
  court_case: "Federal court case",
};
export const fentanylColor = "#8a5a2b";

let cache: Promise<UsRoute[]> | null = null;
export function loadUsRoutes(): Promise<UsRoute[]> {
  cache ??= fetch("/data/us-routes.json")
    .then((r) => (r.ok ? r.json() : { data: { routes: [] } }))
    .then((d) => (d.data?.routes ?? []) as UsRoute[])
    .catch(() => {
      cache = null;
      return [];
    });
  return cache;
}
// Routes shown for a drug filter; fentanyl shows under "all" only (it is not a
// drug tab in the global atlas).
export function filterUsRoutes(routes: UsRoute[], drug: Drug | "all") {
  return routes.filter((r) => drug === "all" || r.drug === drug);
}
