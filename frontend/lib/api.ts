// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
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
import { fixtureRouteEvidence, type RouteEvidence } from "./route-evidence";

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
    throw Object.assign(
      new Error(
        detail?.error?.message ||
          detail?.detail ||
          `Data service returned ${res.status}`,
      ),
      { status: res.status },
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
// Estimated local flows (map-only layer). With the API connected, ask
// /api/estimated-flows for a layer built from the live routes; until the
// backend serves it (404) or if it fails, use the precomputed snapshot file.
// The endpoint is probed once; a 404 switches straight to the snapshots.
let estimatedEndpoint: "unknown" | "live" | "missing" = "unknown";
export async function estimatedFlows(year: number, mode: Mode) {
  const { parseEstimated } = await import("./estimated-flows");
  type File = Parameters<typeof parseEstimated>[0];
  const snapshot = () => snapshotFile<File>(`/data/estimated/${mode}-${year}.json`);
  if (!API_BASE || estimatedEndpoint === "missing") return parseEstimated(await snapshot());
  const path = `/api/estimated-flows?year=${year}&mode=${mode}`;
  const file = await once(path, async () => {
    try {
      const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(15000) });
      if (res.status === 404) estimatedEndpoint = "missing";
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as File;
      if (body.data?.year !== year || body.data?.mode !== mode) throw new Error("mismatched layer");
      estimatedEndpoint = "live";
      return { ...body, live: true };
    } catch {
      return { ...(await snapshot()), live: false };
    }
  });
  return parseEstimated(file);
}
// Route evidence: the whole cited set (a few hundred records) is paged in
// once from /api/route-evidence and filtered on the client by drug, pair
// type and view. Without the API, the curated direct pairs are the fixture.
export async function routeEvidence(): Promise<RouteEvidence[]> {
  if (!API_BASE) return fixtureRouteEvidence;
  return once("/api/route-evidence", async () => {
    const out: RouteEvidence[] = [];
    let cursor: string | null = null;
    for (let page = 0; page < 20; page++) {
      const q = new URLSearchParams({ limit: "250" });
      if (cursor) q.set("cursor", cursor);
      const body: Envelope<RouteEvidence[]> & { meta: { next_cursor?: string | null } } =
        await request(`/api/route-evidence?${q}`, () => {
          throw new Error("unreachable");
        });
      out.push(...body.data);
      cursor = body.meta.next_cursor ?? null;
      if (!cursor) break;
    }
    return out;
  });
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
  // A 404 (unknown country, or a year outside the 2008+ profile range such
  // as 2006-2007 route years) means "no profile", not a failure.
  country: (iso3: string, year: number) =>
    request<Envelope<CountryDetail> | null>(
      `/api/country/${encodeURIComponent(iso3)}?year=${year}`,
      () =>
        iso3 === "COL" && year === countryCOL.data.year ? countryCOL : null,
    ).catch((e: Error & { status?: number }) => {
      if (e.status === 404) return null;
      throw e;
    }),
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
  cannabis: "#0c5a43",
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
