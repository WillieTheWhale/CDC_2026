# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""GET /api/us-routes: cited US drug-route pairs (city or state level) from NDIC and HIDTA reports.

Serves seed/us_routes_placed.json, written by `uv run trace us-routes` from seed/us_routes.csv (validated, placed on
Natural Earth cities or state label points). Every route carries its report URL, PDF page and verbatim quote.
Routes only describe where drugs flow; there is no enforcement, checkpoint or detection attribute (design boundary).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import APIRouter, Query

from .. import config
from ..sources import refs
from .responses import UTF8JSONResponse

router = APIRouter(default_response_class=UTF8JSONResponse)

PLACED = config.SEED / "us_routes_placed.json"
NOTES = ["Documented routes: each states one drug moving between two places, quoted from a public US government "
         "report (mostly 2008-2011 NDIC HIDTA Drug Market Analyses). Absence of a route is not evidence of absence.",
         "Places are no more precise than the source: state label point when only a state is named, country anchor "
         "for foreign origins. Checked against the model in docs/US_ROUTES_VALIDATION.md."]


@lru_cache(maxsize=1)
def routes() -> list[dict]:
    if not PLACED.exists():
        return []
    return json.loads(PLACED.read_text(encoding="utf-8"))["data"]["routes"]


@router.get("/api/us-routes")
def get_us_routes(drug: str | None = Query(None, pattern="^(cocaine|heroin|meth|cannabis)$"),
                  state: str | None = Query(None, pattern="^[A-Z]{2}$")):
    rows = [r for r in routes() if (drug is None or r["drug"] == drug)
            and (state is None or state in (r["from"]["state"], r["to"]["state"]))]
    # own meta (no exported-store dependency): this layer is a committed seed, not pipeline output
    meta = {"generated_at": _generated_at(), "model_version": config.MODEL_VERSION,
            "sources": refs("us_route_reports", "natural_earth"), "notes": NOTES}
    return {"meta": meta, "data": {"total": len(rows), "routes": rows}}


@lru_cache(maxsize=1)
def _generated_at() -> str:
    ts = PLACED.stat().st_mtime if PLACED.exists() else datetime.now(UTC).timestamp()
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")
