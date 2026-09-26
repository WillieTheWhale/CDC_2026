# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Collect edition-dated HRI/GI-TOC and original CEPII geography into a SQLite shard.

Run from the repository root with backend/.venv/bin/python data_collection/context_sources.py.
Requires the World Bank shard's countries table; never makes duplicate World Bank calls.
No edition values are backfilled, no unknown cells become zero, no legacy-state distances
are attributed to successor countries. Raw country labels and cells remain available.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pdfplumber
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from trace_backend.ingest.names import ALIASES, norm  # noqa: E402

BASE = ROOT / "data_collection"
COLUMNS = ["policy", "nsp", "oat", "dcr", "naloxone", "naloxone_peer", "safer_smoking", "stimulant_rx",
           "nsp_prison", "oat_prison"]
HRI = {
    2008: ("https://hri.global/wp-content/uploads/2022/10/GSHRFullReport1-1.pdf", 16, 16),
    2010: ("https://www.hri.global/files/2010/06/29/GlobalState2010_Web.pdf", 9, 10),
    2012: ("https://hri.global/wp-content/uploads/2014/08/GlobalState2012_Web.pdf", 15, 16),
    2014: ("https://hri.global/wp-content/uploads/2022/10/GSHR2014-2.pdf", 12, 14),
    2016: ("https://hri.global/wp-content/uploads/2022/10/GSHR2016_14nov-2.pdf", 12, 14),
    2018: ("https://hri.global/wp-content/uploads/2022/10/global-state-harm-reduction-2018.pdf", 13, 16),
    2020: ("https://hri.global/wp-content/uploads/2022/10/Global_State_HRI_2020_BOOK_FA_Web-1.pdf", 10, 13),
    2022: ("https://hri.global/wp-content/uploads/2022/11/HRI_GSHR-2022_Full-Report_Final-1.pdf", 14, 19),
    2024: ("https://hri.global/wp-content/uploads/2024/10/HRI-GSHR-2024_Full-Report_Final.pdf", 12, 17),
}
EXPECTED_ROWS = {2008: 82, 2010: 94, 2012: 97, 2014: 101, 2016: 100, 2018: 161, 2020: 173, 2022: 199, 2024: 199}
# These are genuine one-to-one code changes. YUG and ANT are deliberately NOT remapped.
CEPII_CODE_FIX = {"ROM": "ROU", "ZAR": "COD", "TMP": "TLS", "PAL": "PSE"}
EXTRA_NAMES = {"pdr laos": "LAO", "laos pdr": "LAO", "san mari": "SMR", "san marino": "SMR",
               "democratic republic of the congo drc": "COD", "democratic republic of congo drc": "COD",
               # Literal spelling errors in the cited HRI tables. Preserve the printed names.
               "tunisa": "TUN", "azerbijan": "AZE", "krygyzstan": "KGZ"}
SOURCE_TYPOS = {"san mari", "tunisa", "azerbijan", "krygyzstan"}
HRI_NOTES = {
    2018: {"a": "OST is available for detoxification only.",
           "b": "OST is available for continuation only.",
           "c": "OST is available for continuation only.",
           "d": "OST in prisons is reported to be largely accessible.",
           "e": "OST is available for detoxification only.",
           "f": "The extent to which OST is available in practice in prisons is unknown."},
    2020: {"a": "OAT cannot be initiated within the prison, but is available as a continuation of medication.",
           "b": "OAT is available for detoxification only.",
           "c": "A harm reduction site allows drug use on its premises but is not officially recognised as a DCR.",
           "d": "A DCR operates without legal recognition by the government."},
}


def stamp(epoch: float | None = None) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else datetime.now(timezone.utc).isoformat()


def columns_for(year: int) -> list[str]:
    if year == 2008:
        return COLUMNS[:3]
    if year <= 2014:
        return COLUMNS[:4]
    if year == 2016:
        return COLUMNS[:4] + ["oat_prison", "nsp_prison"]
    if year <= 2020:
        return COLUMNS[:4] + ["naloxone_peer", "oat_prison", "nsp_prison"]
    return COLUMNS


