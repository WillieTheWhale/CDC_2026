# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Route evidence API: the cited, country-pair (or regional text) evidence behind TRACE's route edges.

Three layers, each flagged by `pair_type`:
- `direct_reported_pair`: a country pair stated explicitly in a cited primary publication at an exact locator
  (seed/route_evidence*.csv, transcribed from the frontend team's frontend/lib/route-evidence.ts).
- `interpreted_corridor`: TRACE's own transcription of UNODC/EUDA regional route maps and report text into
  country pairs (seed/corridors.csv). These are our reading of regional maps, not pairs the sources list verbatim.
- `narrative_context`: multiregional statements from the archive's `evidence_claims`
  (type published_aggregate_corridor_context), kept as text; never turned into country pairs.

Nothing here is a trafficked volume, a city/road/port path, or a statement about enforcement or monitoring.
Build the narrative seed once from the archive: `python -m trace_backend.api.route_evidence`.
"""
from __future__ import annotations

import base64
import csv
import json
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from .. import config
from .responses import UTF8JSONResponse

# Titles and locators carry en/em dashes; declare the charset and ASCII-escape them (responses.py) so clients that
# default to ISO-8859-1 without a charset no longer show "â€“".
router = APIRouter(default_response_class=UTF8JSONResponse)

DRUGS = ("cocaine", "heroin", "meth", "cannabis")
PAIR_TYPES = ("direct_reported_pair", "interpreted_corridor", "narrative_context")
CLAIMS_SEED = config.SEED / "evidence_claims.json"
CORRIDOR_SOURCE = {"id": "trace-corridors", "publisher": "TRACE (transcription of UNODC/EUDA publications)",
                   "title": "TRACE documented corridors: country pairs transcribed from UNODC/EUDA regional route "
                            "maps and report text", "publication_year": 2026,
                   "url": "https://github.com/WillieTheWhale/CDC_2026/blob/main/backend/trace_backend/seed/corridors.csv"}
_WDR_ANNEX = "https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html"
# corridors.csv citation keys (seed/README.md). Every URL checked 2026-09-27 (HTTP 200, title matches; the EUDA page
# sits behind a browser check). UNODC-AOT2024 and UNODC-WA2023 cite a series, so they link its publication index.
CITATIONS = {
    "WDR2026-7.2.1": ("UNODC", "World Drug Report 2026, Statistical Annex 7.2.1: Main methamphetamine trafficking "
                               "flows as described in reported seizures, 2021-2024", 2026, _WDR_ANNEX),
    "WDR2026-7.3.1": ("UNODC", "World Drug Report 2026, Statistical Annex 7.3.1: Main cocaine trafficking flows as "
                               "described in reported seizures, 2021-2024", 2026, _WDR_ANNEX),
    "WDR2026-7.4.1": ("UNODC", "World Drug Report 2026, Statistical Annex 7.4.1: Main heroin trafficking flows as "
                               "described in reported seizures, 2021-2024", 2026, _WDR_ANNEX),
    "WDR2023-B2": ("UNODC", "World Drug Report 2023, Booklet 2 (cannabis markets and trafficking)", 2023,
                   "https://www.unodc.org/unodc/en/data-and-analysis/wdr-2023_booklet-2.html"),
    "WDR2023-B3": ("UNODC", "World Drug Report 2023, cocaine market chapter", 2023,
                   "https://www.unodc.org/unodc/en/data-and-analysis/wdr-2023-online-segment.html"),
    "UNODC-GRC2023": ("UNODC", "Global Report on Cocaine 2023: Local dynamics, global challenges", 2023,
                      "https://www.unodc.org/documents/data-and-analysis/cocaine/Global_cocaine_report_2023.pdf"),
    "UNODC-AOT2024": ("UNODC", "Afghan Opiate Trade Project reports and updates, 2020-2024", 2024,
                      "https://www.unodc.org/unodc/en/data-and-analysis/aotp.html"),
    "UNODC-AFGMETH2023": ("UNODC", "Understanding illegal methamphetamine manufacture in Afghanistan", 2023,
                          "https://www.unodc.org/documents/data-and-analysis/briefs/Methamphetamine_Manufacture_in_Afghanistan.pdf"),
    "UNODC-SEA2024": ("UNODC", "Synthetic Drugs in East and Southeast Asia: latest developments and challenges",
                      2024, "https://www.unodc.org/roseap/uploads/documents/Publications/2024/Synthetic_Drugs_in_East_and_Southeast_Asia_2024.pdf"),
    "UNODC-WA2023": ("UNODC", "West and Central Africa drug trafficking assessments", 2023,
                     "https://www.unodc.org/westandcentralafrica/en/research-and-awareness.html"),
    "EUDA-EDM2024": ("EUDA and Europol", "EU Drug Markets analyses (cocaine 2022; heroin, methamphetamine, "
                                         "cannabis 2023-2024)", 2024,
                     "https://www.euda.europa.eu/publications/eu-drug-markets_en"),
}
CORRIDOR_BASIS = {"map": "regional route map (TRACE transcription)", "text": "report text (TRACE transcription)",
                  "map+text": "regional route map and report text (TRACE transcription)"}
DIRECT_CAVEAT = ("Country pair stated in the cited publication at this locator. Not a volume estimate or an "
                 "annual observation; no city, road or port path.")
CORRIDOR_CAVEAT = ("TRACE's transcription of countries named on UNODC/EUDA regional route maps or in report text; "
                   "the maps are drawn between regions, so the pair is indicative, not verbatim. No volume or path.")
NOTES = ["Route evidence documents where flows are reported; it carries no trafficked volumes and no city-level "
         "geometry. pair_type separates pairs stated verbatim in a source (direct_reported_pair) from TRACE's "
         "transcription of regional maps and text (interpreted_corridor) and regional narrative (narrative_context).",
         "The public UNODC IDS export lists seizure locations only, with no route endpoints; no lines are inferred "
         "from it."]


def _seed_rows(name: str) -> list[dict]:
    if not (config.SEED / name).exists():  # a bundle without seed/ serves empty layers rather than failing /api/routes
        return []
    with open(config.SEED / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def _edge_id(drug: str, a: str, b: str) -> str:
    return f"{drug}:{a}:{b}"


def build_claims_seed() -> int:
    """Write seed/evidence_claims.json from the archive (corridor-context claims plus their sources)."""
    from .. import db
    claims = db.read_table("evidence_claims")
    claims = claims[claims["claim_type"] == "published_aggregate_corridor_context"]
    srcs = db.read_table("evidence_sources")
    srcs = srcs[srcs["source_id"].isin(claims["source_id"])][["source_id", "publisher", "title", "url",
                                                             "publication_year", "retrieved_at"]]
    clean = lambda df: json.loads(df.to_json(orient="records", force_ascii=False))  # noqa: E731 (NaN -> null)
    out = {"_ai_assisted": "Generated with Claude Code (Anthropic) by trace_backend.api.route_evidence."
                           "build_claims_seed from the data_collection archive tables evidence_claims and "
                           "evidence_sources. See docs/AI_USAGE.md.",
           "claims": clean(claims.sort_values("claim_id")), "sources": clean(srcs.sort_values("source_id"))}
    CLAIMS_SEED.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(out["claims"])


def _claims_seed() -> dict:
    if CLAIMS_SEED.exists():
        return json.loads(CLAIMS_SEED.read_text(encoding="utf-8"))
    return {"claims": [], "sources": []}  # deploy without the seed: narrative layer is simply empty


@lru_cache(maxsize=1)
def dataset() -> dict:
    """{records (stable order), by_id, sources, edge_index: edge id -> evidence ids (direct pairs first)}."""
    sources = {r["id"]: {**r, "publication_year": int(r["publication_year"]), "layer": "direct_reported_pair"}
               for r in _seed_rows("route_evidence_sources.csv")}
    recs = []
    for r in _seed_rows("route_evidence.csv"):
        s = sources[r["source_id"]]
        period = [int(r["period_start"]), int(r["period_end"])] if r["period_start"] else None
        recs.append({"id": f"{r['drug']}:{r['from']}:{r['to']}:{r['source_id']}", "drug": r["drug"],
                     "from": r["from"], "to": r["to"], "geography_from": None, "geography_to": None,
                     "pair_type": "direct_reported_pair", "basis": r["basis"], "period": period,
                     "source": {k: s[k] for k in ("id", "publisher", "title", "publication_year", "url")},
                     "source_locator": r["source_locator"], "citations": [], "original_excerpt": None,
                     "geometry_precision": "country pair", "caveat": DIRECT_CAVEAT,
                     "supports_edge_ids": [_edge_id(r["drug"], r["from"], r["to"])]})
    sources[CORRIDOR_SOURCE["id"]] = {**CORRIDOR_SOURCE, "layer": "interpreted_corridor"}
    for r in _seed_rows("corridors.csv"):
        keys = [k for k in r["citation"].split(";") if k]
        cites = [{"key": k, "publisher": CITATIONS[k][0], "title": CITATIONS[k][1],
                  "publication_year": CITATIONS[k][2], "url": CITATIONS[k][3]} for k in keys]
        mapped = "map" in r["basis"] and any(k.startswith("WDR2026-7.") for k in keys)
        recs.append({"id": f"{r['drug']}:{r['from']}:{r['to']}:trace-corridors", "drug": r["drug"],
                     "from": r["from"], "to": r["to"], "geography_from": None, "geography_to": None,
                     "pair_type": "interpreted_corridor", "basis": CORRIDOR_BASIS[r["basis"]],
                     "period": [2021, 2024] if mapped else None, "source": dict(CORRIDOR_SOURCE),
                     "source_locator": f"seed/corridors.csv row {r['drug']},{r['from']},{r['to']}; cites "
                                       + ", ".join(keys), "citations": cites, "original_excerpt": None,
                     "geometry_precision": "country pair interpreted from regional map/text",
                     "caveat": CORRIDOR_CAVEAT, "supports_edge_ids": [_edge_id(r["drug"], r["from"], r["to"])]})
    seed = _claims_seed()
    for s in seed["sources"]:
        sources[s["source_id"]] = {"id": s["source_id"], "publisher": s["publisher"], "title": s["title"],
                                   "publication_year": int(s["publication_year"]), "url": s["url"],
                                   "layer": "narrative_context"}
    for c in seed["claims"]:
        s = sources[c["source_id"]]
        drug = "meth" if c["drug"] == "methamphetamine" else c["drug"]
        start, end = c.get("observation_start_year"), c.get("observation_end_year")
        recs.append({"id": f"{drug}:claim:{c['claim_id']}:{c['source_id']}", "drug": drug, "from": None, "to": None,
                     "geography_from": c["geography_from"], "geography_to": c["geography_to"],
                     "pair_type": "narrative_context", "basis": "published aggregate context (reported departures)",
                     "period": [int(start), int(end)] if start is not None and end is not None else None,
                     "source": {k: s[k] for k in ("id", "publisher", "title", "publication_year", "url")},
                     "source_locator": c["source_locator"], "citations": [], "original_excerpt": c["original_excerpt"],
                     "geometry_precision": f"regional text ({c.get('geography_scope') or 'regional'})",
                     "caveat": c["caveat"], "supports_edge_ids": []})
    assert all(r["drug"] in DRUGS for r in recs), "drug code outside the backend's set"
    index: dict[str, list[str]] = {}
    for r in recs:  # records are ordered direct pairs first, so each edge's list is too
        for e in r["supports_edge_ids"]:
            index.setdefault(e, []).append(r["id"])
    return {"records": recs, "by_id": {r["id"]: r for r in recs}, "sources": sources, "edge_index": index}


def link_edges(edges: list[dict]) -> list[dict]:
    """Copies of /api/routes edges with `evidence_ids` and `kg_basis` (kg is always allocated, never observed)."""
    idx = dataset()["edge_index"]
    return [{**e, "evidence_ids": idx.get(e.get("id") or _edge_id(e["drug"], e["from"], e["to"]), []),
             "kg_basis": "allocated_seizure_scale"} for e in edges]


KG_NOTE = ("kg_basis is allocated_seizure_scale on every edge: national seizure totals allocated over documented "
           "corridors. No pair-level volumes are observed; evidence_ids list the cited records supporting the pair.")


def _bad(message: str):
    raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": message})


def _in_bbox(lon: float, lat: float, box: tuple[float, float, float, float]) -> bool:
    west, south, east, north = box
    if lat < south or lat > north:
        return False
    if east - west >= 360:
        return True
    return ((lon - west) % 360 + 360) % 360 <= east - west


def _envelope(data, **extra) -> dict:
    from .app import ROUTE_SOURCES, envelope
    body = envelope(data, *ROUTE_SOURCES, notes=NOTES)
    body["meta"].update(extra)
    return body


@router.get("/api/route-evidence")
def get_route_evidence(drug: str | None = Query(None, pattern="^(cocaine|heroin|meth|cannabis)$"),
                       from_: str | None = Query(None, alias="from", pattern="^[A-Za-z]{3}$"),
                       to: str | None = Query(None, pattern="^[A-Za-z]{3}$"),
                       iso3: str | None = Query(None, pattern="^[A-Za-z]{3}$"),
                       pair_type: str | None = Query(None, pattern="^(direct_reported_pair|interpreted_corridor|"
                                                                   "narrative_context)$"),
                       basis: str | None = Query(None, max_length=120), bbox: str | None = None,
                       limit: int = Query(100, ge=1, le=250), cursor: str | None = Query(None, max_length=4096)):
    """Evidence records in stable dataset order (direct pairs, interpreted corridors, narrative context). With
    `bbox`, a record matches if either endpoint's capital is inside; narrative records have no point and drop out."""
    box = None
    if bbox is not None:
        try:
            box = tuple(float(v) for v in bbox.split(","))
        except ValueError:
            box = ()
        if (len(box) != 4 or not (-90 <= box[1] <= 90 and -90 <= box[3] <= 90) or box[1] > box[3]
                or box[2] < box[0] or box[2] - box[0] > 720):
            _bad("bbox must be west,south,east,north")
    from_, to, iso3 = (v.upper() if v else None for v in (from_, to, iso3))
    coords = {}
    if box:
        from .app import store
        coords = {c["iso3"]: (c["lon"], c["lat"]) for c in store().countries
                  if c.get("lon") is not None and c.get("lat") is not None}

    def keep(r: dict) -> bool:
        return ((drug is None or r["drug"] == drug) and (from_ is None or r["from"] == from_)
                and (to is None or r["to"] == to) and (iso3 is None or iso3 in (r["from"], r["to"]))
                and (pair_type is None or r["pair_type"] == pair_type) and (basis is None or r["basis"] == basis)
                and (box is None or any(i in coords and _in_bbox(*coords[i], box) for i in (r["from"], r["to"]))))

    rows = [r for r in dataset()["records"] if keep(r)]
    fkey = json.dumps([drug, from_, to, iso3, pair_type, basis, list(box) if box else None])
    start = 0
    if cursor:
        try:
            last = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
            assert isinstance(last, list) and len(last) == 2 and last[0] == fkey
        except Exception:
            _bad("cursor does not match these filters")
        start = next((i + 1 for i, r in enumerate(rows) if r["id"] == last[1]), None)
        if start is None:
            _bad("cursor refers to an unknown record")
    page = rows[start:start + limit]
    nxt = None
    if page and start + len(page) < len(rows):
        nxt = base64.urlsafe_b64encode(json.dumps([fkey, page[-1]["id"]]).encode()).decode().rstrip("=")
    return _envelope(page, total=len(rows), next_cursor=nxt)


@router.get("/api/route-evidence/sources")
def get_route_evidence_sources():
    """Every publication (or TRACE transcription) cited by a route-evidence record, with the layer it backs."""
    return _envelope(sorted(dataset()["sources"].values(), key=lambda s: (s["layer"], s["id"])))


@router.get("/api/route-evidence/{evidence_id}")
def get_route_evidence_item(evidence_id: str):
    r = dataset()["by_id"].get(evidence_id)
    if r is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_evidence",
                                                     "message": f"No route evidence with id {evidence_id}"})
    return _envelope(r)


if __name__ == "__main__":
    print(f"wrote {build_claims_seed()} corridor-context claims to {CLAIMS_SEED}")
