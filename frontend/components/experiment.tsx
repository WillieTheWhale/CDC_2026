// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Experiment } from "@/lib/api";
import { EVIDENCE_API_CONFIGURED, loadObservedCountry } from "@/lib/observed-data";
import type {
  ObservedCountry,
  ObservedOverview,
  ResearchValue,
} from "@/lib/observed-data";
import type { Country } from "@/lib/types";
import { EvidenceValueDrawer } from "./evidence-value-detail";
import "./evidence-markets.css";

const fmt = (n: number | null | undefined, digits = 3) =>
  n == null
    ? "Unavailable"
    : n.toLocaleString(undefined, {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      });

function SourceTrail({
  value,
  country,
  onTrace,
}: {
  value: ResearchValue;
  country: ObservedCountry;
  onTrace?: (metricId: string) => void;
}) {
  const sample = country.researchSamples.find(
    (r) => r.metricId === value.metricId,
  );
  return (
    <div className="er-detail">
      <h3>{value.label}</h3>
      <dl>
        <dt>{sample ? "Next-year homicide" : "Published revision"}</dt>
        <dd>
          {fmt(value.value)} {value.unit} · observed{" "}
          {sample?.outcomeYear ?? value.year ?? "year unavailable"}
        </dd>
        {sample && (
          <>
            <dt>Model pair</dt>
            <dd>
              Seizures {sample.seizureYear} → homicide {sample.outcomeYear};
              log(1 + reported seizure kg) {fmt(sample.log1pSeizureKg)};
              homicide {fmt(sample.homicidePer100k)} per 100,000.
            </dd>
          </>
        )}
        <dt>Formula</dt>
        <dd>{value.formula}</dd>
        <dt>Source editions</dt>
        <dd>
          {value.firstPublicationYear ?? "unknown"}
          {value.lastPublicationYear &&
          value.lastPublicationYear !== value.firstPublicationYear
            ? `–${value.lastPublicationYear}`
            : ""}
        </dd>
        <dt>Linked inputs</dt>
        <dd>
          {value.supportCount} rows, including aggregates and original rows; not
          independent countries.
        </dd>
        <dt>Quality</dt>
        <dd>{value.qualityFlags || "No flag supplied"}</dd>
      </dl>
      <ul className="er-inputs">
        {value.inputs.map((r, i) => (
          <li key={`${r.sourceKey}-${r.role}-${i}`}>
            <strong>
              {r.role.replaceAll("_", " ")} · {r.sourceTable}
            </strong>
            <span>
              {fmt(r.value)} {r.unit ?? "unit unavailable"} · observed{" "}
              {r.observationYear ?? "year unavailable"} · edition{" "}
              {r.publicationYear ?? "not specified"}
            </span>
            <br />
            {r.sourceKey}
            <br />
            {r.transform && (
              <>
                {r.transform}
                <br />
              </>
            )}
            {r.sourceUrl && (
              <a href={r.sourceUrl} target="_blank" rel="noreferrer">
                Original source ↗
              </a>
            )}
          </li>
        ))}
      </ul>
      {onTrace ? (
        <button
          className="evd-trigger em-drill"
          onClick={() => onTrace(value.metricId)}
        >
          Trace this value: formula, inputs and source cells →
        </button>
      ) : (
        <p className="er-note">
          Full value drilldown (original workbook cells, World Bank download and
          edition revisions) needs the live evidence API.
        </p>
      )}
    </div>
  );
}

