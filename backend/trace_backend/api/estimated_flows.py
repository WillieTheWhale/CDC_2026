# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""GET /api/estimated-flows: the labelled, map-only estimated local-flow layer, built live from the served routes.

Same payload as the snapshot files frontend/public/data/estimated/{mode}-{year}.json (`uv run trace estimate-flows`)
and the same algorithm (model/estimated_flows.estimate), but computed from the modeled edges /api/routes serves for
that year and mode, so the arrows follow the deployed route model instead of a frozen export.

Inputs, all available on the Vercel bundle (no archive, no network):
- route edges: Store.routes(mode, year), the modeled edges behind /api/routes (before the Live Wire news bonus,
  which changes minute to minute; the layer uses modeled confidence only, as the snapshots do);
- GDP per capita PPP: World Bank NY.GDP.PCAP.PP.KD (source 2) from the exported indicators.json, which the World Bank
  ingest writes from the same wb_indicators rows the snapshot generator reads (identical values);
- cities and route anchors: committed seeds seed/estimated_flows_cities.csv (Natural Earth populated places, 150k+)
  and seed/estimated_flows_anchors.csv (Natural Earth admin-0 label points), see seed/README.md.

Cities are placement anchors for drawing arrows, not evidence of city-level trafficking. No enforcement, customs,
detection or monitoring variable is used anywhere (design boundary).

Rebuild the seeds (needs the Natural Earth download and frontend/public/geo/countries.json):
    python -m trace_backend.api.estimated_flows
"""
from __future__ import annotations

import csv
import json
from functools import lru_cache

from fastapi import APIRouter, Query

from .. import config
from .responses import UTF8JSONResponse

router = APIRouter(default_response_class=UTF8JSONResponse)  # city names are non-ASCII (São Paulo, København)

CITIES_SEED = config.SEED / "estimated_flows_cities.csv"
ANCHORS_SEED = config.SEED / "estimated_flows_anchors.csv"
GDP_CODE = "NY.GDP.PCAP.PP.KD"  # same as model/estimated_flows.GDP_CODE (not imported: keeps import time low)
MAX_KM = 1_500
SEED_HEADER = "# AI-assisted: generated with Claude Code (Anthropic) by trace_backend.api.estimated_flows. " \
              "See docs/AI_USAGE.md and seed/README.md.\n"
NOTE = "Estimated local flows for map density only. Not observed, not modeled, not used in any score."
METHOD = ("Entry city per modeled edge; arrows follow money = city population x GDP per capita "
          f"(PPP), score = supply x money / (1 + km/400)^2, <= {MAX_KM} km, three waves with a per-country quota.")
NOTES = [NOTE,
         "Cities are placement anchors for drawing arrows (Natural Earth populated places of 150,000+ people), not "
         "evidence of city-level trafficking; no city, road or port path is observed.",
         "Built from the modeled route edges for this year and mode (modeled confidence, without the live news "
         "bonus). Inputs: city population, GDP per capita PPP, great-circle distance and modeled route density only."]


def _rows(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


@lru_cache(maxsize=1)
def cities() -> list[dict]:
    """Natural Earth populated places (150k+), in the generator's order (order breaks score ties)."""
    if not CITIES_SEED.exists():  # local dev without the seed: the generator's own loader (downloads once)
        from ..model.estimated_flows import load_cities
        return load_cities()
    return [{"name": r["name"], "iso3": r["iso3"], "pop": int(r["pop"]), "lon": float(r["lon"]),
             "lat": float(r["lat"])} for r in _rows(CITIES_SEED)]


def anchors(countries: list[dict]) -> dict[str, tuple[float, float]]:
    """Route anchors as in model/estimated_flows._anchors: label points (seed), else World Bank capitals."""
    out = {c["iso3"]: (c["lon"], c["lat"]) for c in countries if c.get("lon") is not None}
    if ANCHORS_SEED.exists():
        out.update({r["iso3"]: (float(r["label_lon"]), float(r["label_lat"])) for r in _rows(ANCHORS_SEED)})
    return out


def gdp_per_capita(indicators: dict[str, dict]) -> dict[str, dict[int, float]]:
    """{iso3: {year: GDP per capita PPP}} (non-null) from the exported World Bank indicator series."""
    out: dict[str, dict[int, float]] = {}
    for iso3, series in indicators.items():
        pts = {int(y): float(v) for y, v in series.get(GDP_CODE, []) if v is not None}
        if pts:
            out[iso3] = pts
    return out


