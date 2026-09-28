# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Collect public UNODC histories into SQLite, preserving original records and cells.

Run with backend/.venv/bin/python data_collection/unodc.py. No API key is needed.
Downloads are cached, sequential, retried three times, and spaced one second apart.
A shard is rebuilt atomically; other collectors' SQLite files are never modified.
"""
from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from trace_backend.ingest.unodc_annex import FILES as ANNEX_FILES, BASE as ANNEX_BASE, map_drug
from trace_backend.ingest.names import ALIASES, norm

CACHE = ROOT / 'data_collection/work/unodc_cache'
IDS_BASE = 'https://dmp.unodc.org/sites/dmp.local/files/'
DOWNLOADS = {
    'ids_2011.xlsx': IDS_BASE + '2024-05/IDS-data-2011_17-May24.xlsx',
    'ids_2018.xlsx': IDS_BASE + '2026-09/IDS-data-2018-2022.xlsx',
    'ids_2023.xlsx': IDS_BASE + '2026-09/IDS-data-2023-2026.xlsx',
    **{k + '.xlsx': ANNEX_BASE + v for k, v in ANNEX_FILES.items()},
    'hist2015_coca_pdf.pdf': 'https://www.unodc.org/wdr2015/field/8.1._Coca_cultivation_production_and_eradication.pdf',
    'hist2015_opium_pdf.pdf': 'https://www.unodc.org/wdr2015/field/8.2._Opium_cultivation_production_eradication.pdf',
}
HISTORY_PAGES = {
    2012: 'https://www.unodc.org/unodc/en/data-and-analysis/WDR-2012.html',
    2015: 'https://www.unodc.org/wdr2015/en/maps-and-graphs.html',
    2020: 'https://wdr.unodc.org/wdr2020/en/maps-and-tables.html',
}
MASS_KG = {'kg': 1., 'kilogram': 1., 'kilograms': 1., 'gram': .001, 'g': .001, 'mg': .000001, 'ton': 1000., 'tons': 1000., 't': 1000.}
PRICE_PER = {'grams': 1., 'gram': 1., 'g': 1., 'kilograms': 1000., 'kilogram': 1000., 'kg': 1000.}


def number(v):
    if v is None or isinstance(v, (dt.date, dt.datetime, bool)):
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def year_of(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.year
    n = number(v)
    return int(n) if n is not None and n.is_integer() and 1850 <= n <= dt.date.today().year + 1 else None


def txt(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v) if v is not None else ''


def countries():
    # This fixture is the project's programmatically retrieved country metadata, not synthetic values.
    data = json.loads((ROOT / 'contracts/fixtures/countries.json').read_text())['data']
    idx = {norm(r['name']): r['iso3'] for r in data}
    idx.update({norm(r['iso3']): r['iso3'] for r in data})
    idx.update({norm(k): v for k, v in ALIASES.items()})
    # Preserve historical entities without silently assigning their observations to successors.
    idx.update({'serbia and montenegro': 'SCG', 'yugoslavia': 'YUG', 'netherlands antilles': 'ANT'})
    return idx


COUNTRIES = countries()


def resolve(name):
    s = re.sub(r'\(.*?estimate.*?\)[a-z]*', '', str(name), flags=re.I).strip()
    s = re.sub(r'(?:\s+[a-z](?:\s*,\s*[a-z])*|\*+)\s*$', '', s).strip()
    return COUNTRIES.get(norm(s))


def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = path.with_suffix('.json')
    if path.exists() and meta.exists():
        expected = json.loads(meta.read_text())['sha256']
        if hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() == expected:
            return
    for attempt in range(3):
        try:
            with requests.get(url, timeout=(30, 180), stream=True,
                              headers={'User-Agent': 'TRACE-CDC2026 academic data collector'}) as response:
                response.raise_for_status()
                tmp = path.with_suffix(path.suffix + '.part')
                digest = hashlib.sha256()
                with tmp.open('wb') as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        handle.write(chunk)
                        digest.update(chunk)
            magic = tmp.open('rb').read(4)
            expected = (magic == b'%PDF') if path.suffix.lower() == '.pdf' else (
                magic.startswith(b'PK') or magic.startswith(b'\xd0\xcf\x11\xe0'))
            if not expected:
                raise ValueError('Downloaded file has an unexpected format')
            tmp.replace(path)
            meta.write_text(json.dumps({'url': url, 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                                        'sha256': digest.hexdigest(), 'bytes': path.stat().st_size}))
            print(f'Downloaded {path.name}: {path.stat().st_size:,} bytes', flush=True)
            time.sleep(1)
            return
        except (requests.RequestException, ValueError) as error:
            if attempt == 2:
                raise RuntimeError(f'{url}: {error}') from error
            time.sleep(2 ** (attempt + 1))


def discover_history():
    found = {}
    for edition, url in HISTORY_PAGES.items():
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        for href in re.findall(r'href=[\"\']([^\"\']+)', response.text):
            if re.search(r'\.xlsx?$', href, re.I) and re.search(
                r'Seizures|illicit_cultivation|potential_production|Prices?_and_Purity|Prices_|Price_time_series', href, re.I
            ):
                link = urljoin(url, href)
                found[f'hist{edition}_' + link.rsplit('/', 1)[1]] = link
        time.sleep(1)
    return found


def schema(db):
    db.executescript('''
    PRAGMA journal_mode=OFF;
    PRAGMA synchronous=OFF;
    CREATE TABLE unodc_sources(source_id TEXT PRIMARY KEY,url TEXT NOT NULL,sha256 TEXT NOT NULL,retrieved_at TEXT NOT NULL,
       bytes INTEGER,edition INTEGER,citation TEXT,license_note TEXT);
    CREATE TABLE unodc_sheets(source_id TEXT,sheet TEXT,row_count INTEGER,col_count INTEGER,headers_json TEXT,
       PRIMARY KEY(source_id,sheet));
    CREATE TABLE unodc_cells(source_id TEXT,sheet TEXT,row_no INTEGER,col_no INTEGER,value_text TEXT,value_number REAL,
       value_type TEXT,italic INTEGER,PRIMARY KEY(source_id,sheet,row_no,col_no));
    CREATE TABLE unodc_pdf_pages(source_id TEXT,page_no INTEGER,text TEXT,PRIMARY KEY(source_id,page_no));
    CREATE TABLE seizures_raw(source_id TEXT,sheet TEXT,row_no INTEGER,year INTEGER,date TEXT,country TEXT,iso3 TEXT,
       subregion TEXT,region TEXT,drug_raw TEXT,qty REAL,quantity_text TEXT,unit TEXT,city TEXT,admin_region TEXT,
       location TEXT,mode TEXT,reporting_source TEXT,reporting_channel TEXT,drug TEXT,kg REAL,kg_trace_equivalent REAL,
       conversion TEXT,extra_json TEXT,PRIMARY KEY(source_id,sheet,row_no));
    CREATE TABLE seizures_ids(iso3 TEXT,year INTEGER,drug TEXT,kg REAL,kg_trace_equivalent REAL,cases INTEGER,
       unmapped_mass_rows INTEGER,source TEXT);
    CREATE TABLE unodc_seizure_observations(source_id TEXT,sheet TEXT,row_no INTEGER,iso3 TEXT,country TEXT,year INTEGER,
       drug_group TEXT,drug_raw TEXT,quantity REAL,unit TEXT,drug TEXT,kg_trace_equivalent REAL,notes TEXT);
    CREATE TABLE seizures_annex(iso3 TEXT,year INTEGER,drug TEXT,kg REAL,source TEXT,edition INTEGER);
    CREATE TABLE unodc_price_observations(source_id TEXT,sheet TEXT,row_no INTEGER,col_no INTEGER,iso3 TEXT,country TEXT,
       year INTEGER,drug TEXT,drug_raw TEXT,level TEXT,value REAL,minimum REAL,maximum REAL,unit TEXT,
       measure TEXT,basis TEXT,value_text TEXT,upstream_estimate INTEGER);
    CREATE TABLE prices(iso3 TEXT,drug TEXT,level TEXT,year INTEGER,usd_g REAL,purity_pct REAL,source TEXT,
       basis TEXT,upstream_estimate INTEGER);
    CREATE TABLE unodc_cultivation_observations(source_id TEXT,sheet TEXT,row_no INTEGER,col_no INTEGER,iso3 TEXT,
       country TEXT,crop TEXT,year INTEGER,metric TEXT,value REAL,value_text TEXT,estimate_type TEXT,unit TEXT);
    CREATE TABLE cultivation(iso3 TEXT,crop TEXT,year INTEGER,hectares REAL,production_t REAL,source TEXT);
    CREATE TABLE cannabis_regulation(iso3 TEXT,jurisdiction TEXT,year_effective INTEGER,scope TEXT,source TEXT,
       date_text TEXT,sheet TEXT,row_no INTEGER,col_no INTEGER);
    CREATE TABLE unodc_collection_issues(source_id TEXT,issue TEXT);
    ''')


def store_cells(db, source, wb, path):
    # Annexes are small; retain explicit blanks inside each worksheet's used rectangle.
    # Italic cells identify estimates supplied by UNODC in the price history workbook.
    styles = {}
    if path.suffix.lower() == '.xlsx':
        import openpyxl
        x = openpyxl.load_workbook(path, read_only=False, data_only=True)
        styles = {(s.title, c.row, c.column): int(bool(c.font.i)) for s in x for row in s for c in row if c.value is not None}
        x.close()
    for sheet in wb.sheet_names:
        rows = wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
        db.execute('INSERT INTO unodc_sheets VALUES(?,?,?,?,?)',
                   (source, sheet, len(rows), max(map(len, rows), default=0), None))
        def values():
            for i, row in enumerate(rows, 1):
                for j, v in enumerate(row, 1):
                    typ = 'blank' if v in ('', None) else 'date' if isinstance(v, dt.date) else 'number' if number(v) is not None else 'text'
                    yield source, sheet, i, j, txt(v), number(v), typ, styles.get((sheet, i, j), 0)
        db.executemany('INSERT INTO unodc_cells VALUES(?,?,?,?,?,?,?,?)', values())
    return styles


def ids(db, path):
    source = path.stem
    wb = CalamineWorkbook.from_path(str(path))
    for sheet in wb.sheet_names:
        rows = wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
        headers = [str(c).strip() for c in rows[0]] if rows else []
        db.execute('INSERT INTO unodc_sheets VALUES(?,?,?,?,?)', (source, sheet, len(rows), len(headers), json.dumps(headers)))
        if not re.fullmatch(r'\d{4}', sheet.strip()):
            db.executemany('INSERT INTO unodc_cells VALUES(?,?,?,?,?,?,?,?)',
                           ((source, sheet, i, j, txt(v), number(v), type(v).__name__, 0)
                            for i, row in enumerate(rows, 1) for j, v in enumerate(row, 1)))
            continue
        fields = {'Seizure Date':'date','Country/Territory of Seizure':'country','ISO3':'iso3','Subregion':'subregion',
                  'Region':'region','Drug/Substance':'drug_raw','Quantity Seized':'quantity_text','Measurement Unit':'unit',
                  'City':'city','Administrative Region':'admin_region','Physical Seizure Location':'location',
                  'Trafficking Mode of Transportation':'mode','Source':'reporting_source','Reporting Channel':'reporting_channel'}
        def values():
            for i, row in enumerate(rows[1:], 2):
                if not any(v not in ('', None) for v in row):
                    continue
                r = {fields.get(k,k): v for k,v in zip(headers,row)}
                drug, mult = map_drug('', r.get('drug_raw'))
                qty = number(r.get('quantity_text'))
                factor = MASS_KG.get(str(r.get('unit', '')).strip().lower())
                kg = qty * factor if qty is not None and factor is not None else None
                eq = kg * mult if drug and kg is not None else None
                conversion = 'mass unit only' if kg is not None else 'unit not convertible without an assumption'
                if drug == 'heroin' and mult != 1:
                    conversion += '; opium:heroin equivalent 10:1 project approximation'
                extra = {k: txt(v) for k,v in r.items() if k not in fields.values()}
                yield (source,sheet,i,int(sheet),*[txt(r.get(k)) for k in ['date','country','iso3','subregion','region','drug_raw']],
                       qty,txt(r.get('quantity_text')),*[txt(r.get(k)) for k in ['unit','city','admin_region','location','mode','reporting_source','reporting_channel']],
                       drug,kg,eq,conversion,json.dumps(extra,ensure_ascii=False) if extra else None)
        db.executemany('INSERT INTO seizures_raw VALUES('+','.join('?' for _ in range(24))+')', values())
        db.commit()
        print(f'IDS {sheet}: {len(rows)-1:,} source rows preserved', flush=True)
        del rows


def current_seizures(db, source, wb):
    rows = wb.get_sheet_by_name(wb.sheet_names[0]).to_python(skip_empty_area=False)
    header = next((i for i,r in enumerate(rows[:10]) if any(str(v).strip() == 'Iso3_code' for v in r)), None)
    if header is None:
        return False
    cols = [str(v).strip() for v in rows[header]]
    values=[]
    for i,row in enumerate(rows[header+1:], header+2):
        r=dict(zip(cols,row));year=year_of(r.get('Reference year'))
        if not year:continue
        drug,mult=map_drug(r.get('DrugGroup'),r.get('DrugName'))
        kg=number(r.get('Kilograms'))
        values.append((source,wb.sheet_names[0],i,txt(r.get('Iso3_code')),txt(r.get('Country')),year,txt(r.get('DrugGroup')),
                       txt(r.get('DrugName')),kg,'kg',drug,kg*mult if kg is not None and drug else None,
                       json.dumps({k:txt(v) for k,v in r.items() if k in ('Source','Footnote')},ensure_ascii=False)))
    db.executemany('INSERT INTO unodc_seizure_observations VALUES('+','.join('?'*13)+')',values)
    return True


def current_prices(db, source, wb):
    if 'Prices in USD' not in wb.sheet_names:return False
    for sheet,measure in [('Prices in USD','price'),('Purities','purity')]:
        rows=wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False);cols=[str(v).strip() for v in rows[1]]
        for i,row in enumerate(rows[2:],3):
            r=dict(zip(cols,row));year=year_of(r.get('Year'))
            if not year:continue
            drug,_=map_drug(r.get('DrugGroup'),r.get('Drug'))
            pre='_USD' if measure=='price' else ''
            typical,low,high=(number(r.get(n+pre)) for n in ['Typical','Minimum','Maximum'])
            unit=txt(r.get('Unit') if measure=='price' else r.get('Measurement'))
            db.execute('INSERT INTO unodc_price_observations VALUES('+','.join('?'*18)+')',
                       (source,sheet,i,0,resolve(r.get('Country/Territory')),txt(r.get('Country/Territory')),year,drug,
                        txt(r.get('Drug')),txt(r.get('LevelOfSale')).lower(),typical,low,high,unit,measure,'typical',txt(r.get('Typical'+pre)),0))
    return True


def price_series(db, source, wb, styles):
    for sheet in wb.sheet_names:
        drug='heroin' if 'heroin' in sheet.lower() else 'cocaine' if 'cocaine' in sheet.lower() else None
        if not drug:continue
        rows=wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
        years={};level=None;unit=None
        for i,row in enumerate(rows,1):
            text=' '.join(str(v) for v in row if isinstance(v,str)).lower()
            if ('retail' in text or 'street prices' in text) and 'price' in text:
                level='retail';unit='USD/kg' if 'kilogram' in text else 'USD/g'
            elif 'wholesale' in text and 'price' in text:
                level='wholesale';unit='USD/kg' if 'kilogram' in text else 'USD/g'
            yr={j:year_of(v) for j,v in enumerate(row) if year_of(v)}
            if len(yr)>=5:
                years=yr;continue
            label=str(row[0]).strip() if row else ''
            if not label or not years or not level or label.lower().startswith(('source','note','*')):continue
            iso=resolve(label)
            is_us=sheet.lower().endswith('_us')
            if is_us and label.lower().startswith('average'):iso='USA'
            if iso is None:continue
            basis='nominal'
            if 'inflation' in label.lower():basis='inflation-adjusted'
            if 'purity' in label.lower():basis += ';purity-adjusted'
            for j,year in years.items():
                v=row[j]
                db.execute('INSERT INTO unodc_price_observations VALUES('+','.join('?'*18)+')',
                           (source,sheet,i,j+1,iso,'United States' if is_us else label,year,drug,drug,level,number(v),None,None,
                            unit,'price',basis,txt(v),styles.get((sheet,i,j+1),0)))


def wide_cultivation(db, source, wb, crop, metric):
    for sheet in wb.sheet_names:
        rows=wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False);years={};prior=None
        for i,row in enumerate(rows,1):
            yc={j:year_of(v) for j,v in enumerate(row) if year_of(v)}
            if len(yc)>=5:years=yc;continue
            if not years:continue
            labels=[str(v).strip() for v in row[:min(years)] if isinstance(v,str) and v.strip()]
            if not labels:continue
            label=labels[-1] if len(labels)>1 and labels[0].isupper() else labels[0]
            if label.lower().startswith(('source','note','a ','b ','c ','d ','e ','f ')):continue
            estimate='central';iso=resolve(label)
            if label.lower().startswith('lower'):estimate='lower';iso=prior
            elif label.lower().startswith('upper'):estimate='upper';iso=prior
            elif iso:prior=iso
            elif label.lower().startswith(('total','other','sub')):estimate='aggregate';prior=None
            else:prior=None;continue
            for j,year in years.items():
                v=row[j]
                db.execute('INSERT INTO unodc_cultivation_observations VALUES('+','.join('?'*13)+')',
                           (source,sheet,i,j+1,iso,label,crop,year,metric,number(v),txt(v),estimate,'hectares' if metric=='hectares' else 'metric tons'))


def pdf_cultivation(db, source, path):
    """Read two named WDR 2015 tables; retain their cells and full page notes.

    These pages also contain eradication and coca-leaf tables. They remain in the
    source-cell archive but are not mislabeled as cultivated area or opium output.
    """
    import pdfplumber
    specs = {
        'hist2015_coca_pdf': [(0, 0, 'coca', 'hectares', 2002, 2013)],
        'hist2015_opium_pdf': [(0, 0, 'opium_poppy', 'hectares', 1999, 2014),
                               (1, 0, 'opium_poppy', 'production_t', 1999, 2014)],
    }
    names = {
        'Afghanistan': 'AFG', 'Pakistan': 'PAK', "Lao People's": 'LAO',
        'Myanmar': 'MMR', 'Thailand': 'THA', 'Viet Nam': 'VNM',
        'Colombia': 'COL', 'Mexico': 'MEX', 'Bolivia': 'BOL', 'Peru': 'PER',
    }
    with pdfplumber.open(path) as pdf:
        tables = []
        for page_no, page in enumerate(pdf.pages, 1):
            db.execute('INSERT INTO unodc_pdf_pages VALUES(?,?,?)', (source, page_no, page.extract_text() or ''))
            for table_no, rows in enumerate(page.extract_tables(), 1):
                sheet = f'page_{page_no}_table_{table_no}'
                db.execute('INSERT INTO unodc_sheets VALUES(?,?,?,?,?)',
                           (source, sheet, len(rows), max(map(len, rows), default=0), json.dumps(rows[0])))
                db.executemany('INSERT INTO unodc_cells VALUES(?,?,?,?,?,?,?,?)',
                    ((source, sheet, i, j, txt(v), number(v),
                      'blank' if v in ('', None) else 'number' if number(v) is not None else 'text', 0)
                     for i, row in enumerate(rows, 1) for j, v in enumerate(row, 1)))
                tables.append((page_no - 1, table_no - 1, sheet, rows))
        for page_idx, table_idx, crop, metric, first, last in specs[source]:
            sheet, rows = next((s, r) for p, t, s, r in tables if p == page_idx and t == table_idx)
            title = txt(rows[0][0]).lower()
            assert ('cultivation' if metric == 'hectares' else 'oven-dry opium') in title, (source, title)
            for row_no, row in enumerate(rows[2:], 3):
                label = txt(row[0]).replace('\n', ' ').strip()
                iso = next((v for k, v in names.items() if label.startswith(k)), None)
                if iso is None:
                    continue
                # The opium production PDF merges 2013 and 2014 in its final
                # cell for some rows; split only when both numbers are visible.
                cells = list(row[1:])
                if metric == 'production_t':
                    tail = txt(cells[-1]).split()
                    cells[-1:] = tail if len(tail) == 2 else [cells[-1], '']
                assert len(cells) == last - first + 1, (source, label, cells)
                for j, raw in enumerate(cells, 1):
                    year = first + j - 1
                    # Peru has two measurement concepts in the coca PDF. Use
                    # the 31 December net-area concept from 2011 onward and
                    # keep the satellite-area 2011 figure as an alternative.
                    estimate = 'central'
                    if crop == 'coca' and iso == 'PER':
                        net = label.endswith(' b')
                        if (net and year < 2011) or (not net and year >= 2011):
                            estimate = 'alternate_concept'
                    value = number(txt(raw).replace(',', '').strip())
                    db.execute('INSERT INTO unodc_cultivation_observations VALUES('+','.join('?'*13)+')',
                               (source, sheet, row_no, j+1, iso, label, crop, year, metric,
                                value, txt(raw), estimate,
                                'hectares' if metric == 'hectares' else 'metric tons'))


def regulation(db,source,wb):
    for sheet in wb.sheet_names:
        country=re.sub(r'\s+\d+$','',sheet).strip();iso=resolve(country)
        rows=wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
        for i,row in enumerate(rows,1):
            if not any(str(v).lower().startswith('date implemented') for v in row):continue
            for j,v in enumerate(row):
                text=txt(v)
                if not text or text.lower().startswith('date implemented'):continue
                y=year_of(v)
                if y is None:
                    found=re.findall(r'\b(?:19|20)\d{2}\b',text);y=min(map(int,found)) if found else None
                if y is None:continue
                # Country sheets carry jurisdiction headers in row 2 or row 3 (US).
                jurisdiction=txt(rows[2 if country=='United States' else 1][j])
                db.execute('INSERT INTO cannabis_regulation VALUES(?,?,?,?,?,?,?,?,?)',
                           (iso,jurisdiction,y,'subnational' if country=='United States' or jurisdiction not in ('Federal law','') else 'national',source,text,sheet,i,j+1))


def final_tables(db):
    db.executescript('''
    INSERT INTO seizures_ids
      SELECT iso3,year,drug,SUM(kg),SUM(kg_trace_equivalent),COUNT(*),SUM(kg IS NULL),'unodc_ids'
      FROM seizures_raw WHERE drug IS NOT NULL GROUP BY iso3,year,drug;
    CREATE INDEX seizures_raw_country_year ON seizures_raw(iso3,year);
    CREATE INDEX unodc_seizure_key ON unodc_seizure_observations(source_id,iso3,year,drug_raw);
    CREATE INDEX unodc_price_key ON unodc_price_observations(iso3,year,drug,level);
    CREATE INDEX unodc_cultivation_key ON unodc_cultivation_observations(iso3,year,crop);
    ''')
    # Annex entries remain split by source edition. Prefer total cocaine rows over components within each edition.
    db.executescript('''
    INSERT INTO seizures_annex
    SELECT a.iso3,a.year,a.drug,SUM(a.kg_trace_equivalent),a.source_id,s.edition
    FROM unodc_seizure_observations a JOIN unodc_sources s ON s.source_id=a.source_id
    WHERE a.drug IS NOT NULL AND a.kg_trace_equivalent IS NOT NULL
      AND NOT(a.drug='cocaine' AND a.drug_raw NOT LIKE 'Cocaine (total%' AND EXISTS(
        SELECT 1 FROM unodc_seizure_observations t WHERE t.source_id=a.source_id AND t.iso3=a.iso3
        AND t.year=a.year AND t.drug_raw LIKE 'Cocaine (total%'))
    GROUP BY a.source_id,a.iso3,a.year,a.drug;
    ''')
    # Model-friendly prices use nominal observations only. Source rows and ranges remain accessible.
    raw=db.execute('''SELECT iso3,drug,level,year,value,minimum,maximum,unit,source_id,basis,upstream_estimate
      FROM unodc_price_observations WHERE measure='price' AND basis IN ('typical','nominal')
      AND iso3 IS NOT NULL AND drug IS NOT NULL AND lower(drug_raw) NOT LIKE 'opium%' ''').fetchall()
    candidates={}
    editions=dict(db.execute("SELECT source_id,edition FROM unodc_sources"))
    for iso,drug,level,year,value,low,high,unit,source,basis,estimate in raw:
        factor=PRICE_PER.get(unit.lower())
        if unit=='USD/kg':factor=1000.
        elif unit=='USD/g':factor=1.
        if factor is None or level not in ('retail','wholesale'):continue
        if value is None and low is not None and high is not None:
            value=(low+high)/2;basis='range-midpoint'
        if value is None or value<=0:continue
        key=(iso,drug,level,year)
        priority=(editions[source],int('price_ts' not in source and 'Price_time_series' not in source and 'Prices_Cocaine_heroin' not in source))
        entry=(value/factor,source,basis,estimate)
        if key not in candidates or priority>candidates[key][0]:candidates[key]=(priority,[entry])
        elif priority==candidates[key][0]:candidates[key][1].append(entry)
    import statistics
    for (iso,drug,level,year),(_,entries) in candidates.items():
        db.execute('INSERT INTO prices VALUES(?,?,?,?,?,?,?,?,?)',
                   (iso,drug,level,year,statistics.median(e[0] for e in entries),None,
                    ';'.join(sorted({e[1] for e in entries})),';'.join(sorted({e[2] for e in entries})),max(e[3] for e in entries)))
    # Latest edition wins a crop/year/metric. Missing cells do not erase earlier published observations.
    entries=db.execute('''SELECT o.iso3,o.crop,o.year,o.metric,o.value,o.source_id FROM unodc_cultivation_observations o
      JOIN unodc_sources s ON s.source_id=o.source_id WHERE o.estimate_type='central' AND o.iso3 IS NOT NULL
      AND o.value IS NOT NULL ORDER BY s.edition,o.row_no''').fetchall()
    chosen={}
    for iso,crop,year,metric,value,source in entries:
        chosen.setdefault((iso,crop,year),{})[metric]=(value,source)
    for (iso,crop,year),v in chosen.items():
        sources=sorted({x[1] for x in v.values()})
        db.execute('INSERT INTO cultivation VALUES(?,?,?,?,?,?)',(iso,crop,year,v.get('hectares',(None,))[0],v.get('production_t',(None,))[0],';'.join(sources)))


def build(output, skip_ids=False):
    tmp=output.with_suffix('.building.sqlite');tmp.unlink(missing_ok=True)
    db=sqlite3.connect(tmp);schema(db)
    paths=(sorted(CACHE.glob('*.xls'))+sorted(CACHE.glob('*.xlsx'))+
           [CACHE / name for name in ('hist2015_coca_pdf.pdf', 'hist2015_opium_pdf.pdf')])
    for path in paths:
        if path.stem.startswith('ids') and skip_ids:continue
        meta=json.loads(path.with_suffix('.json').read_text());source=path.stem
        with path.open('rb') as handle:
            actual=hashlib.file_digest(handle,'sha256').hexdigest()
        if actual != meta['sha256']:
            raise ValueError(f'Cached source checksum mismatch: {path.name}')
        edition=int(source[4:8]) if source.startswith('hist') else 2026
        note=('DMP public data may be copied and redistributed with UNODC DMP attribution; https://dmp.unodc.org/downloadIDS'
              if source.startswith('ids') else 'UNODC World Drug Report statistical annex; source citation required; workbook source notes preserved')
        db.execute('INSERT INTO unodc_sources VALUES(?,?,?,?,?,?,?,?)',
                   (source,meta['url'],meta['sha256'],meta['retrieved_at'],meta['bytes'],edition,'UNODC, World Drug Report / Drugs Monitoring Platform',note))
        if source.startswith('ids'):
            ids(db,path);continue
        if path.suffix.lower() == '.pdf':
            print('Parse',path.name,flush=True)
            pdf_cultivation(db,source,path);db.commit();continue
        print('Parse',path.name,flush=True)
        wb=CalamineWorkbook.from_path(str(path));styles=store_cells(db,source,wb,path)
        if 'seizure' in source.lower():
            if not current_seizures(db,source,wb): historical_seizures(db,source,wb)
        elif source=='prices':current_prices(db,source,wb)
        elif source=='price_ts' or 'Price_time_series' in source or 'Prices_Cocaine_heroin' in source:price_series(db,source,wb,styles)
        elif source=='coca' or 'cultivation_of_coca' in source:wide_cultivation(db,source,wb,'coca','hectares')
        elif source=='opium' or 'cultivation_of_opium_poppy' in source:wide_cultivation(db,source,wb,'opium_poppy','hectares')
        elif source=='opium_prod' or 'production_of_oven-dry_opium' in source:wide_cultivation(db,source,wb,'opium_poppy','production_t')
        elif source=='cannabis_reg':regulation(db,source,wb)
        elif 'Price' in source or 'price' in source:
            historical_prices(db,source,wb)
        db.commit()
    final_tables(db);db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    summary={t:db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    print(json.dumps(summary,indent=2),flush=True)
    db.close();tmp.replace(output)


def historical_seizures(db,source,wb):
    for sheet in wb.sheet_names:
        rows=wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
        if not rows:continue
        header=next((i for i,r in enumerate(rows[:10]) if 'Year' in r and ('Quantity' in r or 'Amount' in r)),None)
        if header is None:
            db.execute('INSERT INTO unodc_collection_issues VALUES(?,?)',(source,'Unrecognized seizure sheet '+sheet+' retained as source cells.'))
            continue
        cols=[str(v).strip() for v in rows[header]]
        for i,row in enumerate(rows[header+1:],header+2):
            r=dict(zip(cols,row));year=year_of(r.get('Year'))
            if not year:continue
            country=r.get('Country') or r.get('Country or Territory')
            drug,mult=map_drug(r.get('DrugGroup'),r.get('Drug'))
            unit=txt(r.get('Unit'));quantity=number(r.get('Quantity',r.get('Amount')))
            factor=MASS_KG.get(unit.strip().lower())
            eq=quantity*factor*mult if quantity is not None and factor is not None and drug else None
            db.execute('INSERT INTO unodc_seizure_observations VALUES('+','.join('?'*13)+')',
                       (source,sheet,i,txt(r.get('Code')) or resolve(country),txt(country),year,txt(r.get('DrugGroup')),
                        txt(r.get('Drug')),quantity,unit,drug,eq,
                        json.dumps({k:txt(v) for k,v in r.items() if k in ('Specifics','Comment','SourceType','Territories')},ensure_ascii=False)))


def historical_prices(db,source,wb):
    for sheet in wb.sheet_names:
        rows=wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
        if not rows:continue
        # Some workbooks include a duplicate raw data sheet plus presentation sheets.
        if any('PriceStreetTypical' in r for r in rows[:1]):continue
        header=next((i for i,r in enumerate(rows[:12]) if r.count('Typical')>=2 and 'Year' in r),None)
        if header is None:
            db.execute('INSERT INTO unodc_collection_issues VALUES(?,?)',(source,'Unrecognized historical price sheet '+sheet+' retained as source cells.'))
            continue
        h=rows[header];starts=[j for j,v in enumerate(h) if v=='Typical'];country=None;drugraw=None
        for i,row in enumerate(rows[header+1:],header+2):
            if len(row)<4:continue
            if row[2]:country=txt(row[2])
            if row[3]:drugraw=txt(row[3])
            if not country or not drugraw:continue
            drug,_=map_drug('Cannabis-type' if 'cannabis' in source.lower() else '',drugraw)
            for n,start in enumerate(starts):
                end=starts[n+1] if n+1<len(starts) else len(h)
                yearcol=next((j for j in range(start,end) if h[j]=='Year'),None)
                if yearcol is None:continue
                year=year_of(row[yearcol])
                if year is None:continue
                unitcol=next((j for j in range(start,end) if 'unit' in str(h[j]).lower() or 'measurement' in str(h[j]).lower()),None)
                measure='price' if n%2==0 else 'purity'
                unit=txt(row[unitcol]) if unitcol is not None else '%'
                low=number(row[start+1]);high=number(row[start+3])
                db.execute('INSERT INTO unodc_price_observations VALUES('+','.join('?'*18)+')',
                           (source,sheet,i,start+1,resolve(country),country,year,drug,drugraw,
                            'retail' if n<2 else 'wholesale',number(row[start]),low,high,unit,measure,'typical',txt(row[start]),0))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'data_collection/work/unodc.sqlite')
    parser.add_argument('--cached-only',action='store_true',help='Use previously downloaded verified workbooks without network requests.')
    parser.add_argument('--skip-ids',action='store_true',help='Build annex-only shard for development (not full collection).')
    args=parser.parse_args();CACHE.mkdir(parents=True,exist_ok=True);args.db.parent.mkdir(parents=True,exist_ok=True)
    if not args.cached_only:
        sources=dict(DOWNLOADS);sources.update(discover_history())
        for name,url in sources.items():
            if args.skip_ids and name.startswith('ids'):continue
            fetch(url,CACHE/name)
    build(args.db,args.skip_ids)


if __name__=='__main__':main()