def parse_mark(raw: str | None, year: int) -> tuple[int | None, str, str]:
    """Keep unknown, omitted columns and qualified checkbox observations distinct."""
    if raw is None:
        return None, "not_collected_in_edition", ""
    token = " ".join(raw.split())
    if token in ("nd", "nk", "", "-"):
        return None, "unknown", ""
    yes, no = "✓\uf0fc", "✕✗x\uf0fb"
    if year == 2016:  # Visually verified PDF font maps check to 3 and cross to 7.
        yes += "3"
        no += "7"
    match = re.fullmatch(rf"([{yes}{no}])([a-z]?)", token)
    if not match:
        return None, "unparsed", token
    value = int(match[1] in yes)
    qualifier = match[2]
    return value, "qualified_yes" if value and qualifier else "qualified_no" if qualifier else "yes" if value else "no", qualifier


class Resolver:
    """Exact names/explicit aliases only: no fuzzy country assignment."""
    def __init__(self, countries: pd.DataFrame):
        self.codes = set(countries.iso3)
        self.lookup = {norm(r["name"]): r["iso3"] for r in countries.to_dict("records")}
        self.lookup.update({norm(k): v for k, v in ALIASES.items() if v is not None})
        self.lookup.update(EXTRA_NAMES)

    def resolve(self, name: str) -> tuple[str | None, str, str | None]:
        n = norm(name)
        if "zanzibar" in n:
            return None, "subnational_not_merged", "TZA"
        if n in ("taiwan", "taiwan province of china"):
            return None, "outside_world_bank_scope", "TWN"
        code = self.lookup.get(n)
        if code not in self.codes:
            return None, "unmapped", code
        return code, "explicit_typo_correction" if n in SOURCE_TYPOS else "exact_or_explicit_alias", code


def fetch(session: requests.Session, cache: Path, filename: str, url: str, refresh: bool) -> tuple[Path, dict]:
    path = cache / filename
    sidecar = path.with_suffix(path.suffix + ".http.json")
    if path.exists() and not refresh:
        payload = path.read_bytes()
        meta = json.loads(sidecar.read_text()) if sidecar.exists() else {
            "source_url": url, "final_url": url, "retrieved_at": stamp(path.stat().st_mtime),
            "http_status": 200, "cache_note": "Retrieved during this collection's source inspection; timestamp is file write time."}
        if meta.get("sha256") and hashlib.sha256(payload).hexdigest() != meta["sha256"]:
            raise ValueError(f"Cached file checksum mismatch: {path}")
    else:
        response = session.get(url, timeout=(30, 180))
        response.raise_for_status()
        payload = response.content
        meta = {"source_url": url, "final_url": response.url, "retrieved_at": stamp(),
                "http_status": response.status_code, "content_type": response.headers.get("Content-Type"),
                "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
        if not payload:
            raise ValueError(f"Empty source: {url}")
        path.write_bytes(payload)
        time.sleep(0.4)
    if filename.endswith(".pdf") and not payload.startswith(b"%PDF"):
        raise ValueError(f"Expected PDF from {url}")
    meta.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload), local_cache_path=str(path.relative_to(BASE)))
    sidecar.write_text(json.dumps(meta, indent=2) + "\n")
    return path, meta


def hri_tables(page, year: int):
    if year != 2020:
        return page.extract_tables()
    # The 2020 PDF outlines alternate rows. Extend the column boundaries across all
    # horizontal edges to recover white rows, including wrapped country labels.
    first = page.find_tables()[0]
    xs = sorted({cell[0] for cell in first.cells} | {cell[2] for cell in first.cells})
    ys = sorted({edge["top"] for edge in page.edges if edge["orientation"] == "h" and edge["width"] > 30})
    last_mark = max(char["bottom"] for char in page.chars if char["text"] in "\uf0fc\uf0fb")
    if max(ys) < last_mark:  # Lebanon on PDF page 11 has no bottom horizontal rule.
        ys.append(last_mark + 4)
    return page.extract_tables({"vertical_strategy": "explicit", "explicit_vertical_lines": xs,
                                "horizontal_strategy": "explicit", "explicit_horizontal_lines": ys})


