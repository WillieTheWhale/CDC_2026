# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Collect the complete native history of TRACE's World Bank registry into SQLite.

No date, mrv, gapfill or imputation is used. Run from the repository root:
    python3 data_collection/world_bank.py
Each successful response is cached with a SHA-256 and its original retrieval time.
The database also embeds gzip-compressed original API responses for auditability.
"""
from __future__ import annotations

import argparse
import email.utils
import gzip
import hashlib
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from trace_backend.wb.indicators import INDICATORS  # noqa: E402

BASE = 'https://api.worldbank.org/v2/'
TERMS = 'https://data.worldbank.org/summary-terms-of-use'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS wb_downloads (
 request_id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, retrieved_at TEXT NOT NULL,
 sha256 TEXT NOT NULL, content_type TEXT, last_modified TEXT,
 payload_gzip BLOB NOT NULL, byte_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS wb_entities (
 iso3 TEXT PRIMARY KEY, iso2 TEXT, name TEXT, region TEXT, region_id TEXT,
 income_group TEXT, capital TEXT, lat REAL, lon REAL, is_aggregate INTEGER NOT NULL,
 request_id TEXT NOT NULL REFERENCES wb_downloads(request_id));
CREATE TABLE IF NOT EXISTS countries (
 iso3 TEXT PRIMARY KEY, iso2 TEXT, name TEXT, region TEXT, region_id TEXT,
 income_group TEXT, capital TEXT, lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS wb_source_periods (
 source_id INTEGER NOT NULL, period TEXT NOT NULL, period_id TEXT NOT NULL,
 request_id TEXT NOT NULL REFERENCES wb_downloads(request_id),
 PRIMARY KEY(source_id,period_id));
CREATE TABLE IF NOT EXISTS wb_source_meta (
 source_id INTEGER PRIMARY KEY, name TEXT, description TEXT, url TEXT,
 metadata_json TEXT NOT NULL, request_id TEXT NOT NULL REFERENCES wb_downloads(request_id));
CREATE TABLE IF NOT EXISTS wb_indicator_meta (
 code TEXT NOT NULL, source_id INTEGER NOT NULL, feature TEXT NOT NULL, role TEXT NOT NULL,
 label TEXT, name TEXT, unit TEXT, api_unit TEXT, source_name TEXT, source_org TEXT,
 source_note TEXT, public INTEGER NOT NULL, forward_fill INTEGER NOT NULL,
 license_type TEXT, license_url TEXT, terms_url TEXT NOT NULL, metadata_json TEXT NOT NULL,
 PRIMARY KEY(code,source_id));
CREATE TABLE IF NOT EXISTS wb_indicators (
 iso3 TEXT NOT NULL REFERENCES countries(iso3), year INTEGER, period TEXT NOT NULL,
 code TEXT NOT NULL, source_id INTEGER NOT NULL, value REAL, unit TEXT,
 obs_status TEXT, decimal_places INTEGER, footnote TEXT, lastupdated TEXT,
 retrieved_at TEXT NOT NULL, request_id TEXT NOT NULL REFERENCES wb_downloads(request_id),
 PRIMARY KEY(iso3,period,code,source_id),
 FOREIGN KEY(code,source_id) REFERENCES wb_indicator_meta(code,source_id));
CREATE TABLE IF NOT EXISTS wb_excluded_observations (
 source_id INTEGER NOT NULL, code TEXT NOT NULL, country_iso3 TEXT, country_code TEXT,
 country_name TEXT NOT NULL, entity_type TEXT NOT NULL, period TEXT NOT NULL, year INTEGER,
 value REAL, unit TEXT, obs_status TEXT, decimal_places INTEGER, footnote TEXT,
 lastupdated TEXT, retrieved_at TEXT NOT NULL,
 request_id TEXT NOT NULL REFERENCES wb_downloads(request_id),
 PRIMARY KEY(source_id,code,country_name,period),
 FOREIGN KEY(code,source_id) REFERENCES wb_indicator_meta(code,source_id));
CREATE INDEX IF NOT EXISTS wb_indicators_code_year ON wb_indicators(code,year);
CREATE INDEX IF NOT EXISTS wb_indicators_iso3_year ON wb_indicators(iso3,year);
CREATE TABLE IF NOT EXISTS wb_coverage (
 code TEXT NOT NULL, source_id INTEGER NOT NULL, first_period INTEGER, last_period INTEGER,
 first_non_null_year INTEGER, last_non_null_year INTEGER, rows INTEGER NOT NULL,
 non_null_rows INTEGER NOT NULL, countries_with_data INTEGER NOT NULL,
 api_total_records INTEGER NOT NULL, api_pages INTEGER NOT NULL,
 excluded_aggregate_rows INTEGER NOT NULL, unknown_entity_rows INTEGER NOT NULL,
 PRIMARY KEY(code,source_id));
CREATE TABLE IF NOT EXISTS wb_coverage_year (
 code TEXT NOT NULL, source_id INTEGER NOT NULL, year INTEGER NOT NULL,
 rows INTEGER NOT NULL, non_null_rows INTEGER NOT NULL, countries_with_data INTEGER NOT NULL,
 PRIMARY KEY(code,source_id,year));
CREATE TABLE IF NOT EXISTS wb_collection_issues (
 context TEXT PRIMARY KEY, message TEXT NOT NULL, observed_at TEXT NOT NULL);
'''


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def retry_seconds(value: str | None, attempt: int) -> float:
    """Honor either Retry-After seconds or HTTP dates, without uncontrolled retries."""
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, (email.utils.parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                pass
    return min(2 ** attempt * 2, 60)


def validate_json(raw: bytes):
    body = json.loads(raw)
    first = body[0] if isinstance(body, list) and body else body
    if isinstance(first, dict) and 'message' in first:
        raise ValueError(f'World Bank API error body: {first["message"]}')
    return body


class Client:
    def __init__(self, db: sqlite3.Connection, cache: Path, interval: float = 1.0,
                 retries: int = 5, opener: Callable = urllib.request.urlopen,
                 sleeper: Callable = time.sleep, monotonic: Callable = time.monotonic,
                 refresh: bool = False):
        self.db, self.cache = db, cache
        self.interval, self.retries = interval, retries
        self.opener, self.sleep, self.clock = opener, sleeper, monotonic
        self.refresh, self.last_request = refresh, None
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, path: str, params: dict):
        url = BASE + path.lstrip('/') + '?' + urllib.parse.urlencode({'format': 'json', **params})
        request_id = hashlib.sha256(url.encode()).hexdigest()
        data_path, meta_path = self.cache / (request_id + '.json.gz'), self.cache / (request_id + '.meta.json')
        if not self.refresh and data_path.exists() and meta_path.exists():
            raw, meta = gzip.decompress(data_path.read_bytes()), json.loads(meta_path.read_text())
            if hashlib.sha256(raw).hexdigest() != meta['sha256'] or meta['url'] != url:
                raise ValueError(f'Cache integrity mismatch: {data_path}')
            body = validate_json(raw)
        else:
            for attempt in range(self.retries):
                if self.last_request is not None:
                    self.sleep(max(0, self.interval - (self.clock() - self.last_request)))
                self.last_request = self.clock()
                try:
                    request = urllib.request.Request(url, headers={'User-Agent': 'TRACE-academic-data-collector/1.0', 'Accept': 'application/json'})
                    with self.opener(request, timeout=90) as response:
                        content_type = response.headers.get('Content-Type', '')
                        if 'json' not in content_type.lower():
                            raise ValueError(f'Non-JSON Content-Type: {content_type}')
                        raw = response.read()
                        body = validate_json(raw)
                        meta = {'url': url, 'retrieved_at': now(), 'sha256': hashlib.sha256(raw).hexdigest(),
                                'content_type': content_type, 'last_modified': response.headers.get('Last-Modified')}
                    data_path.write_bytes(gzip.compress(raw, mtime=0))
                    meta_path.write_text(json.dumps(meta, indent=2) + '\n')
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code not in (408, 429, 500, 502, 503, 504) or attempt + 1 >= self.retries:
                        raise
                    delay = retry_seconds(exc.headers.get('Retry-After'), attempt)
                    print(f'Retry HTTP {exc.code} in {delay:.1f}s: {url}', flush=True)
                    self.sleep(delay)
                except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
                    if attempt + 1 >= self.retries:
                        raise
                    delay = retry_seconds(None, attempt)
                    print(f'Retry {exc} in {delay:.1f}s: {url}', flush=True)
                    self.sleep(delay)
        self.db.execute('INSERT OR REPLACE INTO wb_downloads VALUES (?,?,?,?,?,?,?,?)',
                        (request_id, url, meta['retrieved_at'], meta['sha256'], meta['content_type'],
                         meta.get('last_modified'), gzip.compress(raw, mtime=0), len(raw)))
        return body, request_id, meta

    def pages(self, path: str, params: dict | None = None):
        """Yield every page; reject changing pagination and source snapshots."""
        params = params or {}
        page, pages, total, lastupdated, sourceid = 1, 1, None, None, None
        while page <= pages:
            body, request_id, meta = self.get(path, {'per_page': 10000, **params, 'page': page})
            header = body[0] if isinstance(body, list) else body
            if not isinstance(header, dict) or 'pages' not in header:
                raise ValueError(f'Missing pagination: {path}')
            this_total, this_pages = int(header['total']), int(header['pages'])
            if int(header['page']) != page:
                raise ValueError(f'Wrong page returned: {path}')
            if page == 1:
                total, pages, lastupdated, sourceid = this_total, max(1, this_pages), header.get('lastupdated'), header.get('sourceid')
            elif (total, pages, lastupdated, sourceid) != (this_total, max(1, this_pages), header.get('lastupdated'), header.get('sourceid')):
                raise ValueError(f'Source changed during pagination; refresh the collection: {path}')
            yield body, request_id, meta
            page += 1


def advanced_items(body: dict, field: str):
    for source in body.get('source', []):
        for concept in source.get('concept', []):
            for variable in concept.get('variable', []):
                if field == 'variable':
                    yield variable
                else:
                    yield from variable.get(field, [])


def load_countries(client: Client):
    count, expected = 0, None
    for body, request_id, _ in client.pages('country'):
        expected = int(body[0]['total'])
        for item in body[1] or []:
            count += 1
            agg = int(item['region']['value'].strip() == 'Aggregates')
            values = (item['id'], item['iso2Code'], item['name'], item['region']['value'], item['region']['id'],
                      item['incomeLevel']['value'], item['capitalCity'] or None,
                      float(item['latitude']) if item['latitude'] else None,
                      float(item['longitude']) if item['longitude'] else None)
            client.db.execute('INSERT OR REPLACE INTO wb_entities VALUES (?,?,?,?,?,?,?,?,?,?,?)', (*values, agg, request_id))
            if not agg:
                client.db.execute('INSERT OR REPLACE INTO countries VALUES (?,?,?,?,?,?,?,?,?)', values)
    if count != expected:
        raise ValueError(f'Incomplete country pages: {count} != {expected}')
    client.db.commit()


def load_sources(client: Client):
    for source_id in sorted({ind.source_id for ind in INDICATORS}):
        for body, request_id, _ in client.pages(f'sources/{source_id}'):
            for item in body[1] or []:
                client.db.execute('INSERT OR REPLACE INTO wb_source_meta VALUES (?,?,?,?,?,?)',
                                  (source_id, item.get('name'), item.get('description'), item.get('url'), json.dumps(item), request_id))
        count, expected = 0, None
        for body, request_id, _ in client.pages(f'sources/{source_id}/time/data'):
            expected = int(body['total'])
            for variable in advanced_items(body, 'variable'):
                count += 1
                client.db.execute('INSERT OR REPLACE INTO wb_source_periods VALUES (?,?,?,?)',
                                  (source_id, variable['value'], variable['id'], request_id))
        if count != expected:
            raise ValueError(f'Incomplete source period pages: {count} != {expected}')
        client.db.commit()


def indicator_metadata(client: Client, ind):
    basic, advanced = [], []
    for body, _, _ in client.pages(f'indicator/{ind.code}', {'source': ind.source_id}):
        basic.extend(body[1] or [])
    for body, _, _ in client.pages(f'sources/{ind.source_id}/series/{ind.code}/metadata'):
        advanced.extend(advanced_items(body, 'metatype'))
    if len(basic) != 1 or str(basic[0]['source']['id']) != str(ind.source_id):
        raise ValueError(f'Unexpected metadata source: {ind.code}')
    md, extras = basic[0], {x['id']: x['value'] for x in advanced}
    client.db.execute('INSERT OR REPLACE INTO wb_indicator_meta VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ind.code, ind.source_id, ind.feature, ind.role, ind.label, md.get('name'), ind.unit,
                       md.get('unit'), md.get('source', {}).get('value'), md.get('sourceOrganization'),
                       md.get('sourceNote'), int(ind.public), int(ind.forward_fill), extras.get('License_Type'),
                       extras.get('License_URL'), TERMS, json.dumps({'basic': md, 'advanced': advanced})))


def ingest_observation_page(db, ind, body, request_id, meta, known, aggregates):
    retained, dropped, unknown = 0, 0, 0
    for row in body[1] or []:
        if row['indicator']['id'] != ind.code:
            raise ValueError('Unexpected indicator in observation response')
        iso3 = row.get('countryiso3code') or ''
        period = str(row['date'])
        year = int(period) if len(period) == 4 and period.isdigit() else None
        if iso3 not in known:
            country = row.get('country', {})
            aggregate = iso3 in aggregates or bool(country.get('id') and country['id'] in aggregates)
            dropped += int(aggregate)
            unknown += int(not aggregate)
            db.execute('INSERT INTO wb_excluded_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (ind.source_id, ind.code, iso3, country.get('id'), country.get('value') or iso3,
                        'aggregate' if aggregate else 'unmapped_source_entity', period, year,
                        row.get('value'), row.get('unit'), row.get('obs_status'), row.get('decimal'),
                        row.get('footnote'), body[0].get('lastupdated'), meta['retrieved_at'], request_id))
            continue
        db.execute('INSERT INTO wb_indicators VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (iso3, year, period, ind.code, ind.source_id, row.get('value'), row.get('unit'),
                    row.get('obs_status'), row.get('decimal'), row.get('footnote'), body[0].get('lastupdated'),
                    meta['retrieved_at'], request_id))
        retained += 1
    return retained, dropped, unknown


def collect_indicator(client: Client, ind):
    indicator_metadata(client, ind)
    known = {r[0] for r in client.db.execute('SELECT iso3 FROM countries')}
    aggregates = {code for row in client.db.execute('SELECT iso3,iso2 FROM wb_entities WHERE is_aggregate=1') for code in row if code}
    # One transaction per indicator means an interrupted run never publishes a partial series.
    client.db.execute('DELETE FROM wb_indicators WHERE code=? AND source_id=?', (ind.code, ind.source_id))
    client.db.execute('DELETE FROM wb_excluded_observations WHERE code=? AND source_id=?', (ind.code, ind.source_id))
    count = dropped = unknown = pages = 0
    for body, request_id, meta in client.pages(f'country/all/indicator/{ind.code}', {'source': ind.source_id, 'footnote': 'y', 'ctrycode': 'y'}):
        if str(body[0].get('sourceid')) != str(ind.source_id):
            raise ValueError(f'Unexpected observations source: {ind.code}')
        pages += 1
        count += len(body[1] or [])
        _, a, u = ingest_observation_page(client.db, ind, body, request_id, meta, known, aggregates)
        dropped, unknown = dropped + a, unknown + u
        expected = int(body[0]['total'])
    if count != expected:
        raise ValueError(f'Incomplete indicator pages: {ind.code}: {count} != {expected}')
    stats = client.db.execute('''SELECT MIN(year), MAX(year), MIN(CASE WHEN value IS NOT NULL THEN year END),
        MAX(CASE WHEN value IS NOT NULL THEN year END), COUNT(*), COUNT(value),
        COUNT(DISTINCT CASE WHEN value IS NOT NULL THEN iso3 END)
        FROM wb_indicators WHERE code=? AND source_id=?''', (ind.code, ind.source_id)).fetchone()
    if stats[5] == 0:
        raise ValueError(f'Indicator has no values: {ind.code}')
    client.db.execute('INSERT OR REPLACE INTO wb_coverage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ind.code, ind.source_id, *stats, count, pages, dropped, unknown))
    client.db.execute('DELETE FROM wb_coverage_year WHERE code=? AND source_id=?', (ind.code, ind.source_id))
    client.db.execute('''INSERT INTO wb_coverage_year SELECT code,source_id,year,COUNT(*),COUNT(value),
        COUNT(DISTINCT CASE WHEN value IS NOT NULL THEN iso3 END) FROM wb_indicators
        WHERE code=? AND source_id=? AND year IS NOT NULL GROUP BY code,source_id,year''', (ind.code, ind.source_id))
    # No date filter ensures no native periods are cut out. Verify response years against source time dimension.
    native = {r[0] for r in client.db.execute('SELECT period FROM wb_source_periods WHERE source_id=?', (ind.source_id,))}
    returned = {r[0] for r in client.db.execute('SELECT DISTINCT period FROM wb_indicators WHERE code=? AND source_id=?', (ind.code, ind.source_id))}
    if native - returned:
        raise ValueError(f'Missing native source periods for {ind.code}: {sorted(native-returned)}')
    client.db.execute('DELETE FROM wb_collection_issues WHERE context=?', (ind.code,))
    client.db.commit()
    print(f'{ind.code}: {stats[4]:,} rows; {stats[5]:,} non-null; {stats[2]}–{stats[3]}; {stats[6]} economies; {pages} pages', flush=True)


def report(db: sqlite3.Connection, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = db.execute('''SELECT m.code,m.source_id,m.feature,c.first_non_null_year,c.last_non_null_year,
        c.non_null_rows,c.countries_with_data,c.rows,c.unknown_entity_rows FROM wb_indicator_meta m
        JOIN wb_coverage c USING(code,source_id) ORDER BY m.role,m.code''').fetchall()
    bounds = db.execute('SELECT MIN(first_non_null_year),MAX(last_non_null_year),MAX(first_non_null_year),MIN(last_non_null_year),SUM(rows),SUM(non_null_rows) FROM wb_coverage').fetchone()
    complete_years = db.execute('''SELECT year,COUNT(*) FROM wb_coverage_year WHERE non_null_rows>0
        GROUP BY year HAVING COUNT(*)=? ORDER BY year''', (len(INDICATORS),)).fetchall()
    balanced = db.execute('''SELECT COUNT(*) FROM (SELECT iso3,year FROM wb_indicators WHERE value IS NOT NULL
        GROUP BY iso3,year HAVING COUNT(*)=?)''', (len(INDICATORS),)).fetchone()[0]
    lines = ['<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->',
             '# World Bank complete-history collection', '', f'Generated {now()}. Programmatic API v2 retrieval, explicit WDI source 2 and WGI source 3.', '',
             f'{len(rows)}/{len(INDICATORS)} registry indicators; {bounds[4] or 0:,} country observations including nulls; {bounds[5] or 0:,} non-null values.',
             f'Observed history extends **{bounds[0]}–{bounds[1]}**. The intersection of variable first/last observed bounds is **{bounds[2]}–{bounds[3]}**; this is an envelope, not an annually complete panel.',
             f'Years in which all 24 indicators have at least one non-null country observation: **{", ".join(str(r[0]) for r in complete_years) or "none"}**.',
             f'Country-year combinations with all 24 variables observed concurrently: **{balanced}**.', '',
             'Retain the entire history in the database. For analysis, choose a task-specific cohort and record each value’s observation year. Sparse surveys do not justify cutting older observations or backward-filling future observations. This collector performs no filling, imputation or model-panel selection.', '',
             'The source time dimensions and every no-date observation page were fetched and checked. No fixed starting year, `date`, `mrv`, `mrnev` or `gapfill` is used. Current country classifications are not historical borders. Aggregate and otherwise unmatched source observations remain directly queryable in `wb_excluded_observations` and preserved in compressed original responses, outside the country-observation table. Unmapped source entities with blank source country codes retain their source names; no ISO code is invented.', '',
             '| Indicator | Source | Feature | First non-null | Last non-null | Non-null rows | Economies | All rows | Unmatched source rows |',
             '|---|---:|---|---:|---:|---:|---:|---:|---:|']
    lines.extend('| ' + ' | '.join(map(str, r)) + ' |' for r in rows)
    lines += ['', '## Coverage and provenance', '',
              '`wb_coverage_year` stores per-indicator/year non-null counts. `wb_coverage` stores bounds, country counts, pagination totals and excluded row counts. `wb_source_periods` records the source-native time dimension.',
              '`wb_downloads` stores exact query URLs, original retrieval timestamps, SHA-256 checksums, content types, and the complete original response compressed with gzip. The checksum applies to decompressed bytes. `wb_indicators.request_id` joins to this provenance; `lastupdated` retains the API source update date. Original period labels, nulls, observation status, decimals and footnotes are retained.',
              '`wb_indicator_meta` stores the API name, project unit, API unit, source organization, source note, full advanced metadata and source-specific license fields. A blank API unit is not interpreted as unitless. `public=0` for the customs detection-bias control; it must not become a public ranking or route-avoidance feature.', '',
              '## Sources and reproducibility', '',
              '- [Indicators API documentation](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)',
              '- [World Bank dataset terms](https://data.worldbank.org/summary-terms-of-use); per-series license fields must be honored.',
              '- Registry: `backend/trace_backend/wb/indicators.py` (read only).',
              '- Rebuild: `python3 data_collection/world_bank.py`; `--refresh` refetches all pages. A default rerun verifies and uses the checksummed cache.',
              '- Rate control: serial HTTP requests at least one second apart; bounded retries for 429/5xx/network errors, honoring `Retry-After`.', '']
    issues = db.execute('SELECT context,message FROM wb_collection_issues').fetchall()
    if issues:
        lines.extend(['## Collection issues', ''] + [f'- `{c}`: {m}' for c, m in issues])
    target.write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data_collection/work/world_bank.sqlite')
    parser.add_argument('--cache', type=Path, default=ROOT / 'data_collection/cache/world_bank')
    parser.add_argument('--report', type=Path, default=ROOT / 'data_collection/reports/world_bank.md')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.db)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript(SCHEMA)
    client = Client(db, args.cache, refresh=args.refresh)
    load_countries(client)
    load_sources(client)
    failures = []
    for ind in INDICATORS:
        try:
            collect_indicator(client, ind)
        except Exception as exc:
            db.rollback()
            failures.append(ind.code)
            db.execute('INSERT OR REPLACE INTO wb_collection_issues VALUES (?,?,?)', (ind.code, str(exc), now()))
            db.commit()
            print(f'FAILED {ind.code}: {exc}', flush=True)
    report(db, args.report)
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    if not failures:
        parsed = db.execute('SELECT (SELECT COUNT(*) FROM wb_indicators)+(SELECT COUNT(*) FROM wb_excluded_observations)').fetchone()[0]
        assert parsed == db.execute('SELECT SUM(api_total_records) FROM wb_coverage').fetchone()[0]
    db.close()
    if failures:
        raise SystemExit('Failed indicators (rerun resumes from verified cache): ' + ', '.join(failures))


if __name__ == '__main__':
    main()
