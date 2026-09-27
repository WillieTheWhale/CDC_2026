// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// Estimated-flow arrow layer, volume coloring, API-backed route evidence (three
// pair types) and cited US routes added with Claude Code (Anthropic).
// AI-assisted: country anchor fix written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { MapLibreOverlay } from "@deck.gl/maplibre";
import { ArcLayer, ScatterplotLayer, SolidPolygonLayer } from "@deck.gl/layers";
import type { Color, PickingInfo } from "@deck.gl/core";
import type { FeatureCollection, Geometry } from "geojson";
import { LocateFixed, Minus, Plus, RotateCcw } from "lucide-react";
import type { Country, Edge, LiveEvent, RiskRow } from "@/lib/types";
import { drugColor, formatNumber } from "@/lib/api";
import { visibleModelRoutes } from "@/lib/route-visibility";
import { countryAnchors, type Anchor } from "@/lib/country-anchors";
import {
  evidenceForEdge,
  evidencePeriod,
  kgBasisNote,
  pairTypeLabel,
  type DrawableEvidence,
} from "@/lib/route-evidence";
import { useRouteEvidence } from "@/lib/route-evidence-store";
import type { Drug } from "@/lib/types";
import { basisLabel, fentanylColor, filterUsRoutes, type UsRoute } from "@/lib/us-routes";
import {
  fieldArrows,
  nearestBigPaths,
  placeArrows,
  spacingKm,
  volumeBands,
  windGlyphs,
  type EstimatedLayer,
  type FieldArrow,
  type PlacedArrow,
} from "@/lib/estimated-flows";
interface Props {
  countries: Country[];
  edges: Edge[];
  risk: RiskRow[];
  selected: string | null;
  selectedEvent: LiveEvent | null;
  showDots: boolean;
  showRoutes: boolean;
  showEvidence: boolean;
  drug: Drug | "all";
  exposureLabel: string;
  estimated?: EstimatedLayer | null;
  usRoutes?: UsRoute[];
  showUsRoutes?: boolean;
  showEstimated?: boolean;
  colorBy?: "volume" | "exposure";
  onCountry: (iso: string) => void;
  onRoute: (edge: Edge) => void;
  resetKey: number;
}
const rgba = (h: string, a = 255): Color => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
  a,
];
const exposureColors = [
  "#e8edf5",
  "#f2ad75",
  "#f17246",
  "#ed482d",
  "#ad377b",
  "#653caf",
];
const fitWorld = (m: maplibregl.Map, duration = 900) =>
  m.fitBounds(
    [
      [-172, -55],
      [180, 75],
    ],
    {
      padding: { top: 65, bottom: 112, left: 24, right: 48 },
      duration,
      maxZoom: 2,
    },
  );

function touchesView(
  bounds: maplibregl.LngLatBounds,
  points: ReadonlyMap<string, { lat: number | null; lon: number | null }>,
  from: string,
  to: string,
) {
  const source = points.get(from);
  const destination = points.get(to);
  const center = (bounds.getWest() + bounds.getEast()) / 2;
  const contains = (point: { lat: number | null; lon: number | null } | undefined) => {
    if (point?.lon == null || point.lat == null) return false;
    const nearestCopy = point.lon + 360 * Math.round((center - point.lon) / 360);
    return bounds.contains([nearestCopy, point.lat]);
  };
  return !!(
    contains(source) || contains(destination)
  );
}

// A screen-space halftone, not a grid of purported observations. Density and
// color encode six bands of the country exposure index. Each ink mark is 1px.
function exposureTexture(band: number) {
  const width = 16,
    data = new Uint8Array(width * width * 4);
  const rgb = rgba(exposureColors[band]);
  const positions = [
    [2, 2],
    [10, 10],
    [2, 10],
    [10, 2],
    [6, 6],
    [14, 14],
    [6, 14],
    [14, 6],
  ];
  const count = [1, 2, 3, 4, 6, 8][band];
  for (const [x, y] of positions.slice(0, count))
    for (let dy = 0; dy < 2; dy++)
      for (let dx = 0; dx < 2; dx++) {
        const i = ((y + dy) * width + x + dx) * 4;
        data.set([rgb[0], rgb[1], rgb[2], 235], i);
      }
  return { width, height: width, data };
}