def parse_hri(path: Path, year: int, resolver: Resolver) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    columns = columns_for(year)
    facts, cells, raw_rows, checks = [], [], [], []
    source_id = f"hri_{year}"
    printed_totals = None
    with pdfplumber.open(path) as pdf:
        for page_number in range(HRI[year][1], HRI[year][2] + 1):
            for table_number, table in enumerate(hri_tables(pdf.pages[page_number - 1], year), 1):
                for row_number, row in enumerate(table, 1):
                    raw_rows.append({"source_id": source_id, "year": year, "pdf_page": page_number,
                                     "table_number": table_number, "row_number": row_number,
                                     "cells_json": json.dumps(row, ensure_ascii=False)})
                    if len(row) != len(columns) + 1:
                        continue
                    name = " ".join((row[0] or "").split())
                    if name in ("TOTALS", "GLOBAL TOTAL"):
                        printed_totals = dict(zip(columns, map(int, row[1:]), strict=True))
                        continue
                    parsed = [parse_mark(v, year) for v in row[1:]]
                    # Regional labels, headers and blank layout rows have no service observations.
                    if not name or all(v is None for v in row[1:]) or all((v or "").strip() == "" for v in row[1:]):
                        continue
                    if any(p[1] == "unparsed" for p in parsed):
                        if any(p[1] in ("yes", "no", "qualified_yes", "qualified_no") for p in parsed):
                            raise ValueError(f"Unparsed HRI data row {year} page {page_number}: {row}")
                        continue
                    iso3, status, entity_code = resolver.resolve(name)
                    fact = {"iso3": iso3, "country_name": name, "year": year, **dict.fromkeys(COLUMNS),
                            "source_id": source_id, "pdf_page": page_number, "mapping_status": status,
                            "source_entity_code": entity_code, "observed_edition": 1}
                    for col in COLUMNS:
                        raw = row[columns.index(col) + 1] if col in columns else None
                        value, mark_status, qualifier = parse_mark(raw, year)
                        fact[col] = value
                        cells.append({"source_id": source_id, "country_name": name, "iso3": iso3, "year": year,
                                      "field": col, "raw_cell": raw, "reported_value": value, "status": mark_status,
                                      "qualifier": qualifier, "qualifier_note": HRI_NOTES.get(year, {}).get(qualifier),
                                      "pdf_page": page_number})
                    prison = [fact["nsp_prison"], fact["oat_prison"]]
                    fact["prison_programs"] = 1 if 1 in prison else 0 if prison == [0, 0] else None
                    facts.append(fact)
    if len(facts) != EXPECTED_ROWS[year] or len({x["country_name"] for x in facts}) != len(facts):
        raise ValueError(f"HRI {year}: expected {EXPECTED_ROWS[year]} unique rows, got {len(facts)}")
    for col in columns:
        observed = sum(row[col] == 1 for row in facts)
        printed = printed_totals.get(col) if printed_totals else None
        checks.append({"source_id": source_id, "year": year, "field": col, "country_territory_rows": len(facts),
                       "reported_yes_count": observed, "reported_no_count": sum(row[col] == 0 for row in facts),
                       "unknown_count": sum(row[col] is None for row in facts), "printed_global_total": printed,
                       "difference": observed - printed if printed is not None else None,
                       "status": "no_printed_total" if printed is None else "matches" if printed == observed else "source_total_discrepancy"})
    return facts, cells, raw_rows, checks


