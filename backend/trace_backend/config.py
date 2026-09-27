# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Paths, constants, and environment settings shared by the whole backend."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
load_dotenv(REPO / ".env")

DATA = BACKEND / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
CACHE = DATA / "cache"
API_DIR = Path(os.environ["TRACE_API_DIR"]) if os.environ.get("TRACE_API_DIR") else PROCESSED / "api"
SEED = BACKEND / "trace_backend" / "seed"  # small, citable, hand-transcribed reference tables (committed)


def _path(env: str, default: Path) -> Path:
    v = os.environ.get(env)
    if not v:
        return default
    p = Path(v)
    return p if p.is_absolute() else REPO / p


def _db_path() -> Path:
    return _path("TRACE_DB_PATH", DATA / "derived.sqlite")


# Canonical collected-data archive (SQLite v2, owned by data_collection/; read-only here).
ARCHIVE_PATH = _path("TRACE_ARCHIVE_PATH", REPO / "data_collection" / "work" / "trace.sqlite")
DB_PATH = _db_path()

MODEL_VERSION = "trace-0.1.0"
DRUGS = ["cocaine", "heroin", "meth", "cannabis"]
DRUG_LABELS = {"cocaine": "Cocaine / crack", "heroin": "Heroin / opiates", "meth": "Methamphetamine",
               "cannabis": "Cannabis"}
# Relative harm weights for exposure (higher = more acute health harm per unit of flow).
HARM_WEIGHTS = {"cocaine": 1.0, "heroin": 1.3, "meth": 1.1, "cannabis": 0.3}

YEAR_MIN = 2000
ROUTE_YEAR_MIN = 2006  # first year of UNODC annex seizure series in the archive
BACKTEST_TRAIN_THROUGH = 2019
AFGHAN_TRAIN_THROUGH = 2021

TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "").strip()
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GDELT_POLL_MINUTES = int(os.environ.get("GDELT_POLL_MINUTES", "15") or 15)
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]


def ensure_dirs() -> None:
    for d in (RAW, PROCESSED, CACHE, API_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:  # read-only deploy filesystem (e.g. Vercel): serving never writes here
            pass
