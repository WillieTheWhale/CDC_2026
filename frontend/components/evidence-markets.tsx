// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { loadObservedCountry } from "@/lib/observed-data";
import type {
  ObservedCountry,
  ObservedOverview,
  ObservedRecord,
} from "@/lib/observed-data";
import type { Country } from "@/lib/types";
import "./evidence-markets.css";

type MarketRecord = ObservedRecord;
type CountryOption = {
  iso3: string;
  name: string;
  marketCount?: number;
};
type MarketOverview = ObservedOverview & {
  marketCatalog?: { iso3: string; count: number }[];
  countrySummaries?: { iso3: string; counts: Record<string, number> }[];
};

function number(value: number | null | undefined, digits = 2) {
  if (value == null) return "Unavailable";
  if (value !== 0 && Math.abs(value) < 1)
    return value.toLocaleString(undefined, { maximumSignificantDigits: 3 });
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}
function unit(unit: string | null | undefined) {
  const labels: Record<string, string> = {
    usd_per_gram: "USD/g",
    usd_per_pure_gram: "USD/pure g",
    usd_per_tablet: "USD/tablet",
    usd_per_unit: "USD/unit",
    percent: "%",
    mg_per_tablet: "mg/tablet",
    ratio: "×",
  };
  return labels[unit ?? ""] ?? (unit || "unit unavailable");
}
function drugMatch(record: MarketRecord, drug: string) {
  if (drug === "all") return true;
  const s = (record.substance ?? "").toLowerCase();
  if (drug === "cocaine") return /cocaine|crack/.test(s);
  if (drug === "heroin") return /heroin/.test(s);
  if (drug === "meth") return /methamphetamine/.test(s);
  if (drug === "cannabis")
    return /cannabis|marijuana|marihuana|hashish/.test(s);
  return false;
}
function observationId(record: MarketRecord) {
  if (typeof record.observationId === "number") return record.observationId;
  const match = String(record.id).match(/(\d+)$/);
  return match ? Number(match[1]) : null;
}
function metricName(record: MarketRecord) {
  if (record.metric === "retail_wholesale_price_ratio")
    return "Retail / wholesale unit-price ratio";
  if (record.metric === "purity_adjusted_price_usd_per_pure_g")
    return "Purity-adjusted nominal price";
  if (record.metric === "purity") return "Purity";
  return "Reported price";
}

