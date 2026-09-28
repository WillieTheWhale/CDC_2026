# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Collect official UNODC health annex and CDC provisional overdose observations.

Run with backend/.venv/bin/python data_collection/health/collect.py. Downloads are
cached with SHA-256 metadata. Every reported row retains its source row and original
fields; normalized values never interpolate years or standardize unlike age groups.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from python_calamine import CalamineWorkbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from trace_backend.ingest.names import ALIASES, norm  # noqa: E402

CACHE = ROOT / "data_collection/work/health_cache"
OUTPUT = ROOT / "data_collection/work/health.sqlite"
ANNEX = "https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html"
UNODC_BASE = "https://www.unodc.org"
FILES = {
    "unodc_1_1.xlsx": "/documents/data-and-analysis/WDR_2026/Annex/1.1_prevalence_of_drug_use_in_the_general_population_regional_and_global_estimates.xlsx",
    "unodc_1_2.xlsx": "/documents/data-and-analysis/WDR_2026/Annex/1.2_prevalence_of_drug_use_in_the_general_population_national_data.xlsx",
    "unodc_1_3.xlsx": "/documents/data-and-analysis/WDR_2026/Annex/1.3_prevalence_of_drug_use_in_the_population_1516_regional_and_global_estimates.xlsx",
    "unodc_1_4.xlsx": "/documents/data-and-analysis/WDR_2026/Annex/1.4_prevalence_of_drug_use_in_the_youth_population_national_data_national_data.xlsx",
    "unodc_4_1.xlsx": "/documents/data-and-analysis/WDR_2026/Annex/4.1_people_who_inject_drugs_and_prevalence_of_diseases.xlsx",
    "unodc_4_2.xlsx": "/documents/data-and-analysis/WDR_2026/Annex/4.2_people_who_inject_drugs_and_prevalence_of_diseases_by_sex.xlsx",
    "unodc_5_1.xlsx": "/documents/data-and-analysis/WDR_2026/Annex/5.1_treatment_by_primary_drug_of_use.xlsx",
}
CDC = "https://data.cdc.gov/resource/xkb8-kh2a.json"
CDC_META = "https://data.cdc.gov/api/views/xkb8-kh2a.json"
SDG = "https://unstats.un.org/SDGAPI/v1/sdg/Indicator/Data"
AGENT = "TRACE-CDC2026 academic public-health collector (source URLs in reports)"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def text(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value).strip() if value is not None else ""


