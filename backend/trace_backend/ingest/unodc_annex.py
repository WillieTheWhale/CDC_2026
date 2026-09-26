# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""UNODC World Drug Report 2026 statistical annex: seizures, cultivation, production, prices, cannabis regulation.

Source: https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html
"""
from __future__ import annotations

import datetime as dt
import logging
import re

import numpy as np
import pandas as pd

from .. import config
from .http import fetch
from .names import CountryResolver

log = logging.getLogger(__name__)
BASE = "https://www.unodc.org/documents/data-and-analysis/WDR_2026/Annex/"
FILES = {
    "seizures": "7.1_Drug_seizures_2015-2024.xlsx",
    "coca": "6.1.1_global_Illicit_cultivation_of_coca_bush.xlsx",
    "opium": "6.2.1_illicit_cultivation_of_opium_poppy.xlsx",
    "opium_prod": "6.2.2_potential_production_of_oven-dry_opium.xlsx",
    "prices": "8.1_Prices_and_purities_of_drugs.xlsx",
    "price_ts": "8.3_price_time_series_in_western_europe_and_united_states.xlsx",
    "cannabis_reg": "11.1_cannabis_regulation_in_different_countries_and_jurisdictions.xlsx",
    "pwid": "4.1_people_who_inject_drugs_and_prevalence_of_diseases.xlsx",
}
DIR = config.RAW / "unodc_wdr_annex"
OPIUM_TO_HEROIN = 10.0  # kg opium per kg heroin-equivalent (documented approximation)


def download(refresh: bool = False) -> dict[str, str]:
    return {k: fetch(BASE + f, DIR / f, refresh=refresh) for k, f in FILES.items()}


def _read(key: str, **kw) -> pd.DataFrame:
    return pd.read_excel(DIR / FILES[key], engine="calamine", **kw)


# ------------------------------------------------------------------ drug mapping
COCAINE_EXCLUDE = re.compile(r"coca (leaf|bush)", re.I)
CANNABIS_KEEP = re.compile(r"herb|resin|oil|non-specified cannabis|other types of cannabis|^cannabis-type$", re.I)


def map_drug(group: str, name: str) -> tuple[str | None, float]:
    """Return (trace_drug, multiplier to heroin/kg-equivalent) for a UNODC drug label."""
    g, n = str(group or ""), str(name or "")
    gl, nl = g.lower(), n.lower()
    if "cocaine" in gl or "cocaine" in nl or "coca paste" in nl or "crack" in nl:
        if COCAINE_EXCLUDE.search(n):
            return None, 0
        return "cocaine", 1.0
    if nl.startswith("heroin") or nl == "illicit morphine" or nl.startswith("morphine"):
        return "heroin", 1.0
    if nl.startswith("opium") or nl == "acetylated opium":
        return "heroin", 1 / OPIUM_TO_HEROIN
    if re.match(r"^(crystalline )?methamphetamine", nl) or nl in {"methamphetamine tablets", "ice"}:
        return "meth", 1.0
    if "cannabis" in gl or "cannabis" in nl:
        if "plant" in nl or "seed" in nl or "synthetic" in nl or "am-2201" in nl:
            return None, 0
        if CANNABIS_KEEP.search(n):
            return "cannabis", 1.0
    return None, 0


# ------------------------------------------------------------------ seizures (7.1)
def seizures() -> pd.DataFrame:
    df = _read("seizures", header=1)
    df = df.rename(columns={"Iso3_code": "iso3", "Reference year": "year", "Kilograms": "kg"})
    df["kg"] = pd.to_numeric(df["kg"], errors="coerce")
    df = df.dropna(subset=["kg", "year"])
    df["year"] = df["year"].astype(int)
    mapped = df.apply(lambda r: map_drug(r["DrugGroup"], r["DrugName"]), axis=1, result_type="expand")
    df["drug"], df["mult"] = mapped[0], mapped[1]
    df = df.dropna(subset=["drug"])
    df["kg_eq"] = df["kg"] * df["mult"]
    # Cocaine: some countries report a "total" row as well as components; prefer the total.
    is_total = df["DrugName"].str.startswith("Cocaine (total", na=False)
    tot_keys = set(map(tuple, df.loc[is_total, ["iso3", "year"]].values))
    coc_comp = (df["drug"] == "cocaine") & ~is_total
    df = df[~(coc_comp & df[["iso3", "year"]].apply(tuple, axis=1).isin(tot_keys))]
    out = df.groupby(["iso3", "year", "drug"], as_index=False)["kg_eq"].sum().rename(columns={"kg_eq": "kg"})
    out["source"] = "unodc_wdr_annex_7.1"
    return out


# ------------------------------------------------------------------ cultivation / production
def _year_of(v) -> int | None:
    if isinstance(v, (dt.datetime, dt.date, pd.Timestamp)):
        return v.year
    try:
        f = float(v)
        return int(f) if 1990 <= f <= 2035 else None
    except (TypeError, ValueError):
        return None


def strip_footnotes(name: str) -> str:
    """'Myanmar  b, c' -> 'Myanmar'; 'Other countries e' stays unmatched later."""
    return re.sub(r"(\s+[a-z](\s*,\s*[a-z])*|\*+)\s*$", "", name.strip()).strip()


def _wide_country_table(df: pd.DataFrame, resolve: CountryResolver) -> pd.DataFrame:
    """Parse UNODC wide tables: a header row of years, then name rows with numbers."""
    hdr_idx, year_cols = None, {}
    for i in range(min(15, len(df))):
        yc = {j: _year_of(v) for j, v in df.iloc[i].items() if _year_of(v)}
        if len(yc) >= 5:
            hdr_idx, year_cols = i, yc
            break
    if hdr_idx is None:
        raise ValueError("no year header row found")
    first_year_col = min(year_cols)
    rows = []
    for i in range(hdr_idx + 1, len(df)):
        r = df.iloc[i]
        names = [str(v).strip() for j, v in r.items() if j < first_year_col and isinstance(v, str) and v.strip()]
        if not names:
            continue
        name = names[-1] if len(names) > 1 and names[0].isupper() else names[0]
        low = name.lower()
        if low.startswith(("lower", "upper", "total", "sub", "source", "note", "a ", "b ", "c ")) or name.isupper():
            continue
        name = re.sub(r"\(best estimate\)|\(.*estimate.*\)", "", name, flags=re.I).strip()
        name = strip_footnotes(name)
        iso3 = resolve(name)
        if not iso3:
            continue
        for j, y in year_cols.items():
            v = pd.to_numeric(r[j], errors="coerce")
            if pd.notna(v):
                rows.append({"iso3": iso3, "year": y, "value": float(v)})
    out = pd.DataFrame(rows)
    # series breaks (e.g. Peru reported twice) -> keep the later row's value
    return out.groupby(["iso3", "year"], as_index=False)["value"].last()


def cultivation(resolve: CountryResolver) -> pd.DataFrame:
    coca = _wide_country_table(_read("coca", header=None), resolve).assign(crop="coca").rename(
        columns={"value": "hectares"})
    opium = _wide_country_table(_read("opium", header=None), resolve).assign(crop="opium_poppy").rename(
        columns={"value": "hectares"})
    prod = _wide_country_table(_read("opium_prod", header=None), resolve).rename(columns={"value": "production_t"})
    opium = opium.merge(prod, on=["iso3", "year"], how="outer").assign(crop="opium_poppy")
    coca["production_t"] = np.nan
    out = pd.concat([coca, opium], ignore_index=True)[["iso3", "crop", "year", "hectares", "production_t"]]
    return out.sort_values(["crop", "iso3", "year"]).reset_index(drop=True)


# ------------------------------------------------------------------ prices
UNIT_PER_GRAM = {"grams": 1.0, "gram": 1.0, "g": 1.0, "kilograms": 1000.0, "kilogram": 1000.0, "kg": 1000.0}


def prices(resolve: CountryResolver) -> pd.DataFrame:
    p = _read("prices", sheet_name="Prices in USD", header=1)
    p.columns = [str(c).strip() for c in p.columns]
    mapped = p.apply(lambda r: map_drug(r["DrugGroup"], r["Drug"]), axis=1, result_type="expand")
    p["drug"] = mapped[0]
    p = p[p["drug"].notna() & ~p["Drug"].astype(str).str.lower().str.startswith("opium")]
    p["per"] = p["Unit"].astype(str).str.strip().str.lower().map(UNIT_PER_GRAM)
    p = p.dropna(subset=["per"])
    typ = pd.to_numeric(p["Typical_USD"], errors="coerce")
    mid = pd.concat([pd.to_numeric(p["Minimum_USD"], errors="coerce"),
                     pd.to_numeric(p["Maximum_USD"], errors="coerce")], axis=1).mean(axis=1)
    p["usd_g"] = typ.fillna(mid) / p["per"]
    p["level"] = p["LevelOfSale"].astype(str).str.strip().str.lower()
    p = p[p["level"].isin(["retail", "wholesale"])].dropna(subset=["usd_g"])
    p["iso3"] = p["Country/Territory"].map(resolve)
    p = p.dropna(subset=["iso3"])
    p["year"] = pd.to_numeric(p["Year"], errors="coerce").astype("Int64")
    out = (p.groupby(["iso3", "drug", "level", "year"], as_index=False)["usd_g"].median()
           .assign(source="unodc_wdr_annex_8.1", purity_pct=np.nan))
    # 8.3 long time series (retail, W. Europe and US): fill years before 2020
    ts = price_time_series(resolve)
    if len(ts):
        key = ["iso3", "drug", "level", "year"]
        ts = ts[~ts.set_index(key).index.isin(out.set_index(key).index)]
        out = pd.concat([out, ts], ignore_index=True)
    out = out[(out["usd_g"] > 0) & (out["usd_g"] < 5000)]
    return out.sort_values(["iso3", "drug", "level", "year"]).reset_index(drop=True)


def price_time_series(resolve: CountryResolver) -> pd.DataFrame:
    rows = []
    xl = pd.ExcelFile(DIR / FILES["price_ts"], engine="calamine")
    for sheet in xl.sheet_names:
        drug = "heroin" if sheet.lower().startswith("heroin") else "cocaine" if sheet.lower().startswith(
            "cocaine") else None
        if not drug:
            continue
        df = xl.parse(sheet, header=None)
        hdr = None
        for i in range(min(12, len(df))):
            if sum(_year_of(v) is not None for v in df.iloc[i].values[1:]) >= 10:
                hdr = i
                break
        if hdr is None:
            continue
        years = {j: _year_of(v) for j, v in enumerate(df.iloc[hdr].values) if _year_of(v)}
        level, per = "retail", 1.0  # tables are stacked: retail US$/g first, then wholesale US$/kg
        for i in range(hdr + 1, len(df)):
            name = df.iat[i, 0]
            cells = [str(v) for v in df.iloc[i].values if isinstance(v, str)]
            text = " ".join(cells).lower()
            if "wholesale" in text:
                level, per = "wholesale", (1000.0 if "kilogram" in text else 1.0)
            elif "retail" in text and "price" in text:
                level, per = "retail", (1000.0 if "kilogram" in text else 1.0)
            elif "inflation" in text or "average" in text:
                level = None
            yrow = {j: _year_of(v) for j, v in enumerate(df.iloc[i].values) if _year_of(v)}
            if len(yrow) >= 10:
                years = yrow
                continue
            if not level or not isinstance(name, str) or not name.strip():
                continue
            if name.strip().lower().startswith(("note", "source", "*", "average", "weighted", "mean", "unweighted")):
                continue
            iso3 = resolve(strip_footnotes(name))
            if not iso3:
                continue
            for j, y in years.items():
                v = pd.to_numeric(df.iat[i, j], errors="coerce")
                if pd.notna(v) and y >= 2005:
                    rows.append({"iso3": iso3, "drug": drug, "level": level, "year": y, "usd_g": float(v) / per,
                                 "source": "unodc_wdr_annex_8.3", "purity_pct": np.nan})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ cannabis regulation (11.1)
SHEET_ISO = {"canada": "CAN", "united states": "USA", "uruguay": "URY", "germany": "DEU", "luxembourg": "LUX",
             "malta": "MLT"}
# Documented first-effective years where the sheet gives only state-level dates (US: Colorado/Washington 2012)
KNOWN_START = {"USA": 2012, "URY": 2013}


def cannabis_regulation() -> pd.DataFrame:
    xl = pd.ExcelFile(DIR / FILES["cannabis_reg"], engine="calamine")
    found: dict[str, dict] = {}
    for sheet in xl.sheet_names:
        base = re.sub(r"\s*\d+$", "", sheet).strip().lower()
        iso3 = SHEET_ISO.get(base)
        if not iso3:
            continue
        df = xl.parse(sheet, header=None)
        years = []
        for i in range(len(df)):
            if str(df.iat[i, 0]).strip().lower().startswith("date implemented") or any(
                    str(v).strip().lower().startswith("date implemented") for v in df.iloc[i].values):
                for v in df.iloc[i].values:
                    y = _year_of(v) if not isinstance(v, str) else None
                    if y:
                        years.append(y)
                    elif isinstance(v, str):
                        m = re.search(r"(19|20)\d{2}", v)
                        if m and "date" not in v.lower():
                            years.append(int(m.group(0)))
        scope = "subnational" if iso3 == "USA" else "national"
        prev = found.get(iso3, {"years": []})
        found[iso3] = {"years": prev["years"] + years, "scope": scope}
    rows = []
    for iso3, d in found.items():
        start = min(d["years"]) if d["years"] else None
        start = min(filter(None, [start, KNOWN_START.get(iso3)])) if (start or KNOWN_START.get(iso3)) else None
        rows.append({"iso3": iso3, "year_effective": start, "scope": d["scope"], "source": "unodc_wdr_annex_11.1"})
    return pd.DataFrame(rows)
