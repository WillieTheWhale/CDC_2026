// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import meta from "../../contracts/fixtures/meta.json";
import countries from "../../contracts/fixtures/countries.json";
import observed from "../../contracts/fixtures/routes_observed.json";
import predicted from "../../contracts/fixtures/routes_predicted.json";
import risk from "../../contracts/fixtures/risk.json";
import countryCOL from "../../contracts/fixtures/country_COL.json";
import prices from "../../contracts/fixtures/prices.json";
import livewire from "../../contracts/fixtures/livewire.json";
import experiment from "../../contracts/fixtures/afghan_ban.json";
import metrics from "../../contracts/fixtures/metrics.json";
import simulation from "../../contracts/fixtures/simulate.json";
import type {
  Country,
  Drug,
  Edge,
  Envelope,
  LiveEvent,
  Mode,
  Price,
  Risk,
  Routes,
  SimulationRequest,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(
  /\/$/,
  "",
);
export const DEMO = !API_BASE;
export const SNAPSHOT_YEAR = risk.data.year;
export const PROFILE_YEAR = countryCOL.data.year;
export const SNAPSHOT_TIME = meta.meta.generated_at;
export type CountryDetail = typeof countryCOL.data;
export type Experiment = typeof experiment.data;
export type Metrics = typeof metrics.data;
export type Simulation = typeof simulation.data;
export type Catalog = typeof meta.data;

async function request<T>(
  path: string,
  fallback: () => T | Promise<T>,
  init?: RequestInit,
): Promise<T> {
  if (!API_BASE) return structuredClone(await fallback());
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      detail?.error?.message ||
        detail?.detail ||
        `Data service returned ${res.status}`,
    );
  }
  return res.json() as Promise<T>;
}
// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// Each year is fetched once and kept, so timeline playback swaps lines and
// colors from memory instead of reloading. Failed loads are not cached.
const loaded = new Map<string, Promise<unknown>>();
function once<T>(key: string, load: () => Promise<T>): Promise<T> {
  let hit = loaded.get(key) as Promise<T> | undefined;
  if (!hit) {
    hit = load();
    loaded.set(key, hit);
    hit.catch(() => loaded.delete(key));
  }
  return hit;
}
async function snapshotFile<T>(path: string): Promise<T> {
  return once(path, async () => {
    const res = await fetch(path);
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as T;
  });
}
function filterRoutes(
  envelope: Envelope<Routes>,
  year: number,
  drug?: Drug,
  minConfidence = 0,
): Envelope<Routes> {
  return {
    ...envelope,
    data: {
      ...envelope.data,
      year,
      drug: drug ?? null,
      edges:
        envelope.data.year === year
          ? envelope.data.edges.filter(
              (e) =>
                (!drug || e.drug === drug) && e.confidence >= minConfidence,
            )
          : [],
    },
  };
}
export function fixtureRoutes(
  year: number,
  mode: Mode,
  drug?: Drug,
  minConfidence = 0,
): Envelope<Routes> {
  const fixture = (
    mode === "predicted" ? predicted : observed
  ) as Envelope<Routes>;
  return filterRoutes(fixture, year, drug, minConfidence);
}
// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// Full per-year route exports (`uv run trace export --route-snapshots`) so the
// no-API atlas draws every modeled corridor for every year, not only the
// trimmed contract fixture. Falls back to the fixture if a file is missing.
export async function snapshotRoutes(
  year: number,
  mode: Mode,
  drug?: Drug,
  minConfidence = 0,
): Promise<Envelope<Routes>> {
  try {
    const full = await snapshotFile<Envelope<Routes>>(
      `/data/routes/${mode}-${year}.json`,
    );
    return filterRoutes(full, year, drug, minConfidence);
  } catch {
    return fixtureRoutes(year, mode, drug, minConfidence);
  }
}
export function fixtureRisk(year: number): Envelope<Risk> {
  return {
    ...risk,
    data: {
      ...risk.data,
      year,
      rows: year === risk.data.year ? risk.data.rows : [],
    },
  };
}
// Full per-year risk (every country) so the map's exposure shading and the
// risk board work for 2008-2025 without the API; falls back to the fixture.
export async function snapshotRisk(year: number): Promise<Envelope<Risk>> {
  try {
    return await snapshotFile<Envelope<Risk>>(`/data/risk/${year}.json`);
  } catch {
    return fixtureRisk(year);
  }
}
// Estimated local flows are precomputed files in both modes (map-only layer).
export async function estimatedFlows(year: number, mode: Mode) {
  const { parseEstimated } = await import("./estimated-flows");
  return parseEstimated(
    await snapshotFile<Parameters<typeof parseEstimated>[0]>(
      `/data/estimated/${mode}-${year}.json`,
    ),
  );
}
export const api = {
  meta: () => request<Envelope<Catalog>>("/api/meta", () => meta),
  countries: () =>
    request<Envelope<Country[]>>("/api/countries", () => countries),
  routes: (year: number, mode: Mode, drug?: Drug, minConfidence = 0) => {
    const q = new URLSearchParams({
      year: String(year),
      mode,
      min_confidence: String(minConfidence),
    });
    if (drug) q.set("drug", drug);
    const path = `/api/routes?${q}`;
    return API_BASE
      ? once(path, () => request<Envelope<Routes>>(path, () => fixtureRoutes(year, mode)))
      : snapshotRoutes(year, mode, drug, minConfidence);
  },
  risk: (year: number) =>
    API_BASE
      ? once(`/api/risk?year=${year}`, () =>
          request<Envelope<Risk>>(`/api/risk?year=${year}`, () => fixtureRisk(year)),
        )
      : snapshotRisk(year),
  country: (iso3: string, year: number) =>
    request<Envelope<CountryDetail> | null>(
      `/api/country/${encodeURIComponent(iso3)}?year=${year}`,
      () =>
        iso3 === "COL" && year === countryCOL.data.year ? countryCOL : null,
    ),
  prices: () =>
    request<Envelope<{ series: Price[] }>>("/api/prices", () => prices),
  livewire: () =>
    request<Envelope<{ classifier: string; events: LiveEvent[] }>>(
      "/api/livewire",
      () => livewire,
    ),
  experiment: () =>
    request<Envelope<Experiment>>(
      "/api/experiments/afghan-ban",
      () => experiment,
    ),
  metrics: () => request<Envelope<Metrics>>("/api/metrics", () => metrics),
  command: (text: string) =>
    request<
      Envelope<{
        intent: string;
        params: Record<string, unknown>;
        message: string;
      }>
    >(
      "/api/command",
      () => ({
        meta: meta.meta,
        data: {
          intent: "unknown",
          params: {},
          message:
            "Try a country code, COCAINE ROUTES, RISK TOP 20, or YEAR 2024.",
        },
      }),
      { method: "POST", body: JSON.stringify({ text }) },
    ),
  simulate: (input: SimulationRequest) =>
    request<Envelope<Simulation>>(
      "/api/simulate",
      () => {
        if (
          /^(?:colombia cuts coca 50%|COL CULTIVATION -50%)[.!]?$/i.test(
            input.scenario?.trim() ?? "",
          )
        )
          return simulation;
        throw new Error(
          "The demo includes Colombia’s 50% cultivation scenario. Connect the model API to run a custom scenario; the Afghanistan study is available in Experiments.",
        );
      },
      { method: "POST", body: JSON.stringify(input) },
    ),
};