function Study({
  overview,
  countryNames,
}: {
  overview: ObservedOverview;
  countryNames: Country[];
}) {
  const model = overview.researchModelResults[0];
  const [metric, setMetric] = useState("cocaine_seizure_next_homicide"),
    [metricId, setMetricId] = useState<string | null>(null);
  const countKey =
    metric === "seizure_edition_revision_pct"
      ? "research_values"
      : "research_samples";
  const countries = useMemo(
    () =>
      overview.countrySummaries
        .filter((r) => (r.counts[countKey] ?? 0) > 0)
        .sort((a, b) => (b.counts[countKey] ?? 0) - (a.counts[countKey] ?? 0)),
    [overview, countKey],
  );
  const names = useMemo(
    () => new Map(countryNames.map((r) => [r.iso3, r.name])),
    [countryNames],
  );
  const [iso3, setIso3] = useState("COL"),
    [country, setCountry] = useState<ObservedCountry | null>(null),
    [error, setError] = useState("");
  // /api/evidence/value/{metric_id} drilldown for research values (API only).
  const [drillValue, setDrillValue] = useState<string | null>(null);
  const closeDrill = useCallback(() => setDrillValue(null), []);
  const onTrace = EVIDENCE_API_CONFIGURED ? setDrillValue : undefined;
  useEffect(() => {
    if (!countries.some((r) => r.iso3 === iso3))
      setIso3(countries[0]?.iso3 ?? "");
  }, [countries, iso3]);
  useEffect(() => {
    if (!iso3) return;
    let active = true;
    setCountry(null);
    setError("");
    setMetricId(null);
    loadObservedCountry(iso3)
      .then((data) => {
        if (active) setCountry(data);
      })
      .catch(() => {
        if (active) setError("Research rows could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [iso3]);
  const values = useMemo(
    () =>
      (country?.researchValues ?? [])
        .filter((r) => r.metricKey === metric)
        .sort((a, b) => (a.year ?? 0) - (b.year ?? 0)),
    [country, metric],
  );
  const selected =
    values.find((r) => r.metricId === metricId) ?? values[0] ?? null;
  const definition = overview.researchDefinitions.find(
    (r) => r.metricKey === metric,
  );
  const span =
    model?.ciLow != null && model.ciHigh != null
      ? Math.max(0.3, Math.abs(model.ciLow), Math.abs(model.ciHigh)) * 1.15
      : 1;
  const x = (n: number) => 50 + (n / span) * 50;
  return (
    <>
      <div className="er-result">
        <section className="er-section">
          <header>
            <h2>Prespecified association</h2>
            <span>Country and seizure-year fixed effects</span>
          </header>
          {model ? (
            <>
              <div className="er-result-number">
                {fmt(model.coefficient, 4)} <span>homicides / 100,000</span>
              </div>
              <p className="er-note">
                Per one-unit rise in log(1 + reported cocaine seizure kg). The
                interval spans both decreases and increases.
              </p>
              <div className="er-stat-line">
                <span>
                  <small>95% interval</small>[{fmt(model.ciLow)},{" "}
                  {fmt(model.ciHigh)}]
                </span>
                <span>
                  <small>Clustered SE</small>
                  {fmt(model.standardError)}
                </span>
                <span>
                  <small>p-value</small>
                  {fmt(model.pValue)}
                </span>
              </div>
            </>
          ) : (
            <p className="er-empty">Verified model result unavailable.</p>
          )}
        </section>
        <section className="er-section">
          <header>
            <h2>Estimate and uncertainty</h2>
            <span>Homicide rate difference / 100,000</span>
          </header>
          {model?.ciLow != null &&
            model.ciHigh != null &&
            model.coefficient != null && (
              <>
                <div
                  className="er-interval"
                  role="img"
                  aria-label={`Coefficient ${fmt(model.coefficient, 4)}, 95 percent interval ${fmt(model.ciLow)} to ${fmt(model.ciHigh)}, crossing zero`}
                >
                  <div
                    className="er-interval-range"
                    style={{
                      left: `${x(model.ciLow)}%`,
                      width: `${x(model.ciHigh) - x(model.ciLow)}%`,
                    }}
                  />
                  <div
                    className="er-interval-point"
                    style={{ left: `${x(model.coefficient)}%` }}
                  />
                </div>
                <div className="er-interval-labels">
                  <span>−{fmt(span, 2)}</span>
                  <span>0</span>
                  <span>+{fmt(span, 2)}</span>
                </div>
              </>
            )}
          <div className="er-stat-line">
            <span>
              <small>Country-years</small>
              {model?.n.toLocaleString() ?? "—"}
            </span>
            <span>
              <small>Countries / clusters</small>
              {model?.countries ?? "—"} / {model?.clusterCount ?? "—"}
            </span>
            <span>
              <small>Seizure years</small>
              {model?.firstPredictorYear ?? "—"}–
              {model?.lastPredictorYear ?? "—"}
            </span>
          </div>
        </section>
      </div>
      <p className="er-caveat">
        Retrospective ecological association, not a causal effect or forecast
        test. Seizures reflect enforcement and reporting, not observed trade
        volume or route exposure. The homicide outcome is general-population.
        Source editions downloaded in 2026 may revise past years.
      </p>
      <div className="er-sample-grid">
        <section className="er-section">
          <header>
            <h2>Inspect model inputs</h2>
            <span>
              {values.length} rows · {iso3}
            </span>
          </header>
          <div className="er-controls">
            <div className="er-control">
              <label htmlFor="er-country">Country</label>
              <select
                id="er-country"
                value={iso3}
                onChange={(e) => setIso3(e.target.value)}
              >
                {countries.map((r) => (
                  <option key={r.iso3} value={r.iso3}>
                    {names.get(r.iso3) ?? r.iso3} · {r.iso3} ·{" "}
                    {r.counts[countKey]} rows
                  </option>
                ))}
              </select>
            </div>
            <div className="er-control wide">
              <label htmlFor="er-metric">Research layer</label>
              <select
                id="er-metric"
                value={metric}
                onChange={(e) => {
                  setMetric(e.target.value);
                  setMetricId(null);
                }}
              >
                <option value="cocaine_seizure_next_homicide">
                  Seizure / next-year homicide pairs
                </option>
                <option value="seizure_edition_revision_pct">
                  Published seizure revisions
                </option>
              </select>
            </div>
          </div>
          {error ? (
            <p className="er-empty">{error}</p>
          ) : !country ? (
            <p className="er-empty">Loading source-linked rows…</p>
          ) : !values.length ? (
            <p className="er-empty">
              No matching row. Missing records are not zero.
            </p>
          ) : (
            <div className="er-table-wrap">
              <table className="er-table">
                <thead>
                  <tr>
                    <th>
                      {metric === "cocaine_seizure_next_homicide"
                        ? "Seizure year"
                        : "Observation year"}
                    </th>
                    <th>Drug</th>
                    <th>
                      {metric === "cocaine_seizure_next_homicide"
                        ? "Next-year homicide"
                        : "Published revision"}
                    </th>
                    <th>Inputs</th>
                  </tr>
                </thead>
                <tbody>
                  {values.map((r) => (
                    <tr
                      key={r.metricId}
                      className={`er-row${selected?.metricId === r.metricId ? " active" : ""}`}
                      tabIndex={0}
                      onClick={() => setMetricId(r.metricId)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setMetricId(r.metricId);
                        }
                      }}
                    >
                      <td>{r.year ?? "—"}</td>
                      <td>{r.drug ?? "—"}</td>
                      <td className="numeric">
                        {onTrace ? (
                          <button
                            className="evd-trigger"
                            title="Open formula, inputs and source cells"
                            onClick={(event) => {
                              event.stopPropagation();
                              setMetricId(r.metricId);
                              onTrace(r.metricId);
                            }}
                          >
                            {fmt(
                              r.value,
                              metric === "seizure_edition_revision_pct" ? 2 : 3,
                            )}{" "}
                            {r.unit}
                          </button>
                        ) : (
                          <>
                            {fmt(
                              r.value,
                              metric === "seizure_edition_revision_pct" ? 2 : 3,
                            )}{" "}
                            {r.unit}
                          </>
                        )}
                      </td>
                      <td>{r.supportCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {definition && (
            <p className="er-note">
              {definition.selectionRule} {definition.interpretation}
            </p>
          )}
        </section>
        <section className="er-section">
          <header>
            <h2>Source trail</h2>
            <span>
              {selected
                ? `${selected.iso3} · ${selected.year}`
                : "Select a row"}
            </span>
          </header>
          {selected && country ? (
            <SourceTrail value={selected} country={country} onTrace={onTrace} />
          ) : (
            <p className="er-empty">
              Select a row to inspect original source inputs.
            </p>
          )}
        </section>
      </div>
      <p className="er-note">
        Method: {model?.specification ?? "unavailable"}. Source links and
        observation years accompany every contributing input. World Bank
        `lastupdated` is metadata, not a publication year.
      </p>
      <EvidenceValueDrawer valueId={drillValue} onClose={closeDrill} />
    </>
  );
}

function AfghanHistory({ experiment }: { experiment: Experiment }) {
  const series = experiment.series.filter((s) => s.id.endsWith("_cultivation"));
  const points = useMemo(() => {
    const rows = new Map<number, Record<string, number | null>>();
    for (const s of series)
      for (const p of s.points) {
        const row = rows.get(p.year) ?? { year: p.year };
        row[s.id] = p.value;
        rows.set(p.year, row);
      }
    return [...rows.values()].sort((a, b) => Number(a.year) - Number(b.year));
  }, [series]);
  return (
    <>
      <section className="er-section">
        <header>
          <h2>Afghanistan cultivation history</h2>
          <span>UNODC reported hectares · 2026 annex</span>
        </header>
        <div
          className="er-history"
          role="img"
          aria-label="Reported opium cultivation in Afghanistan and Myanmar by year, on one hectare scale"
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={points}
              margin={{ top: 20, right: 16, bottom: 5, left: 2 }}
            >
              <CartesianGrid vertical={false} stroke="#e2e9f1" />
              <XAxis
                dataKey="year"
                type="number"
                domain={["dataMin", "dataMax"]}
                allowDecimals={false}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 10, fill: "#667b90" }}
              />
              <YAxis
                width={55}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 10, fill: "#667b90" }}
                tickFormatter={(n: number) => `${Math.round(n / 1000)}k`}
              />
              <Tooltip
                contentStyle={{
                  border: "1px solid #b8c8d8",
                  borderRadius: 0,
                  fontSize: 11,
                }}
                formatter={(v, name) => [
                  `${Number(v).toLocaleString()} ha`,
                  String(name).startsWith("afg") ? "Afghanistan" : "Myanmar",
                ]}
              />
              <ReferenceLine
                x={2022}
                stroke="#8092a5"
                strokeDasharray="3 3"
                label={{ value: "2022 ban", fill: "#5f7488", fontSize: 10 }}
              />
              {series.map((s) => (
                <Line
                  key={s.id}
                  dataKey={s.id}
                  type="linear"
                  connectNulls={false}
                  stroke={s.id.startsWith("afg") ? "#d54c3d" : "#7b60a6"}
                  strokeWidth={2}
                  dot={{ r: 2, strokeWidth: 0 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="er-note">
          Afghanistan <span style={{ color: "#d54c3d" }}>■</span> · Myanmar{" "}
          <span style={{ color: "#7b60a6" }}>■</span>. Published cultivation
          observations show a sharp Afghan decline after the ban. They do not
          establish a measured bilateral route shift.
        </p>
      </section>
      <p className="er-caveat">
        UNODC World Drug Report 2026 statistical annex ·{" "}
        <a
          href="https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html"
          target="_blank"
          rel="noreferrer"
        >
          source ↗
        </a>
        . This historical comparison is separate from the seizure–homicide
        model.
      </p>
    </>
  );
}

export function EvidenceResearch({
  overview,
  experiment,
  countries = [],
}: {
  overview: ObservedOverview;
  experiment: Experiment | null;
  countries?: Country[];
}) {
  const [tab, setTab] = useState<"study" | "afghan">("study");
  const model = overview.researchModelResults[0];
  return (
    <div className="er-view">
      <div className="er-heading">
        <div>
          <span className="er-kicker">Research / observed-source evidence</span>
          <h1>Experiment</h1>
          <p>
            One prespecified retrospective model, with uncertainty and
            source-linked inputs. Afghan cultivation appears as a separate
            observed comparison.
          </p>
        </div>
        <span className="er-count">
          1 model · {model?.n.toLocaleString() ?? "—"} country-years ·{" "}
          {model?.countries ?? "—"} countries
        </span>
      </div>
      <nav className="er-tabs" aria-label="Experiment sections">
        <button
          className={tab === "study" ? "active" : ""}
          onClick={() => setTab("study")}
        >
          Retrospective study
        </button>
        <button
          className={tab === "afghan" ? "active" : ""}
          onClick={() => setTab("afghan")}
        >
          Afghanistan 2022 ban
        </button>
      </nav>
      {tab === "study" ? (
        <Study overview={overview} countryNames={countries} />
      ) : experiment ? (
        <AfghanHistory experiment={experiment} />
      ) : (
        <p className="er-empty">Cultivation history is unavailable.</p>
      )}
    </div>
  );
}
export { EvidenceResearch as ExperimentView };
