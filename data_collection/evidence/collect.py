# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Build a small, source-verified catalog of published context claims.

These are cited contextual statements and policy milestones, not annual bilateral
flow observations. Keep all cache files outside Git in data_collection/work.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import sqlite3
import time
from pathlib import Path

import requests
from python_calamine import CalamineWorkbook

ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/"data_collection/work/evidence_cache"
OUTPUT=ROOT/"data_collection/work/evidence.sqlite"
SOURCES={
 "wdr2026_cocaine":("https://data.unodc.org/wdr2026?page=51","World Drug Report 2026: Cocaine trafficking","html"),
 "wdr2026_meth":("https://data.unodc.org/wdr2026?page=17","World Drug Report 2026: Methamphetamine trafficking flows","html"),
 "wdr2026_policy":("https://www.unodc.org/documents/data-and-analysis/WDR_2026/Annex/11.1_cannabis_regulation_in_different_countries_and_jurisdictions.xlsx","World Drug Report 2026 annex 11.1: cannabis regulation","xlsx"),
}
ROUTES=[
 ("cocaine_andean_reported_departures","wdr2026_cocaine","cocaine","Colombia and Ecuador","North America and Europe","2020-2024",
  "UNODC reports Colombia and Ecuador as cocaine shipment departure countries serving North America and Europe.",
  "Colombia and Ecuador supplying North America and Europe","Cocaine trafficking, bullet 1",
  "Reported departure and destination patterns are aggregated over 2020-2024; no shipment-level country-pair counts or annual flows are published here."),
 ("cocaine_brazil_reported_destinations","wdr2026_cocaine","cocaine","Brazil","Europe, Africa and Asia","2020-2024",
  "UNODC describes Brazil as a significant cocaine departure point for flows to Europe, Africa and Asia.",
  "Brazil playing a key role in flows to Europe, as well as Africa and Asia","Cocaine trafficking, bullet 1",
  "Brazil may be a departure or transshipment country rather than the cultivation origin; this source does not quantify annual bilateral flows."),
 ("meth_afghanistan_asia_departure","wdr2026_meth","methamphetamine","Afghanistan","Asia reporting countries","2021-2024",
  "Afghanistan was the leading reported methamphetamine departure country for seizures reported in Asia in the 2021-2024 period.",
  "Afghanistan was the main country reported in Asia","Methamphetamine trafficking flows, bullet 3",
  "This is a ranking of reported countries of departure, not a measured Afghanistan-to-any-destination annual flow."),
 ("meth_mexico_americas_departure","wdr2026_meth","methamphetamine","Mexico","Americas reporting countries","2021-2024",
  "Mexico was the dominant reported methamphetamine departure country for seizures reported in the Americas in the 2021-2024 period.",
  "Mexico dominates in the Americas","Methamphetamine trafficking flows, bullet 3",
  "This is a regional departure ranking; it neither identifies every destination nor quantifies bilateral flows."),
]
POLICIES=[
 ("canada_cannabis_federal_implementation","Canada",5,1,"2018-10-17",
  "Canada's federal Cannabis Act and Cannabis Regulations were implemented on 17 October 2018.",
  "Nationwide federal implementation; provincial rules differ."),
 ("germany_cannabis_act_implementation","Germany",6,1,"2024-04",
  "Germany's Cannabis Act came into force in April 2024, with grower clubs following in July 2024.",
  "The annex describes separate implementation stages and does not imply a general retail market."),
 ("luxembourg_cannabis_implementation","Luxembourg",6,1,"2023-07-21",
  "Luxembourg implemented its limited non-medical cannabis reform on 21 July 2023.",
  "The annex limits cultivation, possession and use to residences; this is not a commercial retail legalization."),
 ("malta_cannabis_implementation","Malta",6,1,"2021-12-18",
  "Malta implemented its non-medical cannabis reform on 18 December 2021.",
  "The annex describes nonprofit clubs and home cultivation, not general commercial retail sales."),
]


def utc():return dt.datetime.now(dt.timezone.utc).isoformat()


def fetch(source_id,url,kind):
    CACHE.mkdir(parents=True,exist_ok=True)
    path=CACHE/(source_id+(".xlsx" if kind=="xlsx" else ".html"))
    meta=path.with_suffix(path.suffix+".json")
    if path.exists() and meta.exists():
        info=json.loads(meta.read_text())
        with path.open("rb") as handle:
            if hashlib.file_digest(handle,"sha256").hexdigest()==info["sha256"]:return path,info
    for attempt in range(3):
        try:
            r=requests.get(url,headers={"User-Agent":"TRACE-CDC2026 academic evidence catalog"},timeout=45)
            r.raise_for_status()
            if kind=="xlsx" and not r.content.startswith(b"PK\x03\x04"):raise ValueError("Invalid XLSX")
            if len(r.content)>2_000_000:raise ValueError("Source exceeds 2 MB catalog limit")
            path.write_bytes(r.content)
            info={"url":url,"retrieved_at":utc(),"sha256":hashlib.sha256(r.content).hexdigest(),"bytes":len(r.content)}
            meta.write_text(json.dumps(info,indent=2));time.sleep(.3)
            return path,info
        except (requests.RequestException,ValueError):
            if attempt==2:raise
            time.sleep(2**attempt)


