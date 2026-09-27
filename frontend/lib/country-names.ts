// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// One shared display-name mapping for countries. The API and snapshot files
// carry World Bank economy names ("Venezuela, RB", "Korea, Rep."), which are
// the formal names the World Bank citations use; the interface shows the
// common short names instead. Data keeps the formal name (`formal_name` on
// normalized records) so citations can still quote it.

// Keyed by the World Bank (or Natural Earth, for a few territories) name.
const DISPLAY: Record<string, string> = {
  "Bahamas, The": "Bahamas",
  "Brunei Darussalam": "Brunei",
  "Congo, Dem. Rep.": "DR Congo",
  "Congo, Rep.": "Republic of the Congo",
  "Cote d'Ivoire": "Côte d’Ivoire",
  "Egypt, Arab Rep.": "Egypt",
  "Gambia, The": "Gambia",
  "Hong Kong SAR, China": "Hong Kong",
  "Iran, Islamic Rep.": "Iran",
  "Korea, Dem. People's Rep.": "North Korea",
  "Korea, Rep.": "South Korea",
  "Kyrgyz Republic": "Kyrgyzstan",
  "Lao PDR": "Laos",
  "Macao SAR, China": "Macao",
  "Micronesia, Fed. Sts.": "Micronesia",
  "Puerto Rico (US)": "Puerto Rico",
  "Russian Federation": "Russia",
  "Sao Tome and Principe": "São Tomé and Príncipe",
  "Sint Maarten (Dutch part)": "Sint Maarten",
  "Slovak Republic": "Slovakia",
  "Somalia, Fed. Rep.": "Somalia",
  "St. Kitts and Nevis": "Saint Kitts and Nevis",
  "St. Lucia": "Saint Lucia",
  "St. Martin (French part)": "Saint Martin",
  "St. Vincent and the Grenadines": "Saint Vincent and the Grenadines",
  "Syrian Arab Republic": "Syria",
  "Turkiye": "Türkiye",
  "Venezuela, RB": "Venezuela",
  "Viet Nam": "Vietnam",
  "Virgin Islands (U.S.)": "U.S. Virgin Islands",
  "Yemen, Rep.": "Yemen",
};

// Same names by ISO3, for places that only carry a code or an older spelling.
const BY_ISO3: Record<string, string> = {
  BHS: "Bahamas",
  BRN: "Brunei",
  COD: "DR Congo",
  COG: "Republic of the Congo",
  CIV: "Côte d’Ivoire",
  EGY: "Egypt",
  FSM: "Micronesia",
  GMB: "Gambia",
  HKG: "Hong Kong",
  IRN: "Iran",
  KGZ: "Kyrgyzstan",
  KNA: "Saint Kitts and Nevis",
  KOR: "South Korea",
  LAO: "Laos",
  LCA: "Saint Lucia",
  MAC: "Macao",
  MAF: "Saint Martin",
  PRI: "Puerto Rico",
  PRK: "North Korea",
  RUS: "Russia",
  SOM: "Somalia",
  STP: "São Tomé and Príncipe",
  SVK: "Slovakia",
  SXM: "Sint Maarten",
  SYR: "Syria",
  TUR: "Türkiye",
  VCT: "Saint Vincent and the Grenadines",
  VEN: "Venezuela",
  VIR: "U.S. Virgin Islands",
  VNM: "Vietnam",
  YEM: "Yemen",
};

/**
 * The name to show for a country. Accepts a World Bank name, an ISO3 code
 * (when no name is known), or both; unknown names pass through unchanged.
 */
export function displayCountryName(name: string | null | undefined, iso3?: string | null): string {
  const n = (name ?? "").trim();
  if (n && DISPLAY[n]) return DISPLAY[n];
  // A bare code (the fallback when a layer has no name for it).
  if (!n || (iso3 && n === iso3) || /^[A-Z]{3}$/.test(n)) {
    const code = (iso3 || n).toUpperCase();
    return BY_ISO3[code] ?? (n || code);
  }
  return n;
}

/** Copy of a record with its display name, keeping the formal name for citations. */
export function withDisplayName<T extends { name: string; iso3?: string }>(row: T): T & { formal_name: string } {
  const formal = (row as { formal_name?: string }).formal_name ?? row.name;
  return { ...row, name: displayCountryName(formal, row.iso3), formal_name: formal };
}

/** Display names for an {iso3: name} map (the estimated-flows `countries` block). */
export function displayNameMap(names: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(names).map(([iso3, name]) => [iso3, displayCountryName(name, iso3)]));
}

/** Free text from the API (scenario summaries, briefings) with World Bank names replaced. */
export function displayCountryText(text: string): string;
export function displayCountryText(text: string | null | undefined): string | null | undefined;
export function displayCountryText(text: string | null | undefined) {
  if (!text) return text;
  let out = text;
  // Longest first, so "Korea, Dem. People's Rep." is not caught by "Korea, Rep.".
  for (const formal of FORMAL_BY_LENGTH) if (out.includes(formal)) out = out.split(formal).join(DISPLAY[formal]);
  return out;
}
const FORMAL_BY_LENGTH = Object.keys(DISPLAY)
  // Only the unmistakable World Bank forms; plain words like "Turkiye" stay as written in prose.
  .filter((k) => /[,()]| PDR$|Republic|Federation|Darussalam|^St\. /.test(k))
  .sort((a, b) => b.length - a.length);
