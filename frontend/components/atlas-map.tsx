// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { MapLibreOverlay } from "@deck.gl/maplibre";
import { ArcLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Color, PickingInfo } from "@deck.gl/core";
import type { FeatureCollection, Geometry } from "geojson";
import { LocateFixed, Minus, Plus, RotateCcw } from "lucide-react";
import type { Country, Edge, LiveEvent, RiskRow } from "@/lib/types";
import { drugColor, formatNumber } from "@/lib/api";
import { visibleModelRoutes } from "@/lib/route-visibility";
interface Props {
  countries: Country[];
  edges: Edge[];
  risk: RiskRow[];
  selected: string | null;
  selectedEvent: LiveEvent | null;
  showDots: boolean;
  showRoutes: boolean;
  exposureLabel: string;
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
  const [geography, setGeography] = useState<{
    geo: FeatureCollection<Geometry>;
    style: maplibregl.StyleSpecification;
  } | null>(null);
  const [position, setPosition] = useState({ lng: 0, lat: 0, zoom: 1 });
  const localScale = position.zoom >= 6;
  const countryByIso = useMemo(
    () => new Map(props.countries.map((country) => [country.iso3, country])),
    [props.countries],
  );
  const visibleEdges = useMemo(
    () => visibleModelRoutes(props.edges, countryByIso, position.zoom),
    [props.edges, countryByIso, position.zoom],
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
    m.on("movestart", () => setHover(null));
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
    for (const row of props.risk) {
      const band = Math.min(5, Math.floor(row.exposure / (100 / 6)));
      pattern.push(row.iso3, `exposure-${band}`);
      colors.push(row.iso3, exposureColors[band]);
    }
    pattern.push("exposure-none");
    colors.push("#fbfcfe");
    m.setPaintProperty(
      "exposure-stipple",
      "fill-pattern",
      props.risk.length
        ? (pattern as maplibregl.ExpressionSpecification)
        : "exposure-none",
    );
    m.setPaintProperty(
      "exposure-tone",
      "fill-color",
      props.risk.length
        ? (colors as maplibregl.ExpressionSpecification)
        : "#fbfcfe",
    );
    for (const id of ["exposure-stipple", "exposure-tone"])
      m.setLayoutProperty(
        id,
        "visibility",
        props.showDots ? "visible" : "none",
      );
  }, [ready, props.risk, props.showDots]);
  useEffect(() => {
    if (!ready || !overlay.current) return;
    const active = new Set(visibleEdges.flatMap((e) => [e.from, e.to]));
    const hubs = props.countries.filter(
      (c) => active.has(c.iso3) && c.lon != null && c.lat != null,
    );
    const point = (c: Country): [number, number] => [c.lon!, c.lat!];
    overlay.current.setProps({
      layers: [
        new ArcLayer<Edge>({
          id: "route-arcs",
          data: props.showRoutes ? visibleEdges : [],
          opacity: Math.max(0, Math.min(1, (6 - position.zoom) / 2)),
          getSourcePosition: (e) => point(countryByIso.get(e.from)!),
          getTargetPosition: (e) => point(countryByIso.get(e.to)!),
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
            setHover(
              info.object ? { edge: info.object, x: info.x, y: info.y } : null,
            ),
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
        new ScatterplotLayer<Country>({
          id: "route-hubs",
          data: props.showRoutes && !localScale ? hubs : [],
          opacity: Math.max(0, Math.min(1, (6 - position.zoom) / 2)),
          getPosition: point,
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
    countryByIso,
    visibleEdges,
    props.selected,
    props.showRoutes,
    position.zoom,
    localScale,
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
      onMouseLeave={() => setHover(null)}
    >
      <div className="map-canvas" ref={host} />
      {!ready && !error && (
        <div className="map-loading">
          <span>Loading map</span>
        </div>
      )}
      {error && <div className="map-error">{error}</div>}
      {props.showRoutes && props.edges.length > 0 && (
        <div className="map-route-scale" role="status">
          {localScale
            ? "City scale: no verified city-to-city route observations"
            : `${visibleEdges.length} of ${props.edges.length} modeled country corridors shown · ${position.zoom < 1.7 ? "world" : position.zoom < 3.4 ? "regional" : "country"} view`}
        </div>
      )}
      {!localScale && props.showDots && props.risk.length > 0 && (
        <div
          className="map-legend"
          title="Texture density and color encode country exposure, not local observations. Country links join representative coordinates. Both fade at local scales."
        >
          <span>{props.exposureLabel}</span>
          <img src="/figma/exposure-strip.svg" alt="Exposure index, 0 to 100" />
          <div>
            <span>0</span>
            <span>50</span>
            <span>100</span>
          </div>
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
          {hover.edge.drivers.slice(0, 3).map((d) => (
            <small key={d.feature}>{d.label}</small>
          ))}
        </div>
      )}
    </div>
  );
}
