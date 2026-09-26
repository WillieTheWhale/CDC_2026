# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Build a compact, auditable market shard from cached official UNODC annexes.

The source annex collector retains every workbook cell in unodc.sqlite. This
shard copies only market-related cells, keeping source row/column coordinates.
No network access is needed. Run after data_collection/unodc.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data_collection/work/unodc.sqlite"
DEFAULT_OUTPUT = ROOT / "data_collection/work/markets.sqlite"
DERIVED_SUBSTANCES = {
    "cocaine hydrochloride", "heroin", "amphetamine powder",
    "methamphetamine powder", "mdma", "“crack” cocaine", "fentanyl",
}


def form_of(name: str) -> str:
    s = (name or "").casefold()
    for key, form in (("hydrochloride", "hydrochloride"), ("crack", "crack"),
                      ("resin", "resin"), ("hashish", "resin"),
                      ("herb", "herb"), ("marijuana", "herb"),
                      ("powder", "powder"), ("tablet", "tablet"),
                      ("base", "base"), ("salts", "salts")):
        if key in s:
            return form
    return "unspecified"


def unit_and_value(measure: str, unit: str, value: float | None):
    if value is None or not math.isfinite(value):
        return None, None
    u = (unit or "").casefold().strip()
    if measure == "purity":
        if u == "% (percent)" and 0 < value <= 100:
            return "percent", value
        if u == "mg/tablet" and value > 0:
            return "mg_per_tablet", value
        return None, None
    if measure != "price" or value <= 0:
        return None, None
    if u in {"gram", "grams", "usd/g"}:
        return "usd_per_gram", value
    if u in {"kilogram", "kilograms", "usd/kg"}:
        return "usd_per_gram", value / 1000
    if u in {"tablet", "tablets"}:
        return "usd_per_tablet", value
    if u == "1000 tablets":
        return "usd_per_tablet", value / 1000
    if u in {"unit", "units"}:
        return "usd_per_unit", value
    if u == "1000 units":
        return "usd_per_unit", value / 1000
    return None, None


def schema(db: sqlite3.Connection):
    db.executescript("""
      PRAGMA journal_mode=DELETE;
      CREATE TABLE market_sources(
        source_id TEXT PRIMARY KEY, url TEXT NOT NULL, sha256 TEXT NOT NULL,
        retrieved_at TEXT NOT NULL, bytes INTEGER, edition INTEGER,
        citation TEXT, license_note TEXT);
      CREATE TABLE market_sheets(
        source_id TEXT, sheet TEXT, row_count INTEGER, col_count INTEGER,
        headers_json TEXT, PRIMARY KEY(source_id,sheet));
      CREATE TABLE market_cells(
        source_id TEXT, sheet TEXT, row_no INTEGER, col_no INTEGER,
        value_text TEXT, value_number REAL, value_type TEXT, italic INTEGER,
        PRIMARY KEY(source_id,sheet,row_no,col_no));
      CREATE TABLE market_observations(
        observation_id INTEGER PRIMARY KEY,
        source_id TEXT NOT NULL, sheet TEXT NOT NULL, row_no INTEGER NOT NULL,
        col_no INTEGER, iso3 TEXT, country TEXT, year INTEGER,
        drug_group TEXT, substance TEXT NOT NULL, form TEXT NOT NULL,
        market_level TEXT, measure TEXT NOT NULL, basis TEXT,
        original_value REAL, minimum REAL, maximum REAL, original_unit TEXT,
        normalized_value REAL, normalized_unit TEXT, original_text TEXT,
        publisher_estimate INTEGER NOT NULL,
        source_row_ref TEXT NOT NULL,
        UNIQUE(source_id,sheet,row_no,col_no,measure,market_level));
      CREATE TABLE market_metric_definitions(
        metric_code TEXT PRIMARY KEY, label TEXT NOT NULL, unit TEXT,
        formula TEXT, eligibility TEXT, interpretation TEXT, cautions TEXT);
      CREATE TABLE market_derived(
        derived_id INTEGER PRIMARY KEY,
        metric_code TEXT NOT NULL, iso3 TEXT NOT NULL, year INTEGER NOT NULL,
        substance TEXT NOT NULL, form TEXT NOT NULL, market_level TEXT,
        value REAL NOT NULL, unit TEXT NOT NULL, formula TEXT NOT NULL,
        inputs_json TEXT NOT NULL, source_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(metric_code,iso3,year,substance,form,market_level,source_id));
      CREATE TABLE market_collection_status(
        source_id TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT NOT NULL,
        url TEXT NOT NULL, checked_at TEXT NOT NULL);
      CREATE INDEX market_obs_lookup ON market_observations(iso3,year,substance,form,market_level,measure);
      CREATE INDEX market_derived_lookup ON market_derived(iso3,year,substance,metric_code);
    """)