export function EvidenceMarkets({
  overview,
  drug,
  countries: countryNames = [],
}: {
  overview: ObservedOverview;
  drug: string;
  countries?: Country[];
}) {
  const catalog = overview as MarketOverview;
  const countries = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of catalog.marketCatalog ?? [])
      counts.set(row.iso3, (counts.get(row.iso3) ?? 0) + row.count);
    const names = new Map(countryNames.map((c) => [c.iso3, c.name]));
    return [...counts]
      .map(
        ([iso3, marketCount]): CountryOption => ({
          iso3,
          name: names.get(iso3) ?? iso3,
          marketCount,
        }),
      )
      .sort(
        (a, b) =>
          b.marketCount! - a.marketCount! || a.name.localeCompare(b.name),
      );
  }, [catalog, countryNames]);
  const [iso3, setIso3] = useState("");
  const [country, setCountry] = useState<ObservedCountry | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [measure, setMeasure] = useState("price");
  const [level, setLevel] = useState("all");
  const [year, setYear] = useState("latest");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(80);
  useEffect(() => {
    setVisibleCount(80);
  }, [iso3, drug, query, measure, level, year]);
  useEffect(() => {
    if (!iso3 && countries.length)
      setIso3(
        countries.find((c) => c.iso3 === "COL")?.iso3 ?? countries[0].iso3,
      );
  }, [countries, iso3]);
  useEffect(() => {
    if (!iso3) return;
    let active = true;
    setLoading(true);
    setError("");
    setCountry(null);
    setSelectedId(null);
    loadObservedCountry(iso3)
      .then((data) => {
        if (active) setCountry(data);
      })
      .catch(() => {
        if (active)
          setError("Market records could not be loaded for this country.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [iso3]);
  const market = useMemo(
    () =>
      (country?.observations ?? []).filter(
        (r) => r.domain === "market_price" || r.domain === "market_derived",
      ),
    [country],
  );
  const years = useMemo(
    () =>
      [
        ...new Set(
          market.map((r) => r.year).filter((y): y is number => y != null),
        ),
      ].sort((a, b) => b - a),
    [market],
  );
  const rows = useMemo(
    () =>
      market
        .filter((r) => {
          if (!drugMatch(r, drug)) return false;
          if (
            measure === "price" &&
            !(r.domain === "market_price" && r.metric === "price")
          )
            return false;
          if (
            measure === "purity" &&
            !(r.domain === "market_price" && r.metric === "purity")
          )
            return false;
          if (
            measure !== "price" &&
            measure !== "purity" &&
            r.metric !== measure
          )
            return false;
          if (level !== "all" && r.marketLevel !== level) return false;
          if (
            query &&
            !`${r.substance ?? ""} ${r.form ?? ""}`
              .toLowerCase()
              .includes(query.toLowerCase())
          )
            return false;
          return year === "latest" || r.year === Number(year);
        })
        .sort(
          (a, b) =>
            (b.year ?? 0) - (a.year ?? 0) ||
            (a.substance ?? "").localeCompare(b.substance ?? "") ||
            a.sourceId.localeCompare(b.sourceId),
        ),
    [market, drug, measure, level, query, year],
  );
  const selected = rows.find((r) => r.id === selectedId) ?? rows[0] ?? null;
  const trend = useMemo(() => {
    if (!selected) return [];
    const matching = market.filter(
      (r) =>
        r.metric === selected.metric &&
        r.substance === selected.substance &&
        r.form === selected.form &&
        r.marketLevel === selected.marketLevel &&
        r.unit === selected.unit &&
        r.sourceId === selected.sourceId &&
        r.basis === selected.basis &&
        drugMatch(r, drug) &&
        r.year != null,
    );
    const years = [...new Set(matching.map((r) => r.year as number))].sort(
      (a, b) => a - b,
    );
    if (!years.length) return [];
    return Array.from({ length: years.at(-1)! - years[0] + 1 }, (_, i) => {
      const y = years[0] + i;
      const values = [
        ...new Set(
          matching
            .filter((r) => r.year === y)
            .map((r) => r.value)
            .filter((v): v is number => v != null),
        ),
      ];
      return { year: y, value: values.length === 1 ? values[0] : null };
    });
  }, [market, selected, drug]);
  const inputs =
    selected?.inputObservationIds
      ?.map((id) =>
        market.find(
          (r) => r.domain === "market_price" && observationId(r) === id,
        ),
      )
      .filter((r): r is MarketRecord => Boolean(r)) ?? [];
  return (
    <div className="em-view">
      <div className="em-heading">
        <div>
          <span className="em-kicker">
            Observed source data / market composition
          </span>
          <h1>Markets</h1>
          <p>
            Country and exact-product price and purity observations, with
            original units, source basis and edition preserved.
          </p>
        </div>
        <span className="em-count">
          17,504 source observations · 925 matched derivations
        </span>
      </div>
      <div className="em-controls">
        <div className="em-control wide">
          <label htmlFor="em-country">Country</label>
          <select
            id="em-country"
            value={iso3}
            onChange={(e) => setIso3(e.target.value)}
          >
            {countries.map((c) => (
              <option key={c.iso3} value={c.iso3}>
                {c.name} · {c.iso3} · {c.marketCount?.toLocaleString()}
              </option>
            ))}
          </select>
        </div>
        <div className="em-control">
          <label htmlFor="em-measure">Measure</label>
          <select
            id="em-measure"
            value={measure}
            onChange={(e) => {
              setMeasure(e.target.value);
              setSelectedId(null);
            }}
          >
            <option value="price">Observed price</option>
            <option value="purity">Observed purity</option>
            <option value="purity_adjusted_price_usd_per_pure_g">
              Purity-adjusted price
            </option>
            <option value="retail_wholesale_price_ratio">
              Retail / wholesale ratio
            </option>
          </select>
        </div>
        <div className="em-control">
          <label htmlFor="em-level">Sale level</label>
          <select
            id="em-level"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          >
            <option value="all">All levels</option>
            <option value="retail">Retail</option>
            <option value="wholesale">Wholesale</option>
          </select>
        </div>
        <div className="em-control">
          <label htmlFor="em-year">Year</label>
          <select
            id="em-year"
            value={year}
            onChange={(e) => setYear(e.target.value)}
          >
            <option value="latest">All observed years</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        <div className="em-control wide">
          <label htmlFor="em-product">Product / form</label>
          <input
            id="em-product"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search exact product"
          />
        </div>
      </div>
      <div className="em-layout">
        <section className="em-section">
          <header>
            <h2>Observations</h2>
            <span>
              {loading
                ? "Loading"
                : `${Math.min(visibleCount, rows.length).toLocaleString()} of ${rows.length.toLocaleString()} matching`}
            </span>
          </header>
          {error ? (
            <p className="em-empty">{error}</p>
          ) : !loading && !rows.length ? (
            <p className="em-empty">
              No matching measurement is published for this selection. Missing
              data is not zero.
            </p>
          ) : (
            <>
              <div className="em-table-wrap">
                <table className="em-table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Product / form</th>
                      <th>Level</th>
                      <th>Value</th>
                      <th>Edition</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, visibleCount).map((r) => (
                      <tr
                        className={`em-row${selected?.id === r.id ? " active" : ""}`}
                        key={r.id}
                        tabIndex={0}
                        onClick={() => setSelectedId(r.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedId(r.id);
                          }
                        }}
                      >
                        <td>{r.year ?? "—"}</td>
                        <td>
                          {r.substance || "Unspecified"}
                          <small>
                            {r.form || "Form unspecified"} ·{" "}
                            {r.basis ??
                              (r.domain === "market_derived"
                                ? "matched nominal inputs"
                                : "basis unspecified")}
                            {r.publisherEstimate ? " · publisher estimate" : ""}
                          </small>
                        </td>
                        <td>{r.marketLevel || "—"}</td>
                        <td className="numeric">
                          {number(r.value)} {unit(r.unit)}
                        </td>
                        <td>{r.publicationYear ?? "n.d."}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {rows.length > visibleCount && (
                <button
                  className="em-more"
                  onClick={() => setVisibleCount((n) => n + 80)}
                >
                  Show next {Math.min(80, rows.length - visibleCount)}{" "}
                  observations
                </button>
              )}
            </>
          )}
        </section>
        <section className="em-section">
          <header>
            <h2>Product history</h2>
            <span>
              {selected
                ? `${selected.substance ?? "Product"}${selected.form && selected.form !== "unspecified" ? ` · ${selected.form}` : ""}`
                : "Select an observation"}
            </span>
          </header>
          {selected ? (
            <>
              <div
                className="em-plot"
                role="img"
                aria-label={`Observed ${metricName(selected).toLowerCase()} by year for selected exact product, form, level, unit, and source edition`}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={trend}
                    margin={{ top: 12, right: 16, bottom: 4, left: 0 }}
                  >
                    <CartesianGrid vertical={false} stroke="#e2e9f1" />
                    <XAxis
                      dataKey="year"
                      type="number"
                      domain={["dataMin", "dataMax"]}
                      tickLine={false}
                      axisLine={false}
                      allowDecimals={false}
                      tick={{ fontSize: 10, fill: "#667b90" }}
                    />
                    <YAxis
                      width={54}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10, fill: "#667b90" }}
                      tickFormatter={(v: number) => number(v, 0)}
                    />
                    <Tooltip
                      formatter={(v) => [
                        `${number(Number(v))} ${unit(selected.unit)}`,
                        metricName(selected),
                      ]}
                      contentStyle={{
                        border: "1px solid #b8c8d8",
                        borderRadius: 0,
                        fontSize: 11,
                      }}
                    />
                    <Line
                      dataKey="value"
                      type="linear"
                      connectNulls={false}
                      stroke="#087f93"
                      strokeWidth={2}
                      dot={{ r: 3, strokeWidth: 0, fill: "#087f93" }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="em-plot-note">
                Same product, form, level, unit, basis and source edition only ·{" "}
                {trend.filter((p) => p.value != null).length} observed year
                {trend.filter((p) => p.value != null).length === 1 ? "" : "s"}.
                Gaps and conflicting duplicates are left blank. Basis:{" "}
                {selected.basis ?? "source basis unavailable"}.
              </p>
              <div className="em-detail">
                <h3>{metricName(selected)}</h3>
                <dl>
                  <dt>Measurement</dt>
                  <dd>
                    {number(selected.value)} {unit(selected.unit)} ·{" "}
                    {selected.year ?? "year unavailable"}
                  </dd>
                  <dt>Source basis</dt>
                  <dd>
                    {selected.basis ??
                      (selected.domain === "market_derived"
                        ? "Nominal, matched 2026 annex inputs"
                        : "Unavailable")}
                  </dd>
                  {selected.publisherEstimate != null && (
                    <>
                      <dt>Publisher flag</dt>
                      <dd>
                        {selected.publisherEstimate
                          ? "Publisher estimate"
                          : "Source-reported observation"}
                      </dd>
                    </>
                  )}
                  {selected.originalValue != null && (
                    <>
                      <dt>Original value</dt>
                      <dd>
                        {number(selected.originalValue)}{" "}
                        {selected.originalUnit ?? "original unit unavailable"}
                        {selected.originalLower != null ||
                        selected.originalUpper != null
                          ? ` · source range ${selected.originalLower ?? "?"}–${selected.originalUpper ?? "?"}`
                          : ""}
                      </dd>
                    </>
                  )}
                  <dt>Source</dt>
                  <dd>
                    <a
                      href={selected.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      UNODC source workbook ↗
                    </a>{" "}
                    · {selected.publicationYear ?? "edition not dated"}
                  </dd>
                  <dt>Original row</dt>
                  <dd>
                    {selected.sourceRow
                      ? `${selected.sourceRow.sheet}, row ${selected.sourceRow.rowNo}${selected.sourceRow.cellNo != null ? `, column ${selected.sourceRow.cellNo}` : ""}`
                      : "Row coordinate unavailable"}
                  </dd>
                  {selected.formula && (
                    <>
                      <dt>Formula</dt>
                      <dd>
                        {selected.formula}
                        {selected.inputs &&
                          ` · ${Object.entries(selected.inputs)
                            .filter(([key]) => !key.endsWith("_id"))
                            .map(
                              ([key, value]) =>
                                `${key.replaceAll("_", " ")} ${number(value)}`,
                            )
                            .join(" · ")}`}
                      </dd>
                    </>
                  )}
                  <dt>Interpretation</dt>
                  <dd>
                    {selected.metric === "retail_wholesale_price_ratio"
                      ? "Matched unit-price contrast; not a profit margin, transaction spread or route gradient."
                      : selected.metric ===
                          "purity_adjusted_price_usd_per_pure_g"
                        ? "Nominal USD per pure gram calculated from matched price and purity; the values can come from different samples."
                        : selected.metric === "purity"
                          ? "Preserves the publisher’s unit; mg per tablet and percent are different measures."
                          : "Publisher price observation. National methods and product definitions can differ."}
                  </dd>
                  {selected.caveat && (
                    <>
                      <dt>Source note</dt>
                      <dd>{selected.caveat}</dd>
                    </>
                  )}
                </dl>
                {inputs.length > 0 && (
                  <ul className="em-inputs">
                    {inputs.map((r) => (
                      <li key={r.id}>
                        <strong>
                          {r.metric === "purity"
                            ? "Purity input"
                            : "Price input"}
                        </strong>
                        {number(r.value)} {unit(r.unit)} ·{" "}
                        {r.year ?? "year unavailable"} ·{" "}
                        {r.sourceRow
                          ? `${r.sourceRow.sheet}, row ${r.sourceRow.rowNo}${r.sourceRow.cellNo != null ? `, column ${r.sourceRow.cellNo}` : ""}`
                          : "source row unavailable"}{" "}
                        ·{" "}
                        <a href={r.sourceUrl} target="_blank" rel="noreferrer">
                          workbook ↗
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
                {selected.domain === "market_derived" && !inputs.length && (
                  <p className="em-note">
                    Contributing row IDs:{" "}
                    {selected.inputObservationIds?.join(", ") || "unavailable"}.
                  </p>
                )}
              </div>
            </>
          ) : (
            <p className="em-empty">
              Choose an observation to inspect the source and matching history.
            </p>
          )}
        </section>
      </div>
      <p className="em-note">
        UNODC World Drug Report annex. The 1990–2024 span belongs mainly to
        Western Europe and US series; it is not a global panel. Different
        workbook editions are kept separate.
      </p>
    </div>
  );
}