def parse_oc(path: Path, resolver: Resolver) -> tuple[list[dict], list[dict]]:
    facts, raw = [], []
    xl = pd.ExcelFile(path, engine="calamine")
    fields = {"criminality": r"criminality avg", "resilience": r"resilience(?: avg)?[.,]?$",
              "cocaine": r"cocaine trade", "heroin": r"heroin trade", "cannabis": r"cannabis trade", "synthetic": r"synthetic drug trade"}
    for sheet in xl.sheet_names:
        match = re.fullmatch(r"(\d{4})_dataset", sheet)
        if not match:
            continue
        edition = int(match[1])
        df = xl.parse(sheet)
        for number, record in enumerate(df.to_dict("records"), 2):
            name = record["Country"]
            iso3, status, entity = resolver.resolve(name)
            fact = {"iso3": iso3, "country_name": name, "edition": edition, "year": edition,
                    "source_id": "gitoc_ocindex", "mapping_status": status, "observed_edition": 1}
            for field, pattern in fields.items():
                matches = [k for k in record if re.match(pattern, k, flags=re.I)]
                if len(matches) != 1:
                    raise ValueError(f"Ambiguous OCIndex field {field} in {sheet}: {matches}")
                fact[field] = record[matches[0]]
            facts.append(fact)
            for column, value in record.items():
                raw.append({"source_id": "gitoc_ocindex", "sheet": sheet, "edition": edition,
                            "source_row": number, "country_name": name, "iso3": iso3,
                            "field": column, "raw_value": None if pd.isna(value) else str(value),
                            "numeric_value": float(value) if isinstance(value, (float, int)) and not pd.isna(value) else None})
        if len(df) != 193:
            raise ValueError(f"Unexpected OCIndex country count {edition}: {len(df)}")
    if sorted({x["edition"] for x in facts}) != [2021, 2023, 2025]:
        raise ValueError("OCIndex workbook editions changed; review scope before accepting.")
    return facts, raw


