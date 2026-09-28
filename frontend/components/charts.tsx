// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
export function Sparkline({
  points,
  color = "#ed482d",
  dataKey = "score",
}: {
  points: Record<string, number | null>[];
  color?: string;
  dataKey?: string;
}) {
  return (
    <div className="sparkline" aria-label="Historical trend">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <Line
            type="linear"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={1.6}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
export function HistoryChart({
  points,
  dataKey = "score",
  color = "#ed482d",
  unit = "",
  height = 160,
}: {
  points: Record<string, number | null>[];
  dataKey?: string;
  color?: string;
  unit?: string;
  height?: number;
}) {
  return (
    <div className="history-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={points}
          margin={{ left: -22, right: 12, top: 12, bottom: 0 }}
        >
          <CartesianGrid vertical={false} stroke="#dce3eb" />
          <XAxis
            dataKey="year"
            tick={{ fontSize: 10, fill: "#667689" }}
            axisLine={false}
            tickLine={false}
            minTickGap={20}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#667689" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : v)}
          />
          <Tooltip
            contentStyle={{
              background: "#ffffff",
              border: "1px solid #b9c6d6",
              borderRadius: 0,
              fontSize: 12,
            }}
            formatter={(v) => [`${Number(v).toLocaleString()}${unit}`, ""]}
          />
          <Line
            type="linear"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            dot={{ r: 1.6, fill: color, strokeWidth: 0 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