def unique_positive(rows):
    """Use a repeated publisher value once; decline genuinely conflicting rows."""
    rows = [r for r in rows if r[2] is not None and r[2] > 0]
    if not rows:
        return None
    values = {round(r[2], 10) for r in rows}
    return rows[0] if len(values) == 1 else None


def derive(db: sqlite3.Connection, now: str):
    # 2026 annex has one workbook for price and purity and explicit product forms.
    # Historical editions are retained as observations but never mixed into joins.
    rows = db.execute("""SELECT observation_id,source_id,iso3,year,substance,form,
        market_level,measure,normalized_value,normalized_unit,publisher_estimate
        FROM market_observations WHERE source_id='prices' AND iso3 IS NOT NULL
        AND basis='typical' AND normalized_value IS NOT NULL""").fetchall()
    groups = {}
    for obs_id, source, iso, year, substance, form, level, measure, value, unit, estimate in rows:
        if level not in ("retail", "wholesale"):
            continue
        groups.setdefault((iso, year, substance, form, level, measure, unit), []).append(
            (obs_id, source, value, estimate))
    canonical = {key: unique_positive(items) for key, items in groups.items()}

    def add(metric, iso, year, substance, form, level, val, unit, formula, inputs):
        db.execute("""INSERT INTO market_derived(metric_code,iso3,year,substance,form,
            market_level,value,unit,formula,inputs_json,source_id,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (metric, iso, year, substance, form, level, val, unit, formula,
             json.dumps(inputs, separators=(",", ":")), "prices", now))

    for (iso, year, substance, form, level, measure, unit), price in canonical.items():
        if measure != "price" or unit != "usd_per_gram" or price is None:
            continue
        # Generic categories and precursors may contain unlike formulations.
        # Retain their observations but do not claim a matched product metric.
        if substance.casefold() not in DERIVED_SUBSTANCES:
            continue
        # Cannabis THC potency measures a different substance concept; omit it.
        if form in ("resin", "herb") or "cannabis" in substance.casefold():
            continue
        purity = canonical.get((iso, year, substance, form, level, "purity", "percent"))
        if purity is not None and 0 < purity[2] <= 100:
            add("purity_adjusted_price_usd_per_pure_g", iso, year, substance, form,
                level, price[2] / (purity[2] / 100), "usd_per_pure_gram",
                "price_usd_per_gram / (purity_percent / 100)",
                {"price_observation_id": price[0], "price_usd_per_gram": price[2],
                 "purity_observation_id": purity[0], "purity_percent": purity[2]})
        if level == "retail":
            wholesale = canonical.get((iso, year, substance, form, "wholesale", "price", "usd_per_gram"))
            if wholesale is not None:
                add("retail_wholesale_price_ratio", iso, year, substance, form,
                    None, price[2] / wholesale[2], "ratio",
                    "retail_usd_per_gram / wholesale_usd_per_gram",
                    {"retail_observation_id": price[0], "retail_usd_per_gram": price[2],
                     "wholesale_observation_id": wholesale[0], "wholesale_usd_per_gram": wholesale[2]})


def build(source_path: Path, output_path: Path):
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise FileNotFoundError(f"Nonempty UNODC shard required: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_suffix(".building.sqlite")
    temp.unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    db = sqlite3.connect(temp)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        schema(db)
        source_ids = [r[0] for r in src.execute("SELECT DISTINCT source_id FROM unodc_price_observations")]
        for source_id in source_ids:
            db.execute("INSERT INTO market_sources VALUES(?,?,?,?,?,?,?,?)",
                       src.execute("SELECT * FROM unodc_sources WHERE source_id=?", (source_id,)).fetchone())
            for sheet, *metadata in src.execute("SELECT sheet,row_count,col_count,headers_json FROM unodc_sheets WHERE source_id=?", (source_id,)):
                if not src.execute("SELECT 1 FROM unodc_price_observations WHERE source_id=? AND sheet=? LIMIT 1", (source_id,sheet)).fetchone():
                    continue
                db.execute("INSERT INTO market_sheets VALUES(?,?,?,?,?)", (source_id,sheet,*metadata))
                db.executemany("INSERT INTO market_cells VALUES(?,?,?,?,?,?,?,?)",
                    src.execute("SELECT * FROM unodc_cells WHERE source_id=? AND sheet=?", (source_id,sheet)))
        for r in src.execute("""SELECT source_id,sheet,row_no,col_no,iso3,country,year,drug,
            drug_raw,level,measure,basis,value,minimum,maximum,unit,value_text,upstream_estimate
            FROM unodc_price_observations"""):
            (source, sheet, row, col, iso, country, year, group, substance,
             level, measure, basis, value, low, high, unit, original, estimate) = r
            normalized_unit, normalized_value = unit_and_value(measure, unit, value)
            db.execute("""INSERT INTO market_observations(source_id,sheet,row_no,col_no,
                iso3,country,year,drug_group,substance,form,market_level,measure,basis,
                original_value,minimum,maximum,original_unit,normalized_value,
                normalized_unit,original_text,publisher_estimate,source_row_ref)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source,sheet,row,col,iso,country,year,group,substance,form_of(substance),
                 level,measure,basis,value,low,high,unit,normalized_value,normalized_unit,
                 original,estimate,f"{source}:{sheet}:R{row}"))
        definitions = [
            ("purity_adjusted_price_usd_per_pure_g", "Nominal price per gram of pure substance",
             "usd_per_pure_gram", "price_usd_per_gram / (purity_percent / 100)",
             "Named product only; exact country, year, substance, form, market level and 2026 UNODC edition; observed typical price and purity; grams and percent only; all repeated rows agree.",
             "Useful for comparing reported price after accounting for reported purity. It is not a transaction price or inflation-adjusted series.",
             "Price and purity samples can come from different national collection systems; representativeness and timing may differ. No cannabis potency conversion."),
            ("retail_wholesale_price_ratio", "Retail to wholesale unit-price ratio", "ratio",
             "retail_usd_per_gram / wholesale_usd_per_gram",
             "Named product only; exact country, year, substance, form and 2026 UNODC edition; observed typical retail and wholesale values; both normalized to USD per gram; all repeated rows agree.",
             "Descriptive contrast between two reported market levels, not a profit margin or corridor signal.",
             "Different transaction sizes, sampling frames, and reporting methods limit interpretation."),
        ]
        db.executemany("INSERT INTO market_metric_definitions VALUES(?,?,?,?,?,?,?)", definitions)
        derive(db, now)
        db.executemany("INSERT INTO market_collection_status VALUES(?,?,?,?,?)", [
            ("euda_2026_wastewater", "blocked", "Official source CSV link blocked by local browser; no values inferred from narrative summaries.",
             "https://www.euda.europa.eu/publications/pods/waste-water-analysis_en", now),
            ("euda_2026_price_purity", "blocked", "Official interactive table page readable, but table export endpoint unavailable in this environment.",
             "https://www.euda.europa.eu/data/stats2026/ppp_en", now),
        ])
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
    finally:
        db.close()
        src.close()
    temp.replace(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.input, args.output)
