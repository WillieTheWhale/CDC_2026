# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Estimated local flows: a labelled, map-only layer that extends modeled corridors to nearby cities.

The route model works country to country, so zoomed-in views are sparse. This fills them with
*estimates*, drawn as faint wind-style arrows and never used in any score, count or ranking:

1. Every modeled edge (from A to B) delivers into an **entry city** in B: the city that maximises
   money / (distance from A's anchor + 300 km), i.e. a rich city on the side facing the route.
   Its supply is the edge weight, volume_norm x confidence / 100.
2. **Follow the money.** Every other city of 150k+ people is a target with money = population x
   GDP per capita (PPP, World Bank NY.GDP.PCAP.PP.KD, source 2). Each target draws one arrow from
   the source that maximises supply x money / (1 + km / 400)^2, within MAX_KM.
3. A **second wave** spreads from the cities reached in step 2 at half their strength, so the field
   extends into countries the dataset does not cover.
4. **City intensity** sums modeled supply and estimated strength through each city (darker where
   many paths cross).

Inputs are population, wealth, distance and modeled route density only. No enforcement,
customs or detection variable is used (design boundary). Cities: Natural Earth populated places
(public domain). Output: frontend/public/data/estimated/{mode}-{year}.json.
"""
from __future__ import annotations

import json
import logging
import math
import urllib.request
from collections import defaultdict

from .. import config, db

log = logging.getLogger(__name__)

CITIES_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
              "ne_10m_populated_places_simple.geojson")
CITIES_PATH = config.RAW / "natural_earth" / "ne_10m_populated_places_simple.geojson"
OUT_DIR = config.REPO / "frontend" / "public" / "data" / "estimated"
MIN_POP = 150_000
MAX_KM = 1_500          # estimates stay regional: "shallow" arrows, never new intercontinental routes
ENTRY_CANDIDATES = 15   # entry city chosen among the country's 15 richest cities
PER_DRUG = 260          # first-wave arrows kept per drug and year
SECOND_WAVE = 140       # second-wave arrows kept per drug and year
GDP_CODE = "NY.GDP.PCAP.PP.KD"


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def load_cities() -> list[dict]:
    if not CITIES_PATH.exists():
        CITIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading Natural Earth populated places")
        urllib.request.urlretrieve(CITIES_URL, CITIES_PATH)  # noqa: S310 (fixed https URL)
    out = []
    for f in json.loads(CITIES_PATH.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        if (p.get("pop_max") or 0) < MIN_POP or not p.get("adm0_a3"):
            continue
        out.append({"name": p["name"], "iso3": p["adm0_a3"], "pop": p["pop_max"],
                    "lon": round(p["longitude"], 4), "lat": round(p["latitude"], 4)})
    return out


def gdp_per_capita() -> dict[str, dict[int, float]]:
    """{iso3: {year: GDP per capita PPP}} from the archive (non-null values only)."""
    with db.connect(read_only=True) as con:
        rows = con.execute("SELECT iso3, year, value FROM archive.wb_indicators "
                           "WHERE code = ? AND source_id = 2 AND value IS NOT NULL", [GDP_CODE]).fetchall()
    out: dict[str, dict[int, float]] = defaultdict(dict)
    for iso3, year, value in rows:
        out[iso3][int(year)] = float(value)
    return out


def _wealth(series: dict[int, float], year: int, fallback: float) -> float:
    """Latest value at or before `year`, else the earliest after it, else the global median."""
    if not series:
        return fallback
    past = [y for y in series if y <= year]
    return series[max(past)] if past else series[min(series)]


def estimate(edges: list[dict], cities: list[dict], gdp: dict[str, dict[int, float]],
             anchors: dict[str, tuple[float, float]], year: int) -> dict:
    values = sorted(v for s in gdp.values() for v in s.values())
    median = values[len(values) // 2] if values else 10_000.0
    by_country: dict[str, list[dict]] = defaultdict(list)
    for c in cities:
        c = {**c, "money": c["pop"] * _wealth(gdp.get(c["iso3"], {}), year, median)}
        by_country[c["iso3"]].append(c)
    for lst in by_country.values():
        lst.sort(key=lambda c: -c["money"])
    all_cities = [c for lst in by_country.values() for c in lst]
    top_money = max((c["money"] for c in all_cities), default=1.0)
    key = lambda c: (c["iso3"], c["name"], c["lon"], c["lat"])  # noqa: E731

    flows: list[dict] = []
    intensity: dict[tuple, float] = defaultdict(float)
    city_of = {key(c): c for c in all_cities}
    for drug in sorted({e["drug"] for e in edges}):
        supply: dict[tuple, float] = defaultdict(float)
        for e in (e for e in edges if e["drug"] == drug):
            cands = by_country.get(e["to"], [])[:ENTRY_CANDIDATES]
            origin = anchors.get(e["from"])
            if not cands or origin is None:
                continue
            entry = max(cands, key=lambda c: c["money"] / (_km(origin, (c["lon"], c["lat"])) + 300))
            supply[key(entry)] += e["volume_norm"] * e["confidence"] / 100
        if not supply:
            continue
        hubs = [(city_of[k], s) for k, s in supply.items()]
        for k, s in supply.items():
            intensity[k] += s

        def wave(sources: list[tuple[dict, float]], taken: set, limit: int, generation: int,
                 drug: str = drug) -> list[dict]:
            best: dict[tuple, tuple[float, dict, float]] = {}
            for t in all_cities:
                kt = key(t)
                if kt in taken:
                    continue
                for src, s in sources:
                    if src is t:
                        continue
                    d = _km((src["lon"], src["lat"]), (t["lon"], t["lat"]))
                    if d > MAX_KM or d < 25:
                        continue
                    score = s * (t["money"] / top_money) / (1 + d / 400) ** 2
                    if kt not in best or score > best[kt][0]:
                        best[kt] = (score, src, d)
            chosen = sorted(best.items(), key=lambda kv: -kv[1][0])[:limit]
            out = []
            for kt, (score, src, d) in chosen:
                out.append({"drug": drug, "generation": generation, "score": score, "km": round(d),
                            "src": src, "dst": city_of[kt]})
            return out

        first = wave(hubs, set(supply), PER_DRUG, 1)
        taken = set(supply) | {key(f["dst"]) for f in first}
        top = max((f["score"] for f in first), default=1.0)
        second_sources = [(f["dst"], 0.5 * f["score"] / top * max(s for _, s in hubs)) for f in first]
        second = wave(second_sources, taken, SECOND_WAVE, 2)
        for f in first + second:
            flows.append(f)
    if flows:
        peak_by_drug: dict[str, float] = defaultdict(float)
        for f in flows:
            peak_by_drug[f["drug"]] = max(peak_by_drug[f["drug"]], f["score"])
        for f in flows:
            f["strength"] = round(math.sqrt(f["score"] / peak_by_drug[f["drug"]]), 3)
            intensity[key(f["src"])] += f["strength"] * 0.5
            intensity[key(f["dst"])] += f["strength"]
    peak = max(intensity.values(), default=1.0)
    # Compact, index-based format: each city once, each arrow a short tuple.
    drugs = sorted({f["drug"] for f in flows})
    idx: dict[tuple, int] = {}
    cities_out: list[list] = []
    for k in sorted(intensity, key=lambda k: -intensity[k]):
        idx[k] = len(cities_out)
        cities_out.append([k[1], k[0], k[2], k[3], round(intensity[k] / peak, 3)])
    return {
        "drugs": drugs,
        "city_fields": ["name", "iso3", "lon", "lat", "intensity"],
        "cities": cities_out,
        "flow_fields": ["drug", "generation", "strength", "from", "to", "km"],
        "flows": [[drugs.index(f["drug"]), f["generation"], f["strength"], idx[key(f["src"])], idx[key(f["dst"])],
                   f["km"]] for f in flows],
    }


def _anchors() -> dict[str, tuple[float, float]]:
    """Route anchors the map uses: Natural Earth label points (land-anchored), else World Bank capitals."""
    out = {c["iso3"]: (c["lon"], c["lat"]) for c in json.loads((config.API_DIR / "countries.json")
           .read_text(encoding="utf-8")) if c.get("lon") is not None}
    geo = config.REPO / "frontend" / "public" / "geo" / "countries.json"
    if geo.exists():
        for f in json.loads(geo.read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            if isinstance(p.get("label_lon"), (int, float)):
                out[p["iso3"]] = (p["label_lon"], p["label_lat"])
    return out


def run() -> int:
    cities, gdp, anchors = load_cities(), gdp_per_capita(), _anchors()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.json"):
        old.unlink()
    written = 0
    for mode in ("observed", "predicted"):
        routes = json.loads((config.API_DIR / f"routes_{mode}.json").read_text(encoding="utf-8"))
        for year, edges in sorted(routes.items()):
            body = estimate(edges, cities, gdp, anchors, int(year))
            doc = {"meta": {
                "kind": "estimated",
                "note": "Estimated local flows for map density only. Not observed, not modeled, not used in any score.",
                "method": "Entry city per modeled edge; arrows follow money = city population x GDP per capita "
                          f"(PPP), score = supply x money / (1 + km/400)^2, <= {MAX_KM} km, two waves.",
                "sources": ["Natural Earth populated places (public domain)",
                            f"World Bank Indicators API {GDP_CODE} (source 2)", "TRACE modeled corridors"],
                "variables": ["city population", "GDP per capita PPP", "great-circle distance", "modeled route density"],
            }, "data": {"year": int(year), "mode": mode, **body}}
            (OUT_DIR / f"{mode}-{year}.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False),
                                                       encoding="utf-8")
            written += 1
            log.info("%s %s: %d estimated flows, %d cities", mode, year, len(body["flows"]), len(body["cities"]))
    (OUT_DIR / "index.json").write_text(json.dumps({
        "_ai_assisted": "Claude Code (Anthropic). See docs/AI_USAGE.md.",
        "generated_by": "uv run trace estimate-flows", "kind": "estimated",
        "files": sorted(p.name for p in OUT_DIR.glob("*-*.json"))}, indent=2) + "\n", encoding="utf-8")
    return written
