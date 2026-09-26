// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import {useEffect,useRef,useState} from "react";
import * as maplibregl from "maplibre-gl";
import {MapLibreOverlay} from "@deck.gl/maplibre";
import {ArcLayer,ScatterplotLayer,TextLayer} from "@deck.gl/layers";
import type {Color,PickingInfo} from "@deck.gl/core";
import type {FeatureCollection,Geometry} from "geojson";
import {LocateFixed,Minus,Plus,RotateCcw} from "lucide-react";
import type {Country,Edge,LiveEvent,RiskRow} from "@/lib/types";
import {drugColor,formatNumber} from "@/lib/api";
type Dot=[number,number,string];
interface Props {countries:Country[]; edges:Edge[]; risk:RiskRow[]; selected:string|null; selectedEvent:LiveEvent|null; showDots:boolean; showRoutes:boolean; onCountry:(iso:string)=>void; onRoute:(edge:Edge)=>void; resetKey:number;}
const color=(h:string,a=255):Color=>[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16),a];
const exposureColor=(v:number):Color=>color(v>=85?"#a93c7d":v>=70?"#d44c3d":v>=55?"#ea7b32":v>=35?"#d9a954":"#d4c78d",205);
export default function AtlasMap(props:Props){
  const host=useRef<HTMLDivElement>(null), map=useRef<maplibregl.Map|null>(null), overlay=useRef<MapLibreOverlay|null>(null), latest=useRef(props);
  latest.current=props;
  const [ready,setReady]=useState(false), [error,setError]=useState<string|null>(null), [hover,setHover]=useState<{edge:Edge;x:number;y:number}|null>(null);
  const [geo,setGeo]=useState<FeatureCollection<Geometry>>(), [dots,setDots]=useState<Dot[]>([]);
  useEffect(()=>{
    let cancelled=false;
    Promise.all([fetch("/geo/countries.json").then(r=>{if(!r.ok)throw Error("Geography unavailable");return r.json()}),fetch("/geo/dots.json").then(r=>r.json())]).then(([g,d])=>{if(!cancelled){setGeo(g);setDots(d)}}).catch(e=>setError(e.message));
    return()=>{cancelled=true};
  },[]);
  useEffect(()=>{
    if(!host.current||!geo)return;
    let m:maplibregl.Map;
    try {maplibregl.setWorkerUrl("/vendor/maplibre/maplibre-gl-worker.mjs");m=new maplibregl.Map({container:host.current,center:[8,15],zoom:1.55,minZoom:.8,maxZoom:6.2,renderWorldCopies:false,attributionControl:false,dragRotate:false,pitchWithRotate:false,style:{version:8,sources:{countries:{type:"geojson",data:geo}},layers:[{id:"paper",type:"background",paint:{"background-color":"#f0eee5"}},{id:"land",type:"fill",source:"countries",paint:{"fill-color":"#e7e4d9","fill-opacity":.6}},{id:"country-boundaries",type:"line",source:"countries",paint:{"line-color":"#bbb9ac","line-opacity":.35,"line-width":.5}},{id:"selection",type:"line",source:"countries",filter:["==",["get","iso3"],""],paint:{"line-color":"#b14b34","line-width":1.5,"line-opacity":.85}}]}});
    } catch {setError("The map needs WebGL. Use the country search and risk board to continue.");return;}
    map.current=m;
    const o=new MapLibreOverlay({interleaved:false,layers:[]});overlay.current=o;m.addControl(o);
    m.on("load",()=>{setReady(true);m.resize()});
    m.on("click","land",e=>{const iso=e.features?.[0]?.properties.iso3;if(iso&&latest.current.countries.some(c=>c.iso3===iso))latest.current.onCountry(iso)});
    m.on("mouseenter","land",()=>{m.getCanvas().style.cursor="pointer"});m.on("mouseleave","land",()=>{m.getCanvas().style.cursor="grab"});
    m.on("error",e=>{if(e.error?.message?.includes("WebGL"))setError(e.error.message)});
    const resize=new ResizeObserver(()=>m.resize());resize.observe(host.current);
    return()=>{resize.disconnect();m.remove();map.current=null;overlay.current=null;setReady(false)};
  },[geo]);
  useEffect(()=>{
    if(!ready||!overlay.current||!geo)return;
    const countries=new Map(props.countries.map(c=>[c.iso3,c]));
    const risk=new Map(props.risk.map(r=>[r.iso3,r.exposure]));
    const edges=props.edges.filter(e=>countries.get(e.from)?.lon!=null&&countries.get(e.to)?.lon!=null);
    const active=new Set(edges.flatMap(e=>[e.from,e.to]));
    const hubs=props.countries.filter(c=>active.has(c.iso3)&&c.lon!=null&&c.lat!=null);
    const getPosition=(c:Country):[number,number]=>[c.lon!,c.lat!];
    const labels=geo.features.filter(f=>f.properties?.iso3!=="ATA"&&["USA","BRA","CAN","RUS","CHN","IND","AUS","ZAF","COL","MEX","IRN","MMR","FRA"].includes(f.properties?.iso3));
    overlay.current.setProps({layers:[
      new ScatterplotLayer<Dot>({id:"atlas-dots",data:props.showDots?dots:[],getPosition:d=>[d[0],d[1]],getRadius:18000,radiusUnits:"meters",radiusMinPixels:.65,radiusMaxPixels:3.5,getFillColor:d=>risk.has(d[2])?exposureColor(risk.get(d[2])!):color("#c8bf9b",140),updateTriggers:{getFillColor:[props.risk]},transitions:{getFillColor:600},pickable:false}),
      new ArcLayer<Edge>({id:"route-arcs",data:props.showRoutes?edges:[],getSourcePosition:e=>getPosition(countries.get(e.from)!),getTargetPosition:e=>getPosition(countries.get(e.to)!),getSourceColor:e=>color(drugColor[e.drug],Math.round(e.confidence*2.0)*(props.selected&&e.from!==props.selected&&e.to!==props.selected? .32:1)),getTargetColor:e=>color(drugColor[e.drug],Math.round(e.confidence*1.3)),getWidth:e=>.5+e.volume_norm*2.5,getHeight:.28,greatCircle:true,pickable:true,autoHighlight:true,highlightColor:[38,45,37,255],onHover:(info:PickingInfo<Edge>)=>setHover(info.object?{edge:info.object,x:info.x,y:info.y}:null),onClick:(info:PickingInfo<Edge>)=>{if(info.object){latest.current.onRoute(info.object);return true;}return false;},updateTriggers:{getSourceColor:[props.selected]},transitions:{getWidth:500}}),
      new ScatterplotLayer<Country>({id:"route-hubs",data:props.showRoutes?hubs:[],getPosition,getRadius:3.8,radiusUnits:"pixels",getFillColor:[244,241,230],stroked:true,getLineColor:[155,91,62],lineWidthUnits:"pixels",getLineWidth:1.2,pickable:true,onClick:({object}:PickingInfo<Country>)=>{if(object)latest.current.onCountry(object.iso3);return true;}}),
      new TextLayer({id:"country-labels",data:labels,getPosition:f=>[f.properties!.label_lon,f.properties!.label_lat],getText:f=>f.properties!.name.toUpperCase(),getSize:10,fontFamily:"forma-djr-text, sans-serif",getColor:[115,116,99,200],getTextAnchor:"middle",getAlignmentBaseline:"center",outlineWidth:2,outlineColor:[240,238,229],fontSettings:{sdf:true},pickable:false}),
    ]});
  },[ready,geo,dots,props.countries,props.edges,props.risk,props.selected,props.showDots,props.showRoutes]);
  useEffect(()=>{
    if(!ready||!map.current)return;
    map.current.setFilter("selection",["==",["get","iso3"],props.selected??""]);
    const c=props.countries.find(c=>c.iso3===props.selected);
    if(c?.lon!=null&&c.lat!=null)map.current.flyTo({center:[c.lon,c.lat],zoom:2.65,duration:1200,essential:false});
  },[props.selected,ready,props.countries]);
  useEffect(()=>{if(props.resetKey>0)map.current?.flyTo({center:[8,15],zoom:1.55,duration:1100})},[props.resetKey]);
  useEffect(()=>{
    const e=props.selectedEvent,m=map.current;if(!ready||!m||!e||e.lon==null||e.lat==null)return;
    const el=document.createElement("div");el.className="map-beacon";el.innerHTML='<img src="/figma/signal-beacon.svg" alt="Selected news event"/><span></span>';
    const marker=new maplibregl.Marker({element:el}).setLngLat([e.lon,e.lat]).addTo(m);m.flyTo({center:[e.lon,e.lat],zoom:3,duration:1200});
    return()=>{marker.remove()};
  },[props.selectedEvent,ready]);
  return <div className="map-stage" aria-label="Interactive world map"><div className="map-canvas" ref={host}/>
    {!ready&&!error&&<div className="map-loading"><img src="/figma/trace-mark.svg" alt=""/><span>Preparing the atlas…</span></div>}
    {error&&<div className="map-error">{error}</div>}
    <div className="map-tools"><button aria-label="Zoom in" onClick={()=>map.current?.zoomIn()}><Plus size={17}/></button><button aria-label="Zoom out" onClick={()=>map.current?.zoomOut()}><Minus size={17}/></button><button aria-label="Reset map view" onClick={()=>map.current?.flyTo({center:[8,15],zoom:1.55,duration:1000})}><RotateCcw size={16}/></button><button aria-label="Focus selected country" disabled={!props.selected} onClick={()=>{const c=props.countries.find(c=>c.iso3===props.selected);if(c?.lon!=null&&c.lat!=null)map.current?.flyTo({center:[c.lon,c.lat],zoom:3.5,duration:1000})}}><LocateFixed size={17}/></button></div>
    {hover&&<div className="route-tooltip" style={{left:Math.max(12,Math.min(hover.x+16,(host.current?.clientWidth??800)-260)),top:Math.max(12,hover.y-120)}}><strong>{hover.edge.from} <span>→</span> {hover.edge.to}</strong><div>{hover.edge.drug} · {hover.edge.confidence}% confidence</div><p>{formatNumber(hover.edge.kg)} kg · normalized volume {hover.edge.volume_norm.toFixed(2)}</p>{hover.edge.drivers[0]&&<small>{hover.edge.drivers[0].label}</small>}</div>}
    <div className="map-attribution"><a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a> · Country-level illustration</div>
  </div>;
}
