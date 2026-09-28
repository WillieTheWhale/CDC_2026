// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// Route evidence: cited records behind /api/routes edges, in the
// /api/route-evidence shape. Three layers, kept visibly separate:
//  - direct_reported_pair: a country pair stated in a cited publication;
//  - interpreted_corridor: TRACE's transcription of UNODC/EUDA regional route
//    maps and report text (indicative, not verbatim);
//  - narrative_context: regional text with no country endpoints, never drawn.
// With the API connected these records come from /api/route-evidence. The
// hardcoded direct pairs below are only the no-API fixture fallback.
import type { Drug, Edge } from "./types";

export type RouteEvidencePairType =
  | "direct_reported_pair"
  | "interpreted_corridor"
  | "narrative_context";
type DirectBasis =
  | "reported seizure origin/destination"
  | "reported provenance"
  | "official route assessment";

export interface RouteEvidenceSource {
  id: string;
  publisher: string;
  title: string;
  publication_year: number;
  url: string;
}
export interface RouteEvidenceCitation {
  key: string;
  publisher: string;
  title: string;
  publication_year: number;
  url: string | null;
}
export interface RouteEvidence {
  id: string;
  drug: Drug;
  from: string | null;
  to: string | null;
  geography_from: string | null;
  geography_to: string | null;
  pair_type: RouteEvidencePairType;
  basis: string;
  period: [number, number] | null;
  source: RouteEvidenceSource;
  source_locator: string;
  citations: RouteEvidenceCitation[];
  original_excerpt: string | null;
  geometry_precision: string;
  caveat: string;
  supports_edge_ids: string[];
}
/** A record with two country endpoints (direct pair or interpreted corridor). */
export type DrawableEvidence = RouteEvidence & { from: string; to: string };

export const pairTypeLabel: Record<RouteEvidencePairType, string> = {
  direct_reported_pair: "Reported country pair",
  interpreted_corridor: "TRACE transcription of regional maps and text",
  narrative_context: "Regional context (text only)",
};
// Wording for Edge.kg_basis wherever a kg figure is shown.
export function kgBasisNote(basis: Edge["kg_basis"]): string {
  return basis === "direct_pair_observation"
    ? "reported for this country pair"
    : "allocated from national seizure totals; not an observed pair volume";
}

export const DIRECT_CAVEAT =
  "Country pair stated in the cited publication at this locator. Not a volume estimate or an annual observation; no city, road or port path.";

const fixtureSourceRows: { id: string; publisher: string; title: string; publicationYear: number; url: string }[] = [
  { id: "unodc-cocaine-2023", publisher: "UNODC", title: "Global Report on Cocaine 2023", publicationYear: 2023, url: "https://www.unodc.org/documents/data-and-analysis/cocaine/Global_cocaine_report_2023.pdf" },
  { id: "unodc-haiti-2023", publisher: "UNODC", title: "Haiti criminal markets assessment", publicationYear: 2023, url: "https://www.unodc.org/documents/data-and-analysis/toc/Haiti_assessment_UNODC.pdf" },
  { id: "euda-heroin-2024", publisher: "EUDA / Europol", title: "EU Drug Market: Heroin and other opioids — trafficking and supply", publicationYear: 2024, url: "https://www.euda.europa.eu/publications/eu-drug-markets/heroin-and-other-opioids/trafficking-and-supply_en" },
  { id: "euda-cannabis-2023", publisher: "EUDA / Europol", title: "EU Drug Market: Cannabis — trafficking and supply", publicationYear: 2023, url: "https://www.euda.europa.eu/publications/eu-drug-markets/cannabis/trafficking-and-supply_en" },
  { id: "unodc-southern-2024", publisher: "UNODC", title: "Findings of the Expert Working Group on Opiates and Methamphetamine Trafficking on the Southern Route", publicationYear: 2024, url: "https://www.unodc.org/documents/data-and-analysis/AOTP/Southern_Route_Booklet_Online.pdf" },
  { id: "unodc-nigeria-2023", publisher: "UNODC", title: "Nigeria Organised Crime Threat Assessment", publicationYear: 2023, url: "https://www.unodc.org/conig/uploads/documents/NOCTA_Web_Version_25.09.2023.pdf" },
  { id: "unodc-wdr-2026", publisher: "UNODC", title: "World Drug Report 2026: methamphetamine supply", publicationYear: 2026, url: "https://data.unodc.org/wdr2026?page=22" },
  { id: "incb-2025", publisher: "INCB", title: "Report of the International Narcotics Control Board for 2025", publicationYear: 2026, url: "https://www.incb.org/incb/uploads/documents/Publications/AnnualReports/AR2025/Annual_Report/E_INCB_2025_1_eng.pdf" },
  { id: "ncb-india-2023", publisher: "Narcotics Control Bureau, India", title: "Annual Report 2023–24", publicationYear: 2024, url: "https://narcoticsindia.nic.in/Publication/ncb-annual-report-2023-24.pdf" },
];