def parse_cepii(path: Path, geo_path: Path, wb_codes: set[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with zipfile.ZipFile(path) as zipped:
        members = [n for n in zipped.namelist() if n.lower().endswith((".xls", ".xlsx", ".dta"))]
        if len(members) != 1:
            raise ValueError("CEPII dyadic archive shape changed")
        payload = io.BytesIO(zipped.read(members[0]))
        raw = pd.read_stata(payload) if members[0].endswith(".dta") else pd.read_excel(payload, engine="calamine")
    geo = pd.read_excel(geo_path, engine="calamine")
    if len(raw) != 50176 or len(geo) != 238:
        raise ValueError("CEPII source dimensions changed; inspect before accepting.")
    distances = raw.copy()
    distances["from_iso3"] = distances.iso_o.map(lambda x: CEPII_CODE_FIX.get(x, x))
    distances["to_iso3"] = distances.iso_d.map(lambda x: CEPII_CODE_FIX.get(x, x))
    distances["source_from_code"] = raw.iso_o
    distances["source_to_code"] = raw.iso_d
    distances["dist_imputed"] = 0
    distances["code_remapped"] = ((distances.from_iso3 != raw.iso_o) | (distances.to_iso3 != raw.iso_d)).astype(int)
    distances["from_in_world_bank"] = distances.from_iso3.isin(wb_codes).astype(int)
    distances["to_in_world_bank"] = distances.to_iso3.isin(wb_codes).astype(int)
    distances["legacy_state_pair"] = (raw.iso_o.isin(["ANT", "YUG"]) | raw.iso_d.isin(["ANT", "YUG"])).astype(int)
    distances["source_id"] = "cepii_dist"
    distances["source_publication_year"] = 2011
    # Static geography is not an observed time series: no fabricated observation year.
    return raw, geo, distances


def write_table(con: sqlite3.Connection, name: str, rows):
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    for col in COLUMNS + ["prison_programs", "reported_value", "printed_global_total", "difference"]:
        if col in df:
            df[col] = df[col].astype("Int64")
    df.to_sql(name, con, if_exists="replace", index=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BASE / "work/context.sqlite")
    parser.add_argument("--countries-db", type=Path, default=BASE / "work/world_bank.sqlite")
    parser.add_argument("--cache", type=Path, default=BASE / "work/context_raw")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{args.countries_db}?mode=ro", uri=True, timeout=30) as wb:
        countries = pd.read_sql_query("SELECT * FROM countries", wb)
    resolver = Resolver(countries)
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], respect_retry_after_header=True)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "TRACE-CDC2026-research/1.0 (+https://github.com/WillieTheWhale/CDC_2026)"
    provenance = []

    def source(source_id, filename, url, name, citation, license_note, license_url, year=None):
        path, metadata = fetch(session, args.cache, filename, url, args.refresh)
        provenance.append({"source_id": source_id, "name": name, "citation": citation, "license_note": license_note,
                           "license_url": license_url, "publication_year": year, **metadata})
        return path

    oc_path = source("gitoc_ocindex", "ocindex.xlsx", "https://ocindex.net/assets/downloads/global_oc_index.xlsx",
                     "Global Organized Crime Index, 2021/2023/2025 editions",
                     "Global Initiative Against Transnational Organized Crime, Global Organized Crime Index, 2021, 2023, 2025.",
                     "Official downloads page labels this Open data and invites database download; no named dataset license located.",
                     "https://ocindex.net/downloads")
    oc, oc_raw = parse_oc(oc_path, resolver)
    all_facts, all_cells, all_raw, all_checks = [], [], [], []
    for year, (url, first, last) in HRI.items():
        path = source(f"hri_{year}", f"hri{year}.pdf", url, f"The Global State of Harm Reduction {year}",
                      f"Harm Reduction International (International Harm Reduction Association for 2008/2010), The Global State of Harm Reduction {year}, global country/territory policy and service table, PDF pages {first}-{last}.",
                      f"Copyright HRI/IHRA {year}; no named open license found in report. Database contains attributed factual service observations, not the full report; original PDFs remain untracked cache.",
                      url, year)
        facts, cells, raw, checks = parse_hri(path, year, resolver)
        all_facts.extend(facts); all_cells.extend(cells); all_raw.extend(raw); all_checks.extend(checks)
        print(f"HRI {year}: {len(facts)} country/territory observations", flush=True)
    cepii_license = "Etalab Open Licence 2.0; cite Mayer and Zignago (2011)."
    cepii_url = "https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=6"
    citation = "Mayer, T. and Zignago, S. (2011), Notes on CEPII's distances measures: the GeoDist database, CEPII Working Paper 2011-25."
    dist_path = source("cepii_dist", "cepii_dist.zip", "https://www.cepii.fr/distance/dist_cepii.zip", "CEPII GeoDist dyadic file", citation, cepii_license, cepii_url, 2011)
    geo_path = source("cepii_geo", "cepii_geo.xls", "https://www.cepii.fr/distance/geo_cepii.xls", "CEPII GeoDist country/city file", citation, cepii_license, cepii_url, 2011)
    dist_raw, geo_raw, distances = parse_cepii(dist_path, geo_path, resolver.codes)
    tables = {"oc_index": oc, "context_ocindex_raw": oc_raw, "harm_reduction": all_facts,
              "context_hri_cells": all_cells, "context_hri_raw_rows": all_raw, "context_hri_checks": all_checks,
              "context_cepii_dist_raw": dist_raw, "context_cepii_geo_raw": geo_raw, "distances": distances,
              "context_sources": provenance}
    temp = args.output.with_suffix(".sqlite.tmp")
    if temp.exists():
        temp.unlink()
    with sqlite3.connect(temp) as con:
        for table, data in tables.items():
            write_table(con, table, data)
        con.executescript("""
            CREATE UNIQUE INDEX oc_index_key ON oc_index(country_name, edition);
            CREATE UNIQUE INDEX harm_reduction_key ON harm_reduction(country_name, year);
            CREATE INDEX harm_reduction_country_year ON harm_reduction(iso3, year);
            CREATE UNIQUE INDEX context_hri_cell_key ON context_hri_cells(country_name,year,field);
            CREATE UNIQUE INDEX distances_key ON distances(from_iso3,to_iso3);
            CREATE UNIQUE INDEX context_source_key ON context_sources(source_id);
        """)
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        con.commit()
    temp.replace(args.output)
    unmapped = [(x["year"], x["country_name"]) for x in all_facts if x["mapping_status"] == "unmapped"]
    if unmapped:
        raise ValueError(f"Unresolved HRI names retained in database: {unmapped}")
    print(f"Wrote {args.output}: {len(oc)} OCIndex, {len(all_facts)} HRI, {len(distances)} distances; source totals are audited in context_hri_checks.", flush=True)


if __name__ == "__main__":
    main()
