# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""UNODC Individual Drug Seizures (IDS), public release from https://dmp.unodc.org/downloadIDS.

The public workbooks (2011-2026) list country of seizure, drug, quantity, unit, date, location and
transport mode. They do NOT include departure / transit / destination (restricted tier). So:

- `load()` returns case-level seizures (`seizures_raw`) and a country-year-drug aggregate that we use
  as node volume and to backcast 2011-2014 before the WDR annex series starts.
- `route_hops()` is ready for a release that does carry route fields: if any workbook has
  departure/transit/destination columns, hops are built exactly as SYSTEM_DESIGN section 6 describes
  (departure->transit, transit->destination, or departure->destination) and the edge builder uses them.
"""
from __future__ import annotations

import logging
import re

import pandas as pd
from python_calamine import CalamineWorkbook

from .. import config
from .http import fetch
from .unodc_annex import map_drug

log = logging.getLogger(__name__)
BASE = "https://dmp.unodc.org/sites/dmp.local/files/"
FILES = ["2024-05/IDS-data-2011_17-May24.xlsx", "2026-09/IDS-data-2018-2022.xlsx", "2026-09/IDS-data-2023-2026.xlsx"]
DIR = config.RAW / "unodc_ids"
UNIT_KG = {"kg": 1.0, "g": 0.001, "mg": 1e-6, "ton": 1000.0, "tons": 1000.0, "t": 1000.0}
TABLET_KG = 0.0001  # 0.1 g per methamphetamine tablet (UNODC conversion convention)
ROUTE_PATTERNS = {"departure": re.compile(r"depart|origin", re.I), "transit": re.compile(r"transit", re.I),
                  "destination": re.compile(r"destination", re.I)}


def download(refresh: bool = False) -> dict[str, str]:
    return {f: fetch(BASE + f, DIR / f.split("/")[-1], refresh=refresh) for f in FILES}


def _canon(col: str) -> str:
    c = str(col).strip().lower()
    for k, pat in ROUTE_PATTERNS.items():
        if pat.search(c):
            return k
    return {"seizure date": "date", "iso3": "iso3", "drug/substance": "drug_raw", "measurement unit": "unit",
            "quantity seized": "qty", "trafficking mode of transportation": "mode",
            "physical seizure location": "location"}.get(c, c)


def load() -> tuple[pd.DataFrame, list[str]]:
    frames, route_cols = [], set()
    for f in FILES:
        path = DIR / f.split("/")[-1]
        wb = CalamineWorkbook.from_path(str(path))
        for sheet in wb.sheet_names:
            if not re.fullmatch(r"\d{4}", sheet.strip()):
                continue
            rows = wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
            if not rows:
                continue
            cols = [_canon(c) for c in rows[0]]
            df = pd.DataFrame(rows[1:], columns=cols)
            route_cols |= {c for c in cols if c in ROUTE_PATTERNS}
            keep = [c for c in ["date", "iso3", "drug_raw", "unit", "qty", "mode", "location", *ROUTE_PATTERNS]
                    if c in df]
            df = df[keep].copy()
            df["year"] = int(sheet)
            frames.append(df)
            log.info("IDS %s sheet %s: %d cases", path.name, sheet, len(df))
    raw = pd.concat(frames, ignore_index=True)
    raw["qty"] = pd.to_numeric(raw["qty"], errors="coerce")
    drugs = {n: map_drug("", n) for n in raw["drug_raw"].dropna().unique()}
    raw["drug"] = raw["drug_raw"].map(lambda n: drugs.get(n, (None, 0))[0])
    raw["mult"] = raw["drug_raw"].map(lambda n: drugs.get(n, (None, 0))[1])
    unit = raw["unit"].astype(str).str.strip().str.lower()
    kg = unit.map(UNIT_KG)
    tablets = unit.str.contains("tablet|pill", regex=True) & (raw["drug"] == "meth")
    kg = kg.where(~tablets, TABLET_KG)
    raw["kg"] = raw["qty"] * kg * raw["mult"]
    raw["iso3"] = raw["iso3"].astype(str).str.strip().str.upper()
    raw = raw.dropna(subset=["drug", "kg"])
    raw = raw[raw["kg"] > 0]
    cols = ["iso3", "year", "date", "drug", "drug_raw", "kg", "mode", "location", *sorted(route_cols)]
    return raw[[c for c in cols if c in raw]].reset_index(drop=True), sorted(route_cols)


def aggregate(raw: pd.DataFrame) -> pd.DataFrame:
    return (raw.groupby(["iso3", "year", "drug"], as_index=False)
            .agg(kg=("kg", "sum"), cases=("kg", "size")).assign(source="unodc_ids"))


def route_hops(raw: pd.DataFrame, resolve) -> pd.DataFrame:
    """Split each seizure into hops (SYSTEM_DESIGN section 6). Empty if the release has no route fields."""
    if not any(c in raw for c in ROUTE_PATTERNS):
        return pd.DataFrame(columns=["year", "drug", "from_iso3", "to_iso3", "kg", "cases"])
    r = raw.copy()
    for c in ROUTE_PATTERNS:
        r[c] = r[c].map(resolve) if c in r else None
    hops = []
    for _, s in r.iterrows():
        dep, tra, dst = s.get("departure"), s.get("transit"), s.get("destination") or s["iso3"]
        pairs = [(dep, tra), (tra, dst)] if tra else [(dep, dst)]
        for a, b in pairs:
            if a and b and a != b:
                hops.append({"year": s["year"], "drug": s["drug"], "from_iso3": a, "to_iso3": b, "kg": s["kg"]})
    h = pd.DataFrame(hops)
    if h.empty:
        return pd.DataFrame(columns=["year", "drug", "from_iso3", "to_iso3", "kg", "cases"])
    return h.groupby(["year", "drug", "from_iso3", "to_iso3"], as_index=False).agg(kg=("kg", "sum"),
                                                                                  cases=("kg", "size"))
