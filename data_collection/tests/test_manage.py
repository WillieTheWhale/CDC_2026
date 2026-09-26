# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from data_collection import manage


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def shard(self, name, table):
        path = self.root / name
        with sqlite3.connect(path) as con:
            con.execute(f'CREATE TABLE "{table}" (iso3 TEXT, year INTEGER, value REAL, PRIMARY KEY(iso3,year))')
            con.executemany(f'INSERT INTO "{table}" VALUES (?,?,?)', [("COL", 1960, 0.0), ("COL", 1961, None)])
            con.execute(f'CREATE INDEX "{table}_year" ON "{table}"(year)')
        return path

    def test_merge_preserves_nulls_and_indexes(self):
        a, b = self.shard("a.sqlite", "series_a"), self.shard("b.sqlite", "series_b")
        output = self.root / "trace.sqlite"
        report = manage.merge([a, b], output)
        self.assertEqual(report["tables"]["series_a"]["first_year"], 1960)
        with sqlite3.connect(output) as con:
            self.assertIsNone(con.execute("SELECT value FROM series_b WHERE year=1961").fetchone()[0])
            self.assertEqual(con.execute("SELECT count(*) FROM collection_shards").fetchone()[0], 2)
            self.assertTrue(con.execute("SELECT 1 FROM sqlite_master WHERE name='series_a_year'").fetchone())

    @unittest.skipUnless(sys.platform == "darwin", "APFS clone is macOS-only")
    def test_clone_base_equivalent_and_source_unchanged(self):
        a, b = self.shard("a.sqlite", "series_a"), self.shard("b.sqlite", "series_b")
        before = manage.digest(a)
        regular = self.root / "regular.sqlite"
        cloned = self.root / "cloned.sqlite"
        standard_report = manage.merge([a, b], regular)
        clone_report = manage.merge([a, b], cloned, clone_base=True)
        self.assertEqual(standard_report["tables"], clone_report["tables"])
        self.assertEqual(manage.digest(a), before)
        with sqlite3.connect(cloned) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM collection_shards").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT value FROM series_a WHERE year=1960").fetchone()[0], 0.0)

    def test_extend_retains_base_and_adds_new_shard(self):
        a, b, c = (self.shard(f"{letter}.sqlite", f"series_{letter}") for letter in "abc")
        base = self.root / "base.sqlite"
        output = self.root / "extended.sqlite"
        manage.merge([a, b], base)
        with sqlite3.connect(base) as con:
            con.execute("PRAGMA user_version=1")
        base_digest = manage.digest(base)
        report = manage.extend(base, [c], output)
        self.assertEqual(manage.digest(base), base_digest)
        self.assertEqual(report["tables"]["series_c"]["rows"], 2)
        with sqlite3.connect(output) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM collection_shards").fetchone()[0], 3)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_collision_leaves_previous_database_untouched(self):
        a, b = self.shard("a.sqlite", "series"), self.shard("b.sqlite", "series")
        output = self.root / "trace.sqlite"
        manage.merge([a], output)
        before = manage.digest(output)
        with self.assertRaisesRegex(ValueError, "collision"):
            manage.merge([a, b], output)
        self.assertEqual(manage.digest(output), before)

    def test_snapshot_download_roundtrip_and_tamper_rejection(self):
        source = self.shard("source.sqlite", "series")
        archive, manifest = self.root / "trace.sqlite.gz", self.root / "snapshot.json"
        meta = manage.snapshot(source, archive, manifest, "test", "example/repo")
        output = self.root / "restored.sqlite"
        with patch.object(manage, "urlopen", return_value=io.BytesIO(archive.read_bytes())):
            manage.download(manifest, output)
        self.assertEqual(manage.digest(source), manage.digest(output))
        meta["database"]["sha256"] = "bad"
        manifest.write_text(json.dumps(meta))
        with patch.object(manage, "urlopen", return_value=io.BytesIO(archive.read_bytes())):
            with self.assertRaisesRegex(ValueError, "SQLite database"):
                manage.download(manifest, output)
        self.assertEqual(manage.digest(source), manage.digest(output))
        with patch.object(manage, "urlopen", return_value=io.BytesIO(b"corrupt")):
            with self.assertRaisesRegex(ValueError, "archive"):
                manage.download(manifest, output)

    def test_verify_remote_stream_checks_both_hashes(self):
        source = self.shard("source.sqlite", "series")
        archive, manifest = self.root / "trace.sqlite.gz", self.root / "snapshot.json"
        manage.snapshot(source, archive, manifest, "test", "example/repo")
        with patch.object(manage, "urlopen", return_value=io.BytesIO(archive.read_bytes())):
            result = manage.verify_remote(manifest)
        self.assertTrue(result["remote_stream_verified"])
        corrupted = archive.read_bytes()[:-1]
        with patch.object(manage, "urlopen", return_value=io.BytesIO(corrupted)):
            with self.assertRaises(ValueError):
                manage.verify_remote(manifest)


if __name__ == "__main__":
    unittest.main()
