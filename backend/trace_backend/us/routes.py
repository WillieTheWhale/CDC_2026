# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Load, validate and geolocate cited US drug-route pairs (seed/us_routes.csv) for the map.

One row = one origin -> destination movement of one drug that a public source states in words:
HIDTA threat assessments, archived NDIC drug market analyses, DEA National Drug Threat Assessments,
or DOJ case filings/press releases. Every row must carry the source URL, an exact locator (page or
section) and a verbatim quote. Rows are never inferred: if a source names only states, the row is
state-level and is drawn between state label points, never between guessed cities.

Placement: a named city is matched to Natural Earth populated places (city + state); otherwise the
Natural Earth state label point is used (`precision: "state"`). A foreign origin (e.g. MEX) uses the
country label point from the atlas geography.

Design boundary: routes only describe where drugs flow. No column may record checkpoints, patrols,
seizure odds or any "least watched" attribute; `validate` rejects such text in basis/locator.
Output: frontend/public/data/us-routes.json.
"""
from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass

from .. import config

log = logging.getLogger(__name__)

SEED = config.BACKEND / "trace_backend" / "seed" / "us_routes.csv"
PLACES = config.RAW / "natural_earth" / "ne_10m_populated_places_simple.geojson"
STATES = config.RAW / "natural_earth" / "ne_110m_admin_1_states_provinces.geojson"
GEO = config.REPO / "frontend" / "public" / "geo" / "countries.json"
OUT = config.REPO / "frontend" / "public" / "data" / "us-routes.json"

DRUGS = {"cocaine", "heroin", "meth", "cannabis", "fentanyl"}
BASES = {"hidta_assessment", "ndic_market_analysis", "dea_ndta", "court_case"}
REQUIRED = ["route_id", "drug", "basis", "source_id", "source_url", "publisher", "title",
            "publication_year", "locator", "quote"]
FORBIDDEN = re.compile(r"checkpoint|patrol|least[- ]watched|unmonitored|evade|avoid detection|weak enforcement",
                       re.I)


@dataclass
class Place:
    name: str
    state: str | None
    country: str
    lon: float
    lat: float
    precision: str  # "city" | "state" | "country"


class Geocoder:
    def __init__(self) -> None:
        states = json.loads(STATES.read_text(encoding="utf-8"))["features"]
        self.state_name = {f["properties"]["postal"]: f["properties"]["name"] for f in states}
        self.state_point = {f["properties"]["postal"]: (f["properties"]["longitude"], f["properties"]["latitude"])
                            for f in states}
        self.cities: dict[tuple[str, str], tuple[float, float]] = {}
        for f in json.loads(PLACES.read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            if p.get("adm0_a3") != "USA":
                continue
            key = (_norm(p["name"]), _norm(p.get("adm1name") or ""))
            if key not in self.cities:  # file is ordered by rank; keep the first (largest) match
                self.cities[key] = (p["longitude"], p["latitude"])
        self.countries: dict[str, tuple[float, float]] = {}
        if GEO.exists():
            for f in json.loads(GEO.read_text(encoding="utf-8"))["features"]:
                p = f["properties"]
                if isinstance(p.get("label_lon"), (int, float)):
                    self.countries.setdefault(p["iso3"], (p["label_lon"], p["label_lat"]))

    def place(self, city: str, state: str, country: str) -> Place:
        country = (country or "USA").upper()
        if country != "USA":
            if country not in self.countries:
                raise ValueError(f"unknown country {country}")
            lon, lat = self.countries[country]
            return Place(city or country, None, country, lon, lat, "country")
        state = state.upper()
        if state not in self.state_name:
            raise ValueError(f"unknown US state {state!r}")
        if city:
            hit = self.cities.get((_norm(city), _norm(self.state_name[state])))
            if hit is None:
                raise ValueError(f"city not found: {city}, {state}")
            return Place(city, state, "USA", hit[0], hit[1], "city")
        lon, lat = self.state_point[state]
        return Place(self.state_name[state], state, "USA", lon, lat, "state")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower().replace("saint ", "st "))


def validate(row: dict) -> list[str]:
    errs = [f"missing {k}" for k in REQUIRED if not (row.get(k) or "").strip()]
    if row.get("drug") not in DRUGS:
        errs.append(f"drug {row.get('drug')!r} not in {sorted(DRUGS)}")
    if row.get("basis") not in BASES:
        errs.append(f"basis {row.get('basis')!r} not in {sorted(BASES)}")
    if not (row.get("source_url") or "").startswith("https://"):
        errs.append("source_url must be https")
    if FORBIDDEN.search(" ".join(row.get(k) or "" for k in ("basis", "locator", "quote"))):
        errs.append("enforcement-weakness wording is outside the design boundary")
    for side in ("from", "to"):
        if not (row.get(f"{side}_city") or row.get(f"{side}_state") or
                (row.get(f"{side}_country") or "USA").upper() != "USA"):
            errs.append(f"{side}: need a city, state or foreign country")
    return errs


def load(path=SEED) -> tuple[list[dict], list[str]]:
    geo = Geocoder()
    routes, problems, seen = [], [], set()
    with open(path, newline="", encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            errs = validate(row)
            if row.get("route_id") in seen:
                errs.append("duplicate route_id")
            if not errs:
                try:
                    a = geo.place(row["from_city"], row["from_state"], row["from_country"])
                    b = geo.place(row["to_city"], row["to_state"], row["to_country"])
                except ValueError as e:
                    errs.append(str(e))
            if errs:
                problems.append(f"line {n} ({row.get('route_id')}): " + "; ".join(errs))
                continue
            seen.add(row["route_id"])
            routes.append({
                "id": row["route_id"], "drug": row["drug"], "basis": row["basis"],
                "from": a.__dict__, "to": b.__dict__,
                "precision": "city" if a.precision == b.precision == "city" else
                             "state" if "country" not in (a.precision, b.precision) else "mixed",
                "period": [int(row["period_start"]), int(row["period_end"] or row["period_start"])]
                          if row.get("period_start") else None,
                "source": {"id": row["source_id"], "url": row["source_url"], "publisher": row["publisher"],
                           "title": row["title"], "year": int(row["publication_year"]),
                           "locator": row["locator"], "quote": row["quote"]},
            })
    return routes, problems


def run() -> dict:
    routes, problems = load()
    for p in problems:
        log.warning("rejected %s", p)
    doc = {"meta": {
        "_ai_assisted": "Claude Code (Anthropic). See docs/AI_USAGE.md.",
        "kind": "documented",
        "note": "US drug-route pairs stated in public government reports and court records. Each has a quote and "
                "locator. City-level only where the source names both cities; otherwise state-level.",
        "generated_by": "uv run trace us-routes",
        "sources": sorted({(r["source"]["id"], r["source"]["publisher"], r["source"]["title"], r["source"]["url"])
                           for r in routes}),
    }, "data": {"routes": routes}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log.info("us routes: %d written, %d rejected -> %s", len(routes), len(problems), OUT)
    return {"routes": len(routes), "rejected": len(problems)}
