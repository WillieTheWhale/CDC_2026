// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { Command } from "cmdk";
import { Dock } from "./dock";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  Command as CommandIcon,
  Database,
  FlaskConical,
  Globe2,
  GripHorizontal,
  Layers3,
  Pause,
  Play,
  Radio,
  Search,
  SlidersHorizontal,
  TrendingUp,
  X,
} from "lucide-react";
import {
  api,
  API_BASE,
  Catalog,
  DEMO,
  drugColor,
  drugLabel,
  Experiment,
  Metrics,
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
  Price,
  RiskRow,
  View,
} from "@/lib/types";
import {
  Compare,
  CountryInspector,
  Empty,
  ExperimentView,
  Markets,
  NewsList,
  RiskTable,
  RouteInspector,
  ScenarioPanel,
  Sources,
} from "./panels";
import { Sparkline } from "./charts";
const AtlasMap = dynamic(() => import("./atlas-map"), {
  ssr: false,
  loading: () => <div className="map-loading">Preparing the atlas…</div>,
});
const NAV: { id: View; label: string }[] = [
  { id: "atlas", label: "Atlas" },
  { id: "risk", label: "Risk board" },
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
    [prices, setPrices] = useState<Price[]>([]),
    [events, setEvents] = useState<LiveEvent[]>([]),
    [experiment, setExperiment] = useState<Experiment | null>(null),
    [metrics, setMetrics] = useState<Metrics | null>(null);
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
    [layersOpen, setLayersOpen] = useState(false),
    [minConfidence, setMinConfidence] = useState(0),
    [resetKey, setResetKey] = useState(0),
    [playing, setPlaying] = useState(false),
    [scenario, setScenario] = useState(""),
    [simulation, setSimulation] = useState<Simulation | null>(null),
    [riskLimit, setRiskLimit] = useState(250),
    [clock, setClock] = useState("--:--:--");
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
      setCountries(c.data);
      setYear(m.data.latest_observed_year);
      const results = await Promise.allSettled([
        api.prices(),
        api.livewire(),
        api.experiment(),
        api.metrics(),
      ] as const);
      const [p, n, e, mt] = results;
      if (p.status === "fulfilled") setPrices(p.value.data.series);
      if (n.status === "fulfilled")
        setEvents(n.value.data.events.filter((e) => e.confidence >= 0.6));
      if (e.status === "fulfilled") setExperiment(e.value.data);
      if (mt.status === "fulfilled") setMetrics(mt.value.data);
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
    if ((selected || route || event) && window.innerWidth <= 760)
      document
        .querySelector(".inspector")
        ?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "instant"
            : "smooth",
          block: "start",
        });
  }, [selected, route, event]);
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
                  change_pct: changed.delta_pct,
                }
              : e;
          })
        : edges,
    [edges, simulation],
  );
  const networkCountries = new Set(edges.flatMap((e) => [e.from, e.to])).size;
  return (
    <MotionConfig reducedMotion="user">
      <div className="terminal">
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
                onClick={() => setView(n.id)}
              >
                {n.label}
              </button>
            ))}
          </nav>
          <button
            className="command-trigger"
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
        <div className="workspace-toolbar">
          <div className="workspace-name">
            <Globe2 size={17} />
            <span>
              {view === "atlas"
                ? "World atlas"
                : NAV.find((n) => n.id === view)?.label}
            </span>
            <ChevronDown size={12} />
          </div>
          <div className="drug-filters" aria-label="Filter by drug">
            {["all", "cocaine", "heroin", "meth", "cannabis"].map((d) => (
              <button
                key={d}
                className={drug === d ? "active" : ""}
                onClick={() => {
                  setDrug(d as Drug | "all");
                  setSimulation(null);
                }}
              >
                {d !== "all" && <i style={{ background: drugColor[d] }} />}
                {d === "all"
                  ? "All substances"
                  : d === "meth"
                    ? "Meth"
                    : drugLabel[d]}
              </button>
            ))}
          </div>
          <span className="demo-badge">
            <i />
            {DEMO ? "Illustrative data" : "Connected data"}
          </span>
        </div>
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
                    <div>
                      <h1>
                        Global flows<span className="title-dot">.</span>
                      </h1>
                      <p>
                        {networkCountries} economies connected across{" "}
                        {edges.length} corridors
                      </p>
                    </div>
                    <div className="atlas-controls">
                      <div className="segmented">
                        <button
                          onClick={() => switchMode("observed")}
                          className={mode === "observed" ? "active" : ""}
                        >
                          Observed
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
                              Exposure dots
                            </label>
                            <label>
                              <input
                                type="checkbox"
                                checked={showRoutes}
                                onChange={(e) =>
                                  setShowRoutes(e.target.checked)
                                }
                              />
                              Route network
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
                        <button onClick={() => changeYear(2024)}>
                          Return to 2024 demo <ArrowRight size={12} />
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
                  <div className="map-legend">
                    <img
                      src="/figma/exposure-legend.svg"
                      alt="Country exposure color scale from sand to violet"
                    />
                    <div>
                      <span>Lower exposure</span>
                      <span>Higher</span>
                    </div>
                    <small>
                      Color = country exposure · width = corridor volume
                    </small>
                  </div>
                  <div className="timeline">
                    <button
                      className="play-button"
                      aria-label={playing ? "Pause timeline" : "Play timeline"}
                      onClick={() => {
                        if (year === years.at(-1)) changeYear(years[0]);
                        setPlaying(!playing);
                      }}
                    >
                      {playing ? <Pause size={14} /> : <Play size={14} />}
                    </button>
                    <div className="year-display">
                      {year}
                      <span>
                        {mode === "predicted" ? "Forecast" : "Observed"}
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
                  <Dock>
                    <section key="risk" className="dock-panel">
                      <div className="dock-heading">
                        <h2>
                          Risk watchlist <span>{year}</span>
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
                      <RiskTable rows={risk} compact onCountry={openCountry} />
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
                            <h1>Where harm could follow.</h1>
                            <p>
                              Compare exposure, vulnerability, and prevention
                              capacity.
                            </p>
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
                        <div className="risk-summary">
                          <div>
                            <span>Countries in view</span>
                            <b>{risk.length.toString().padStart(2, "0")}</b>
                          </div>
                          <div>
                            <span>Critical exposure</span>
                            <b>
                              {risk
                                .filter((r) => r.tier === "critical")
                                .length.toString()
                                .padStart(2, "0")}
                            </b>
                          </div>
                          <div>
                            <span>Prevention lens</span>
                            <p>
                              Higher protection.
                              <br />
                              Lower potential harm.
                            </p>
                          </div>
                          <img
                            src="/figma/exposure-legend.svg"
                            alt="Exposure scale"
                          />
                        </div>
                        <RiskTable
                          rows={risk}
                          onCountry={openCountry}
                          limit={riskLimit}
                        />
                      </>
                    )}
                    {view === "livewire" && (
                      <>
                        <div className="view-heading">
                          <div>
                            <h1>Signals across the network.</h1>
                            <p>
                              Click an event to locate it on the atlas. Times
                              shown in UTC.
                            </p>
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
                        onApplied={(s) => {
                          setSimulation(s);
                          setDrug("all");
                          switchMode("predicted");
                          setSimulation(s);
                        }}
                        onExperiment={() => setView("experiment")}
                      />
                    )}
                    {view === "markets" && (
                      <Markets series={prices} drug={drug} />
                    )}
                    {view === "experiment" &&
                      (experiment && metrics ? (
                        <ExperimentView
                          experiment={experiment}
                          metrics={metrics}
                        />
                      ) : (
                        <Empty>
                          Evaluation results are not available from the data
                          service yet.
                        </Empty>
                      ))}
                  </motion.div>
                )}
              </div>
              {view === "atlas" && (
                <aside
                  className="inspector"
                  aria-label="Country and route details"
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
                      edges={edges}
                      onClose={() => {
                        setSelected(null);
                        setResetKey((k) => k + 1);
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
                          onClick={() => setEvent(null)}
                        >
                          <X size={17} />
                        </button>
                      </div>
                      <div className="event-graphic">
                        <img src="/figma/signal-beacon.svg" alt="" />
                        <span />
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
                      {DEMO ? (
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
                        <span>Global outlook</span>
                        <span className="mono muted">{year}</span>
                      </div>
                      <h2>
                        Follow the flows.
                        <br />
                        <span>Understand the impact.</span>
                      </h2>
                      <p className="outlook-intro">
                        A connected view of drug trade, community vulnerability,
                        and prevention.
                      </p>
                      <div className="outlook-stats">
                        <div>
                          <b>{edges.length}</b>
                          <span>corridors</span>
                        </div>
                        <div>
                          <b>{networkCountries}</b>
                          <span>economies</span>
                        </div>
                        <div>
                          <b>
                            {edges
                              .filter((e) => e.is_emerging)
                              .length.toString()
                              .padStart(2, "0")}
                          </b>
                          <span>emerging</span>
                        </div>
                      </div>
                      <div className="section-line">
                        <h3>Countries to watch</h3>
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
                        className="feature-story"
                        onClick={() => setView("experiment")}
                      >
                        <img src="/figma/route-study.svg" alt="" />
                        <div>
                          <span>Afghanistan, after the ban</span>
                          <p>One policy. A global shift.</p>
                          <b>
                            Explore the experiment <ArrowUpRight size={14} />
                          </b>
                        </div>
                      </button>
                      <p className="sidebar-hint">
                        <CommandIcon size={13} /> Press ⌘K to go anywhere.
                      </p>
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
            {DEMO ? "Demo workspace" : "API connected"}
          </span>
          <button onClick={() => setSourcesOpen(true)}>
            Data sources <ArrowUpRight size={11} />
          </button>
          <span className="status-model">
            {catalog?.model_version ?? "TRACE"}
          </span>
          <span className="status-right">
            Built for prevention<span className="mono">{clock} UTC</span>
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
          <Sources catalog={catalog} onClose={() => setSourcesOpen(false)} />
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
