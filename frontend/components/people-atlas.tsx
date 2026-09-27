// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, ZoomIn, ZoomOut } from "lucide-react";
import * as maplibregl from "maplibre-gl";
import { loadPeople, loadPeopleCountryCounts, loadPersonNetwork } from "@/lib/people-api";
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
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [countryCounts, setCountryCounts] = useState<{ iso3: string; total: number; visible: number }[] | null | undefined>();
  const searching = query.trim().length > 0;
  const requestZoom = searching || selectedCountry ? 3 : zoom;
  const requestBounds = searching || selectedCountry ? undefined : bounds;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [publishedTotal, setPublishedTotal] = useState<number | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [graphShownCount, setGraphShownCount] = useState(30);
  const filterKey = JSON.stringify([query, requestZoom, requestBounds, selectedCountry]);
  const filterKeyRef = useRef(filterKey);
  filterKeyRef.current = filterKey;

  useEffect(() => {
    let active = true;
    void loadPeople({ zoom: 3, limit: 1 }).then((result) => {
      if (active) setPublishedTotal(result.status === "ready" ? result.total : null);
    });
    return () => { active = false; };
  }, []);

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
    setCountryCounts(undefined);
    void loadPeopleCountryCounts(query, zoom).then((counts) => { if (active) setCountryCounts(counts); });
    return () => { active = false; };
  }, [query, zoom]);

  useEffect(() => {
    let active = true;
    setDataset(null);
    setTotal(null);
    setNextCursor(null);
    setLoadingMore(false);
    const timer = setTimeout(() => {
      void loadPeople({ search: query, country: selectedCountry ?? undefined, zoom: requestZoom, bounds: requestBounds, limit: 100 }).then((result) => {
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
  }, [query, selectedCountry, requestZoom, requestBounds]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    const requestedKey = filterKey;
    setLoadingMore(true);
    const result = await loadPeople({ search: query, country: selectedCountry ?? undefined, zoom: requestZoom, bounds: requestBounds, limit: 100, cursor: nextCursor });
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
  const selectedCountryName = selectedCountry ? countryById.get(selectedCountry)?.name ?? selectedCountry : null;
  const mapBounds = mapRef.current?.getBounds();
  const trayEntries = zoom === 3 && mapReady ? matching.flatMap((person) => {
    const region = person.regions.find((item) => {
      if (selectedCountry && item.iso3 !== selectedCountry) return false;
      const country = countryById.get(item.iso3);
      return country?.lat != null && country.lon != null && mapBounds?.contains([country.lon, country.lat]);
    });
    return region ? [{ person, region }] : [];
  }).sort((a, b) => a.person.prominence - b.person.prominence || a.person.name.localeCompare(b.person.name)) : [];
  const trayShown = trayEntries.slice(0, 48);
  if (selected && !trayShown.some(({ person }) => person.id === selected.id)) {
    const region = selected.regions.find((item) => {
      if (selectedCountry && item.iso3 !== selectedCountry) return false;
      const country = countryById.get(item.iso3);
      return country?.lat != null && country.lon != null && mapBounds?.contains([country.lon, country.lat]);
    });
    if (region) trayShown.push({ person: selected, region });
  }

  useEffect(() => { setGraphShownCount(30); }, [query]);

  const choosePerson = (person: Person, focusIso3?: string) => {
    setSelectedId(person.id);
    setMode("map");
    const region = person.regions.find((item) => item.iso3 === focusIso3 && countryById.has(item.iso3)) ?? person.regions.find((item) => countryById.has(item.iso3));
    const country = region ? countryById.get(region.iso3) : undefined;
    if (country?.lat != null && country.lon != null) {
      mapRef.current?.flyTo({ center: [country.lon, country.lat], zoom: Math.max(mapRef.current.getZoom(), 5.2), duration: 550 });
    }
  };

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    const mapBounds = map.getBounds();
    for (const count of countryCounts ?? []) {
      if (count.visible === 0) continue;
      const country = countryById.get(count.iso3);
      if (!country || country.lat == null || country.lon == null || !mapBounds.contains([country.lon, country.lat])) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `people-map-cluster${count.iso3 === selectedCountry ? " selected" : ""}`;
      button.setAttribute("aria-label", `${country.name}: ${count.visible} people visible at this zoom, ${count.total} matching all zoom levels. Open country records.`);
      const number = document.createElement("span");
      number.textContent = String(count.visible);
      const label = document.createElement("small");
      label.textContent = count.total === count.visible ? country.name : `${country.name} · ${count.total} all tiers`;
      button.append(number, label);
      button.addEventListener("click", () => {
        setSelectedCountry(count.iso3);
        map.flyTo({ center: [country.lon!, country.lat!], zoom: Math.max(map.getZoom(), 5.2), duration: 550 });
      });
      markersRef.current.push(new maplibregl.Marker({ element: button, anchor: "center" }).setLngLat([country.lon, country.lat]).addTo(map));
    }
  }, [mapReady, selectedCountry, countryById, countryCounts, bounds]);

  useEffect(() => {
    if (mode === "map") requestAnimationFrame(() => mapRef.current?.resize());
  }, [mode]);

  const selectedNetwork = network?.people.some((person) => person.id === selectedId) ? network : null;
  const graphData = selectedNetwork ?? dataset ?? { people: [], organizations: [], connections: [] };

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
      <span className="people-result-count">{personCount.toLocaleString()}{total === null ? " loaded people · matching total unavailable" : ` of ${total.toLocaleString()} matching people`} · {publishedTotal === null ? "published total unavailable" : `${publishedTotal.toLocaleString()} published people, all tiers`} · {dataset?.connections.length.toLocaleString() ?? "—"} loaded claims</span>
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
          <div className="people-map-legend">Circles mark country associations only, never cities or live positions. Open a country to page through all tiers.</div>
          {countryCounts === null && <div className="people-map-count-warning">Country totals unavailable from this API.</div>}
        </div>
        {zoom === 3 && trayShown.length > 0 && <section className="people-country-tray" aria-label="People with country-level associations">
          <div className="people-country-tray-heading"><div><h2>{selectedCountryName ?? "People in the visible countries"}</h2><p>Country association only · Portraits are not placed at city or street locations.</p></div><span>{trayShown.length} shown{trayEntries.length > 48 ? ` of ${trayEntries.length} loaded here` : ""}</span></div>
          <div className="people-country-tray-grid">{trayShown.map(({ person, region }) => <button key={person.id} className={person.id === selectedId ? "selected" : ""} onClick={() => choosePerson(person, region.iso3)} aria-label={`Review ${person.name}, ${STATUS_LABEL[person.status]}, ${person.statusAsOf ? `as of ${person.statusAsOf}` : "status date not provided"}, associated with ${region.label} at country level`}>
            <span className="people-country-tray-avatar">{person.photo ? <img src={person.photo.url} alt="" loading="lazy" /> : person.name.slice(0, 1).toUpperCase()}</span>
            <span className="people-country-tray-copy"><strong>{person.name}</strong><small>{region.label}</small><span className="people-country-tray-legal"><span className={`people-status status-${person.status}`}>{STATUS_LABEL[person.status]}</span><small>{person.statusAsOf ? `as of ${person.statusAsOf}` : "date unavailable"}</small></span></span>
          </button>)}</div>
          {(trayEntries.length > 48 || nextCursor) && <p className="people-country-tray-overflow">Cards are limited to 48 loaded people plus the selected person. Use the paged records below to reach everyone.</p>}
        </section>}
        {dataset ? <>
          {selectedCountryName && <div className="people-country-filter"><span>All sourced people associated with {selectedCountryName} · {total?.toLocaleString() ?? "total unavailable"}</span><button onClick={() => setSelectedCountry(null)}>Clear country</button></div>}
          <div className="people-list">
            {matching.map((person) => <button key={person.id} className={selectedId === person.id ? "selected" : ""} onClick={() => choosePerson(person)}>
              <span className="people-avatar">{person.name.slice(0, 1).toUpperCase()}</span>
              <span className="people-list-name">{person.name}<small>{person.regions.map((region) => region.label).join(" · ") || "Geography not specified"}</small></span>
              <span className="people-list-status"><span className={`people-status status-${person.status}`}>{STATUS_LABEL[person.status]}</span>{person.statusAsOf && <small>as of {person.statusAsOf}</small>}</span>
            </button>)}
            {nextCursor && <button className="people-load-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Loading…" : "Load more people"}</button>}
            {matching.length === 0 && <p>{selectedCountry ? `No sourced people match ${selectedCountryName}${searching ? " and this name or alias" : ""}.` : searching ? "No sourced people match this name or alias." : "No sourced people match the current zoom and map area."}</p>}
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
          {!!selected.regions.length && <div className="people-associations">
            <h3>Historical country associations</h3>
            <ul>{selected.regions.map((region) => {
              const source = selected.sources.find((item) => item.url === region.evidence?.sourceUrl);
              return <li key={region.iso3}>
                <strong>{region.label}</strong>{region.evidence?.period && <span> · {region.evidence.period}</span>}
                <p>{region.evidence?.claim ?? "Direct country evidence review pending."}</p>
                {source && <a href={source.url} target="_blank" rel="noreferrer">Source: {source.publisher}{source.publishedAt ? ` · ${source.publishedAt}` : ""}</a>}
              </li>;
            })}</ul>
            <p>Country-level associations only; these markers do not show live positions.</p>
          </div>}
          {!!selected.drugs.length && <p>Source topics: {selected.drugs.join(", ")}</p>}
      {selected.roleLabel && <p className="people-role-attribution">Role description attributed to the cited sources.</p>}
      {!!selected.organizationIds.length && <div className="people-orgs"><h3>Source-reported organization associations</h3>{selected.organizationIds.map((id) => organizations.get(id)?.name).filter(Boolean).map((name) => <span key={name}>{name}</span>)}</div>}
          {selected.photo && <figure className="people-portrait"><img src={selected.photo.url} alt={`Portrait of ${selected.name}`} loading="lazy" /><figcaption>Photo: {selected.photo.credit} · {selected.photo.licenseUrl ? <a href={selected.photo.licenseUrl} target="_blank" rel="noreferrer">{selected.photo.license}</a> : selected.photo.license} · <a href={selected.photo.sourceUrl} target="_blank" rel="noreferrer">file and attribution record</a></figcaption></figure>}
          <PeopleEventTimeline events={selected.events ?? []} />
          <div className="people-sources"><h3>Sources</h3>{selected.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer"><strong>{source.title}</strong><span>{source.publisher} · {source.language}{source.publishedAt ? ` · ${source.publishedAt}` : ""}</span><small>{source.claim}</small></a>)}</div>
          <p className="people-caution people-detail-caution">A listed connection is a source claim, not proof of guilt.</p>
        </> : <div className="people-detail-empty">Select a person from the country association tray or records to review status and sources.</div>}
      </aside>
    </div><div className="people-graph-panel" style={{ display: mode === "graph" ? undefined : "none" }}>
      {searching && dataset && <section className="people-graph-results" aria-label="Matching people for Connections view">
        <div className="people-graph-results-heading"><strong>Matching people</strong><span>{matching.length} loaded{total !== null ? ` of ${total} matches` : ""}</span></div>
        <div className="people-graph-results-list">{matching.slice(0, graphShownCount).map((person) => <button key={person.id} className={person.id === selectedId ? "selected" : ""} onClick={() => { setNetwork(null); setSelectedId(person.id); }}><strong>{person.name}</strong><span>{STATUS_LABEL[person.status]}{person.statusAsOf ? ` · as of ${person.statusAsOf}` : ""}</span></button>)}</div>
        {matching.length > graphShownCount && <button className="people-graph-results-more" onClick={() => setGraphShownCount((current) => current + 30)}>Show more loaded matches</button>}
        {nextCursor && <button className="people-graph-results-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Loading…" : "Load more matching people"}</button>}
        {matching.length === 0 && <p>No sourced people match this name or alias.</p>}
      </section>}
      {dataset && selectedId ? <PeopleGraph dataset={graphData} selectedId={selectedId} totalConnections={selectedNetwork ? networkClaimTotal : null} evidenceLoaded={selectedNetwork !== null} onSelect={(person) => setSelectedId(person.id)} /> : <div className="people-graph-empty">Select a person from the sourced records to show their documented connection claims.</div>}
      {selected && <><div className="people-graph-status"><span className={`people-status status-${selected.status}`}>{STATUS_LABEL[selected.status]}</span><span>{selected.name}{selected.statusAsOf ? ` · as of ${selected.statusAsOf}` : ""}</span></div><PeopleEventTimeline events={selected.events ?? []} /></>}
    </div></>
    <footer className="people-footer">{loadState} · Individual records and connection claims require cited sources. Map circles represent country-level associations; person portraits appear in a non-geographic tray. {selectedCountry ? "Country lists page through every prominence tier." : searching ? "Name searches cover all published records, regardless of map area or zoom." : "List totals apply to the current zoom and map area; country circles count the zoom tier across the full published dataset."}</footer>
  </section>;
}
