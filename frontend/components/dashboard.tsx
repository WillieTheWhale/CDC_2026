// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// AI-assisted: full screen map mode written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { Command } from "cmdk";
import { Dock } from "./dock";
import { SignalBeacon } from "./figma-motion";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Command as CommandIcon,
  Database,
  FlaskConical,
  Globe2,
  GripHorizontal,
  Layers3,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  Search,
  X,
} from "lucide-react";
import {
  api,
  API_BASE,
  Catalog,
  DEMO,
  SNAPSHOT_YEAR,
  drugColor,
  drugLabel,
  Experiment,
  scoreColor,
  Simulation,
  subscribeLivewire,
} from "@/lib/api";
import { parseCommand } from "@/lib/commands";
import type {
  CommandAction,
  Country,
  Drug,
  Edge,
  LiveEvent,
  Mode,
  RiskRow,
  View,
} from "@/lib/types";
import {
  Compare,
  CountryInspector,
  Empty,
  NewsList,
  RiskTable,
  RouteInspector,
  ScenarioPanel,
  ScenarioRiskList,
  Sources,
} from "./panels";
import { Sparkline } from "./charts";
import { EvidenceHealth } from "./evidence-health";
import { EvidenceMarkets } from "./evidence-markets";
import { EvidenceResearch } from "./experiment";
import { loadObservedOverview, type ObservedOverview } from "@/lib/observed-data";
const AtlasMap = dynamic(() => import("./atlas-map"), {
  ssr: false,
  loading: () => <div className="map-loading">Loading map</div>,
});
const PeopleAtlas = dynamic(() => import("./people-atlas").then((module) => module.PeopleAtlas), {
  ssr: false,
  loading: () => <div className="map-loading">Loading people atlas</div>,
});
const NAV: { id: View; label: string }[] = [
  { id: "atlas", label: "Atlas" },
  { id: "risk", label: "Risk board" },
  { id: "health", label: "Health evidence" },
  { id: "people", label: "People" },
  { id: "livewire", label: "Live wire" },
  { id: "scenarios", label: "Scenarios" },
  { id: "markets", label: "Markets" },
  { id: "experiment", label: "Experiment" },
];
const suggestions = [
  "COCAINE ROUTES",
  "HEROIN ROUTES",
  "COL <GO>",
  "RISK TOP 20",
  "COMPARE COL PER",
  "YEAR 2024",
  "PREDICT ON",
  "SHOCK Colombia cuts coca 50%",
];
export default function Dashboard() {
  const [view, setView] = useState<View>("atlas"),
    [catalog, setCatalog] = useState<Catalog | null>(null),
    [countries, setCountries] = useState<Country[]>([]),
    [edges, setEdges] = useState<Edge[]>([]),
    [risk, setRisk] = useState<RiskRow[]>([]),
    [events, setEvents] = useState<LiveEvent[]>([]),
    [experiment, setExperiment] = useState<Experiment | null>(null);
  const [observedOverview, setObservedOverview] = useState<ObservedOverview | null>(null);
  const [observedError, setObservedError] = useState("");
  const [year, setYear] = useState(2024),
    [mode, setMode] = useState<Mode>("observed"),
    [drug, setDrug] = useState<Drug | "all">("all"),
    [selected, setSelected] = useState<string | null>(null),
    [route, setRoute] = useState<Edge | null>(null),
    [event, setEvent] = useState<LiveEvent | null>(null);
  const [commandOpen, setCommandOpen] = useState(false),
    [command, setCommand] = useState(""),
    [sourcesOpen, setSourcesOpen] = useState(false),
    [compare, setCompare] = useState<string[]>([]),
    [toast, setToast] = useState(""),
    [loadError, setLoadError] = useState(""),
    [loading, setLoading] = useState(true),
    [routeLoading, setRouteLoading] = useState(false),
    [feedState, setFeedState] = useState(DEMO ? "Demo replay" : "Connecting");
  const [showDots, setShowDots] = useState(true),
    [showRoutes, setShowRoutes] = useState(true),
    [showEvidence, setShowEvidence] = useState(true),
    [layersOpen, setLayersOpen] = useState(false),
    [minConfidence, setMinConfidence] = useState(0),
    [resetKey, setResetKey] = useState(0),
    [playing, setPlaying] = useState(false),
    [scenario, setScenario] = useState(""),
    [simulation, setSimulation] = useState<Simulation | null>(null),
    [riskLimit, setRiskLimit] = useState(250),
    [clock, setClock] = useState("--:--:--"),
    [dataTime, setDataTime] = useState("");
  // Full screen map: chrome is hidden and panels become pull-up overlays.
  const [mapFull, setMapFull] = useState(false),
    [sheetOpen, setSheetOpen] = useState(false),
    [drawerOpen, setDrawerOpen] = useState(false);
  const nativeFullscreen = useRef(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const notify = useCallback((message: string) => {
    clearTimeout(toastTimer.current);
    setToast(message);
    toastTimer.current = setTimeout(() => setToast(""), 6500);
  }, []);
  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [m, c] = await Promise.all([api.meta(), api.countries()]);
      setCatalog(m.data);
      setDataTime(m.meta.generated_at);
      setCountries(c.data);
      const startYear = DEMO ? SNAPSHOT_YEAR : m.data.latest_observed_year;
      setYear(startYear);
      setMode(
        m.data.predicted_years.includes(startYear) ? "predicted" : "observed",
      );
      const results = await Promise.allSettled([
        api.livewire(),
        api.experiment(),
      ] as const);
      const [n, e] = results;
      if (n.status === "fulfilled")
        setEvents(n.value.data.events.filter((e) => e.confidence >= 0.6));
      if (e.status === "fulfilled") setExperiment(e.value.data);
      if (results.some((r) => r.status === "rejected"))
        notify(
          "Some data services are unavailable. The atlas remains available.",
        );
    } catch (e) {
      setLoadError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [notify]);
  useEffect(() => {
    void load();
    return () => clearTimeout(toastTimer.current);
  }, [load]);
  useEffect(() => {
    if (!["health", "markets", "experiment", "scenarios"].includes(view) && !sourcesOpen && !selected) return;
    let active = true;
    loadObservedOverview()
      .then((overview) => { if (active) { setObservedOverview(overview); setObservedError(""); } })
      .catch((cause) => { if (active) setObservedError((cause as Error).message); });
    return () => { active = false; };
  }, [view, sourcesOpen, selected]);
  useEffect(() => {
    if (!catalog) return;
    let active = true;
    setRouteLoading(true);
    setEdges([]);
    setRisk([]);
    setRoute(null);
    Promise.allSettled([
      api.routes(year, mode, drug === "all" ? undefined : drug, minConfidence),
      api.risk(year),
    ]).then(([routes, scores]) => {
      if (!active) return;
      if (routes.status === "fulfilled") setEdges(routes.value.data.edges);
      else notify(routes.reason.message);
      if (scores.status === "fulfilled") setRisk(scores.value.data.rows);
      else notify(`Risk scores are unavailable for ${year}.`);
      setRouteLoading(false);
    });
    return () => {
      active = false;
    };
  }, [catalog, year, mode, drug, minConfidence, notify]);
  useEffect(
    () =>
      subscribeLivewire(
        (e) =>
          setEvents((list) =>
            [e, ...list.filter((x) => x.id !== e.id)].slice(0, 100),
          ),
        setFeedState,
      ),
    [],
  );
  useEffect(() => {
    const tick = () =>
      setClock(new Date().toLocaleTimeString("en-GB", { timeZone: "UTC" }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen((o) => !o);
      }
      if (e.key === "Escape") {
        setCommandOpen(false);
        setSourcesOpen(false);
        setCompare([]);
        setLayersOpen(false);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  useEffect(() => {
    if (!commandOpen && !sourcesOpen && !compare.length) return;
    const previous = document.activeElement as HTMLElement | null;
    const root = document.querySelector<HTMLElement>(".modal-backdrop");
    if (!root) return;
    const focusable = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          'button:not([disabled]),a[href],input,textarea,select,[tabindex="0"]',
        ),
      );
    focusable()[0]?.focus();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusable();
      const first = items[0],
        last = items.at(-1);
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    root.addEventListener("keydown", trap);
    return () => {
      root.removeEventListener("keydown", trap);
      document.body.style.overflow = oldOverflow;
      previous?.focus();
    };
  }, [commandOpen, sourcesOpen, compare.length]);
  useEffect(() => {
    document
      .querySelector(".inspector")
      ?.scrollTo({ top: 0, behavior: "instant" });
  }, [selected, route?.id, event?.id]);
  useEffect(() => {
    if ((selected || route || event) && window.innerWidth <= 760)
      document.querySelector(".inspector")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "start",
      });
  }, [selected, route, event]);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [view]);
  const years = useMemo(
    () =>
      catalog
        ? [...catalog.observed_years, ...catalog.predicted_years].sort(
            (a, b) => a - b,
          )
        : [2024, 2025],
    [catalog],
  );
  const changeYear = (y: number) => {
    setYear(y);
    setMode(catalog?.predicted_years.includes(y) ? "predicted" : "observed");
    setSimulation(null);
  };
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      setYear((y) => {
        const next = years[years.indexOf(y) + 1];
        if (next === undefined) {
          setPlaying(false);
          return y;
        }
        setMode(
          catalog?.predicted_years.includes(next) ? "predicted" : "observed",
        );
        return next;
      });
    }, 1400);
    return () => clearInterval(timer);
  }, [playing, years, catalog]);
  const switchMode = (m: Mode) => {
    setMode(m);
    setYear(
      m === "predicted"
        ? (catalog?.predicted_years[0] ?? 2025)
        : (catalog?.latest_observed_year ?? 2024),
    );
    setPlaying(false);
    setSimulation(null);
  };
  const enterMapFull = useCallback(() => {
    setView("atlas");
    setMapFull(true);
    setSheetOpen(false);
    setLayersOpen(false);
    // Browser full screen is a bonus; the layout works without it (iframes,
    // Safari on iPhone), so a refused request is not an error.
    const root = document.documentElement;
    if (!document.fullscreenElement && root.requestFullscreen)
      root
        .requestFullscreen({ navigationUI: "hide" })
        .then(() => (nativeFullscreen.current = true))
        .catch(() => {});
  }, []);
  const exitMapFull = useCallback(() => {
    setMapFull(false);
    setSheetOpen(false);
    setDrawerOpen(false);
    if (nativeFullscreen.current && document.fullscreenElement)
      document.exitFullscreen().catch(() => {});
    nativeFullscreen.current = false;
  }, []);
  useEffect(() => {
    // Leaving browser full screen (Esc, F11) also leaves the map mode.
    const change = () => {
      if (!document.fullscreenElement && nativeFullscreen.current) {
        nativeFullscreen.current = false;
        setMapFull(false);
        setSheetOpen(false);
        setDrawerOpen(false);
      }
    };
    document.addEventListener("fullscreenchange", change);
    return () => document.removeEventListener("fullscreenchange", change);
  }, []);
  useEffect(() => {
    if (mapFull && view !== "atlas") exitMapFull();
  }, [mapFull, view, exitMapFull]);
  useEffect(() => {
    if (mapFull && (selected || route || event)) setDrawerOpen(true);
  }, [mapFull, selected, route, event]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        commandOpen ||
        sourcesOpen ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey ||
        target?.closest("input, textarea, select, [contenteditable='true']")
      )
        return;
      if (e.key.toLowerCase() === "f" && view === "atlas") {
        e.preventDefault();
        if (mapFull) exitMapFull();
        else enterMapFull();
      } else if (mapFull && e.key === "Escape" && !layersOpen) {
        // Peel one layer per press: sheet, then drawer, then the mode.
        if (sheetOpen) setSheetOpen(false);
        else if (drawerOpen) setDrawerOpen(false);
        else exitMapFull();
      } else if (mapFull && e.key.toLowerCase() === "p") {
        setSheetOpen((open) => !open);
      } else if (mapFull && e.key.toLowerCase() === "d") {
        setDrawerOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [
    commandOpen,
    sourcesOpen,
    layersOpen,
    view,
    mapFull,
    sheetOpen,
    drawerOpen,
    enterMapFull,
    exitMapFull,
  ]);
  const returnToMap = () => {
    if (window.innerWidth <= 760)
      window.scrollTo({
        top: 0,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
  };
  const openCountry = (iso: string) => {
    setView("atlas");
    setSelected(iso);
    setRoute(null);
    setEvent(null);
  };
  const openEvent = (e: LiveEvent) => {
    setEvent(e);
    setSelected(null);
    setRoute(null);
    setView("atlas");
  };
  const act = async (action: CommandAction) => {
    const p = action.params;
    switch (action.intent) {
      case "routes":
        setView("atlas");
        setDrug((p.drug as Drug) ?? "all");
        break;
      case "country":
        openCountry(String(p.iso3));
        break;
      case "risk":
        setRiskLimit(Number(p.limit ?? 250));
        setView("risk");
        break;
      case "news":
        setDrug((p.drug as Drug) ?? "all");
        setView("livewire");
        break;
      case "year":
        if (years.includes(Number(p.year))) changeYear(Number(p.year));
        else notify(`Available years: ${years[0]}–${years.at(-1)}.`);
        break;
      case "predict":
        switchMode(p.enabled ? "predicted" : "observed");
        break;
      case "compare":
        setCompare((p.iso3s ?? p.countries ?? []) as string[]);
        break;
      case "shock":
        setScenario(String(p.scenario ?? command));
        setView("scenarios");
        break;
      case "prices":
        setView("markets");
        break;
      case "experiment":
      case "metrics":
        setView("experiment");
        break;
      default:
        notify(
          action.message ??
            "Try a country code, COCAINE ROUTES, or RISK TOP 20.",
        );
    }
  };
  const runCommand = async (text: string) => {
    setCommandOpen(false);
    setCommand("");
    const local = parseCommand(
      text,
      countries.map((c) => c.iso3),
    );
    if (local) {
      await act(local);
      return;
    }
    try {
      const r = await api.command(text);
      await act(r.data);
    } catch (e) {
      notify((e as Error).message);
    }
  };
  const filteredEvents = events.filter(
    (e) => drug === "all" || e.drug === drug,
  );
  const country = countries.find((c) => c.iso3 === selected);
  const mappedEdges = useMemo(
    () =>
      simulation
        ? edges.map((e) => {
            const changed = simulation.edges_changed.find(
              (x) => x.from === e.from && x.to === e.to && x.drug === e.drug,
            );
            return changed
              ? {
                  ...e,
                  volume_norm: changed.scenario_volume_norm,
                  kg: changed.scenario_kg,
                  probability: changed.scenario_probability,
                  change_pct: changed.delta_pct,
                }
              : e;
          })
        : edges,
    [edges, simulation],
  );
  return (
    <MotionConfig reducedMotion="user">
      <div
        className={[
          "terminal",
          mapFull && "map-full",
          mapFull && sheetOpen && "sheet-open",
          mapFull && drawerOpen && "drawer-open",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <header className="topbar">
          <a
            className="brand"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setView("atlas");
              setSelected(null);
              setRoute(null);
              setEvent(null);
              setResetKey((k) => k + 1);
            }}
            aria-label="TRACE home"
          >
            <img src="/figma/trace-mark.svg" alt="" />
            <span>
              TRACE<span className="brand-period">.</span>
            </span>
          </a>
          <nav aria-label="Workspace">
            {NAV.map((n) => (
              <button
                key={n.id}
                className={view === n.id ? "active" : ""}
                aria-current={view === n.id ? "page" : undefined}
                onClick={() => setView(n.id)}
              >
                {n.label}
              </button>
            ))}
          </nav>
          <button
            className="command-trigger"
            aria-label="Search TRACE commands"
            onClick={() => setCommandOpen(true)}
          >
            <Search size={15} />
            <span>Search or jump to…</span>
            <kbd>⌘ K</kbd>
          </button>
          <button
            className="source-trigger"
            onClick={() => setSourcesOpen(true)}
            aria-label="Open data sources"
          >
            <Database size={17} />
          </button>
        </header>
        {view !== "health" && view !== "experiment" && <div className="workspace-toolbar">
          <div className="drug-filters" aria-label="Filter by drug">
            {["all", "cocaine", "heroin", "meth", "cannabis"].map((d) => (
              <button
                key={d}
                className={drug === d ? "active" : ""}
                aria-pressed={drug === d}
                style={
                  {
                    "--drug-ink": drugColor[d] ?? "#192e45",
                  } as React.CSSProperties
                }
                onClick={() => {
                  setDrug(d as Drug | "all");
                  setSimulation(null);
                }}
              >
                {d !== "all" && <img src={`/figma/key-${d}.svg`} alt="" />}
                {d === "all" ? "All" : d === "meth" ? "Meth" : drugLabel[d]}
              </button>
            ))}
          </div>
        </div>}
        {loadError ? (
          <div className="load-error">
            <h1>Data connection interrupted</h1>
            <p>{loadError}</p>
            <button className="primary-button" onClick={load}>
              Retry connection
            </button>
          </div>
        ) : loading ? (
          <div className="app-loading">
            <img src="/figma/trace-mark.svg" alt="" />
            <p>Opening your workspace…</p>
          </div>
        ) : (
          <>
            <main
              className={view === "atlas" ? "workspace" : "workspace analytic"}
            >
              <div className="main-column">
                <div
                  className={
                    view === "atlas" ? "atlas-area" : "atlas-area hidden"
                  }
                >
                  <div className="atlas-heading">
                    <h1 className="sr-only">World atlas</h1>
                    <div className="atlas-controls">
                      <div className="segmented">
                        <button
                          onClick={() => switchMode("observed")}
                          className={mode === "observed" ? "active" : ""}
                        >
                          Baseline model
                        </button>
                        <button
                          onClick={() => switchMode("predicted")}
                          className={mode === "predicted" ? "active" : ""}
                        >
                          Forecast <span>↗</span>
                        </button>
                      </div>
                      <div className="layer-control">
                        <button
                          aria-label="Map layers"
                          className={
                            layersOpen
                              ? "outline-button active"
                              : "outline-button"
                          }
                          onClick={() => setLayersOpen(!layersOpen)}
                        >
                          <Layers3 size={15} />
                          <span>Layers</span>
                        </button>
                        {layersOpen && (
                          <div className="layer-popover">
                            <label>
                              <input
                                type="checkbox"
                                checked={showDots}
                                onChange={(e) => setShowDots(e.target.checked)}
                              />
                              Modeled exposure
                            </label>
                            <label>
                              <input
                                type="checkbox"
                                checked={showRoutes}
                                onChange={(e) =>
                                  setShowRoutes(e.target.checked)
                                }
                              />
                              Modeled corridors
                            </label>
                            <label>
                              <input
                                type="checkbox"
                                checked={showEvidence}
                                onChange={(e) => setShowEvidence(e.target.checked)}
                              />
                              Published country links (dated)
                            </label>
                            <label className="confidence-label">
                              Minimum confidence <b>{minConfidence}%</b>
                              <input
                                aria-label="Minimum route confidence"
                                type="range"
                                min={0}
                                max={100}
                                step={5}
                                value={minConfidence}
                                onChange={(e) =>
                                  setMinConfidence(Number(e.target.value))
                                }
                              />
                            </label>
                          </div>
                        )}
                      </div>
                      <button
                        className={
                          mapFull
                            ? "outline-button map-full-toggle active"
                            : "outline-button map-full-toggle"
                        }
                        aria-label={
                          mapFull ? "Exit full screen map" : "Full screen map"
                        }
                        aria-pressed={mapFull}
                        title={
                          mapFull ? "Exit full screen (Esc)" : "Full screen (F)"
                        }
                        onClick={mapFull ? exitMapFull : enterMapFull}
                      >
                        {mapFull ? (
                          <Minimize2 size={15} />
                        ) : (
                          <Maximize2 size={15} />
                        )}
                        <span>{mapFull ? "Exit" : "Full screen"}</span>
                      </button>
                    </div>
                  </div>
                  <AtlasMap
                    countries={countries}
                    edges={mappedEdges}
                    risk={risk}
                    selected={selected}
                    selectedEvent={event}
                    showDots={showDots}
                    showRoutes={showRoutes}
                    showEvidence={showEvidence}
                    drug={drug}
                    exposureLabel={
                      simulation ? "Baseline exposure" : "Country exposure"
                    }
                    resetKey={resetKey}
                    onCountry={openCountry}
                    onRoute={(e) => {
                      setRoute(e);
                      setEvent(null);
                    }}
                  />
                  {routeLoading && (
                    <div className="map-update" role="status">
                      Updating…
                    </div>
                  )}
                  {!routeLoading && !edges.length && (
                    <div className="map-empty">
                      No {mode} corridors for {year}.{" "}
                      {DEMO && (
                        <button
                          onClick={() => {
                            setMinConfidence(0);
                            setDrug("all");
                            changeYear(SNAPSHOT_YEAR);
                          }}
                        >
                          Reset to saved snapshot <ArrowRight size={12} />
                        </button>
                      )}
                    </div>
                  )}
                  {simulation && (
                    <div className="scenario-map-banner">
                      <FlaskConical size={15} />
                      Scenario overlay · {simulation.scenario}
                      <button
                        onClick={() => setSimulation(null)}
                        aria-label="Clear scenario overlay"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  )}
                  <div className="timeline">
                    <button
                      className="play-button"
                      aria-label={playing ? "Pause timeline" : "Play timeline"}
                      onClick={() => {
                        if (year === years.at(-1)) changeYear(years[0]);
                        setSimulation(null);
                        setPlaying(!playing);
                      }}
                    >
                      {playing ? <Pause size={14} /> : <Play size={14} />}
                    </button>
                    <div className="year-display">
                      {year}
                      <span>
                        {mode === "predicted" ? "Forecast" : "Model baseline"}
                      </span>
                    </div>
                    <div className="year-track">
                      <input
                        type="range"
                        aria-label="Map year"
                        min={years[0]}
                        max={years.at(-1)}
                        step={1}
                        value={year}
                        onChange={(e) => {
                          setPlaying(false);
                          changeYear(Number(e.target.value));
                        }}
                      />
                      <div className="year-ticks">
                        {years
                          .filter(
                            (y) =>
                              y % 2 === 0 ||
                              y === years[0] ||
                              y === years.at(-1),
                          )
                          .map((y) => (
                            <button
                              className={year === y ? "active" : ""}
                              key={y}
                              onClick={() => changeYear(y)}
                            >
                              {y}
                              {catalog?.predicted_years.includes(y) ? " ↗" : ""}
                            </button>
                          ))}
                      </div>
                    </div>
                  </div>
                </div>
                {view === "atlas" && (
                  <div className="dock-shell">
                  {mapFull && (
                    <button
                      className="sheet-tab"
                      aria-expanded={sheetOpen}
                      aria-controls="atlas-panels"
                      title="Risk watchlist and live wire (P)"
                      onClick={() => setSheetOpen((open) => !open)}
                    >
                      {sheetOpen ? (
                        <ChevronDown size={14} />
                      ) : (
                        <ChevronUp size={14} />
                      )}
                      Risk watchlist <i aria-hidden>·</i> Live wire
                    </button>
                  )}
                  <div
                    id="atlas-panels"
                    className="dock-sheet"
                    inert={mapFull && !sheetOpen ? true : undefined}
                  >
                  <Dock>
                    <section key="risk" className="dock-panel">
                      <div className="dock-heading">
                        <h2>
                          {simulation
                            ? "Scenario risk changes"
                            : "Risk watchlist"}{" "}
                          <span>{year}</span>
                        </h2>
                        <button
                          className="panel-handle"
                          aria-label="Drag risk panel"
                        >
                          <GripHorizontal size={16} />
                        </button>
                        <button
                          aria-label="Open risk board"
                          onClick={() => setView("risk")}
                        >
                          <ArrowUpRight size={16} />
                        </button>
                      </div>
                      {simulation ? (
                        <ScenarioRiskList
                          result={simulation}
                          onCountry={openCountry}
                        />
                      ) : (
                        <RiskTable
                          rows={risk}
                          compact
                          onCountry={openCountry}
                        />
                      )}
                    </section>
                    <section key="wire" className="dock-panel">
                      <div className="dock-heading">
                        <h2>
                          <i className="live-dot" />
                          Live wire <span>{DEMO ? "replay" : "live"}</span>
                        </h2>
                        <button
                          className="panel-handle"
                          aria-label="Drag news panel"
                        >
                          <GripHorizontal size={16} />
                        </button>
                        <button
                          aria-label="Open live wire"
                          onClick={() => setView("livewire")}
                        >
                          <ArrowUpRight size={16} />
                        </button>
                      </div>
                      <NewsList
                        events={filteredEvents}
                        compact
                        onEvent={openEvent}
                      />
                    </section>
                  </Dock>
                  </div>
                  </div>
                )}
                {view !== "atlas" && (
                  <motion.div
                    className="analytic-content"
                    key={view}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.28 }}
                  >
                    {view === "risk" && (
                      <>
                        <div className="view-heading">
                          <div>
                            <h1>Spillover risk</h1>
                          </div>
                          <select
                            aria-label="Risk year"
                            value={year}
                            onChange={(e) => changeYear(Number(e.target.value))}
                          >
                            {catalog?.risk_years.map((y) => (
                              <option key={y}>{y}</option>
                            ))}
                          </select>
                        </div>
                        <RiskTable
                          rows={risk}
                          onCountry={openCountry}
                          limit={riskLimit}
                        />
                      </>
                    )}
                    {view === "health" && (
                      <EvidenceHealth countries={countries} selectedIso={selected} onCountry={openCountry} />
                    )}
                    {view === "people" && (
                      <PeopleAtlas countries={countries} />
                    )}
                    {view === "livewire" && (
                      <>
                        <div className="view-heading">
                          <div>
                            <h1>Live wire</h1>
                          </div>
                          <span className="subtle-pill">
                            <i className="live-dot" />
                            {feedState}
                          </span>
                        </div>
                        <NewsList events={filteredEvents} onEvent={openEvent} />
                      </>
                    )}
                    {view === "scenarios" && (
                      <ScenarioPanel
                        initial={scenario}
                        observed={observedOverview}
                        onMap={() => {
                          setView("atlas");
                          setResetKey((k) => k + 1);
                        }}
                        onApplied={(s) => {
                          setSelected(null);
                          setRoute(null);
                          setEvent(null);
                          setDrug("all");
                          switchMode("predicted");
                          setSimulation(s);
                        }}
                        onExperiment={() => setView("experiment")}
                      />
                    )}
                    {view === "markets" && (
                      observedOverview ? <EvidenceMarkets overview={observedOverview} drug={drug} countries={countries} /> : observedError ? <Empty>Observed market data could not load: {observedError}</Empty> : <Empty>Loading observed market data…</Empty>
                    )}
                    {view === "experiment" && (
                      observedOverview ? <EvidenceResearch overview={observedOverview} experiment={experiment} countries={countries} /> : observedError ? <Empty>Research evidence could not load: {observedError}</Empty> : <Empty>Loading research evidence…</Empty>
                    )}
                  </motion.div>
                )}
              </div>
              {view === "atlas" && mapFull && (
                <button
                  className="drawer-tab"
                  aria-expanded={drawerOpen}
                  aria-controls="atlas-inspector"
                  title="Details (D)"
                  onClick={() => setDrawerOpen((open) => !open)}
                >
                  {drawerOpen ? (
                    <ChevronRight size={14} />
                  ) : (
                    <ChevronLeft size={14} />
                  )}
                  <span>
                    {route
                      ? "Route"
                      : country
                        ? country.iso3
                        : event
                          ? "Signal"
                          : "Risk"}
                  </span>
                </button>
              )}
              {view === "atlas" && (
                <aside
                  id="atlas-inspector"
                  className="inspector"
                  aria-label="Country and route details"
                  inert={mapFull && !drawerOpen ? true : undefined}
                >
                  {route ? (
                    <RouteInspector
                      edge={route}
                      onClose={() => setRoute(null)}
                      onCountry={openCountry}
                    />
                  ) : country ? (
                    <CountryInspector
                      country={country}
                      year={year}
                      risk={risk.find((r) => r.iso3 === selected)}
                      scenarioRisk={simulation?.risk_deltas.find(
                        (r) => r.iso3 === selected,
                      )}
                      edges={mappedEdges}
                      observed={observedOverview}
                      onClose={() => {
                        setSelected(null);
                        setResetKey((k) => k + 1);
                        returnToMap();
                      }}
                      onRoute={setRoute}
                    />
                  ) : event ? (
                    <div className="event-inspector">
                      <div className="inspector-top">
                        <span>Selected signal</span>
                        <button
                          className="icon-button"
                          aria-label="Close news event"
                          onClick={() => {
                            setEvent(null);
                            returnToMap();
                          }}
                        >
                          <X size={17} />
                        </button>
                      </div>
                      <div className="event-graphic">
                        <SignalBeacon />
                      </div>
                      <span
                        className="drug-label"
                        style={{ color: drugColor[event.drug] }}
                      >
                        {drugLabel[event.drug] ?? event.drug} ·{" "}
                        {event.event_type.replaceAll("_", " ")}
                      </span>
                      <h2>{event.title}</h2>
                      <p>
                        {event.origin ?? "Unknown origin"} →{" "}
                        {event.destination ?? "Unknown destination"}
                      </p>
                      <div className="evidence-row">
                        <span>Confidence</span>
                        <b>{Math.round(event.confidence * 100)}%</b>
                      </div>
                      <div className="evidence-row">
                        <span>Magnitude</span>
                        <b>{event.size}</b>
                      </div>
                      {event.is_anomaly && (
                        <div className="anomaly-reason">
                          {event.anomaly_reason}
                        </div>
                      )}
                      <p className="source-note">
                        {new Date(event.published_at).toLocaleString("en-GB", {
                          timeZone: "UTC",
                        })}{" "}
                        UTC · {event.classifier}
                      </p>
                      {DEMO || event.source_domain === "sample.trace.local" ? (
                        <p className="quiet-note">
                          Illustrative headline · no source article attached.
                        </p>
                      ) : (
                        <a
                          className="text-button"
                          target="_blank"
                          rel="noreferrer"
                          href={event.url}
                        >
                          Read source article
                          <ArrowUpRight size={14} />
                        </a>
                      )}
                    </div>
                  ) : (
                    <div className="global-outlook">
                      <div className="inspector-top">
                        <h2>Risk</h2>
                        <span className="mono muted">{year}</span>
                      </div>
                      <div className="section-line">
                        <h3>Country</h3>
                        <button
                          className="text-button"
                          aria-label="View all countries by risk"
                          onClick={() => setView("risk")}
                        >
                          <ArrowUpRight size={15} />
                        </button>
                      </div>
                      <div className="country-watchlist">
                        {risk.slice(0, 5).map((r) => (
                          <button
                            key={r.iso3}
                            onClick={() => openCountry(r.iso3)}
                          >
                            <span className="watch-country">
                              <span className="country-code">{r.iso3}</span>
                              <b>
                                {r.name}
                                <small>{r.tier} risk</small>
                              </b>
                            </span>
                            <span
                              className="risk-number"
                              style={{ color: scoreColor(r.score) }}
                            >
                              {r.score.toFixed(1)}
                            </span>
                            <ArrowUpRight size={13} />
                          </button>
                        ))}
                        {!risk.length && (
                          <p className="quiet-note">
                            Risk scores are not available for {year}.
                          </p>
                        )}
                      </div>
                      <button
                        className="experiment-link"
                        onClick={() => setView("experiment")}
                      >
                        Afghanistan opium ban <ArrowUpRight size={15} />
                      </button>
                    </div>
                  )}
                </aside>
              )}
            </main>
          </>
        )}
        <footer className="statusbar">
          <span>
            <i className="status-dot" />
            {DEMO ? "Snapshot mode" : "API connected"}
          </span>
          <button onClick={() => setSourcesOpen(true)}>
            Data sources <ArrowUpRight size={11} />
          </button>
          <span className="status-model">
            {catalog?.model_version ?? "TRACE"}
          </span>
          {dataTime && (
            <span className="data-freshness">
              Snapshot{" "}
              {new Date(dataTime).toLocaleString("en-GB", {
                timeZone: "UTC",
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}{" "}
              UTC
            </span>
          )}
          <span className="status-right">
            <span className="mono">{clock} UTC</span>
          </span>
        </footer>
        {commandOpen && (
          <div
            className="modal-backdrop command-backdrop"
            onClick={() => setCommandOpen(false)}
          >
            <Command
              className="command-dialog"
              label="Search TRACE"
              shouldFilter={false}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="command-input-wrap">
                <Search size={20} />
                <Command.Input
                  autoFocus
                  placeholder="Country, route, or command…"
                  value={command}
                  onValueChange={setCommand}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      command.trim() &&
                      !document.querySelector(
                        '[cmdk-item][aria-selected="true"]',
                      )
                    )
                      void runCommand(command);
                  }}
                />
                <button
                  className="icon-button"
                  aria-label="Close command menu"
                  onClick={() => setCommandOpen(false)}
                >
                  <X size={18} />
                </button>
              </div>
              <Command.List>
                {command.trim() && (
                  <Command.Item
                    value="execute-command"
                    onSelect={() => void runCommand(command)}
                  >
                    <CommandIcon size={15} />
                    <span>Run “{command}”</span>
                    <kbd>↵</kbd>
                  </Command.Item>
                )}
                <Command.Group
                  heading={command ? "Matching countries" : "Jump to"}
                >
                  {(command
                    ? countries
                        .filter((c) =>
                          `${c.name} ${c.iso3}`
                            .toLowerCase()
                            .includes(command.toLowerCase()),
                        )
                        .slice(0, 6)
                    : countries.filter((c) =>
                        ["COL", "ECU", "MMR"].includes(c.iso3),
                      )
                  ).map((c) => (
                    <Command.Item
                      key={c.iso3}
                      value={c.iso3}
                      onSelect={() => void runCommand(`${c.iso3} <GO>`)}
                    >
                      <Globe2 size={15} />
                      <span>{c.name}</span>
                      <small>{c.iso3}</small>
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group heading="Commands">
                  {suggestions
                    .filter(
                      (s) =>
                        !command ||
                        s.toLowerCase().includes(command.toLowerCase()),
                    )
                    .map((s) => (
                      <Command.Item
                        key={s}
                        value={s}
                        onSelect={() => void runCommand(s)}
                      >
                        <ArrowRight size={15} />
                        <span>{s}</span>
                      </Command.Item>
                    ))}
                </Command.Group>
              </Command.List>
              <div className="command-footer">
                <span>↑ ↓ Navigate</span>
                <span>↵ Select</span>
                <span>esc Close</span>
              </div>
            </Command>
          </div>
        )}
        {sourcesOpen && catalog && (
          <Sources catalog={catalog} observed={observedOverview} onClose={() => setSourcesOpen(false)} />
        )}
        {compare.length > 0 && (
          <Compare
            codes={compare}
            countries={countries}
            rows={risk}
            onClose={() => setCompare([])}
            onCountry={openCountry}
          />
        )}
        <AnimatePresence>
          {toast && (
            <motion.div
              className="toast"
              role="status"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
            >
              {toast}
              <button
                className="icon-button"
                aria-label="Dismiss notification"
                onClick={() => setToast("")}
              >
                <X size={15} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </MotionConfig>
  );
}
