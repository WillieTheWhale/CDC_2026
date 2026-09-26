# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""TRACE FastAPI app. Every response follows contracts/openapi.yaml: { "meta": ResponseMeta, "data": ... }.

Run: `uv run trace serve` (or `uv run uvicorn trace_backend.api.app:app --port 8000`).
"""
from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import config
from ..sources import refs
from .store import Store

app = FastAPI(title="TRACE API", version="1.0.0",
              description="Drug-trade terminal with spillover-risk early warning. See contracts/openapi.yaml.")
_origins = config.CORS_ORIGINS
app.add_middleware(CORSMiddleware, allow_origins=["*"] if "*" in _origins else _origins,
                   allow_origin_regex=r"https://.*\.vercel\.app", allow_methods=["*"], allow_headers=["*"])


@lru_cache(maxsize=1)
def store() -> Store:
    return Store()


def envelope(data, *source_ids: str, notes: list[str] | None = None) -> dict:
    meta = {"generated_at": store().meta.get("generated_at") or datetime.now(UTC).isoformat(),
            "model_version": config.MODEL_VERSION, "sources": refs(*source_ids)}
    if notes:
        meta["notes"] = notes
    return {"meta": meta, "data": data}


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(StarletteHTTPException)
async def _http_exc(_: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return error(exc.status_code, detail.get("code", "http_error"), detail.get("message", ""))


@app.exception_handler(RequestValidationError)
async def _val_exc(_: Request, exc: RequestValidationError):
    return error(422, "invalid_request", "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()))


def not_found(code: str, message: str):
    raise HTTPException(status_code=404, detail={"code": code, "message": message})


WB_SOURCES = ("wb_wdi", "wb_wgi")
ROUTE_SOURCES = ("unodc_wdr_annex", "unodc_ids", "unodc_routes", "gitoc_ocindex", "cepii_geodist")


# ------------------------------------------------------------------ endpoints
@app.get("/api/health", include_in_schema=False)
def health():
    return {"status": "ok", "model_version": config.MODEL_VERSION}


@app.get("/api/meta")
def get_meta():
    m = {k: v for k, v in store().meta.items() if k not in ("generated_at", "prot_weights")}
    lw = _livewire_state()
    if lw:
        m["livewire_classifier"] = lw.classifier_name
        m["sources"] = m["sources"] + [lw.source_status()]
    return envelope(m, *WB_SOURCES, *ROUTE_SOURCES, "hri_gshr", "gdelt")


@app.get("/api/countries")
def get_countries():
    return envelope(store().countries, "wb_wdi", notes=["Aggregates excluded; coordinates are capital cities."])


@app.get("/api/routes")
def get_routes(drug: str | None = Query(None, pattern="^(cocaine|heroin|meth|cannabis)$"),
               year: int | None = None, mode: str = Query("observed", pattern="^(observed|predicted)$"),
               min_confidence: float = 0):
    s = store()
    if year is None:
        year = s.meta["latest_observed_year"] if mode == "observed" else s.meta["predicted_years"][0]
    edges = s.routes(mode, year)
    if edges is None:
        not_found("year_not_available", f"No {mode} routes for {year}. "
                  f"Available: {s.meta['observed_years' if mode == 'observed' else 'predicted_years']}")
    lw = _livewire_state()
    news = lw.news_edges() if lw else set()
    if news:  # live news hits are an independent confidence signal (+10)
        edges = [({**e, "signals": {**e["signals"], "news": True}, "confidence": min(100.0, e["confidence"] + 10)}
                  if (e["drug"], e["from"], e["to"]) in news and not e["signals"]["news"] else e) for e in edges]
    edges = [e for e in edges if (drug is None or e["drug"] == drug) and e["confidence"] >= min_confidence]
    notes = ["Corridor volumes are estimated from national seizure totals over documented corridors "
             "(UNODC public IDS has no route fields); kg is seizure-scale, not total trafficked volume."]
    if mode == "predicted":
        notes.append("Predicted with the LightGBM hurdle model; drivers are SHAP values beyond last year's volume.")
    return envelope({"year": year, "mode": mode, "drug": drug, "edges": edges}, *ROUTE_SOURCES, *WB_SOURCES,
                    notes=notes)


@app.get("/api/country/{iso3}")
def get_country(iso3: str, year: int | None = None):
    s = store()
    iso3 = iso3.upper()
    c = s.country_index.get(iso3)
    if not c:
        not_found("unknown_country", f"{iso3} is not a World Bank economy code.")
    years = s.meta["risk_years"]
    year = year or max(years)
    if year not in years:
        not_found("year_not_available", f"No profile for {year}. Available: {years[0]}-{years[-1]}")
    edges = s.edges_for_year(year)
    det = s.risk_details.get(iso3, {}).get(str(year))
    profile = {
        "country": c, "year": year, "indicators": s.indicator_groups(iso3, year),
        "routes": {"inbound": [e for e in edges if e["to"] == iso3], "outbound": [e for e in edges if e["from"] == iso3]},
        "prices": [p for p in s.prices if p["iso3"] == iso3], "oc_index": s.oc_for(iso3, year),
        "harm_reduction": s.harm_reduction.get(iso3), "risk": det, "cultivation": s.cultivation.get(iso3, []),
        "briefing": s.briefings.get(iso3),
    }
    return envelope(profile, *WB_SOURCES, *ROUTE_SOURCES, "hri_gshr")


@app.get("/api/risk")
def get_risk(year: int | None = None, limit: int = Query(250, ge=1)):
    s = store()
    year = year or max(s.risk)
    rows = s.risk.get(year)
    if rows is None:
        not_found("year_not_available", f"No risk scores for {year}. Available: {min(s.risk)}-{max(s.risk)}")
    from ..model.spillover import WEIGHTS
    notes = ["Score = 0.45 exposure + 0.35 vulnerability + 0.20 (100 - protection)."]
    if year == max(s.risk):
        notes.append(f"{year} exposure uses model-predicted corridors.")
    return envelope({"year": year, "weights": WEIGHTS, "rows": rows[:limit]}, *WB_SOURCES, "hri_gshr",
                    *ROUTE_SOURCES, notes=notes)


@app.get("/api/prices")
def get_prices(drug: str | None = Query(None, pattern="^(cocaine|heroin|meth|cannabis)$"),
               iso3: str | None = Query(None, pattern="^[A-Za-z]{3}$")):
    series = [p for p in store().prices if (drug is None or p["drug"] == drug)
              and (iso3 is None or p["iso3"] == iso3.upper())]
    return envelope({"series": series}, "unodc_wdr_annex")


@app.get("/api/experiments/afghan-ban")
def get_afghan_ban():
    return envelope(store().afghan_ban, "unodc_wdr_annex", "unodc_ids", "unodc_routes", *WB_SOURCES)


@app.get("/api/metrics")
def get_metrics():
    m = dict(store().metrics)
    lw = _livewire_state()
    m["livewire"] = lw.accuracy() if lw else m.get("livewire") or {
        "classifier": "mock", "n_labeled": 0, "field_accuracy": {}, "note": "Live Wire not enabled."}
    m.setdefault("model_version", config.MODEL_VERSION)
    return envelope(m, "unodc_wdr_annex", "unodc_ids", *WB_SOURCES, "gdelt")


def _livewire_state():
    try:
        from .livewire import state
    except ImportError:
        return None
    return state()


# Live Wire (T8) and simulator / command bar (T9) routers
for _mod in ("livewire", "simulate"):
    try:
        app.include_router(__import__(f"trace_backend.api.{_mod}", fromlist=["router"]).router)
    except ImportError:
        pass