export default function AtlasMap(props: Props) {
  const host = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map | null>(null),
    overlay = useRef<MapLibreOverlay | null>(null),
    latest = useRef(props),
    clickedCountry = useRef<string | null>(null);
  latest.current = props;
  const [ready, setReady] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<{
    edge: Edge;
    x: number;
    y: number;
  } | null>(null);
  const [reportHover, setReportHover] = useState<{
    route: DrawableEvidence;
    x: number;
    y: number;
  } | null>(null);
  const [reportDetail, setReportDetail] = useState<DrawableEvidence | null>(null);
  const [usHover, setUsHover] = useState<{ route: UsRoute; x: number; y: number } | null>(null);
  const [usDetail, setUsDetail] = useState<UsRoute | null>(null);
  const [windHover, setWindHover] = useState<{
    glyph: PlacedArrow;
    x: number;
    y: number;
  } | null>(null);
  const [geography, setGeography] = useState<{
    geo: FeatureCollection<Geometry>;
    style: maplibregl.StyleSpecification;
  } | null>(null);
  const [position, setPosition] = useState({ lng: 0, lat: 0, zoom: 1 });
  const localScale = position.zoom >= 6;
  // Natural Earth label points indicate a country, avoiding the false
  // capital-to-capital precision of the World Bank country catalog. Anchors
  // are resolved on each country's mainland so no arc ends in open water.
  const anchors = useMemo(
    () => (geography ? countryAnchors(geography.geo) : new Map<string, Anchor>()),
    [geography],
  );
  const routeCoordinates = useMemo(() => {
    const points = new Map<string, { lat: number | null; lon: number | null }>(
      props.countries.map((country) => [country.iso3, { lat: country.lat, lon: country.lon }]),
    );
    for (const [iso3, anchor] of anchors) points.set(iso3, anchor);
    return points;
  }, [props.countries, anchors]);
  const tierEdges = useMemo(
    () => visibleModelRoutes(props.edges, routeCoordinates, position.zoom),
    [props.edges, routeCoordinates, position.zoom],
  );
  const visibleEdges = useMemo(() => {
    const bounds = map.current?.getBounds();
    return position.zoom < 2.2 || !bounds
      ? tierEdges
      : tierEdges.filter((edge) => touchesView(bounds, routeCoordinates, edge.from, edge.to));
  }, [tierEdges, routeCoordinates, position]);
  // Direct reported pairs and TRACE-interpreted corridors are drawn (as two
  // distinct layers); narrative context has no endpoints and stays text-only.
  const { index: evidence } = useRouteEvidence();
  const availableReports = useMemo(
    () => [...evidence.direct, ...evidence.interpreted].filter((route) =>
      (props.drug === "all" || props.drug === route.drug) &&
      routeCoordinates.get(route.from)?.lat != null &&
      routeCoordinates.get(route.from)?.lon != null &&
      routeCoordinates.get(route.to)?.lat != null &&
      routeCoordinates.get(route.to)?.lon != null,
    ),
    [evidence, routeCoordinates, props.drug],
  );
  const visibleReports = useMemo(
    () => {
      const bounds = map.current?.getBounds();
      return props.showEvidence && position.zoom >= 2.2 && !localScale
        ? bounds
          ? availableReports.filter((route) => touchesView(bounds, routeCoordinates, route.from, route.to))
          : availableReports
        : [];
    },
    [availableReports, routeCoordinates, props.showEvidence, position, localScale],
  );
  const visibleDirect = useMemo(
    () => visibleReports.filter((route) => route.pair_type === "direct_reported_pair"),
    [visibleReports],
  );
  const visibleInterpreted = useMemo(
    () => visibleReports.filter((route) => route.pair_type === "interpreted_corridor"),
    [visibleReports],
  );
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(
      ["/geo/countries.json", "/geo/basemap.json"].map(async (url) => {
        const r = await fetch(url, { signal: controller.signal });
        if (!r.ok) throw Error("Map data unavailable");
        return r.json();
      }),
    )
      .then(([geo, style]) => setGeography({ geo, style }))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!host.current || !geography) return;
    let m: maplibregl.Map;
    try {
      maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");
      // Place the local country source beneath roads and labels. Its 1:10m
      // geometry is also a network-independent fallback for country selection.
      const style = structuredClone(geography.style);
      style.sources["trace-countries"] = {
        type: "geojson",
        data: geography.geo,
        promoteId: "iso3",
      };
      style.layers.splice(1, 0, {
        id: "trace-land",
        type: "fill",
        source: "trace-countries",
        paint: { "fill-color": "#f9fbfe", "fill-opacity": 0.8 },
      });
      m = new maplibregl.Map({
        container: host.current,
        center: [8, 15],
        zoom: 0.7,
        minZoom: -1,
        maxZoom: 18,
        // Native Mercator constraints keep the viewport within the polar bounds
        // at every size while allowing the map and deck overlay to repeat east/west.
        renderWorldCopies: true,
        dragRotate: false,
        pitchWithRotate: false,
        attributionControl: { compact: true },
        style,
      });
    } catch {
      setError(
        "WebGL unavailable. Country search and tables remain available.",
      );
      return;
    }
    map.current = m;
    const o = new MapLibreOverlay({ interleaved: false, layers: [] });
    overlay.current = o;
    m.addControl(o);
    m.addControl(
      new maplibregl.ScaleControl({ maxWidth: 110, unit: "metric" }),
      "bottom-right",
    );
    m.on("load", () => {
      for (let band = 0; band < 6; band++)
        m.addImage(`exposure-${band}`, exposureTexture(band), {
          pixelRatio: 2,
        });
      m.addImage("exposure-none", {
        width: 2,
        height: 2,
        data: new Uint8Array(16),
      });
      const before = m.getStyle().layers.find((l) => l.type === "symbol")?.id;
      m.addLayer(
        {
          id: "exposure-tone",
          type: "fill",
          source: "trace-countries",
          paint: {
            "fill-color": "#ffffff",
            "fill-opacity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              2,
              0.13,
              5,
              0.03,
              7,
              0,
            ],
          },
        },
        before,
      );
      m.addLayer(
        {
          id: "exposure-stipple",
          type: "fill",
          source: "trace-countries",
          paint: {
            "fill-pattern": "exposure-none",
            "fill-opacity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              2,
              0.9,
              4,
              0.75,
              6,
              0,
            ],
          },
        },
        before,
      );
      m.addLayer(
        {
          id: "selection",
          type: "line",
          source: "trace-countries",
          filter: ["==", ["get", "iso3"], ""],
          paint: {
            "line-color": "#ed482d",
            "line-width": 1.2,
            "line-opacity": 0.8,
          },
        },
        before,
      );
      m.resize();
      fitWorld(m, 0);
      setReady(true);
    });
    m.on("click", "trace-land", (e) => {
      const iso = e.features?.[0]?.properties.iso3;
      if (iso && latest.current.countries.some((c) => c.iso3 === iso)) {
        clickedCountry.current = iso;
        latest.current.onCountry(iso);
      }
    });
    m.on("movestart", () => {
      setHover(null);
      setReportHover(null);
    });
    m.on("moveend", () => {
      const c = m.getCenter().wrap();
      setPosition({ lng: c.lng, lat: c.lat, zoom: m.getZoom() });
    });
    m.on("zoom", () => {
      const c = m.getCenter().wrap();
      setPosition({ lng: c.lng, lat: c.lat, zoom: m.getZoom() });
    });
    m.on("error", (e) => {
      if (e.error?.message?.includes("WebGL")) setError(e.error.message);
    });
    const resize = new ResizeObserver(() => m.resize());
    resize.observe(host.current);
    return () => {
      resize.disconnect();
      m.remove();
      map.current = null;
      overlay.current = null;
      setReady(false);
    };
  }, [geography]);
  useEffect(() => {
    const m = map.current;
    if (!ready || !m?.getLayer("exposure-stipple")) return;
    const pattern: unknown[] = ["match", ["get", "iso3"]],
      colors: unknown[] = ["match", ["get", "iso3"]];
    // Color by modeled drug volume (default) or by the risk exposure index.
    const bands =
      props.colorBy === "exposure"
        ? new Map(
            props.risk.map((row) => [
              row.iso3,
              Math.min(5, Math.floor(row.exposure / (100 / 6))),
            ]),
          )
        : volumeBands(props.edges);
    for (const [iso3, band] of bands) {
      pattern.push(iso3, `exposure-${band}`);
      colors.push(iso3, exposureColors[band]);
    }
    pattern.push("exposure-none");
    colors.push("#fbfcfe");
    m.setPaintProperty(
      "exposure-stipple",
      "fill-pattern",
      bands.size
        ? (pattern as maplibregl.ExpressionSpecification)
        : "exposure-none",
    );
    m.setPaintProperty(
      "exposure-tone",
      "fill-color",
      bands.size
        ? (colors as maplibregl.ExpressionSpecification)
        : "#fbfcfe",
    );
    for (const id of ["exposure-stipple", "exposure-tone"])
      m.setLayoutProperty(
        id,
        "visibility",
        props.showDots ? "visible" : "none",
      );
  }, [ready, props.risk, props.showDots, props.colorBy, props.edges]);
  // Estimated flows: faint at world scale, full from zoom 3, so zoomed-in views
  // stay dense. Glyph spacing follows zoom (rounded to limit recomputation) and
  // off-screen flows are skipped above zoom 3.
  const glyphZoom = Math.round(position.zoom * 2) / 2;
  const estimatedFlows = useMemo(
    () =>
      (props.estimated?.flows ?? []).filter(
        (f) => props.drug === "all" || f.drug === props.drug,
      ),
    [props.estimated, props.drug],
  );
  // Re-place arrows only when the zoom step or a coarse view window changes,
  // not on every animation frame.
  const viewKey =
    glyphZoom < 3
      ? "world"
      : `${Math.round(position.lng / (40 / 2 ** (glyphZoom - 3)))}:${Math.round(position.lat / (25 / 2 ** (glyphZoom - 3)))}`;
  const glyphs = useMemo(() => {
    if (!props.showEstimated || !estimatedFlows.length) return [];
    const bounds = map.current?.getBounds();
    const flows =
      glyphZoom < 3 || !bounds
        ? estimatedFlows
        : estimatedFlows.filter((f) => {
            const west = Math.min(f.from.lon, f.to.lon);
            const east = Math.max(f.from.lon, f.to.lon);
            const south = Math.min(f.from.lat, f.to.lat);
            const north = Math.max(f.from.lat, f.to.lat);
            return !(
              east < bounds.getWest() - 4 ||
              west > bounds.getEast() + 4 ||
              north < bounds.getSouth() - 4 ||
              south > bounds.getNorth() + 4
            );
          });
    // Net flow per grid cell, each arrow aimed at a city, then greedy
    // placement so no two arrows overlap on screen.
    return placeArrows(
      fieldArrows(windGlyphs(flows, glyphZoom + 1), (spacingKm(glyphZoom) * 1.1) / 111),
      glyphZoom,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estimatedFlows, props.showEstimated, glyphZoom, viewKey]);
  const windOpacity = 1;
  useEffect(() => {
    if (!ready || !overlay.current) return;
    const active = new Set(visibleEdges.flatMap((e) => [e.from, e.to]));
    const hubs = props.countries.filter(
      (c) => active.has(c.iso3) && routeCoordinates.get(c.iso3)?.lon != null,
    );
    const point = (iso3: string): [number, number] => {
      const coordinate = routeCoordinates.get(iso3)!;
      return [coordinate.lon!, coordinate.lat!];
    };
    const reportLayer = (id: string, data: DrawableEvidence[], alpha: number, width: number, height: number) =>
      new ArcLayer<DrawableEvidence>({
        id,
        data,
        getSourcePosition: (route) => point(route.from),
        getTargetPosition: (route) => point(route.to),
        getSourceColor: (route) => rgba(drugColor[route.drug], alpha),
        getTargetColor: (route) => rgba(drugColor[route.drug], alpha),
        getWidth: width,
        getHeight: height,
        greatCircle: true,
        pickable: true,
        autoHighlight: true,
        highlightColor: [48, 80, 114, 210],
        onHover: (info: PickingInfo<DrawableEvidence>) => {
          setReportHover(info.object ? { route: info.object, x: info.x, y: info.y } : null);
          if (info.object) setHover(null);
        },
        onClick: (info: PickingInfo<DrawableEvidence>) => {
          if (!info.object) return false;
          setReportDetail(info.object);
          setHover(null);
          setReportHover(null);
          return true;
        },
      });
    overlay.current.setProps({
      layers: [
        new SolidPolygonLayer<PlacedArrow>({
          id: "estimated-wind",
          data: glyphs,
          opacity: windOpacity,
          // Curved, very faint arrows tinted by drug (shape rebuilt per zoom step).
          getPolygon: (g) => g.polygon,
          getFillColor: (g) =>
            // Faint but readable (darker than before), tinted by drug.
            rgba(drugColor[g.drug], Math.round(40 + g.magnitude * 55)),
          pickable: true,
          onHover: (info: PickingInfo<PlacedArrow>) =>
            setWindHover(
              info.object ? { glyph: info.object, x: info.x, y: info.y } : null,
            ),

        }),
        new ArcLayer<UsRoute>({
          id: "us-documented-routes",
          data: props.showUsRoutes ? filterUsRoutes(props.usRoutes ?? [], props.drug) : [],
          getSourcePosition: (r) => [r.from.lon, r.from.lat],
          getTargetPosition: (r) => [r.to.lon, r.to.lat],
          getSourceColor: (r) =>
            rgba(r.drug === "fentanyl" ? fentanylColor : drugColor[r.drug], 150),
          getTargetColor: (r) =>
            rgba(r.drug === "fentanyl" ? fentanylColor : drugColor[r.drug], 230),
          getWidth: (r) => (r.precision === "city" ? 1.6 : 1.1),
          getHeight: 0.3,
          greatCircle: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [15, 30, 55, 255],
          onHover: (info: PickingInfo<UsRoute>) =>
            setUsHover(info.object ? { route: info.object, x: info.x, y: info.y } : null),
          onClick: (info: PickingInfo<UsRoute>) => {
            if (!info.object) return false;
            setUsDetail(info.object);
            setUsHover(null);
            return true;
          },
        }),
        new ArcLayer<Edge>({
          id: "route-arcs",
          data: props.showRoutes ? visibleEdges : [],
          opacity: Math.max(0, Math.min(1, (6 - position.zoom) / 2)),
          getSourcePosition: (e) => point(e.from),
          getTargetPosition: (e) => point(e.to),
          getSourceColor: (e) =>
            rgba(
              drugColor[e.drug],
              Math.round(e.confidence * 2.15) *
                (props.selected &&
                e.from !== props.selected &&
                e.to !== props.selected
                  ? 0.12
                  : 1),
            ),
          getTargetColor: (e) =>
            rgba(
              drugColor[e.drug],
              Math.round(e.confidence * 1.65) *
                (props.selected &&
                e.from !== props.selected &&
                e.to !== props.selected
                  ? 0.12
                  : 1),
            ),
          getWidth: (e) => 0.5 + e.volume_norm * 2,
          getHeight: 0.2,
          greatCircle: true,
          pickable: !localScale,
          autoHighlight: true,
          highlightColor: [15, 30, 55, 255],
          onHover: (info: PickingInfo<Edge>) =>
            {
              setHover(info.object ? { edge: info.object, x: info.x, y: info.y } : null);
              if (info.object) setReportHover(null);
            },
          onClick: (info: PickingInfo<Edge>) => {
            if (info.object) {
              latest.current.onRoute(info.object);
              return true;
            }
            return false;
          },
          updateTriggers: {
            getSourceColor: [props.selected],
            getTargetColor: [props.selected],
          },
          transitions: { getWidth: 400 },
        }),
        // Interpreted corridors: fainter, thinner and flatter than the direct
        // reported pairs drawn above them, which keep their look.
        reportLayer("interpreted-corridors", visibleInterpreted, 55, 0.55, 0.26),
        reportLayer("reported-country-links", visibleDirect, 105, 0.85, 0.42),
        new ScatterplotLayer<Country>({
          id: "route-hubs",
          data: props.showRoutes && !localScale ? hubs : [],
          opacity: Math.max(0, Math.min(1, (6 - position.zoom) / 2)),
          getPosition: (country) => point(country.iso3),
          getRadius: 2.4,
          radiusUnits: "pixels",
          getFillColor: [255, 255, 255],
          stroked: true,
          getLineColor: [53, 73, 98],
          lineWidthUnits: "pixels",
          getLineWidth: 1,
          pickable: true,
          onClick: ({ object }: PickingInfo<Country>) => {
            if (object) latest.current.onCountry(object.iso3);
            return true;
          },
        }),
      ],
    });
  }, [
    ready,
    props.countries,
    routeCoordinates,
    visibleEdges,
    visibleDirect,
    visibleInterpreted,
    props.selected,
    props.showRoutes,
    position.zoom,
    localScale,
    glyphs,
    glyphZoom,
    windOpacity,
    props.usRoutes,
    props.showUsRoutes,
    props.drug,
  ]);
  useEffect(() => {
    const m = map.current;
    if (!ready || !m?.getLayer("selection")) return;
    m.setFilter("selection", ["==", ["get", "iso3"], props.selected ?? ""]);
    if (clickedCountry.current === props.selected) {
      clickedCountry.current = null;
      return;
    }
    const c = props.countries.find((c) => c.iso3 === props.selected);
    if (c?.lon != null && c.lat != null)
      m.flyTo({
        center: [c.lon, c.lat],
        zoom: 4,
        duration: 1000,
        essential: false,
      });
  }, [props.selected, ready, props.countries]);
  useEffect(() => {
    if (props.resetKey > 0 && map.current) fitWorld(map.current);
  }, [props.resetKey]);
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !props.showRoutes || localScale) return;
    const destinations = new Set(
      props.edges.filter((e) => e.is_emerging).map((e) => e.to),
    );
    const markers = props.countries
      .filter((c) => destinations.has(c.iso3) && c.lon != null && c.lat != null)
      .map((c) => {
        const el = document.createElement("div");
        el.className = "emerging-beacon";
        el.setAttribute("aria-hidden", "true");
        el.innerHTML = "<span></span>";
        return new maplibregl.Marker({ element: el })
          .setLngLat([c.lon!, c.lat!])
          .addTo(m);
      });
    return () => markers.forEach((marker) => marker.remove());
  }, [props.edges, props.countries, props.showRoutes, ready, localScale]);
  useEffect(() => {
    const e = props.selectedEvent,
      m = map.current;
    if (!ready || !m || !e || e.lon == null || e.lat == null) return;
    const el = document.createElement("div");
    el.className = "map-beacon";
    el.innerHTML =
      '<div class="signal-beacon" aria-hidden="true"><div class="signal-ring"><img src="/figma/signal-ring.svg" alt=""/></div><img class="signal-carrier" src="/figma/signal-carrier.svg" alt=""/><img class="signal-core" src="/figma/signal-core.svg" alt=""/></div>';
    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([e.lon, e.lat])
      .addTo(m);
    m.flyTo({ center: [e.lon, e.lat], zoom: 5, duration: 1000 });
    return () => {
      marker.remove();
    };
  }, [props.selectedEvent, ready]);
  return (
    <div
      className="map-stage"
      aria-label="Interactive world map"
      onMouseLeave={() => {
        setHover(null);
        setReportHover(null);
      }}
    >
      <div className="map-canvas" ref={host} />
      {!ready && !error && (
        <div className="map-loading">
          <span>Loading map</span>
        </div>
      )}
      {error && <div className="map-error">{error}</div>}
      {(props.showRoutes || props.showEvidence) && (
        <div className="map-route-scale" role="status">
          {localScale
            ? "City scale: this atlas has no sourced city-to-city route links"
            : position.zoom < 2.2
              ? `${props.showRoutes ? visibleEdges.length : 0} of ${props.edges.length} modeled · zoom for dated reports`
              : `${props.showRoutes ? visibleEdges.length : 0} modeled · ${visibleDirect.length} reported pairs · ${visibleInterpreted.length} interpreted corridors · ${position.zoom < 3.4 ? "regional" : "country"} view`}
        </div>
      )}
      {reportDetail && visibleReports.some((route) => route.id === reportDetail.id) && (
        <section
          className={`map-report-detail${reportDetail.pair_type === "interpreted_corridor" ? " interpreted" : ""}`}
          aria-label="Published route evidence"
        >
          <button type="button" aria-label="Close route evidence" onClick={() => setReportDetail(null)}>×</button>
          <b>{reportDetail.from} → {reportDetail.to}</b>
          <span>{reportDetail.drug} · {pairTypeLabel[reportDetail.pair_type]}</span>
          <p>
            {evidencePeriod(reportDetail)} · {reportDetail.basis}. {reportDetail.caveat}
          </p>
          <a href={reportDetail.source.url} target="_blank" rel="noreferrer">
            {reportDetail.source.publisher} · {reportDetail.source_locator} ↗
          </a>
          {reportDetail.citations.map((c) =>
            c.url ? (
              <a key={c.key} href={c.url} target="_blank" rel="noreferrer">
                Cites {c.publisher}: {c.title} ↗
              </a>
            ) : (
              <small key={c.key}>Cites {c.publisher}: {c.title} (no URL on file)</small>
            ),
          )}
        </section>
      )}
      {!localScale && props.showDots && (props.colorBy === "volume" ? props.edges.length > 0 : props.risk.length > 0) && (
        <div
          className="map-legend"
          title="Texture density and color encode country exposure, not local observations. Country links join representative coordinates. Both fade at local scales."
        >
          <span>{props.colorBy === "volume" ? "Modeled drug volume" : props.exposureLabel}</span>
          <img src="/figma/exposure-strip.svg" alt={props.colorBy === "volume" ? "Modeled drug volume, low to high (log scale)" : "Exposure index, 0 to 100"} />
          {props.colorBy === "volume" ? (
            <div>
              <span>less</span>
              <span>kg, log</span>
              <span>more</span>
            </div>
          ) : (
            <div>
              <span>0</span>
              <span>50</span>
              <span>100</span>
            </div>
          )}
          {props.showEstimated && (
            <small className="legend-estimated">▲ faint arrows: estimated local flows (not observed)</small>
          )}
        </div>
      )}
      <div className="map-tools">
        <button aria-label="Zoom in" onClick={() => map.current?.zoomIn()}>
          <Plus size={17} />
        </button>
        <button aria-label="Zoom out" onClick={() => map.current?.zoomOut()}>
          <Minus size={17} />
        </button>
        <button
          aria-label="Reset map view"
          onClick={() => {
            if (map.current) fitWorld(map.current);
          }}
        >
          <RotateCcw size={16} />
        </button>
        <button
          aria-label="Focus selected country"
          disabled={!props.selected}
          onClick={() => {
            const c = props.countries.find((c) => c.iso3 === props.selected);
            if (c?.lon != null && c.lat != null)
              map.current?.flyTo({
                center: [c.lon, c.lat],
                zoom: 8,
                duration: 1000,
              });
          }}
        >
          <LocateFixed size={17} />
        </button>
      </div>
      <output className="map-position" aria-label="Map center and zoom">
        {Math.abs(position.lat).toFixed(3)}°{position.lat < 0 ? "S" : "N"} /{" "}
        {Math.abs(position.lng).toFixed(3)}°{position.lng < 0 ? "W" : "E"}
        <span>z{position.zoom.toFixed(1)}</span>
      </output>
      {hover && (
        <div
          className="route-tooltip"
          style={{
            left: Math.max(
              12,
              Math.min(hover.x + 16, (host.current?.clientWidth ?? 800) - 260),
            ),
            top: Math.max(12, hover.y - 120),
          }}
        >
          <strong>
            {hover.edge.from} → {hover.edge.to}
          </strong>
          <div>
            {hover.edge.drug} · modeled corridor · {hover.edge.confidence}% evidence score
          </div>
          <p>
            {formatNumber(hover.edge.kg)} kg estimated seizure scale ·{" "}
            {hover.edge.volume_norm.toFixed(2)} normalized
          </p>
          <small>kg {kgBasisNote(hover.edge.kg_basis)}</small>
          {(() => {
            const linked = evidenceForEdge(evidence, hover.edge);
            const direct = linked.filter((r) => r.pair_type === "direct_reported_pair");
            const interpreted = linked.length - direct.length;
            return (
              <>
                {direct.slice(0, 1).map((route) => (
                  <small key={route.id}>Reported country pair: {route.source.publisher} ({route.source.publication_year})</small>
                ))}
                {interpreted > 0 && (
                  <small>
                    {interpreted} TRACE-interpreted corridor record{interpreted > 1 ? "s" : ""} (regional maps and text)
                  </small>
                )}
              </>
            );
          })()}
          {hover.edge.drivers.slice(0, 3).map((d) => (
            <small key={d.feature}>{d.label}</small>
          ))}
        </div>
      )}
      {windHover && !hover && !reportHover && (
        <div
          className="route-tooltip"
          style={{
            left: Math.max(12, Math.min(windHover.x + 16, (host.current?.clientWidth ?? 800) - 260)),
            // Open below the cursor near the top edge (clear of the map toolbar).
            top: windHover.y < 190 ? windHover.y + 18 : windHover.y - 170,
          }}
        >
          <strong>Estimated local flow</strong>
          <div>
            {windHover.glyph.drug} · toward {windHover.glyph.flows[0]?.to.name}
          </div>
          <p>
            Not observed. Follows money (city population × GDP per capita) out of cities that modeled corridors feed.
            {props.estimated && !props.estimated.live ? " Precomputed snapshot." : ""}
          </p>
          <small>Biggest paths nearby</small>
          {nearestBigPaths(windHover.glyph.position, estimatedFlows).map(({ flow, drugs, distanceKm }) => (
            <small key={`${flow.from.iso3}${flow.from.name}${flow.to.name}`}>
              {flow.from.name} → {flow.to.name} · {drugs.join(", ")} · strength {flow.strength.toFixed(2)} ·{" "}
              {distanceKm < 10 ? "here" : `${Math.round(distanceKm)} km away`}
            </small>
          ))}
        </div>
      )}
      {usHover && !hover && (
        <div
          className="route-tooltip"
          style={{
            left: Math.max(12, Math.min(usHover.x + 16, (host.current?.clientWidth ?? 800) - 260)),
            top: usHover.y < 190 ? usHover.y + 18 : usHover.y - 150,
          }}
        >
          <strong>
            {usHover.route.from.name} → {usHover.route.to.name}
          </strong>
          <div>
            {usHover.route.drug} · documented route · {usHover.route.precision === "city" ? "city level" : "state level"}
          </div>
          <p>“{usHover.route.source.quote.length > 160 ? `${usHover.route.source.quote.slice(0, 157)}…` : usHover.route.source.quote}”</p>
          <small>
            {basisLabel[usHover.route.basis]} · {usHover.route.source.publisher} ({usHover.route.source.year}) · click for source
          </small>
        </div>
      )}
      {usDetail && (
        <section className="map-report-detail" aria-label="Documented US route source">
          <button type="button" aria-label="Close route source" onClick={() => setUsDetail(null)}>×</button>
          <b>{usDetail.from.name} → {usDetail.to.name}</b>
          <span>
            {usDetail.drug} · {basisLabel[usDetail.basis]}
            {usDetail.period ? ` · ${usDetail.period[0]}${usDetail.period[1] !== usDetail.period[0] ? `–${usDetail.period[1]}` : ""}` : ""}
          </span>
          <p>“{usDetail.source.quote}” {usDetail.precision === "city" ? "" : "Placed at state level, as the source names states."}</p>
          <a href={usDetail.source.url} target="_blank" rel="noreferrer">
            {usDetail.source.publisher}, {usDetail.source.title} ({usDetail.source.year}) · {usDetail.source.locator} ↗
          </a>
        </section>
      )}
      {reportHover && (
        <div className="route-tooltip" style={{
          left: Math.max(12, Math.min(reportHover.x + 16, (host.current?.clientWidth ?? 800) - 260)),
          top: Math.max(12, reportHover.y - 110),
        }}>
          <strong>{reportHover.route.from} → {reportHover.route.to}</strong>
          <div>{reportHover.route.drug} · {pairTypeLabel[reportHover.route.pair_type]}</div>
          <p>{evidencePeriod(reportHover.route)} · {reportHover.route.source.publisher}</p>
          <small>Click for source and limitations</small>
        </div>
      )}
    </div>
  );
}
