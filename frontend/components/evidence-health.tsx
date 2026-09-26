// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import type { Country } from "@/lib/types";
import {
  loadObservedCountry,
  loadObservedUSOverdose,
  type ObservedCountry,
  type ObservedRecord,
  type ObservedOverdosePoint,
  type EvidenceClaim,
} from "@/lib/observed-data";
import "./evidence-health.css";

const GROUPS: { key: string; label: string; explanation: string }[] = [
  { key: "prevalence", label: "Drug use", explanation: "Survey prevalence retains its original population, age band, sex and reference period." },
  { key: "pwid", label: "Injecting & infection", explanation: "Survey geography and populations vary; these estimates are not a matched country ranking." },
  { key: "treatment_contacts", label: "Treatment contacts", explanation: "People treated by primary drug; group and child rows can overlap. These are counts, not coverage." },
  { key: "treatment_coverage", label: "Treatment coverage", explanation: "Published UN SDG 3.5.1 percentages. Officially modeled and country reported values are labeled separately." },
];

function label(value?: string | null) {
  if (!value) return "—";
  const named: Record<string, string> = {
    BOTHSEX: "Both sexes",
    DRUG_TOTAL: "All drug use disorders",
    ATS: "Amphetamine-type stimulants",
  };
  return named[value] ?? value.replaceAll("_", " ");
}

function unitLabel(unit: string) {
  if (unit === "percent_of_general_population") return "% of general population";
  if (unit === "percent") return "%";
  return unit;
}

