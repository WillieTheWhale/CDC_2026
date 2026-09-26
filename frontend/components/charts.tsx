// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import {
  Area,
  AreaChart,
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
  color = "#bf5c3c",
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
            type="monotone"
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
  color = "#be4e31",
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
        <AreaChart
          data={points}
          margin={{ left: -22, right: 12, top: 12, bottom: 0 }}
        >
          <CartesianGrid
            vertical={false}
            stroke="#e5e2d7"
            strokeDasharray="2 4"
          />
          <XAxis
            dataKey="year"
            tick={{ fontSize: 10, fill: "#858778" }}
            axisLine={false}
            tickLine={false}
            minTickGap={20}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#858778" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : v)}
          />
          <Tooltip
            contentStyle={{
              background: "#fffdf6",
              border: "1px solid #deded1",
              borderRadius: 4,
              fontSize: 12,
            }}
            formatter={(v) => [`${Number(v).toLocaleString()}${unit}`, ""]}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            fill={color}
            fillOpacity={0.09}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
