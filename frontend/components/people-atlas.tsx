// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, ZoomIn, ZoomOut } from "lucide-react";
import * as maplibregl from "maplibre-gl";
import { loadPeople, loadPersonNetwork } from "@/lib/people-api";
import type { PeopleCountry, PeopleDataset, Person, PersonEvent, PersonEventType, PersonStatus } from "@/lib/people-types";
import { PeopleGraph } from "./people-graph";
import "./people-atlas.css";

const STATUS_LABEL: Record<PersonStatus, string> = {
  convicted: "Convicted",
  charged: "Charged",
  sanctioned: "Sanctioned",
  reported: "Reported by cited source",
};

const EVENT_LABEL: Record<PersonEventType, string> = {
  arrest: "Arrest",
  charge: "Charge",
  conviction: "Conviction",
  sentence: "Sentence",
  sanction: "Sanction",
  development: "Development",
};

function PeopleEventTimeline({ events }: { events: PersonEvent[] }) {
  if (!events.length) return <p className="people-events-empty">No dated event history has been verified for this record yet.</p>;
  return <section className="people-events" aria-label="Documented event history">
    <h3>Documented history</h3>
    <ol>{events.map((event) => <li key={event.id}>
      <div className="people-event-meta"><time dateTime={event.occurredAt}>{event.occurredAt}</time><span>{EVENT_LABEL[event.type]}</span></div>
      <strong>{event.title}</strong>
      <p>{event.summary}</p>
      <a href={event.source.url} target="_blank" rel="noreferrer">{event.source.publisher}: {event.source.title}</a>
    </li>)}</ol>
  </section>;
}

interface PeopleAtlasProps {
  countries: PeopleCountry[];
}

function hash(value: string) {
  let result = 0;
  for (let index = 0; index < value.length; index++) result = (result * 31 + value.charCodeAt(index)) | 0;
  return Math.abs(result);
}