// Each row has an explicit country-pair claim in the cited primary publication.
// A publication year or broad assessment is not an annual observation. No row
// carries a trafficked-volume estimate or a city/road/port path.
type EvidenceRow = [Drug, string, string, string, [number, number] | null, string, DirectBasis];
const rows: EvidenceRow[] = [
  ["cocaine", "COL", "ECU", "unodc-cocaine-2023", [2019, 2020], "The Americas, pp. 51–52", "official route assessment"],
  ["cocaine", "COL", "PER", "unodc-cocaine-2023", null, "The Americas, pp. 51–52", "official route assessment"],
  ["cocaine", "COL", "VEN", "unodc-cocaine-2023", null, "The Americas, pp. 51–52", "official route assessment"],
  ["cocaine", "COL", "PAN", "unodc-cocaine-2023", null, "The Americas, pp. 51–52", "official route assessment"],
  ["cocaine", "PER", "BOL", "unodc-cocaine-2023", null, "The Americas, p. 52", "official route assessment"],
  ["cocaine", "PER", "BRA", "unodc-cocaine-2023", null, "The Americas, p. 52", "official route assessment"],
  ["cocaine", "PER", "CHL", "unodc-cocaine-2023", null, "The Americas, p. 52", "official route assessment"],
  ["cocaine", "BOL", "BRA", "unodc-cocaine-2023", null, "The Americas, p. 52", "official route assessment"],
  ["cocaine", "BOL", "PRY", "unodc-cocaine-2023", null, "The Americas, p. 52", "official route assessment"],
  ["cocaine", "BOL", "ARG", "unodc-cocaine-2023", null, "The Americas, p. 52", "official route assessment"],
  ["cocaine", "PRY", "BRA", "unodc-cocaine-2023", [2019, 2019], "The Americas, p. 58; intended destination of seizures", "reported seizure origin/destination"],
  ["cocaine", "SLV", "GTM", "unodc-cocaine-2023", null, "Trafficking to North America, p. 55", "official route assessment"],
  ["cocaine", "HND", "GTM", "unodc-cocaine-2023", null, "Trafficking to North America, p. 55", "official route assessment"],
  ["cocaine", "GTM", "MEX", "unodc-cocaine-2023", null, "Trafficking to North America, p. 55", "official route assessment"],
  ["cannabis", "JAM", "HTI", "unodc-haiti-2023", [2020, 2022], "Drug trafficking dynamics, p. 24", "reported seizure origin/destination"],
  ["cannabis", "HTI", "DOM", "unodc-haiti-2023", [2020, 2022], "Drug trafficking dynamics, p. 24", "reported seizure origin/destination"],
  ["heroin", "NLD", "AUT", "euda-heroin-2024", [2018, 2021], "Heroin trafficking within the EU; WCO RILO-WE data", "reported seizure origin/destination"],
  ["heroin", "NLD", "ITA", "euda-heroin-2024", [2018, 2021], "Heroin trafficking within the EU; WCO RILO-WE data", "reported seizure origin/destination"],
  ["heroin", "NLD", "DEU", "euda-heroin-2024", [2018, 2021], "Heroin trafficking within the EU; WCO RILO-WE data", "reported seizure origin/destination"],
  ["heroin", "BEL", "ITA", "euda-heroin-2024", [2018, 2021], "Heroin trafficking within the EU; WCO RILO-WE data", "reported seizure origin/destination"],
  ["heroin", "BEL", "FRA", "euda-heroin-2024", [2018, 2021], "Heroin trafficking within the EU; WCO RILO-WE data", "reported seizure origin/destination"],
  ["heroin", "DEU", "IRL", "euda-heroin-2024", [2018, 2021], "Heroin trafficking within the EU; single reported seizure", "reported seizure origin/destination"],
  ["heroin", "FRA", "ITA", "euda-heroin-2024", [2018, 2021], "Heroin trafficking within the EU; WCO RILO-WE data", "reported seizure origin/destination"],
  ["heroin", "AFG", "IRN", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: Balkan route", "official route assessment"],
  ["heroin", "IRN", "TUR", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: Balkan route", "official route assessment"],
  ["heroin", "TUR", "BGR", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: Balkan route", "official route assessment"],
  ["heroin", "TUR", "GRC", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: Balkan route", "official route assessment"],
  ["heroin", "AFG", "TJK", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: northern route", "official route assessment"],
  ["heroin", "TJK", "KGZ", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: northern route", "official route assessment"],
  ["heroin", "TJK", "UZB", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: northern route", "official route assessment"],
  ["heroin", "KGZ", "KAZ", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: northern route", "official route assessment"],
  ["heroin", "UZB", "KAZ", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: northern route", "official route assessment"],
  ["heroin", "KAZ", "RUS", "euda-heroin-2024", null, "Heroin trafficking routes to Europe: northern route", "official route assessment"],
  ["cannabis", "MAR", "ESP", "euda-cannabis-2023", null, "Trafficking cannabis resin to and within the EU", "official route assessment"],
  ["cannabis", "ESP", "FRA", "euda-cannabis-2023", null, "Trafficking cannabis resin to and within the EU", "official route assessment"],
  ["cannabis", "ESP", "IRL", "euda-cannabis-2023", null, "Trafficking herbal cannabis", "official route assessment"],
  ["cannabis", "ESP", "GBR", "euda-cannabis-2023", null, "Trafficking herbal cannabis", "official route assessment"],
  ["heroin", "MOZ", "ZAF", "unodc-southern-2024", null, "Other routes within Africa, p. 13", "official route assessment"],
  ["meth", "MOZ", "ZAF", "unodc-southern-2024", null, "Other routes within Africa, p. 13", "official route assessment"],
  ["heroin", "MDG", "MUS", "unodc-southern-2024", null, "Trafficking routes in the Indian Ocean Islands, p. 12", "official route assessment"],
  ["heroin", "TZA", "KEN", "unodc-southern-2024", null, "Drug trafficking routes, p. 20", "official route assessment"],
  ["meth", "NGA", "ZAF", "unodc-nigeria-2023", null, "Section 4.4.1", "official route assessment"],
  ["meth", "AFG", "IRN", "unodc-wdr-2026", [2020, 2025], "Methamphetamine supply in South-West Asia", "reported provenance"],
  ["heroin", "PAK", "IND", "ncb-india-2023", [2023, 2023], "Trends and Patterns 2023, p. 6", "official route assessment"],
  ["heroin", "IRN", "IND", "ncb-india-2023", [2023, 2023], "Trends and Patterns 2023, p. 6", "official route assessment"],
  ["heroin", "IND", "LKA", "ncb-india-2023", [2023, 2023], "Trends and Patterns 2023, p. 6", "official route assessment"],
  ["meth", "MMR", "LAO", "incb-2025", [2024, 2024], "Paragraphs 497 and 526", "official route assessment"],
  ["meth", "LAO", "THA", "incb-2025", [2024, 2024], "Paragraphs 497 and 526", "official route assessment"],
  ["meth", "THA", "KHM", "incb-2025", [2024, 2024], "Paragraphs 497 and 526", "official route assessment"],
  ["meth", "MYS", "PHL", "incb-2025", [2024, 2024], "Paragraphs 497 and 526", "official route assessment"],
  ["meth", "MMR", "IND", "incb-2025", [2024, 2024], "Paragraph 527", "official route assessment"],
];

const fixtureSources = new Map(
  fixtureSourceRows.map(({ publicationYear, ...s }) => [s.id, { ...s, publication_year: publicationYear }]),
);

/** No-API fixture only: the curated direct reported pairs. */
export const fixtureRouteEvidence: RouteEvidence[] = rows.map(
  ([drug, from, to, sourceId, period, source_locator, basis]) => ({
    id: `${drug}:${from}:${to}:${sourceId}`,
    drug,
    from,
    to,
    geography_from: null,
    geography_to: null,
    pair_type: "direct_reported_pair",
    basis,
    period,
    source: fixtureSources.get(sourceId)!,
    source_locator,
    citations: [],
    original_excerpt: null,
    geometry_precision: "country pair",
    caveat: DIRECT_CAVEAT,
    supports_edge_ids: [`${drug}:${from}:${to}`],
  }),
);

export interface RouteEvidenceIndex {
  all: RouteEvidence[];
  direct: DrawableEvidence[];
  interpreted: DrawableEvidence[];
  narrative: RouteEvidence[];
  byId: Map<string, RouteEvidence>;
  byEdgeId: Map<string, RouteEvidence[]>;
  sources: (RouteEvidenceSource & { layer: RouteEvidencePairType; count: number })[];
}
const typeOrder: Record<RouteEvidencePairType, number> = {
  direct_reported_pair: 0,
  interpreted_corridor: 1,
  narrative_context: 2,
};
export function indexRouteEvidence(records: RouteEvidence[]): RouteEvidenceIndex {
  const all = [...records].sort((a, b) => typeOrder[a.pair_type] - typeOrder[b.pair_type]);
  const drawable = (r: RouteEvidence): r is DrawableEvidence =>
    r.pair_type !== "narrative_context" && !!r.from && !!r.to && r.from !== r.to;
  const byEdgeId = new Map<string, RouteEvidence[]>();
  const sources = new Map<string, RouteEvidenceIndex["sources"][number]>();
  for (const r of all) {
    for (const edgeId of r.supports_edge_ids)
      byEdgeId.set(edgeId, [...(byEdgeId.get(edgeId) ?? []), r]);
    const s = sources.get(r.source.id);
    if (s) s.count++;
    else sources.set(r.source.id, { ...r.source, layer: r.pair_type, count: 1 });
  }
  return {
    all,
    direct: all.filter((r): r is DrawableEvidence => r.pair_type === "direct_reported_pair" && drawable(r)),
    interpreted: all.filter((r): r is DrawableEvidence => r.pair_type === "interpreted_corridor" && drawable(r)),
    narrative: all.filter((r) => r.pair_type === "narrative_context"),
    byId: new Map(all.map((r) => [r.id, r])),
    byEdgeId,
    sources: [...sources.values()].sort(
      (a, b) => typeOrder[a.layer] - typeOrder[b.layer] || a.publisher.localeCompare(b.publisher),
    ),
  };
}
export const emptyRouteEvidence = indexRouteEvidence([]);

/**
 * Evidence behind one modeled edge. Uses the edge's `evidence_ids` (API order:
 * direct reported pairs first); snapshot edges without ids fall back to the
 * records whose `supports_edge_ids` name this edge.
 */
export function evidenceForEdge(index: RouteEvidenceIndex, edge: Pick<Edge, "id" | "evidence_ids">): RouteEvidence[] {
  if (edge.evidence_ids?.length)
    return edge.evidence_ids.flatMap((id) => index.byId.get(id) ?? []);
  return index.byEdgeId.get(edge.id) ?? [];
}

export function evidencePeriod(r: RouteEvidence): string {
  return r.period
    ? `${r.period[0]}${r.period[1] !== r.period[0] ? `–${r.period[1]}` : ""} evidence`
    : `${r.source.publication_year} publication`;
}