def numeric(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(str(value).replace(",", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def year(value):
    result = numeric(value)
    return int(result) if result is not None and result.is_integer() and 1950 <= result <= 2026 else None


def cached_get(url, path, kind="xlsx"):
    path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        with path.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() == meta["sha256"]:
                return meta
    for attempt in range(3):
        try:
            with requests.get(url, timeout=(20, 180), stream=True, headers={"User-Agent": AGENT}) as response:
                response.raise_for_status()
                temp = path.with_name(path.name + ".part")
                digest = hashlib.sha256()
                with temp.open("wb") as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        handle.write(chunk)
                        digest.update(chunk)
            if kind == "xlsx" and temp.open("rb").read(4) != b"PK\x03\x04":
                raise ValueError("Downloaded file is not an XLSX archive")
            temp.replace(path)
            meta = {"url": url, "retrieved_at": now(), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}
            meta_path.write_text(json.dumps(meta, indent=2))
            time.sleep(0.5)
            return meta
        except (requests.RequestException, ValueError) as exc:
            if attempt == 2:
                raise RuntimeError(f"Could not retrieve {url}: {exc}") from exc
            time.sleep(2 ** (attempt + 1))


def country_index():
    data = json.loads((ROOT / "contracts/fixtures/countries.json").read_text())["data"]
    index = {norm(row["name"]): row["iso3"] for row in data}
    index.update({norm(row["iso3"]): row["iso3"] for row in data})
    index.update({norm(k): v for k, v in ALIASES.items()})
    index.update({"serbia and montenegro": "SCG", "yugoslavia": "YUG", "netherlands antilles": "ANT"})
    index.update({norm("Lao People's Democratic Republic"): "LAO"})
    return index


COUNTRIES = country_index()


def iso3(country):
    value = text(country)
    return COUNTRIES.get(norm(value)) if value else None


def create_schema(db):
    db.executescript("""
    PRAGMA journal_mode=DELETE;
    PRAGMA synchronous=NORMAL;
    CREATE TABLE health_sources (
      source_id TEXT PRIMARY KEY, publisher TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
      retrieved_at TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
      edition_year INTEGER, source_kind TEXT NOT NULL, license_note TEXT, caveat TEXT);
    CREATE TABLE health_source_files (
      source_id TEXT NOT NULL, part_name TEXT NOT NULL, url TEXT NOT NULL,
      retrieved_at TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
      PRIMARY KEY(source_id,part_name));
    CREATE TABLE health_raw_rows (
      source_id TEXT NOT NULL, sheet TEXT NOT NULL, row_no INTEGER NOT NULL,
      cells_json TEXT NOT NULL, PRIMARY KEY(source_id,sheet,row_no));
    CREATE TABLE health_geographies (
      source_name TEXT PRIMARY KEY, iso3 TEXT, resolution TEXT NOT NULL);
    CREATE TABLE health_prevalence (
      source_id TEXT NOT NULL, sheet TEXT NOT NULL, row_no INTEGER NOT NULL, cell_no INTEGER NOT NULL,
      geography_name TEXT NOT NULL, iso3 TEXT, region TEXT, subregion TEXT, year INTEGER,
      year_text TEXT, population TEXT NOT NULL, age_group TEXT, substance TEXT NOT NULL,
      substance_detail TEXT, reference_period TEXT NOT NULL, sex TEXT NOT NULL,
      value_pct REAL NOT NULL, low_pct REAL, high_pct REAL, source_method TEXT,
      source_attribution TEXT, adjustment_note TEXT, notes TEXT, estimate_status TEXT NOT NULL,
      PRIMARY KEY(source_id,sheet,row_no,cell_no));
    CREATE TABLE health_pwid (
      source_id TEXT NOT NULL, sheet TEXT NOT NULL, row_no INTEGER NOT NULL, cell_no INTEGER NOT NULL,
      geography_name TEXT NOT NULL, iso3 TEXT, region TEXT, subregion TEXT, year INTEGER,
      year_text TEXT, metric TEXT NOT NULL, sex TEXT NOT NULL, value REAL NOT NULL,
      low REAL, high REAL, unit TEXT NOT NULL, denominator TEXT, age_group TEXT,
      injecting_definition TEXT, geographic_coverage TEXT, sample_size TEXT,
      reference TEXT, method TEXT, attribution TEXT, notes TEXT, estimate_status TEXT NOT NULL,
      PRIMARY KEY(source_id,sheet,row_no,cell_no));
    CREATE TABLE health_treatment (
      source_id TEXT NOT NULL, sheet TEXT NOT NULL, row_no INTEGER NOT NULL,
      geography_name TEXT NOT NULL, iso3 TEXT, region TEXT, subregion TEXT,
      year INTEGER, year_text TEXT, drug_group TEXT, drug TEXT, sex TEXT,
      persons_treated REAL NOT NULL, specified_reference_year TEXT, coverage TEXT,
      PRIMARY KEY(source_id,sheet,row_no));
    CREATE TABLE health_treatment_coverage (
      source_id TEXT NOT NULL, source_row_no INTEGER NOT NULL, geography_name TEXT NOT NULL,
      iso3 TEXT, un_m49 TEXT, year INTEGER NOT NULL, substance_group TEXT NOT NULL,
      sex TEXT NOT NULL, value_pct REAL NOT NULL, lower_pct REAL, upper_pct REAL,
      nature_code TEXT, nature_meaning TEXT, source_attribution TEXT, footnotes_json TEXT,
      raw_row_json TEXT NOT NULL, PRIMARY KEY(source_id,source_row_no));
    CREATE TABLE health_regional_estimates (
      source_id TEXT NOT NULL, sheet TEXT NOT NULL, row_no INTEGER NOT NULL, cell_no INTEGER NOT NULL,
      region_name TEXT NOT NULL, region_level TEXT NOT NULL, year INTEGER NOT NULL,
      age_group TEXT NOT NULL, metric TEXT NOT NULL, substance TEXT, value REAL NOT NULL,
      low REAL, high REAL, unit TEXT NOT NULL, estimate_status TEXT NOT NULL,
      PRIMARY KEY(source_id,sheet,row_no,cell_no));
    CREATE TABLE health_cdc_overdose (
      source_id TEXT NOT NULL, state TEXT NOT NULL, state_name TEXT, end_year INTEGER NOT NULL,
      end_month INTEGER NOT NULL, period TEXT NOT NULL, indicator TEXT NOT NULL,
      metric_kind TEXT NOT NULL, value_unit TEXT NOT NULL,
      reported_value REAL, predicted_value REAL, percent_complete REAL,
      percent_pending_investigation REAL, footnote TEXT, footnote_symbol TEXT,
      suppressed_or_unavailable INTEGER NOT NULL, source_row_json TEXT NOT NULL,
      PRIMARY KEY(state,end_year,end_month,period,indicator));
    CREATE INDEX health_prevalence_lookup ON health_prevalence(iso3,year,substance,reference_period);
    CREATE INDEX health_pwid_lookup ON health_pwid(iso3,year,metric);
    CREATE INDEX health_treatment_lookup ON health_treatment(iso3,year,drug_group);
    CREATE INDEX health_cdc_lookup ON health_cdc_overdose(state,end_year,end_month,indicator);
    """)


def add_source(db, source_id, path, title, kind="source_workbook", caveat=""):
    # The older cache metadata written during initial discovery is accepted after
    # checksum verification; subsequent runs use the .xlsx.meta.json convention.
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    else:
        old = path.with_suffix(".json")
        meta = json.loads(old.read_text())
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != meta["sha256"]:
        raise ValueError(f"Checksum mismatch for {path}")
    db.execute("INSERT INTO health_sources VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
        source_id, "UNODC" if source_id.startswith("unodc") else
        "UN Statistics Division / UNODC" if source_id.startswith("unsd") else "CDC NCHS", title,
        meta["url"], meta["retrieved_at"], actual, path.stat().st_size,
        2026 if source_id.startswith("unodc") else None, kind,
        "UNODC World Drug Report: cite source and check third-party source terms" if source_id.startswith("unodc")
        else "UN SDG Global Database: cite UNSD and underlying attribution" if source_id.startswith("unsd")
        else "U.S. Government public domain", caveat))
    db.execute("INSERT INTO health_source_files VALUES(?,?,?,?,?,?)",(
        source_id,path.name,meta["url"],meta["retrieved_at"],actual,path.stat().st_size))


def add_geo(db, name, code):
    if not name:
        return
    resolution = "country_or_territory" if code else "unmapped_preserved"
    db.execute("INSERT OR REPLACE INTO health_geographies VALUES(?,?,?)", (name, code, resolution))


def raw_rows(db, source_id, sheet, rows):
    db.executemany("INSERT INTO health_raw_rows VALUES(?,?,?,?)", (
        (source_id, sheet, n, json.dumps(row, ensure_ascii=False, default=text))
        for n, row in enumerate(rows, 1) if any(text(value) for value in row)))


def prevalence(db, item):
    db.execute("INSERT OR IGNORE INTO health_prevalence VALUES(" + ",".join("?" * 24) + ")", item)


def parse_adult(db, sheet, rows):
    source_id = "unodc_1_2"
    if sheet == "NPS":
        for rn, row in enumerate(rows[4:], 5):
            if len(row) < 15 or not year(row[14]) or not text(row[3]):
                continue
            country, code = text(row[3]), iso3(row[3]); add_geo(db, country, code)
            for j, period, sex in [(j, period, sex) for start, period in ((5,"lifetime"),(8,"past_year"),(11,"past_month"))
                                   for j, sex in ((start,"all"),(start+1,"male"),(start+2,"female"))]:
                val = numeric(row[j]);
                if val is None: continue
                prevalence(db, (source_id,sheet,rn,j+1,country,code,text(row[1]),text(row[2]),year(row[14]),text(row[14]),
                    "general_population",text(row[15]) if len(row)>15 else "", "NPS",text(row[4]) or text(row[0]),period,sex,
                    val,None,None,"",text(row[16]) if len(row)>16 else "","", "", "source_reported"))
        return
    for rn, row in enumerate(rows[3:], 4):
        adult_year = row[6] if sheet == "Tranquillizers and sedatives" else row[8]
        if len(row) < 10 or not year(adult_year) or not text(row[2]): continue
        country, code = text(row[2]), iso3(row[2]); add_geo(db, country, code)
        if sheet == "Tranquillizers and sedatives":
            specs = [(3,"all"),(4,"male"),(5,"female")]
            yr, age, attrib, method, adjust, notes = row[6],row[7],row[8],row[9],"",row[10] if len(row)>10 else ""
        else:
            specs = [(3,"all"),(6,"male"),(7,"female")]
            yr, age, attrib, method, adjust, notes = row[8],row[9],row[10],row[11],row[12],row[13]
        for j,sex in specs:
            val=numeric(row[j]);
            if val is None: continue
            prevalence(db,(source_id,sheet,rn,j+1,country,code,text(row[0]),text(row[1]),year(yr),text(yr),
                "general_population",text(age),sheet,text(notes),"past_year",sex,val,
                numeric(row[4]) if sex=="all" and sheet!="Tranquillizers and sedatives" else None,
                numeric(row[5]) if sex=="all" and sheet!="Tranquillizers and sedatives" else None,
                text(method),text(attrib),text(adjust),text(notes),
                "published_estimate" if "estimate" in text(attrib).lower() else "source_reported"))


def parse_youth(db, sheet, rows):
    source_id = "unodc_1_4"
    if sheet == "Lookup": return
    if sheet == "NPS":
        for rn,row in enumerate(rows[5:],6):
            if len(row)<17 or not text(row[3]) or not year(row[5]):continue
            country,code=text(row[3]),iso3(row[3]);add_geo(db,country,code)
            for base,period in ((7,"lifetime"),(10,"past_year"),(13,"past_month")):
                for offset,sex in enumerate(("all","male","female")):
                    j=base+offset;val=numeric(row[j])
                    if val is None:continue
                    prevalence(db,(source_id,sheet,rn,j+1,country,code,text(row[1]),text(row[2]),year(row[5]),text(row[5]),
                        "youth",text(row[6]),"NPS",text(row[4]) or text(row[0]),period,sex,val,None,None,
                        "",text(row[16]),"",text(row[17]) if len(row)>17 else "","source_reported"))
        return
    for rn,row in enumerate(rows[4:],5):
        if len(row)<9 or not text(row[2]) or not year(row[7]) or text(row[2]).startswith("Would be great"):continue
        country,code=text(row[2]),iso3(row[2]);add_geo(db,country,code)
        for j,period in ((4,"lifetime"),(5,"past_year"),(6,"past_month")):
            val=numeric(row[j]);
            if val is None:continue
            prevalence(db,(source_id,sheet,rn,j+1,country,code,text(row[0]),text(row[1]),year(row[7]),text(row[7]),
                "youth",text(row[3]),sheet,text(row[9]) if len(row)>9 else "",period,"all",val,None,None,
                "",text(row[8]),"",text(row[9]) if len(row)>9 else "","source_reported"))


def pwid(db,item):
    db.execute("INSERT OR IGNORE INTO health_pwid VALUES("+",".join("?"*26)+")",item)


def parse_pwid(db,sheet,rows):
    source_id="unodc_4_1"
    if sheet in ("Notes","Sub-regional summary"):return
    metric={"PWID":"people_who_inject_drugs","HIV among PWID":"hiv_among_pwid",
            "HCV among PWID":"hcv_among_pwid","HBV among PWID":"hbv_active_among_pwid"}[sheet]
    for rn,row in enumerate(rows[5:],6):
        if len(row)<8 or not text(row[2]):continue
        country,code=text(row[2]),iso3(row[2]);add_geo(db,country,code)
        if sheet=="PWID":
            yr=row[10]; specs=[(5,"percent_of_general_population",4,6,"general population"),(8,"persons",7,9,None)]
            extra=(text(row[12]),text(row[11]),text(row[14]),"",text(row[15]),text(row[16]),text(row[17]),text(row[18]))
            sex=text(row[13]) or "all"
        elif sheet=="HBV among PWID":
            yr=row[5];specs=[(4,"percent",None,None,"people who inject drugs")]
            extra=("","","","",text(row[6]),text(row[7]),text(row[9]),text(row[10]));sex="all"
        else:
            yr=row[7];specs=[(5,"percent",4,6,"people who inject drugs")]
            extra=(text(row[9]),text(row[8]),text(row[11]),text(row[12]),text(row[13]),text(row[14]),text(row[15]),text(row[16]));sex=text(row[10]) or "all"
        for j,unit,lo,hi,denom in specs:
            val=numeric(row[j]);
            if val is None:continue
            pwid(db,(source_id,sheet,rn,j+1,country,code,text(row[0]),text(row[1]),year(yr),text(yr),metric,sex,
                val,numeric(row[lo]) if lo is not None else None,numeric(row[hi]) if hi is not None else None,
                unit,denom,*extra,"source_estimate"))


def parse_pwid_sex(db,sheet,rows):
    source_id="unodc_4_2";metric={"People who inject drugs_sex":"people_who_inject_drugs",
        "HIV among PWID_sex":"hiv_among_pwid","HCV among PWID_sex":"hcv_among_pwid",
        "HBV among PWID_sex":"hbv_active_among_pwid"}[sheet]
    for rn,row in enumerate(rows[2:],3):
        if len(row)<8 or not text(row[2]):continue
        country,code=text(row[2]),iso3(row[2]);add_geo(db,country,code)
        if sheet=="People who inject drugs_sex":
            specs=[(4,"male","persons",None),(5,"male","percent_of_general_population","general population"),
                   (6,"female","persons",None),(7,"female","percent_of_general_population","general population")]
            ref=text(row[8]);notes=text(row[9])
        else:
            specs=[(4,"male","percent","people who inject drugs"),(5,"female","percent","people who inject drugs")]
            ref=text(row[6]);notes=text(row[7])
        for j,sex,unit,denom in specs:
            val=numeric(row[j]);
            if val is None:continue
            pwid(db,(source_id,sheet,rn,j+1,country,code,text(row[0]),text(row[1]),year(row[3]),text(row[3]),metric,
                sex,val,None,None,unit,denom,"","","","",ref,"",ref,notes,"source_estimate"))


def region_estimate(db,item):
    db.execute("INSERT OR IGNORE INTO health_regional_estimates VALUES("+",".join("?"*15)+")",item)


def parse_regional_prevalence(db,source_id,rows):
    # Each six-column block is one substance: counts and percentages, each with
    # best/lower/upper. 1.1 has two stacked blocks; 1.3 has one wider block.
    sections=[(4,28,["cannabis","opioids","opiates"]),(35,59,["cocaine","amphetamines_and_prescription_stimulants","ecstasy"])] if source_id=="unodc_1_1" else [(4,28,["cannabis","amphetamines","cocaine","ecstasy"])]
    age="15-64" if source_id=="unodc_1_1" else "15-16"
    count_unit="source_number_header_thousands" if source_id=="unodc_1_1" else "thousand_persons"
    for start,stop,drugs in sections:
        for rowidx in range(start,min(stop,len(rows))):
            row=rows[rowidx];name=text(row[0]);
            if not name or name.startswith(("Sources", "a ","b ")):continue
            level="global" if "GLOBAL" in name.upper() else "region_or_subregion"
            for block,drug in enumerate(drugs):
                base=1+6*block
                for offset,metric,unit in ((0,"past_year_users",count_unit),(3,"past_year_prevalence","percent")):
                    j=base+offset;v=numeric(row[j]) if j<len(row) else None
                    if v is None:continue
                    region_estimate(db,(source_id,"PrevAllDrugtypes" if source_id=="unodc_1_1" else "Prevalence estimates",
                        rowidx+1,j+1,name,level,2024,age,metric,drug,v,
                        numeric(row[j+1]) if j+1<len(row) else None,
                        numeric(row[j+2]) if j+2<len(row) else None,unit,"published_model_estimate"))


def parse_regional_pwid(db,rows):
    for rn,row in enumerate(rows[4:],5):
        if not text(row[0]) and not text(row[1]):continue
        name=text(row[1]) or text(row[0]);level="subregion" if text(row[1]) else ("global" if "global" in name.lower() else "region")
        for j,metric,unit in ((3,"people_who_inject_drugs","persons"),(6,"pwid_prevalence_general_population","percent"),
            (11,"pwid_living_with_hiv","persons"),(13,"hiv_prevalence_among_pwid","percent"),
            (17,"pwid_living_with_hcv","persons"),(19,"hcv_prevalence_among_pwid","percent"),
            (23,"pwid_living_with_hbv","persons"),(25,"hbv_prevalence_among_pwid","percent")):
            if j>=len(row):continue
            v=numeric(row[j]);
            if v is None:continue
            lo=numeric(row[j-1]) if j in (3,6,11,17,23) else None
            hi=numeric(row[j+1]) if j in (3,6,11,17,23) and j+1<len(row) else None
            region_estimate(db,("unodc_4_1","Sub-regional summary",rn,j+1,name,level,2024,"15-64",metric,None,
                v,lo,hi,unit,"published_model_estimate"))


def parse_treatment(db,rows):
    for rn,row in enumerate(rows[3:],4):
        if len(row)<11 or not text(row[2]):continue
        val=numeric(row[8]);
        if val is None:continue
        country=text(row[2]);code=text(row[3]) if re.fullmatch(r"[A-Z]{3}",text(row[3])) else iso3(country)
        add_geo(db,country,code)
        db.execute("INSERT OR IGNORE INTO health_treatment VALUES("+",".join("?"*15)+")",(
            "unodc_5_1","Sheet1",rn,country,code,text(row[0]),text(row[1]),year(row[4]),text(row[4]),
            text(row[5]),text(row[6]),text(row[7]),val,text(row[9]),text(row[10])))


def collect_unodc(db):
    for filename,urlpath in FILES.items():
        source_id=filename[:-5]
        path=CACHE/filename
        if not path.exists():cached_get(urljoin(UNODC_BASE,urlpath),path)
        add_source(db,source_id,path,"UNODC World Drug Report 2026 statistical annex "+source_id.split("_")[1]+"."+source_id.split("_")[2],
            caveat="Source observations vary in age, method, coverage and reference period; regional values are model estimates.")
        wb=CalamineWorkbook.from_path(str(path))
        for sheet in wb.sheet_names:
            rows=wb.get_sheet_by_name(sheet).to_python()
            raw_rows(db,source_id,sheet,rows)
            if source_id=="unodc_1_2":parse_adult(db,sheet,rows)
            elif source_id=="unodc_1_4":parse_youth(db,sheet,rows)
            elif source_id=="unodc_4_1":parse_pwid(db,sheet,rows)
            elif source_id=="unodc_4_2":parse_pwid_sex(db,sheet,rows)
            elif source_id=="unodc_5_1":parse_treatment(db,rows)
            elif source_id in ("unodc_1_1","unodc_1_3"):parse_regional_prevalence(db,source_id,rows)
            if source_id=="unodc_4_1" and sheet=="Sub-regional summary":parse_regional_pwid(db,rows)
        db.commit()
        print(source_id,"parsed",flush=True)


def collect_sdg(db):
    path=CACHE/"unsd_sdg_3_5_1.json"
    url=requests.Request("GET",SDG,params={"indicator":"3.5.1","pageSize":5000}).prepare().url
    cached_get(url,path,"json")
    add_source(db,"unsd_sdg_3_5_1",path,"UN SDG indicator 3.5.1 treatment intervention coverage",
        "live_sdg_api_json", "Drug use disorder coverage, percent. Nature M is modeled; C is country data. Substance groups and sex must be retained.")
    payload=json.loads(path.read_text())
    if payload.get("totalElements") != len(payload.get("data",[])):
        raise ValueError("SDG 3.5.1 response was paginated or incomplete")
    meaning={"M":"modeled","C":"country_data","E":"estimated","G":"global_monitoring","CA":"country_adjusted","NA":"unavailable"}
    for row_no,row in enumerate(payload["data"],1):
        if row.get("series")!="SH_SUD_TREAT":continue
        substance=text(row.get("dimensions",{}).get("Substance use disorders"))
        if substance=="ALCOHOL":continue
        value=numeric(row.get("value"));yr=year(row.get("timePeriodStart"))
        if value is None or yr is None:continue
        country=text(row.get("geoAreaName"));code=iso3(country);add_geo(db,country,code)
        nature=text(row.get("attributes",{}).get("Nature"))
        db.execute("INSERT INTO health_treatment_coverage VALUES("+",".join("?"*16)+")",(
            "unsd_sdg_3_5_1",row_no,country,code,text(row.get("geoAreaCode")),yr,substance,
            text(row.get("dimensions",{}).get("Sex")),value,numeric(row.get("lowerBound")),
            numeric(row.get("upperBound")),nature,meaning.get(nature,"unknown"),text(row.get("source")),
            json.dumps(row.get("footnotes",[]),ensure_ascii=False),json.dumps(row,ensure_ascii=False)))
    db.commit();print("unsd_sdg_3_5_1 parsed",flush=True)


def collect_cdc(db):
    metadata_path=CACHE/"cdc_dataset_metadata.json"
    metadata=cached_get(CDC_META,metadata_path,"json")
    add_source(db,"cdc_xkb8_kh2a",metadata_path,"CDC NCHS VSRR provisional drug overdose death counts",
        "live_socrata_json", "Rolling 12-month ending counts, by occurrence jurisdiction. Reported and predicted are distinct; suppressed/low-quality values remain missing. Drug categories overlap.")
    session=requests.Session();session.headers.update({"User-Agent":AGENT})
    total=int(session.get(CDC,params={"$select":"count(*)"},timeout=60).json()[0]["count"])
    page_size=5000
    for offset in range(0,total,page_size):
        page=CACHE/f"cdc_{offset:06d}.json"
        url=requests.Request("GET",CDC,params={"$limit":page_size,"$offset":offset,"$order":":id"}).prepare().url
        cached_get(url,page,"json")
        page_meta=json.loads(page.with_suffix(".json.meta.json").read_text())
        db.execute("INSERT INTO health_source_files VALUES(?,?,?,?,?,?)",(
            "cdc_xkb8_kh2a",page.name,page_meta["url"],page_meta["retrieved_at"],
            page_meta["sha256"],page_meta["bytes"]))
        data=json.loads(page.read_text())
        if not isinstance(data,list):raise ValueError(f"CDC page {offset} is not an array")
        for row in data:
            y=year(row.get("year"));m=next((n for n in range(1,13) if calendar.month_name[n].lower()==text(row.get("month")).lower()),None)
            if y is None or m is None:continue
            reported=numeric(row.get("data_value"));predicted=numeric(row.get("predicted_value"))
            indicator=text(row.get("indicator"))
            kind=("drug_specification_fraction" if indicator=="Percent with drugs specified" else
                  "all_cause_mortality" if indicator=="Number of Deaths" else
                  "drug_overdose_total" if indicator=="Number of Drug Overdose Deaths" else "drug_involved_overdose")
            unit="percent" if kind=="drug_specification_fraction" else "deaths"
            db.execute("INSERT OR REPLACE INTO health_cdc_overdose VALUES("+",".join("?"*17)+")",(
                "cdc_xkb8_kh2a",text(row.get("state")),text(row.get("state_name")),y,m,
                text(row.get("period")),indicator,kind,unit,reported,predicted,
                numeric(row.get("percent_complete")),numeric(row.get("percent_pending_investigation")),
                text(row.get("footnote")),text(row.get("footnote_symbol")),int(reported is None and predicted is None),
                json.dumps(row,ensure_ascii=False)))
        db.commit();print("cdc",offset+len(data),"/",total,flush=True)
        time.sleep(0.3)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--skip-cdc",action="store_true")
    args=parser.parse_args()
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    temp=OUTPUT.with_suffix(".sqlite.tmp")
    if temp.exists():temp.unlink()
    try:
        with sqlite3.connect(temp) as db:
            create_schema(db);collect_unodc(db);collect_sdg(db)
            if not args.skip_cdc:collect_cdc(db)
            db.execute("PRAGMA optimize")
            check=db.execute("PRAGMA integrity_check").fetchone()[0]
            if check!="ok":raise RuntimeError(f"SQLite integrity failure: {check}")
            db.commit()
        temp.replace(OUTPUT)
        print("ready",OUTPUT,OUTPUT.stat().st_size,"bytes",flush=True)
    except BaseException:
        if temp.exists():temp.unlink()
        raise


if __name__=="__main__":main()