function number(value: number | null, unit: string) {
  if (value === null) return "Unavailable";
  const digits = Math.abs(value) < 10 ? 2 : Math.abs(value) < 100 ? 1 : 0;
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value)} ${unitLabel(unit)}`.trim();
}

function sourceStatus(row: ObservedRecord) {
  if (row.domain === "treatment_coverage") {
    if (row.status === "modeled" || row.status === "M") return "Officially modeled";
    if (row.status === "country_data" || row.status === "country_reported" || row.status === "C") return "Country reported";
  }
  return row.status ? label(row.status) : null;
}

function observationTitle(row: ObservedRecord) {
  const parts = [row.substance, row.metric].filter((part, index, values) => part && values.findIndex((value) => value?.toLowerCase() === part.toLowerCase()) === index);
  return parts.map(label).join(" · ");
}

function ObservationRows({ rows, compact = false }: { rows: ObservedRecord[]; compact?: boolean }) {
  const [visible, setVisible] = useState(compact ? 5 : 25);
  useEffect(() => setVisible(compact ? 5 : 25), [compact, rows]);
  if (!rows.length) return <p className="eh-empty">No source record is available for this selection.</p>;
  return (
    <div className="eh-rows">
      {rows.slice(0, visible).map((row) => (
        <article className="eh-row" key={row.id}>
          <div className="eh-row-main">
            <div>
              <strong>{observationTitle(row)}</strong>
              <span>{[row.population, row.ageGroup, row.sex, row.referencePeriod].filter(Boolean).map(label).join(" · ")}</span>
            </div>
            <div className="eh-value">
              <b>{number(row.value, row.unit)}</b>
              {row.lower != null && row.upper != null && <small>Source interval {number(row.lower, row.unit)}–{number(row.upper, row.unit)}</small>}
            </div>
          </div>
          <div className="eh-provenance">
            <span>Reference year {row.year ?? row.yearText ?? "unspecified"} · source edition {row.publicationYear ?? "year unspecified"}{sourceStatus(row) ? ` · ${sourceStatus(row)}` : ""}</span>
            {row.sourceUrl && <a href={row.sourceUrl} target="_blank" rel="noreferrer">Source <ExternalLink size={11} /></a>}
          </div>
          {(row.caveat || row.method || row.geographicCoverage || row.sourceRow || row.denominator || row.injectingDefinition || row.sampleSize || row.reference) && <details className="eh-detail"><summary>Method and source detail</summary>{row.method && <p>Method: {row.method}</p>}{row.geographicCoverage && <p>Survey geography: {row.geographicCoverage}</p>}{row.denominator && <p>Denominator: {row.denominator}</p>}{row.injectingDefinition && <p>Injecting definition: {row.injectingDefinition}</p>}{row.sampleSize && <p>Sample size: {row.sampleSize}</p>}{row.reference && <p>Source reference: {row.reference}</p>}{row.attribution && <p>Attribution: {row.attribution}</p>}{row.sourceRow && <p>Source locator: {row.sourceRow.sheet ? `${row.sourceRow.sheet} · ` : ""}row {row.sourceRow.rowNo}{row.sourceRow.cellNo ? ` · cell ${row.sourceRow.cellNo}` : ""}</p>}{row.caveat && <p>{row.caveat}</p>}</details>}
        </article>
      ))}
      {rows.length > visible && <button className="eh-more" onClick={() => setVisible((n) => n + 25)}>Show 25 more of {rows.length} observations</button>}
    </div>
  );
}

function currentRows(rows: ObservedRecord[], domain: string) {
  return rows
    .filter((r) => r.domain === domain)
    .sort((a, b) => (b.year ?? -1) - (a.year ?? -1) || a.metric.localeCompare(b.metric));
}

export function PublishedContext({ claims, countryName, policyOnly = false }: { claims: EvidenceClaim[]; countryName?: string; policyOnly?: boolean }) {
  const selected = claims.filter((claim) => {
    if (policyOnly && claim.claimType !== "published_policy_milestone") return false;
    if (!countryName) return true;
    const scope = `${claim.geographyFrom ?? ""} ${claim.geographyTo ?? ""}`.toLowerCase();
    return scope.includes(countryName.toLowerCase());
  });
  if (!selected.length) return null;
  return <section className="eh-context"><h3>{policyOnly ? "Published policy dates" : "Published context"}</h3><p>Source statements and policy dates are context. They are not annual bilateral flow observations or policy effect estimates.</p>{selected.map((claim) => <article key={claim.claimId}><strong>{claim.claim}</strong><span>{claim.policyEffectiveDate ? `Effective ${claim.policyEffectiveDate}` : `${claim.observationStartYear}–${claim.observationEndYear} reported context`} · published {claim.publicationYear}</span><p>{claim.caveat}</p><a href={claim.sourceUrl} target="_blank" rel="noreferrer">UNODC source · {claim.sourceLocator} <ExternalLink size={11} /></a></article>)}</section>;
}

export function CountryEvidence({ iso3 }: { iso3: string }) {
  const [country, setCountry] = useState<ObservedCountry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [group, setGroup] = useState("prevalence");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setCountry(null);
    loadObservedCountry(iso3)
      .then((result) => { if (active) setCountry(result); })
      .catch((cause) => { if (active) setError((cause as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [iso3]);
  const rows = currentRows(country?.observations ?? [], group);
  return (
    <section className="eh-country">
      <div className="section-line"><h3>Health evidence</h3><span>Source archive</span></div>
      <p className="eh-note">Source values use their own years and populations. Map year and model risk do not change these records.</p>
      <div className="eh-tabs" role="tablist" aria-label="Health evidence type">
        {GROUPS.map((item) => <button key={item.key} role="tab" aria-selected={group === item.key} className={group === item.key ? "active" : ""} onClick={() => setGroup(item.key)}>{item.label}</button>)}
      </div>
      <p className="eh-note">{GROUPS.find((item) => item.key === group)?.explanation}</p>
      {loading ? <p className="eh-empty">Loading source observations…</p> : error ? <p className="eh-empty">Source observations could not load: {error}</p> : <ObservationRows rows={rows} compact />}
    </section>
  );
}

export function EvidenceHealth({ countries, selectedIso, onCountry }: { countries: Country[]; selectedIso?: string | null; onCountry?: (iso3: string) => void }) {
  const [iso3, setIso3] = useState(selectedIso || "COL");
  const [country, setCountry] = useState<ObservedCountry | null>(null);
  const [group, setGroup] = useState("prevalence");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [overdose, setOverdose] = useState<ObservedOverdosePoint[]>([]);
  useEffect(() => { if (selectedIso) setIso3(selectedIso); }, [selectedIso]);
  useEffect(() => {
    let active = true;
    setCountry(null);
    setLoading(true);
    setError("");
    loadObservedCountry(iso3)
      .then((result) => { if (active) setCountry(result); })
      .catch((cause) => { if (active) setError((cause as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [iso3]);
  useEffect(() => {
    if (iso3 !== "USA") return;
    let active = true;
    loadObservedUSOverdose().then((rows) => { if (active) setOverdose(rows); }).catch(() => { if (active) setOverdose([]); });
    return () => { active = false; };
  }, [iso3]);
  const rows = useMemo(() => currentRows(country?.observations ?? [], group).filter((row) => `${row.metric} ${row.substance ?? ""} ${row.population ?? ""} ${row.ageGroup ?? ""} ${row.referencePeriod ?? ""}`.toLowerCase().includes(query.toLowerCase())), [country, group, query]);
  const active = GROUPS.find((item) => item.key === group)!;
  const countryName = countries.find((item) => item.iso3 === iso3)?.name ?? iso3;
  return (
    <div className="eh-page">
      <div className="view-heading"><div><h1>Health evidence</h1></div><span className="subtle-pill">Source archive</span></div>
      <div className="eh-toolbar">
        <label>Country<select aria-label="Health evidence country" value={iso3} onChange={(event) => { setIso3(event.target.value); setQuery(""); }}><option value="COL">Colombia</option>{countries.filter((item) => item.iso3 !== "COL").sort((a, b) => a.name.localeCompare(b.name)).map((item) => <option key={item.iso3} value={item.iso3}>{item.name}</option>)}</select></label>
        <button className="eh-country-link" onClick={() => onCountry?.(iso3)}>Open country profile ↗</button>
      </div>
      <div className="eh-tabs" role="tablist" aria-label="Health evidence type">{GROUPS.map((item) => <button key={item.key} role="tab" aria-selected={group === item.key} className={group === item.key ? "active" : ""} onClick={() => { setGroup(item.key); setQuery(""); }}>{item.label}</button>)}</div>
      <div className="eh-heading"><div><h2>{countryName} <small>{iso3}</small></h2><p>{active.explanation}</p></div><span>{rows.length} source records</span></div>
      <label className="eh-search">Filter this source group<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Drug, measure or population" /></label>
      {loading ? <p className="eh-empty">Loading source observations…</p> : error ? <p className="eh-empty">Source observations could not load: {error}</p> : <ObservationRows rows={rows} />}
      {iso3 === "USA" && <USOverdose rows={overdose} />}
    </div>
  );
}

function USOverdose({ rows }: { rows: ObservedOverdosePoint[] }) {
  const indicators = useMemo(() => [...new Set(rows.map((row) => row.indicator))].sort(), [rows]);
  const [indicator, setIndicator] = useState("Drug Overdose Deaths");
  const [visible, setVisible] = useState(24);
  const selected = indicators.includes(indicator) ? indicator : (indicators.find((item) => item.toLowerCase().includes("drug overdose deaths")) ?? indicators[0]);
  const allSeries = rows.filter((row) => row.indicator === selected).sort((a, b) => b.period.localeCompare(a.period));
  const series = allSeries.slice(0, visible);
  return <section className="eh-overdose">
    <h2>US provisional mortality series</h2>
    <p>CDC values use rolling 12-month-ending periods by occurrence jurisdiction. Drug-involved classes overlap within one death and must not be summed. “Number of Deaths” is all-cause mortality, and “Percent with drugs specified” is a percentage. Reported and reporting-delay-adjusted values remain separate; suppressed values remain unavailable.</p>
    {indicators.length ? <>
      <label>CDC indicator<select value={selected} onChange={(event) => { setIndicator(event.target.value); setVisible(24); }}>{indicators.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <div className="eh-overdose-table"><table><thead><tr><th>12 months ending</th><th>Reported</th><th>Adjusted prediction</th><th>Completion</th><th>Source</th></tr></thead><tbody>{series.map((row) => <tr key={row.id}><td>{row.period}</td><td>{number(row.reportedValue, row.unit)}</td><td>{number(row.predictedValue, row.unit)}</td><td>{row.percentComplete == null ? "—" : `${row.percentComplete.toFixed(1)}%`}</td><td><a href={row.sourceUrl} target="_blank" rel="noreferrer">CDC <ExternalLink size={11} /></a></td></tr>)}</tbody></table></div>
      {series.some((row) => row.footnote) && <p className="eh-note">CDC note: {series.find((row) => row.footnote)?.footnote}</p>}
      {allSeries.length > visible && <button className="eh-more" onClick={() => setVisible((count) => count + 24)}>Show earlier periods ({allSeries.length - visible} remaining)</button>}
    </> : <p className="eh-empty">CDC source records are unavailable.</p>}
  </section>;
}