def compute(edges: list[dict], year: int, mode: str) -> dict:
    """The `data` object of a snapshot file for these edges."""
    # lazy: pulls urllib and the model package only when needed
    from ..model.estimated_flows import estimate
    from .app import store
    s = store()
    return {"year": year, "mode": mode,
            **estimate(edges, cities(), gdp_per_capita(s.indicators), anchors(s.countries), year)}


PRECOMPUTED = config.API_DIR / "estimated_flows"  # {mode}-{year}.json written by precompute() at build/export time


@lru_cache(maxsize=64)
def _layer(mode: str, year: int) -> dict | None:
    """Precomputed layer if present (the deploy ships every year: computing ~20 on a cold start starves other
    requests), else computed from the served edges."""
    f = PRECOMPUTED / f"{mode}-{year}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    from .app import store
    edges = store().routes(mode, year)
    if not edges:
        return None
    return compute(edges, year, mode)


def precompute(out_dir=PRECOMPUTED) -> int:
    """Write every observed and predicted year's layer to out_dir; returns the number of files."""
    from .app import store
    s = store()
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for mode, years in (("observed", s.meta["observed_years"]), ("predicted", s.meta["predicted_years"])):
        for year in years:
            edges = s.routes(mode, year)
            if edges:
                (out_dir / f"{mode}-{year}.json").write_text(
                    json.dumps(compute(edges, year, mode), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
                n += 1
    return n


@router.get("/api/estimated-flows")
def get_estimated_flows(year: int | None = None, mode: str = Query("observed", pattern="^(observed|predicted)$")):
    from .app import envelope, not_found, store
    s = store()
    if year is None:
        year = s.meta["latest_observed_year"] if mode == "observed" else s.meta["predicted_years"][0]
    data = _layer(mode, year)
    if data is None:
        not_found("year_not_available", f"No {mode} routes for {year}, so no estimated flows. "
                  f"Available: {s.meta['observed_years' if mode == 'observed' else 'predicted_years']}")
    body = envelope(data, "natural_earth", "wb_wdi", "unodc_routes", "unodc_wdr_annex", notes=NOTES)
    body["meta"].update({"kind": "estimated", "note": NOTE, "method": METHOD, "city_role": "placement_anchor",
                         "variables": ["city population", "GDP per capita PPP", "great-circle distance",
                                       "modeled route density"]})
    return body


def build_seeds() -> tuple[int, int]:
    """Write the two seeds from the Natural Earth downloads the generator uses."""
    from ..model.estimated_flows import load_cities
    rows = load_cities()
    with open(CITIES_SEED, "w", encoding="utf-8", newline="") as f:
        f.write(SEED_HEADER)
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["name", "iso3", "pop", "lon", "lat"])
        for c in rows:
            assert float(c["pop"]).is_integer()
            w.writerow([c["name"], c["iso3"], int(c["pop"]), repr(float(c["lon"])), repr(float(c["lat"]))])
    geo = config.REPO / "frontend" / "public" / "geo" / "countries.json"
    last: dict[str, tuple[float, float]] = {}  # a few iso3 codes repeat (FRA, KAZ, BRA, AUS): the last one wins,
    for f in json.loads(geo.read_text(encoding="utf-8"))["features"]:  # exactly as in the generator's _anchors
        p = f["properties"]
        if isinstance(p.get("label_lon"), (int, float)):
            last[p["iso3"]] = (p["label_lon"], p["label_lat"])
    pts = sorted((iso3, lon, lat) for iso3, (lon, lat) in last.items())
    with open(ANCHORS_SEED, "w", encoding="utf-8", newline="") as f:
        f.write(SEED_HEADER)
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["iso3", "label_lon", "label_lat"])
        for iso3, lon, lat in pts:
            w.writerow([iso3, repr(float(lon)), repr(float(lat))])
    return len(rows), len(pts)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--precompute"]:
        print(f"precomputed {precompute()} layers into {PRECOMPUTED}")
    else:
        n_cities, n_anchors = build_seeds()
        print(f"cities {n_cities}, anchors {n_anchors}")
