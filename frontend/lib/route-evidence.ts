// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type { Drug } from "./types";

export type RouteEvidenceBasis =
  | "reported seizure origin/destination"
  | "reported provenance"
  | "official route assessment";

export interface RouteEvidenceSource {
  id: string;
  publisher: string;
  title: string;
  publicationYear: number;
  url: string;
}

export interface RouteEvidence {
  id: string;
  drug: Drug;
  from: string;
  to: string;
  sourceId: string;
  sourceLocator: string;
  basis: RouteEvidenceBasis;
  period: [number, number] | null;
  geometryPrecision: "country pair";
}

export const routeEvidenceSources: RouteEvidenceSource[] = [
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
type EvidenceRow = [Drug, string, string, string, [number, number] | null, string, RouteEvidenceBasis];
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

export const routeEvidence: RouteEvidence[] = rows.map(
  ([drug, from, to, sourceId, period, sourceLocator, basis]) => ({
    id: `${drug}:${from}:${to}:${sourceId}`,
    drug,
    from,
    to,
    sourceId,
    sourceLocator,
    basis,
    period,
    geometryPrecision: "country pair",
  }),
);

export const routeEvidenceSourceById = new Map(routeEvidenceSources.map((source) => [source.id, source]));
