# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""World Bank collection safeguards; synthetic API responses, no network."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
import urllib.error
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from world_bank import Client, SCHEMA, ingest_observation_page, retry_seconds, validate_json


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())
        self.headers = {'Content-Type': 'application/json'}


def body(page=1, pages=1, total=1, records=None, updated='2026-09-26'):
    return [{'page': str(page), 'pages': str(pages), 'total': str(total),
             'sourceid': '2', 'lastupdated': updated}, records or [{'x': page}]]


class WorldBankTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = sqlite3.connect(':memory:')
        self.db.executescript(SCHEMA)
        self.calls, self.sleeps = [], []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def client(self, responses):
        responses = iter(responses)
        def opener(req, timeout):
            self.calls.append(req.full_url)
            response = next(responses)
            if isinstance(response, BaseException):
                raise response
            return Response(response)
        return Client(self.db, Path(self.tmp.name), opener=opener,
                      sleeper=self.sleeps.append, monotonic=lambda: 0)

    def test_every_page_and_no_history_restriction(self):
        client = self.client([body(1, 3, 3), body(2, 3, 3), body(3, 3, 3)])
        pages = list(client.pages('country/all/indicator/X', {'source': 2, 'footnote': 'y'}))
        self.assertEqual(len(pages), 3)
        for url in self.calls:
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query['source'], ['2'])
            self.assertFalse({'date', 'mrv', 'mrnev', 'gapfill'} & query.keys())
        self.assertEqual([parse_qs(urlparse(u).query)['page'][0] for u in self.calls], ['1', '2', '3'])
        self.assertEqual(self.sleeps, [1.0, 1.0])

    def test_rejects_source_snapshot_change(self):
        client = self.client([body(1, 2, 2), body(2, 2, 2, updated='2026-09-27')])
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            list(client.pages('country'))

    def test_retry_after_and_bounded_retry(self):
        error = urllib.error.HTTPError('https://example.test', 429, 'Too many requests', {'Retry-After': '7'}, None)
        client = self.client([error, body()])
        client.get('country', {})
        self.assertIn(7.0, self.sleeps)
        self.assertEqual(len(self.calls), 2)
        other = self.client([error, error])
        other.retries = 2
        with self.assertRaises(urllib.error.HTTPError):
            other.get('distinct', {})
        self.assertEqual(len(self.calls), 4)
        error.close()

    def test_cache_checksum_original_timestamp_and_embedded_payload(self):
        client = self.client([body()])
        first, request_id, meta = client.get('country', {})
        second, same_id, same_meta = client.get('country', {})
        self.assertEqual((first, request_id, meta), (second, same_id, same_meta))
        self.assertEqual(len(self.calls), 1)
        sha, payload = self.db.execute('SELECT sha256,payload_gzip FROM wb_downloads').fetchone()
        self.assertEqual(hashlib.sha256(gzip.decompress(payload)).hexdigest(), sha)
        (Path(self.tmp.name) / (request_id + '.json.gz')).write_bytes(gzip.compress(b'{}'))
        with self.assertRaisesRegex(ValueError, 'Cache integrity mismatch'):
            client.get('country', {})

    def test_null_zero_footnote_period_and_aggregate_preservation(self):
        ind = SimpleNamespace(code='X', source_id=2)
        def row(iso3, period, value):
            return {'indicator': {'id': 'X'}, 'countryiso3code': iso3, 'date': period,
                    'value': value, 'unit': 'people', 'obs_status': 'F', 'decimal': 1, 'footnote': 'Survey'}
        records = [row('USA', '1960', None), row('USA', '1961', 0), row('USA', '1962Q1', 4),
                   row('WLD', '1960', 100), row('XXX', '1960', 200)]
        payload = body(records=records, total=5)
        client = self.client([payload])
        received, request_id, metadata = client.get('country/all/indicator/X', {})
        counts = ingest_observation_page(self.db, ind, received, request_id, metadata, {'USA'}, {'WLD'})
        self.assertEqual(counts, (3, 1, 1))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM wb_excluded_observations').fetchone()[0], 2)
        values = self.db.execute('SELECT period,year,value,obs_status,footnote,unit FROM wb_indicators ORDER BY period').fetchall()
        self.assertEqual(values[0], ('1960', 1960, None, 'F', 'Survey', 'people'))
        self.assertEqual(values[1][2], 0)
        self.assertIsNone(values[2][1])
        original = json.loads(gzip.decompress(self.db.execute('SELECT payload_gzip FROM wb_downloads').fetchone()[0]))
        self.assertEqual(len(original[1]), 5)

    def test_duplicate_observation_rejected(self):
        ind = SimpleNamespace(code='X', source_id=2)
        row = {'indicator': {'id': 'X'}, 'countryiso3code': 'USA', 'date': '1960', 'value': None}
        with self.assertRaises(sqlite3.IntegrityError):
            ingest_observation_page(self.db, ind, body(records=[row, row]), 'id', {'retrieved_at': 'now'}, {'USA'}, set())

    def test_error_body_at_http_200_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'API error body'):
            validate_json(b'[{"message":[{"id":"120","value":"Invalid indicator"}]}]')

    def test_retry_header_formats(self):
        self.assertEqual(retry_seconds('3', 0), 3)
        self.assertEqual(retry_seconds('invalid', 2), 8)
        self.assertEqual(retry_seconds('Wed, 21 Oct 2015 07:28:00 GMT', 0), 0)


if __name__ == '__main__':
    unittest.main()
