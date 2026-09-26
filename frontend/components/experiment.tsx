// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import { useMemo, useState } from "react";
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
import type { Experiment, Metrics } from "@/lib/api";

function PValue({ value }: { value: number }) {
  if (value >= 0.001) return <>{value.toFixed(3)}</>;
  if (value === 0)
    return (
      <>
        &lt; 10<sup>−6</sup>
      </>
    );
  const [coefficient, exponent] = value.toExponential(1).split("e");
  return (
    <>
      {coefficient} × 10
      <sup>{Number(exponent).toString().replace("-", "−")}</sup>
    </>
  );
}
function Cultivation({ experiment }: { experiment: Experiment }) {
  const series = experiment.series.filter((s) => s.id.endsWith("_cultivation"));
  const data = useMemo(() => {
    const rows = new Map<number, Record<string, number | null>>();
    for (const s of series)
      for (const point of s.points) {
        const row = rows.get(point.year) ?? { year: point.year };
        row[s.id] = point.value;
        rows.set(point.year, row);
      }
    return [...rows.values()].sort((a, b) => Number(a.year) - Number(b.year));
  }, [experiment]);
  return (
    <section className="experiment-section cultivation-section">
      <header>
        <h2>Cultivation</h2>
        <span>hectares</span>
      </header>
      <div className="chart-key">
        <span className="afg-key">Afghanistan</span>
        <span className="mmr-key">Myanmar</span>
      </div>
      <div
        className="cultivation-chart"
        role="img"
        aria-label="Afghanistan and Myanmar opium cultivation by year, on a shared hectares scale"
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 20, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid vertical={false} stroke="#dce3eb" />
            <XAxis
              type="number"
              dataKey="year"
              domain={["dataMin", "dataMax"]}
              tickCount={6}
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: "#61738a" }}
            />
            <YAxis
              width={45}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: "#61738a" }}
              tickFormatter={(v) =>
                v === 0 ? "0" : `${Math.round(v / 1000)}k`
              }
            />
            <Tooltip
              contentStyle={{
                background: "#fff",
                border: "1px solid #b9c6d6",
                borderRadius: 0,
                fontSize: 12,
              }}
              formatter={(v, name) => [
                Number(v).toLocaleString(),
                String(name).toUpperCase().includes("AFG")
                  ? "Afghanistan"
                  : "Myanmar",
              ]}
            />
            <ReferenceLine
              x={2022}
              stroke="#8797aa"
              strokeDasharray="3 3"
              label={{
                value: "2022 ban",
                position: "insideTopRight",
                fill: "#4d6077",
                fontSize: 11,
              }}
            />
            {series.map((s) => (
              <Line
                key={s.id}
                name={s.id}
                dataKey={s.id}
                type="linear"
                stroke={
                  s.id.toUpperCase().startsWith("AFG") ? "#ed482d" : "#8047c9"
                }
                strokeWidth={1.8}
                dot={{
                  r: 2,
                  fill: s.id.toUpperCase().startsWith("AFG")
                    ? "#ed482d"
                    : "#8047c9",
                  strokeWidth: 0,
                }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="source-note">
        UNODC · {data[0]?.year}–{data.at(-1)?.year}
      </p>
    </section>
  );
}
function CorridorPlot({ experiment: e }: { experiment: Experiment }) {
  const [origin, setOrigin] = useState("all");
  const edges = e.edges.filter(
    (edge) => origin === "all" || edge.from === origin,
  );
  const max = Math.max(
    1,
    ...e.edges.flatMap((edge) => [edge.before, edge.predicted, edge.actual]),
  );
  const x = (value: number) => 12 + (value / max) * 196;
  return (
    <section className="experiment-section corridor-section">
      <header>
        <h2>Corridor volumes</h2>
        <select
          aria-label="Filter experiment origin"
          value={origin}
          onChange={(event) => setOrigin(event.target.value)}
        >
          <option value="all">All origins</option>
          <option value="AFG">Afghanistan</option>
          <option value="MMR">Myanmar</option>
        </select>
      </header>
      <div className="plot-key">
        <span>
          <i className="before-marker" />
          2022
        </span>
        <span>
          <i className="predicted-marker" />
          2023 forecast
        </span>
        <span>
          <i className="actual-marker" />
          2023 observed
        </span>
      </div>
      <div className="corridor-table-wrap">
        <table className="corridor-table">
          <thead>
            <tr>
              <th>Route</th>
              <th className="volume-axis">
                <span>0</span>
                <span>{(max / 2).toFixed(1)}</span>
                <span>{max.toFixed(1)}</span>
              </th>
              <th>2022</th>
              <th>Forecast</th>
              <th>2023</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((edge) => (
              <tr key={`${edge.from}-${edge.to}`}>
                <th scope="row">
                  {edge.from}
                  <span> → </span>
                  {edge.to}
                </th>
                <td className="corridor-plot">
                  <svg
                    viewBox="0 0 220 30"
                    role="img"
                    aria-label={`Before ${edge.before.toFixed(2)}, forecast ${edge.predicted.toFixed(2)}, observed ${edge.actual.toFixed(2)}`}
                  >
                    {[0, 0.25, 0.5, 0.75, 1].map((t) => (
                      <path
                        key={t}
                        d={`M${12 + t * 196} 0V30`}
                        stroke="#e5eaf1"
                        strokeWidth=".6"
                      />
                    ))}
                    <path
                      d={`M${x(edge.before)} 15H${x(edge.actual)}`}
                      stroke="#8495aa"
                      strokeWidth="1"
                    />
                    <rect
                      x={x(edge.before) - 2.5}
                      y="12.5"
                      width="5"
                      height="5"
                      fill="#fff"
                      stroke="#64758c"
                      strokeWidth="1"
                    />
                    <path
                      d={`M${x(edge.predicted)} 10L${x(edge.predicted) + 4} 15L${x(edge.predicted)} 20L${x(edge.predicted) - 4} 15Z`}
                      fill="#fff"
                      stroke="#ed482d"
                      strokeWidth="1.4"
                    />
                    <path
                      d={`M${x(edge.actual) - 3} 15H${x(edge.actual) + 3}M${x(edge.actual)} 12V18`}
                      stroke="#172b40"
                      strokeWidth="1.8"
                    />
                  </svg>
                </td>
                <td>{edge.before.toFixed(2)}</td>
                <td className="forecast-number">{edge.predicted.toFixed(2)}</td>
                <td>{edge.actual.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer>
        <span>Normalized volume</span>
        <span>
          {Math.round(e.metrics.direction_accuracy * e.metrics.n_edges)}/
          {e.metrics.n_edges} directions correct
        </span>
      </footer>
    </section>
  );
}
export function ExperimentView({
  experiment: e,
  metrics: m,
}: {
  experiment: Experiment;
  metrics: Metrics;
}) {
  const spillover = m.spillover;
  const outcomes = [
    {
      name: "Combined",
      n: spillover.n,
      base: spillover.auc_vulnerability_only,
      withExposure: spillover.auc_with_exposure,
      odds: Math.exp(spillover.exposure_coef * 10),
      p: spillover.lr_p_value,
    },
    ...Object.entries(spillover.by_outcome).map(([name, value]) => ({
      name: name === "hiv" ? "HIV (15–49)" : "Homicide",
      n: value.n,
      base: value.auc_vulnerability_only,
      withExposure: value.auc_with_exposure,
      odds: value.exposure_odds_ratio_per_10pts,
      p: value.lr_p_value,
    })),
  ];
  return (
    <div className="experiment-sheet">
      <div className="view-heading">
        <h1>Afghanistan opium ban</h1>
        <div className="experiment-meta">
          <span>
            Shock <b>−{Math.round((1 - e.shock.value) * 100)}%</b>
          </span>
          <span>
            Train <b>≤{e.train_through}</b>
          </span>
          <span>
            Forecast <b>2023</b>
          </span>
        </div>
      </div>
      <div className="experiment-comparison">
        <div>
          <Cultivation experiment={e} />
          <section className="experiment-section share-section">
            <header>
              <h2>Southeast Asian share</h2>
              <span>heroin volume</span>
            </header>
            <dl>
              <div>
                <dt>2022</dt>
                <dd>
                  {(m.afghan_ban.sea_share_before * 100).toFixed(1)}
                  <small>%</small>
                </dd>
              </div>
              <div>
                <dt>2023 forecast</dt>
                <dd>
                  {(m.afghan_ban.sea_share_predicted * 100).toFixed(1)}
                  <small>%</small>
                </dd>
              </div>
              <div>
                <dt>2023 observed</dt>
                <dd>
                  {(m.afghan_ban.sea_share_actual * 100).toFixed(1)}
                  <small>%</small>
                </dd>
              </div>
            </dl>
          </section>
        </div>
        <CorridorPlot experiment={e} />
      </div>
      <section className="experiment-section model-section">
        <header>
          <h2>Backtest</h2>
          <span>
            Train ≤{m.backtest.train_through} · Test {m.backtest.test_years[0]}–
            {m.backtest.test_years.at(-1)}
          </span>
        </header>
        <div className="table-scroll">
          <table className="research-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>AUC</th>
                <th>Spearman ρ</th>
                <th>Precision @20</th>
                <th>n</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["LightGBM hurdle", m.backtest.hurdle],
                ["Persistence", m.backtest.persistence_baseline],
                ["Gravity", m.backtest.gravity_baseline],
              ].map(([label, metric]) => {
                const v = metric as Metrics["backtest"]["hurdle"];
                return (
                  <tr key={String(label)}>
                    <th scope="row">{String(label)}</th>
                    <td>{v.auc.toFixed(3)}</td>
                    <td>{v.spearman.toFixed(3)}</td>
                    <td>{(v.precision_at_20 * 100).toFixed(1)}%</td>
                    <td>{v.n.toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="experiment-section spillover-section">
        <header>
          <h2>Spillover hypothesis</h2>
          <strong className="hypothesis-status">
            {spillover.supported ? "Supported" : "Not supported"}
          </strong>
        </header>
        <p className="research-question">
          Does exposure predict harm within three years, beyond baseline
          vulnerability?
        </p>
        <div className="table-scroll">
          <table className="research-table">
            <thead>
              <tr>
                <th>Outcome</th>
                <th>n</th>
                <th>AUC baseline</th>
                <th>AUC + exposure</th>
                <th>Odds ratio / 10pt</th>
                <th>LR p-value</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((row) => (
                <tr key={row.name}>
                  <th scope="row">{row.name}</th>
                  <td>{row.n.toLocaleString()}</td>
                  <td>{row.base.toFixed(3)}</td>
                  <td>{row.withExposure.toFixed(3)}</td>
                  <td>{row.odds.toFixed(3)}</td>
                  <td>
                    <PValue value={row.p} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <details className="research-method">
          <summary>Method & source limitations</summary>
          <p>{spillover.statement}</p>
          <p>
            {spillover.outcome}. Country-level estimates; seizure records
            measure detection, not total trade.
          </p>
        </details>
      </section>
    </div>
  );
}