export function subscribeLivewire(
  onEvent: (event: LiveEvent) => void,
  onState: (state: string) => void,
): () => void {
  let cancelled = false;
  if (DEMO) {
    const demoEvents: LiveEvent[] = livewire.data.events;
    if (demoEvents.length === 0) {
      onState("No verified live events");
      return () => {};
    }
    let i = 0;
    onState("Demo replay");
    const timer = setInterval(() => {
      const event = demoEvents[i++ % demoEvents.length];
      if (event.confidence >= 0.6) onEvent(event);
    }, 18000);
    return () => clearInterval(timer);
  }
  let ws: WebSocket | undefined;
  let retry: ReturnType<typeof setTimeout> | undefined;
  const connect = () => {
    onState("Connecting");
    ws = new WebSocket(`${API_BASE.replace(/^http/, "ws")}/ws/livewire`);
    ws.onopen = () => onState("Connected");
    ws.onmessage = ({ data }) => {
      try {
        const frame = JSON.parse(data);
        const events =
          frame.type === "hello"
            ? frame.data.backlog
            : ["event", "anomaly"].includes(frame.type)
              ? [frame.data]
              : [];
        for (const event of events ?? [])
          if (event.confidence >= 0.6) onEvent(event);
      } catch {
        /* Keep malformed frames from interrupting the feed. */
      }
    };
    ws.onclose = () => {
      if (!cancelled) {
        onState("Reconnecting");
        retry = setTimeout(connect, 5000);
      }
    };
    ws.onerror = () => ws?.close();
  };
  connect();
  return () => {
    cancelled = true;
    clearTimeout(retry);
    ws?.close();
  };
}
export const drugColor: Record<string, string> = {
  cocaine: "#ed482d",
  heroin: "#8047c9",
  meth: "#2864cf",
  cannabis: "#18775c",
};
export const drugLabel: Record<string, string> = {
  cocaine: "Cocaine",
  heroin: "Heroin",
  meth: "Methamphetamine",
  cannabis: "Cannabis",
};
export const scoreColor = (score: number) =>
  score >= 75
    ? "#b32f58"
    : score >= 60
      ? "#df542f"
      : score >= 40
        ? "#d9973f"
        : "#6e8272";
export const formatNumber = (v: number | null | undefined, digits = 1) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        maximumFractionDigits: digits,
        notation: Math.abs(v) > 99999 ? "compact" : "standard",
      }).format(v);
export function countryEdges(edges: Edge[], iso3: string) {
  return edges.filter((e) => e.from === iso3 || e.to === iso3);
}
