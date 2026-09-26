// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  ExternalLink,
  FlaskConical,
  Info,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import { RouteStudy } from "./figma-motion";
import {
  api,
  CountryDetail,
  DEMO,
  SNAPSHOT_YEAR,
  PROFILE_YEAR,
  SNAPSHOT_TIME,
  drugColor,
  drugLabel,
  formatNumber,
  scoreColor,
  Simulation,
} from "@/lib/api";
import type { Catalog } from "@/lib/api";
import type { Country, Edge, LiveEvent, Price, RiskRow } from "@/lib/types";
import { HistoryChart, Sparkline } from "./charts";

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="empty">
      <Info size={18} />
      <p>{children}</p>
    </div>
  );
}
export function RiskTable({
  rows,
  onCountry,
  compact = false,
  limit = 250,
}: {
  rows: RiskRow[];
  onCountry: (iso: string) => void;
  compact?: boolean;
  limit?: number;
}) {
  const [sort, setSort] =
    useState<
      keyof Pick<
        RiskRow,
        | "score"
        | "exposure"
        | "vulnerability"
        | "protection"
        | "name"
        | "delta_1y"
      >
    >("score");
  const [ascending, setAscending] = useState(false);
  const [query, setQuery] = useState("");
  const sorted = useMemo(
    () =>
      rows
        .filter(
          (r) =>
            r.name.toLowerCase().includes(query.toLowerCase()) ||
            r.iso3.toLowerCase().includes(query.toLowerCase()),
        )
        .sort((a, b) => {
          const aa = a[sort],
            bb = b[sort];
          return (
            (typeof aa === "number" && typeof bb === "number"
              ? aa - bb
              : String(aa).localeCompare(String(bb))) * (ascending ? 1 : -1)
          );
        })
        .slice(0, compact ? 4 : limit),
    [rows, query, sort, ascending, compact, limit],
  );
  const sortBy = (key: typeof sort) => {
    if (sort === key) setAscending(!ascending);
    else {
      setSort(key);
      setAscending(key === "name");
    }
  };
  const column = (label: string, key: typeof sort) => (
    <button className="sort-button" onClick={() => sortBy(key)}>
      {label}
      <ArrowDownUp size={11} />
    </button>
  );
  return (
    <div className={compact ? "risk-table compact" : "risk-table"}>
      {!compact && (
        <div className="table-toolbar">
          <label className="field-search">
            <Search size={15} />
            <input
              aria-label="Filter risk countries"
              placeholder="Find a country…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <span>{sorted.length} countries · 0–100 scale</span>
        </div>
      )}
      {!sorted.length ? (
        <Empty>No risk data for this year.</Empty>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th
                  aria-sort={
                    sort === "name"
                      ? ascending
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  {column("Country", "name")}
                </th>
                {!compact && (
                  <>
                    <th>{column("Exposure", "exposure")}</th>
                    <th>{column("Vulnerability", "vulnerability")}</th>
                    <th>{column("Protection", "protection")}</th>
                  </>
                )}
                <th
                  aria-sort={
                    sort === "score"
                      ? ascending
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  {column("Risk", "score")}
                </th>
                <th>Trend</th>
                {!compact && <th>{column("1Y change", "delta_1y")}</th>}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.iso3}>
                  <td className="muted mono">
                    {String(r.rank).padStart(2, "0")}
                  </td>
                  <td>
                    <button
                      className="country-link"
                      onClick={() => onCountry(r.iso3)}
                    >
                      {r.name}
                      <span>{r.iso3}</span>
                    </button>
                  </td>
                  {!compact &&
                    ["exposure", "vulnerability", "protection"].map((k) => (
                      <td key={k}>
                        <div className="metric-cell">
                          <span>{r[k as "exposure"]}</span>
                          <i>
                            <b
                              style={{
                                width: `${r[k as "exposure"]}%`,
                                background:
                                  k === "protection" ? "#7c9279" : "#d3a377",
                              }}
                            />
                          </i>
                        </div>
                      </td>
                    ))}
                  <td>
                    <span
                      className="risk-number"
                      style={{ color: scoreColor(r.score) }}
                    >
                      {r.score.toFixed(1)}
                    </span>
                  </td>
                  <td>
                    <Sparkline points={r.trend} color={scoreColor(r.score)} />
                  </td>
                  {!compact && (
                    <td
                      className={
                        r.delta_1y > 0 ? "negative mono" : "positive mono"
                      }
                    >
                      {r.delta_1y > 0 ? "+" : ""}
                      {r.delta_1y.toFixed(1)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!compact && (
        <p className="table-note">
          Exposure and vulnerability increase risk; protection reduces it.
          Scores support prevention planning, not individual prediction.
        </p>
      )}
    </div>
  );
}
export function NewsList({
  events,
  onEvent,
  compact = false,
}: {
  events: LiveEvent[];
  onEvent: (e: LiveEvent) => void;
  compact?: boolean;
}) {
  if (!events.length) return <Empty>No matching events.</Empty>;
  return (
    <div className={compact ? "news-list compact" : "news-list"}>
      {events.slice(0, compact ? 3 : 50).map((e) => (
        <button
          className={`news-item ${e.is_anomaly ? "anomaly" : ""}`}
          key={e.id}
          onClick={() => onEvent(e)}
        >
          <time>
            {new Date(e.published_at).toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
              timeZone: "UTC",
            })}
          </time>
          <div>
            <div className="news-tags">
              <span style={{ color: drugColor[e.drug] ?? "#777" }}>
                {drugLabel[e.drug] ?? e.drug}
              </span>
              {e.is_anomaly && <b>Unusual signal</b>}
              {!compact && (
                <span>
                  {e.size} · {Math.round(e.confidence * 100)}% confidence
                </span>
              )}
            </div>
            <p>{e.title}</p>
            {!compact && (
              <small>
                {e.origin ?? "—"} → {e.destination ?? "—"} ·{" "}
                {e.event_type.replaceAll("_", " ")} ·{" "}
                {new Date(e.published_at).toLocaleDateString("en-GB", {
                  timeZone: "UTC",
                })}
              </small>
            )}
          </div>
          <ArrowUpRight size={14} />
        </button>
      ))}
    </div>
  );
}
export function CountryInspector({
  country,
  year,
  risk: summaryRisk,
  scenarioRisk,
  edges,
  onClose,
  onRoute,
}: {
  country: Country;
  year: number;
  risk?: RiskRow;
  scenarioRisk?: Simulation["risk_deltas"][number];
  edges: Edge[];
  onClose: () => void;
  onRoute: (e: Edge) => void;
}) {
  const [detail, setDetail] = useState<CountryDetail | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [tab, setTab] = useState("Overview");
  const risk = summaryRisk ?? detail?.risk;
  useEffect(() => {
    let active = true;
    setLoading(true);
    setDetail(null);
    setError("");
    api
      .country(country.iso3, year)
      .then((r) => {
        if (active) setDetail(r?.data ?? null);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [country.iso3, year]);
  const routes = edges.filter(
    (e) => e.from === country.iso3 || e.to === country.iso3,
  );
  return (
    <motion.div
      key={country.iso3}
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      className="country-inspector"
    >
      <div className="inspector-top">
        <span>
          {country.iso3} <span className="muted">/ {year}</span>
        </span>
        <button
          className="icon-button"
          aria-label="Close country details"
          onClick={onClose}
        >
          <X size={17} />
        </button>
      </div>
      <h2>{country.name}</h2>
      <p className="country-region">{country.region}</p>
      <div className="inspector-tabs">
        {["Overview", "Evidence", "Routes"].map((t) => (
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      {scenarioRisk && (
        <div className="country-scenario">
          <span>Scenario risk</span>
          <strong>
            {scenarioRisk.baseline_score.toFixed(1)} <ArrowRight size={16} />{" "}
            {scenarioRisk.scenario_score.toFixed(1)}
          </strong>
          <small>
            Change: {scenarioRisk.delta > 0 ? "+" : ""}
            {scenarioRisk.delta.toFixed(1)} points.{" "}
            {risk && Math.abs(risk.score - scenarioRisk.baseline_score) > 0.1
              ? "This scenario uses a different baseline from the saved profile below."
              : "The profile below is the baseline."}
          </small>
        </div>
      )}
      {loading && (
        <div className="loading-line" role="status">
          Loading country evidence…
        </div>
      )}
      {error && <div className="inline-error">{error}</div>}
      {tab === "Overview" && (
        <>
          {risk ? (
            <>
              <div className="country-score">
                <div>
                  <span>Spillover risk</span>
                  <strong style={{ color: scoreColor(risk.score) }}>
                    {risk.score.toFixed(1)}
                    <small>/100</small>
                  </strong>
                </div>
                <span
                  className="tier"
                  style={{ color: scoreColor(risk.score) }}
                >
                  {risk.tier}
                </span>
              </div>
              <div className="risk-breakdown">
                {(["exposure", "vulnerability", "protection"] as const).map(
                  (k) => (
                    <div key={k}>
                      <span>{k}</span>
                      <b>{risk[k]}</b>
                      <i>
                        <em
                          style={{
                            width: `${risk[k]}%`,
                            background:
                              k === "protection"
                                ? "#779276"
                                : scoreColor(risk[k]),
                          }}
                        />
                      </i>
                    </div>
                  ),
                )}
              </div>
              <HistoryChart points={risk.trend} height={140} />
              <p className="source-note">
                TRACE risk model · {year}
                {DEMO ? " · saved snapshot" : ""}
              </p>
            </>
          ) : (
            <Empty>No risk score available for {year}.</Empty>
          )}
          {detail && (
            <>
              <div className="section-line">
                <h3>Prevention coverage</h3>
                <ShieldCheck size={15} />
              </div>
              <div className="coverage">
                {(
                  [
                    ["nsp", "Needle & syringe programs"],
                    ["oat", "Opioid agonist therapy"],
                    ["naloxone", "Take-home naloxone"],
                    ["dcr", "Consumption rooms"],
                  ] as const
                ).map(([k, label]) => (
                  <div key={k}>
                    <span>{label}</span>
                    {detail.harm_reduction?.[k] ? (
                      <Check size={15} />
                    ) : (
                      <span className="muted">
                        {detail.harm_reduction?.[k] === false
                          ? "Not reported"
                          : "Unknown"}
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <p className="source-note">
                Harm Reduction International · {detail.harm_reduction?.year}
                {DEMO ? " · saved snapshot" : ""}
              </p>
              <p className="briefing">{detail.briefing}</p>
            </>
          )}
          {!loading && !detail && (
            <p className="quiet-note">
              Country evidence is not available for this selection. The saved
              profile covers Colombia in {PROFILE_YEAR}.
            </p>
          )}
        </>
      )}
      {tab === "Evidence" && (
        <>
          {detail?.indicators.map((g) => (
            <section className="indicator-group" key={g.role}>
              <h3>{g.label}</h3>
              {g.indicators.map((i) => (
                <div className="indicator" key={i.code}>
                  <div>
                    <span>{i.name}</span>
                    <b>
                      {formatNumber(i.value)} <small>{i.unit}</small>
                    </b>
                  </div>
                  <a
                    href={`https://api.worldbank.org/v2/country/${country.iso3}/indicator/${encodeURIComponent(i.code)}?source=${i.source_id}&date=${i.year}&format=json`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    World Bank · source {i.source_id} · {i.year}{" "}
                    {i.imputed ? "· imputed" : ""}
                    <ExternalLink size={10} />
                  </a>
                </div>
              ))}
            </section>
          ))}
          {detail?.oc_index && (
            <section className="indicator-group">
              <h3>Organized Crime Index</h3>
              <div className="oc-scores">
                <span>
                  Criminality <b>{detail.oc_index.criminality}</b>
                </span>
                <span>
                  Resilience <b>{detail.oc_index.resilience}</b>
                </span>
              </div>
              <p className="source-note">
                GI-TOC · {detail.oc_index.edition} · 0–10 scale
              </p>
            </section>
          )}
          {!loading && !detail && (
            <Empty>
              Detailed indicators will appear when this country’s profile is
              available.
            </Empty>
          )}
        </>
      )}
      {tab === "Routes" && (
        <>
          <div className="section-line">
            <h3>{routes.length} corridors</h3>
            <span>{year}</span>
          </div>
          {routes.length ? (
            routes.map((e) => (
              <button
                className="route-row"
                key={e.id}
                onClick={() => onRoute(e)}
              >
                <i style={{ background: drugColor[e.drug] }} />
                <div>
                  <b>
                    {e.from} <span>→</span> {e.to}
                  </b>
                  <small>
                    {drugLabel[e.drug]} · {e.confidence}% confidence
                  </small>
                </div>
                <span className="mono">
                  {formatNumber(e.kg)}
                  <small> kg</small>
                </span>
              </button>
            ))
          ) : (
            <Empty>No matching routes.</Empty>
          )}
          {detail?.prices.map((p) => (
            <div className="country-price" key={p.level + p.drug}>
              <span>
                {drugLabel[p.drug]} · {p.level}
              </span>
              <strong>
                ${p.latest.toFixed(2)}
                <small> /g</small>
              </strong>
              <Sparkline points={p.points} dataKey="value" />
              <p className="source-note">UNODC · {p.points.at(-1)?.year}</p>
            </div>
          ))}
        </>
      )}
    </motion.div>
  );
}
export function RouteInspector({
  edge,
  onClose,
  onCountry,
}: {
  edge: Edge;
  onClose: () => void;
  onCountry: (iso: string) => void;
}) {
  return (
    <div className="route-inspector">
      <div className="inspector-top">
        <span style={{ color: drugColor[edge.drug] }}>
          {drugLabel[edge.drug]}
        </span>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close route details"
        >
          <X size={17} />
        </button>
      </div>
      <h2>
        <button onClick={() => onCountry(edge.from)}>{edge.from}</button>{" "}
        <ArrowRight size={22} />{" "}
        <button onClick={() => onCountry(edge.to)}>{edge.to}</button>
      </h2>
      <RouteStudy key={edge.id} />
      <div className="route-numbers">
        <div>
          <span>Normalized volume</span>
          <b>{edge.volume_norm.toFixed(2)}</b>
        </div>
        <div>
          <span>Confidence</span>
          <b>{edge.confidence}%</b>
        </div>
      </div>
      <p className="source-note">
        {edge.year} ·{" "}
        {edge.probability === null ? "Observed corridor" : "Predicted corridor"}
        {DEMO ? " · saved snapshot" : ""}
      </p>
      <div className="section-line">
        <h3>Evidence signals</h3>
      </div>
      {Object.entries(edge.signals).map(([k, v]) => (
        <div className="evidence-row" key={k}>
          <span>{k.replaceAll("_", " ")}</span>
          {v ? <Check size={15} /> : <span className="muted">No signal</span>}
        </div>
      ))}
      <div className="section-line">
        <h3>Model drivers</h3>
      </div>
      {edge.drivers.length ? (
        edge.drivers.map((d) => (
          <div className="driver" key={d.feature}>
            <span>{d.label}</span>
            <b className={d.direction === "up" ? "negative" : "positive"}>
              {d.contribution > 0 ? "+" : ""}
              {d.contribution.toFixed(2)}
            </b>
          </div>
        ))
      ) : (
        <p className="quiet-note">
          Switch to the forecast to inspect model drivers.
        </p>
      )}
      <p className="quiet-note">
        Seizure records are evidence of detection, not a direct measure of total
        trade.
      </p>
    </div>
  );
}
export function Markets({ series, drug }: { series: Price[]; drug: string }) {
  const [level, setLevel] = useState("all");
  const filtered = series.filter(
    (p) =>
      (drug === "all" || p.drug === drug) &&
      (level === "all" || p.level === level),
  );
  return (
    <>
      <div className="view-heading">
        <div>
          <h1>Market signals</h1>
          <p>Retail and wholesale prices across the network.</p>
        </div>
        <select
          aria-label="Price level"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          <option value="all">All price levels</option>
          <option value="retail">Retail</option>
          <option value="wholesale">Wholesale</option>
        </select>
      </div>
      <div className="price-grid">
        {filtered.map((p) => (
          <article
            className="price-card"
            key={`${p.iso3}-${p.drug}-${p.level}`}
          >
            <div className="section-line">
              <h3>{p.name}</h3>
              <span className="mono muted">{p.iso3}</span>
            </div>
            <span className="drug-label" style={{ color: drugColor[p.drug] }}>
              {drugLabel[p.drug]} · {p.level}
            </span>
            <div className="price-value">
              ${p.latest.toFixed(2)}
              <span>{p.unit}</span>
              <small
                className={
                  p.yoy_change_pct == null
                    ? "muted"
                    : p.yoy_change_pct > 0
                      ? "negative"
                      : "positive"
                }
              >
                {p.yoy_change_pct == null
                  ? "YoY unavailable"
                  : `${p.yoy_change_pct > 0 ? "+" : ""}${p.yoy_change_pct.toFixed(1)}% YoY`}
              </small>
            </div>
            <HistoryChart
              points={p.points}
              dataKey="value"
              color={drugColor[p.drug]}
              height={130}
            />
            <p className="source-note">
              UNODC World Drug Report · {p.points.at(-1)?.year}
              {DEMO ? " · saved snapshot" : ""}
            </p>
          </article>
        ))}
      </div>
      {!filtered.length && <Empty>No matching price series.</Empty>}
    </>
  );
}

export function ScenarioRiskList({
  result,
  onCountry,
}: {
  result: Simulation;
  onCountry: (iso: string) => void;
}) {
  return (
    <div className="scenario-risk-list">
      {result.risk_deltas.slice(0, 4).map((r) => (
        <button key={r.iso3} onClick={() => onCountry(r.iso3)}>
          <span>{r.name}</span>
          <b>
            {r.baseline_score.toFixed(1)} <ArrowRight size={11} />{" "}
            {r.scenario_score.toFixed(1)}
          </b>
          <em className={r.delta > 0 ? "negative" : "positive"}>
            {r.delta > 0 ? "+" : ""}
            {r.delta.toFixed(1)}
          </em>
        </button>
      ))}
    </div>
  );
}
export function ScenarioPanel({
  initial,
  onApplied,
  onMap,
  onExperiment,
}: {
  initial: string;
  onApplied: (s: Simulation) => void;
  onMap: () => void;
  onExperiment: () => void;
}) {
  const [text, setText] = useState(initial || "Colombia cuts coca 50%"),
    [pending, setPending] = useState(false),
    [result, setResult] = useState<Simulation | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (initial) setText(initial);
  }, [initial]);
  const run = async () => {
    setError("");
    setPending(true);
    setResult(null);
    try {
      const r = await api.simulate({ scenario: text, year: 2025 });
      setResult(r.data);
      onApplied(r.data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  };
  return (
    <>
      <div className="view-heading">
        <div>
          <h1>Scenario analysis</h1>
        </div>
        <FlaskConical size={28} strokeWidth={1} />
      </div>
      <div className="scenario-layout">
        <section className="scenario-input">
          <label htmlFor="scenario-input">Scenario</label>
          <textarea
            id="scenario-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
          />
          <div className="presets">
            <button onClick={() => setText("Colombia cuts coca 50%")}>
              Colombia coca −50%
            </button>
            <button
              onClick={() => setText("Afghanistan cuts opium cultivation 95%")}
            >
              Afghan cultivation −95%
            </button>
            <button onClick={() => setText("Mexico legalizes cannabis")}>
              Mexico legalization
            </button>
          </div>
          <button
            className="primary-button"
            disabled={pending || !text.trim()}
            onClick={run}
          >
            {pending ? "Running scenario…" : "Run scenario"}
            <ArrowRight size={16} />
          </button>
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
          <p className="quiet-note">
            {DEMO
              ? "The saved snapshot includes the Colombia 50% scenario. Custom scenarios require the connected model."
              : "Scenario effects are model estimates, not forecasts of policy outcomes."}
          </p>
          <button className="text-button" onClick={onExperiment}>
            Afghanistan opium ban
            <ArrowUpRight size={15} />
          </button>
        </section>
        <section className="scenario-results">
          {result ? (
            <>
              <div className="section-line">
                <h2>Network response</h2>
                <button className="text-button" onClick={onMap}>
                  View on map <ArrowUpRight size={14} />
                </button>
              </div>
              <p className="scenario-summary">{result.summary}</p>
              <div className="scenario-deltas">
                {result.risk_deltas.map((r) => (
                  <div key={r.iso3}>
                    <span>{r.name}</span>
                    <b>
                      {r.baseline_score.toFixed(1)}
                      <ArrowRight size={13} />
                      {r.scenario_score.toFixed(1)}
                    </b>
                    <em className={r.delta > 0 ? "negative" : "positive"}>
                      {r.delta > 0 ? "+" : ""}
                      {r.delta.toFixed(1)}
                    </em>
                  </div>
                ))}
              </div>
              <h3>Corridor volume change</h3>
              {result.edges_changed.map((e) => (
                <div className="scenario-edge" key={e.from + e.to}>
                  <span>
                    {e.from} → {e.to}
                  </span>
                  <div>
                    <i style={{ width: `${e.baseline_volume_norm * 100}%` }} />
                    <b style={{ width: `${e.scenario_volume_norm * 100}%` }} />
                  </div>
                  <strong className={e.delta_pct > 0 ? "negative" : "positive"}>
                    {e.delta_pct > 0 ? "+" : ""}
                    {e.delta_pct.toFixed(1)}%
                  </strong>
                </div>
              ))}
              <p className="source-note">
                Light bar: baseline · colored bar: scenario
              </p>
              {result.warnings.map((w) => (
                <p className="quiet-note" key={w}>
                  {w}
                </p>
              ))}
            </>
          ) : (
            <div className="scenario-idle">
              <p>No result</p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
export { ExperimentView } from "./experiment";
export function Sources({
  catalog,
  onClose,
}: {
  catalog: Catalog;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="sources-modal modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sources-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="section-line">
          <h2 id="sources-title">Data sources</h2>
          <button
            className="icon-button"
            aria-label="Close data sources"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <p>
          {DEMO
            ? "You’re exploring saved pipeline output. World Bank values retain their source and year; corridor volumes are model estimates. The news feed replays synthetic sample headlines."
            : "Coverage, freshness and provenance for the connected data services."}
        </p>
        <p className="source-note">
          {DEMO
            ? `Snapshot generated ${new Date(SNAPSHOT_TIME).toLocaleString("en-GB", { timeZone: "UTC" })} UTC`
            : "Source retrieval times are shown below."}
        </p>
        <div className="source-list">
          {catalog.sources.map((s) => (
            <a key={s.id} href={s.url} target="_blank" rel="noreferrer">
              <div>
                <h3>{s.name}</h3>
                <small>
                  Latest year: {s.latest_year ?? "not available"} · {s.status}
                </small>
                {s.retrieved_at && (
                  <small>
                    Retrieved{" "}
                    {new Date(s.retrieved_at).toLocaleDateString("en-GB", {
                      timeZone: "UTC",
                    })}
                  </small>
                )}
                {"note" in s && s.note && <p>{s.note}</p>}
              </div>
              <ExternalLink size={15} />
            </a>
          ))}
        </div>
        <div className="source-foot">
          <p>
            Exposure is country-level. Texture shows index bands, not local
            observations. Links join country coordinates, not measured travel
            paths.
          </p>
          <a href="https://openfreemap.org/" target="_blank" rel="noreferrer">
            Local geography: OpenFreeMap / OpenStreetMap
          </a>
          <a
            href="https://www.naturalearthdata.com/"
            target="_blank"
            rel="noreferrer"
          >
            Cartography: Natural Earth · public domain
          </a>
          <a
            href="https://www.figma.com/design/pGB5GIz2RsLKBPNjnyHpdg"
            target="_blank"
            rel="noreferrer"
          >
            TRACE visual assets · Figma
          </a>
        </div>
      </section>
    </div>
  );
}
export function Compare({
  codes,
  countries,
  rows,
  onClose,
  onCountry,
}: {
  codes: string[];
  countries: Country[];
  rows: RiskRow[];
  onClose: () => void;
  onCountry: (iso: string) => void;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal compare-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="compare-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="section-line">
          <h2 id="compare-title">Country comparison</h2>
          <button
            className="icon-button"
            aria-label="Close comparison"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <div className="compare-grid">
          {codes.map((iso) => {
            const c = countries.find((c) => c.iso3 === iso),
              r = rows.find((r) => r.iso3 === iso);
            return (
              <article key={iso}>
                <span className="mono muted">{iso}</span>
                <h2>{c?.name ?? iso}</h2>
                <p>{c?.region}</p>
                {r ? (
                  <>
                    <div
                      className="compare-score"
                      style={{ color: scoreColor(r.score) }}
                    >
                      {r.score.toFixed(1)}
                      <small>/100</small>
                    </div>
                    {(["exposure", "vulnerability", "protection"] as const).map(
                      (k) => (
                        <div className="evidence-row" key={k}>
                          <span>{k}</span>
                          <b>{r[k]}</b>
                        </div>
                      ),
                    )}
                    <HistoryChart points={r.trend} />
                  </>
                ) : (
                  <Empty>No score in the selected year.</Empty>
                )}
                <button
                  className="text-button"
                  onClick={() => {
                    onCountry(iso);
                    onClose();
                  }}
                >
                  Explore country
                  <ArrowUpRight size={14} />
                </button>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