export function PeopleAtlas({ countries }: PeopleAtlasProps) {
  const mapHost = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [bounds, setBounds] = useState<[number, number, number, number] | undefined>();
  const [dataset, setDataset] = useState<PeopleDataset | null>(null);
  const [network, setNetwork] = useState<PeopleDataset | null>(null);
  const [networkClaimTotal, setNetworkClaimTotal] = useState<number | null>(null);
  const [loadState, setLoadState] = useState("Loading sourced records…");
  const [mode, setMode] = useState<"map" | "graph">("map");
  const [zoom, setZoom] = useState<1 | 2 | 3>(1);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const filterKey = JSON.stringify([query, zoom, bounds]);
  const filterKeyRef = useRef(filterKey);
  filterKeyRef.current = filterKey;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all(["/geo/countries.json", "/geo/basemap.json"].map(async (path) => {
      const response = await fetch(path, { signal: controller.signal });
      if (!response.ok) throw new Error("Map data unavailable");
      return response.json();
    })).then(([geo, style]) => {
      if (!mapHost.current || controller.signal.aborted) return;
      try {
        maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");
        const mapStyle = structuredClone(style) as maplibregl.StyleSpecification;
        mapStyle.sources["people-countries"] = { type: "geojson", data: geo, promoteId: "iso3" };
        mapStyle.layers.splice(1, 0, {
          id: "people-country-fill", type: "fill", source: "people-countries",
          paint: { "fill-color": "#f8fafc", "fill-opacity": 0.46 },
        });
        const map = new maplibregl.Map({
          container: mapHost.current,
          style: mapStyle,
          center: [8, 15],
          zoom: 0.7,
          minZoom: -1,
          maxZoom: 10,
          renderWorldCopies: true,
          dragRotate: false,
          pitchWithRotate: false,
          attributionControl: { compact: true },
        });
        mapRef.current = map;
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
        const updateZoom = () => {
          const value = map.getZoom();
          setZoom(value < 3 ? 1 : value < 5 ? 2 : 3);
        };
        const updateBounds = () => {
          const box = map.getBounds();
          const next: [number, number, number, number] = [box.getWest(), box.getSouth(), box.getEast(), box.getNorth()];
          setBounds((previous) => previous?.every((value, index) => Math.abs(value - next[index]) < 0.1) ? previous : next);
        };
        map.on("load", () => {
          map.resize();
          setMapReady(true);
          updateZoom();
          updateBounds();
        });
        map.on("zoomend", updateZoom);
        map.on("moveend", updateBounds);
        map.on("error", (event) => setMapError(event.error?.message ?? "Map could not load."));
      } catch (error) {
        setMapError(error instanceof Error ? error.message : "Map could not start.");
      }
    }).catch((error) => {
      if (!controller.signal.aborted) setMapError(error instanceof Error ? error.message : "Map data unavailable.");
    });
    return () => {
      controller.abort();
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setDataset(null);
    setTotal(null);
    setNextCursor(null);
    setLoadingMore(false);
    const timer = setTimeout(() => {
      void loadPeople({ search: query, zoom, bounds, limit: 100 }).then((result) => {
        if (!active) return;
        if (result.status === "ready") {
          setDataset(result.dataset);
          setTotal(result.total);
          setNextCursor(result.nextCursor);
          setLoadState(result.source === "fixtures" ? "Curated fixture results" : "Live API results");
        } else {
          setDataset(null);
          setLoadState(result.reason);
        }
      });
    }, query ? 200 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [query, zoom, bounds]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    const requestedKey = filterKey;
    setLoadingMore(true);
    const result = await loadPeople({ search: query, zoom, bounds, limit: 100, cursor: nextCursor });
    if (filterKeyRef.current !== requestedKey) return;
    setLoadingMore(false);
    if (result.status !== "ready") { setLoadState(result.reason); return; }
    setDataset((previous) => {
      if (!previous) return result.dataset;
      const peopleIds = new Set(previous.people.map((person) => person.id));
      const organizationIds = new Set(previous.organizations.map((organization) => organization.id));
      const connectionIds = new Set(previous.connections.map((connection) => connection.id));
      return {
        people: [...previous.people, ...result.dataset.people.filter((person) => !peopleIds.has(person.id))],
        organizations: [...previous.organizations, ...result.dataset.organizations.filter((organization) => !organizationIds.has(organization.id))],
        connections: [...previous.connections, ...result.dataset.connections.filter((connection) => !connectionIds.has(connection.id))],
      };
    });
    setTotal(result.total);
    setNextCursor(result.nextCursor);
  };

  useEffect(() => {
    if (!selectedId) { setNetwork(null); setNetworkClaimTotal(null); return; }
    let active = true;
    void loadPersonNetwork(selectedId).then((result) => {
      if (active) {
        setNetwork(result.status === "ready" ? result.dataset : null);
        setNetworkClaimTotal(result.status === "ready" ? result.totalConnections : null);
      }
    });
    return () => { active = false; };
  }, [selectedId]);

  const people = dataset?.people ?? [];
  const selected = network?.people.find((person) => person.id === selectedId) ?? people.find((person) => person.id === selectedId) ?? null;
  const countryById = useMemo(() => new Map(countries.map((country) => [country.iso3, country])), [countries]);
  const organizations = useMemo(() => new Map([...(dataset?.organizations ?? []), ...(network?.organizations ?? [])].map((item) => [item.id, item])), [dataset, network]);
  const matching = people;
  const personCount = dataset?.people.length ?? 0;

  const choosePerson = (person: Person) => {
    setSelectedId(person.id);
    setMode("map");
    const region = person.regions.find((item) => countryById.has(item.iso3));
    const country = region ? countryById.get(region.iso3) : undefined;
    if (country?.lat != null && country.lon != null) {
      mapRef.current?.flyTo({ center: [country.lon, country.lat], zoom: Math.max(mapRef.current.getZoom(), 4.5), duration: 550 });
    }
  };

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    const threshold = zoom === 1 ? 3 : zoom === 2 ? 2 : 1;
    const visible = matching.filter((person) => person.prominence >= threshold);
    const bounds = map.getBounds();
    if (zoom < 3) {
      const grouped = new Map<string, Person[]>();
      for (const person of visible) for (const region of person.regions) {
        const country = countryById.get(region.iso3);
        if (!country || country.lat == null || country.lon == null || !bounds.contains([country.lon, country.lat])) continue;
        const group = grouped.get(region.iso3) ?? [];
        group.push(person);
        grouped.set(region.iso3, group);
      }
      for (const [iso3, members] of grouped) {
        const country = countryById.get(iso3)!;
        const button = document.createElement("button");
        button.type = "button";
        button.className = `people-map-cluster${members.some((person) => person.id === selectedId) ? " selected" : ""}`;
        button.setAttribute("aria-label", `${country.name}: ${members.length} sourced people`);
        const count = document.createElement("span");
        count.textContent = String(members.length);
        const label = document.createElement("small");
        label.textContent = country.name;
        button.append(count, label);
        button.addEventListener("click", () => {
          if (members.length === 1) choosePerson(members[0]);
          else setSelectedId(members.sort((a, b) => b.prominence - a.prominence)[0].id);
          map.flyTo({ center: [country.lon!, country.lat!], zoom: Math.max(map.getZoom(), 4.5), duration: 550 });
        });
        markersRef.current.push(new maplibregl.Marker({ element: button, anchor: "center" }).setLngLat([country.lon!, country.lat!]).addTo(map));
      }
      return;
    }
    const individual = visible.flatMap((person) => person.regions.map((region) => ({ person, region })))
      .filter(({ region }) => {
        const country = countryById.get(region.iso3);
        return country?.lat != null && country.lon != null && bounds.contains([country.lon, country.lat]);
      })
      .sort((a, b) => b.person.prominence - a.person.prominence || a.person.name.localeCompare(b.person.name))
      .slice(0, 120);
    const offsets = new Map<string, number>();
    for (const { person, region } of individual) {
      const country = countryById.get(region.iso3)!;
      const index = offsets.get(region.iso3) ?? 0;
      offsets.set(region.iso3, index + 1);
      const angle = (hash(person.id) % 628) / 100;
      const radius = 5 + Math.sqrt(index) * 12;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `people-map-person${person.id === selectedId ? " selected" : ""}`;
      button.setAttribute("aria-label", `${person.name}, ${STATUS_LABEL[person.status]}`);
      if (person.photo) {
        const image = document.createElement("img");
        image.src = person.photo.url;
        image.alt = "";
        button.append(image);
      } else {
        const initial = document.createElement("span");
        initial.setAttribute("aria-hidden", "true");
        initial.textContent = person.name.slice(0, 1).toUpperCase();
        button.append(initial);
      }
      const label = document.createElement("small");
      label.textContent = person.name;
      button.append(label);
      button.addEventListener("click", () => choosePerson(person));
      markersRef.current.push(new maplibregl.Marker({
        element: button,
        anchor: "center",
        offset: [Math.cos(angle) * radius, Math.sin(angle) * radius],
      }).setLngLat([country.lon!, country.lat!]).addTo(map));
    }
  }, [dataset, matching, mapReady, selectedId, zoom, bounds, countryById]);

  useEffect(() => {
    if (mode === "map") requestAnimationFrame(() => mapRef.current?.resize());
  }, [mode]);

  const graphData = network ?? dataset ?? { people: [], organizations: [], connections: [] };

  return <section className="people-atlas" aria-labelledby="people-title">
    <header className="people-header">
      <div>
        <p className="people-kicker">Documented network evidence</p>
        <h1 id="people-title">People and connections</h1>
        <p>Browse people and relationships reported in cited public sources.</p>
      </div>
      <div className="people-mode" role="group" aria-label="People view mode">
        <button className={mode === "map" ? "active" : ""} aria-pressed={mode === "map"} onClick={() => setMode("map")}>Map</button>
        <button className={mode === "graph" ? "active" : ""} aria-pressed={mode === "graph"} onClick={() => setMode("graph")}>Connections</button>
      </div>
    </header>

    <p className="people-caution" role="note"><strong>Evidence caution.</strong> A listed connection is a claim from the cited sources, not proof of guilt. Status categories are kept distinct and reflect what the cited source establishes.</p>
    <div className="people-toolbar">
      <label className="people-search"><Search size={15} /><span className="sr-only">Search people</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search names and aliases" /></label>
      <span className="people-result-count">{personCount.toLocaleString()}{total === null ? " loaded people · total unavailable" : ` of ${total.toLocaleString()} matching people`} · {dataset?.connections.length.toLocaleString() ?? "—"} loaded claims</span>
      {mode === "map" && <div className="people-zoom" aria-label="Map zoom controls">
        <button aria-label="Zoom out" disabled={zoom === 1} onClick={() => mapRef.current?.zoomOut()}><ZoomOut size={16} /></button>
        <span>Zoom {zoom}/3</span>
        <button aria-label="Zoom in" disabled={zoom === 3} onClick={() => mapRef.current?.zoomIn()}><ZoomIn size={16} /></button>
      </div>}
    </div>

    <><div className="people-map-layout" style={{ display: mode === "map" ? undefined : "none" }}>
      <div className="people-map-panel">
        <div className="people-map" role="group" aria-label="Country-level geographic associations">
          <div className="people-map-canvas" ref={mapHost} />
          {!mapReady && <div className="people-map-loading" role="status">{mapError || "Loading map…"}</div>}
          <div className="people-map-legend">Country dots show documented geographic association. They do not show a person’s live position.</div>
        </div>
        {dataset ? <>
          <div className="people-list">
            {matching.map((person) => <button key={person.id} className={selectedId === person.id ? "selected" : ""} onClick={() => choosePerson(person)}>
              <span className="people-avatar">{person.name.slice(0, 1).toUpperCase()}</span>
              <span className="people-list-name">{person.name}<small>{person.regions.map((region) => region.label).join(" · ") || "Geography not specified"}</small></span>
              <span className={`people-status status-${person.status}`}>{STATUS_LABEL[person.status]}</span>
            </button>)}
            {nextCursor && <button className="people-load-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Loading…" : "Load more people"}</button>}
            {matching.length === 0 && <p>No sourced people match the current search, zoom and map area.</p>}
          </div>
        </> : <div className="people-empty" role="status">{loadState}</div>}
      </div>
      <aside className="people-detail" aria-label="Selected person details">
        {selected ? <>
          <div className="people-detail-top"><span>Source record</span><span className={`people-status status-${selected.status}`}>{STATUS_LABEL[selected.status]}</span></div>
          <h2>{selected.name}</h2>
          {selected.aliases?.length ? <p className="people-aliases">Also reported as {selected.aliases.join(", ")}</p> : null}
          <p className="people-status-date">{selected.statusAsOf ? `Status as of ${selected.statusAsOf}` : "Status date not provided by source"}</p>
          {selected.roleLabel && <p>{selected.roleLabel}</p>}
          {!!selected.regions.length && <p className="people-associations">Geographic associations: {selected.regions.map((region) => region.label).join(", ")}. These are country associations, not live positions.</p>}
          {!!selected.drugs.length && <p>Source topics: {selected.drugs.join(", ")}</p>}
      {selected.roleLabel && <p className="people-role-attribution">Role description attributed to the cited sources.</p>}
      {!!selected.organizationIds.length && <div className="people-orgs"><h3>Source-reported organization associations</h3>{selected.organizationIds.map((id) => organizations.get(id)?.name).filter(Boolean).map((name) => <span key={name}>{name}</span>)}</div>}
          {selected.photo && <figure className="people-portrait"><img src={selected.photo.url} alt={`Portrait of ${selected.name}`} loading="lazy" /><figcaption>Photo: {selected.photo.credit} · {selected.photo.license} · <a href={selected.photo.sourceUrl} target="_blank" rel="noreferrer">license record</a></figcaption></figure>}
          <PeopleEventTimeline events={selected.events ?? []} />
          <div className="people-sources"><h3>Sources</h3>{selected.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer"><strong>{source.title}</strong><span>{source.publisher} · {source.language}{source.publishedAt ? ` · ${source.publishedAt}` : ""}</span><small>{source.claim}</small></a>)}</div>
          <p className="people-caution people-detail-caution">A listed connection is a source claim, not proof of guilt.</p>
        </> : <div className="people-detail-empty">Select a person marker or record to review status and sources.</div>}
      </aside>
    </div><div className="people-graph-panel" style={{ display: mode === "graph" ? undefined : "none" }}>
      {dataset && selectedId ? <PeopleGraph dataset={graphData} selectedId={selectedId} totalConnections={networkClaimTotal} onSelect={(person) => setSelectedId(person.id)} /> : <div className="people-graph-empty">Select a person from the sourced records to show their documented connection claims.</div>}
      {selected && <><div className="people-graph-status"><span className={`people-status status-${selected.status}`}>{STATUS_LABEL[selected.status]}</span><span>{selected.name}{selected.statusAsOf ? ` · as of ${selected.statusAsOf}` : ""}</span></div><PeopleEventTimeline events={selected.events ?? []} /></>}
    </div></>
    <footer className="people-footer">{loadState} · Individual records and connection claims require cited sources. Map markers represent loaded records at country-level associations; totals apply to the current search, zoom and map area.</footer>
  </section>;
}