def page_text(path):
    raw=path.read_text(errors="replace")
    raw=re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>"," ",raw,flags=re.I|re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>"," ",raw)).split())


def create(db):
    db.executescript("""
    CREATE TABLE evidence_sources (
      source_id TEXT PRIMARY KEY,publisher TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,
      publication_year INTEGER NOT NULL,retrieved_at TEXT NOT NULL,sha256 TEXT NOT NULL,
      bytes INTEGER NOT NULL,source_format TEXT NOT NULL);
    CREATE TABLE evidence_claims (
      claim_id TEXT PRIMARY KEY,source_id TEXT NOT NULL,claim_type TEXT NOT NULL,drug TEXT,
      geography_from TEXT,geography_to TEXT,geography_scope TEXT NOT NULL,
      observation_start_year INTEGER,observation_end_year INTEGER,policy_effective_date TEXT,
      publication_year INTEGER NOT NULL,normalized_claim TEXT NOT NULL,original_excerpt TEXT NOT NULL,
      source_locator TEXT NOT NULL,evidence_basis TEXT NOT NULL,caveat TEXT NOT NULL,
      FOREIGN KEY(source_id) REFERENCES evidence_sources(source_id));
    CREATE INDEX evidence_claims_type ON evidence_claims(claim_type,drug,observation_start_year);
    """)


def build():
    paths={};infos={}
    for sid,(url,title,kind) in SOURCES.items():
        paths[sid],infos[sid]=fetch(sid,url,kind)
    pages={sid:page_text(paths[sid]) for sid in ("wdr2026_cocaine","wdr2026_meth")}
    workbook=CalamineWorkbook.from_path(str(paths["wdr2026_policy"]))
    sheets={name:workbook.get_sheet_by_name(name).to_python() for name in workbook.sheet_names}
    temp=OUTPUT.with_suffix(".sqlite.tmp")
    if temp.exists():temp.unlink()
    try:
        with sqlite3.connect(temp) as db:
            db.execute("PRAGMA foreign_keys=ON");create(db)
            for sid,(url,title,kind) in SOURCES.items():
                info=infos[sid]
                db.execute("INSERT INTO evidence_sources VALUES(?,?,?,?,?,?,?,?,?)",(
                    sid,"UNODC",title,url,2026,info["retrieved_at"],info["sha256"],info["bytes"],kind))
            for claim_id,sid,drug,src,dst,years,claim,excerpt,locator,caveat in ROUTES:
                if excerpt not in pages[sid]:raise ValueError(f"Quote missing from source: {claim_id}")
                start,end=map(int,years.split("-"))
                db.execute("INSERT INTO evidence_claims VALUES("+",".join("?"*16)+")",(
                    claim_id,sid,"published_aggregate_corridor_context",drug,src,dst,
                    "multiregional",start,end,None,2026,claim,excerpt,locator,
                    "UNODC WDR 2026 textual summary of reported seizure departure patterns",caveat))
            for claim_id,sheet,rn,cn,date,claim,caveat in POLICIES:
                if sheet not in sheets:raise ValueError(f"Missing sheet {sheet}")
                original=sheets[sheet][rn-1][cn]
                original_text=original.isoformat() if isinstance(original,(dt.date,dt.datetime)) else str(original)
                if not original_text.strip():raise ValueError(f"Missing policy cell {sheet}!R{rn}C{cn+1}")
                if str(int(date[:4])) not in original_text and date not in original_text:
                    raise ValueError(f"Policy date not verified in source cell: {claim_id}: {original_text}")
                db.execute("INSERT INTO evidence_claims VALUES("+",".join("?"*16)+")",(
                    claim_id,"wdr2026_policy","published_policy_milestone","cannabis",sheet,None,
                    "national",None,None,date,2026,claim,original_text,f"Annex 11.1, {sheet}!R{rn}C{cn+1}",
                    "UNODC WDR 2026 regulatory compilation",caveat))
            assert db.execute("SELECT count(*) FROM evidence_claims").fetchone()[0]==len(ROUTES)+len(POLICIES)
            assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
            db.commit()
        temp.replace(OUTPUT)
    except BaseException:
        if temp.exists():temp.unlink()
        raise
    print(f"ready {OUTPUT}: {len(ROUTES)} corridor context claims, {len(POLICIES)} policy milestones, {OUTPUT.stat().st_size} bytes")


if __name__=="__main__":build()
