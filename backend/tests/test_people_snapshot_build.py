# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Publisher side of the sharded People snapshot (backend/scripts/build_people_snapshot.py).

unittest-style so the publishing workflow can run it with the standard library alone; pytest collects it too.
"""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_people_snapshot.py"
_spec = importlib.util.spec_from_file_location("build_people_snapshot", SCRIPT)
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)


def sample_manifest(n_people: int = 60) -> dict:
    return {
        "organizations": [{"id": f"org-{i}", "name": f"Org {i}", "aliases": [], "regions": [], "sources": []}
                          for i in range(7)],
        "people": [{"id": f"person-{i}", "name": f"Person Ñame {i}", "aliases": [f"Alias {i}"], "status": "active",
                    "prominence": i % 3, "organizationIds": [f"org-{i % 7}"], "sources": []}
                   for i in range(n_people)],
        "connections": [{"id": f"conn-{i}", "fromId": f"person-{i}", "toId": f"person-{i + 1}", "type": "associate",
                         "sources": []} for i in range(20)],
    }


class SnapshotBuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_manifest(self, manifest, name="manifest.json") -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def build(self, manifest, out="out", **kw):
        return snap.build(self.write_manifest(manifest), self.tmp / out, "abc1234", **kw)

    def test_index_shape_and_people_shard_count(self):
        result = self.build(sample_manifest())
        index = json.loads((self.tmp / "out" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["format"], "trace-people-snapshot/1")
        self.assertEqual(index["source_path"], "frontend/data/people/manifest.json")
        self.assertEqual(index["counts"], {"people": 60, "organizations": 7, "connections": 20})
        kinds = [s["kind"] for s in index["shards"]]
        self.assertEqual(kinds.count("people"), 16)
        self.assertEqual(kinds.count("organizations"), 1)
        self.assertEqual(kinds.count("connections"), 1)
        self.assertEqual(result["version"], snap.sha256_hex(snap.canonical_bytes(sample_manifest())))
        for s in index["shards"]:
            gz = (self.tmp / "out" / s["file"]).read_bytes()
            self.assertEqual(s["file"], f"shards/{s['kind']}-{snap.sha256_hex(gz)[:16]}.json.gz")
            body = json.loads(gzip.decompress(gz))
            self.assertEqual(body["kind"], s["kind"])
            self.assertEqual(len(body["records"]), s["records"])

    def test_deterministic_across_builds_and_formatting(self):
        m = sample_manifest()
        a = self.build(m, out="a")
        # Same content, different key order and whitespace on disk: same version, same shard names and bytes.
        reordered = {"connections": m["connections"], "people": m["people"], "organizations": m["organizations"]}
        path = self.tmp / "compact.json"
        path.write_text(json.dumps(reordered, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
        b = snap.build(path, self.tmp / "b", "other")
        self.assertEqual(a["version"], b["version"])
        self.assertEqual(a["index"]["shards"], b["index"]["shards"])
        for s in a["index"]["shards"]:
            self.assertEqual((self.tmp / "a" / s["file"]).read_bytes(), (self.tmp / "b" / s["file"]).read_bytes())

    def test_rebuild_same_manifest_leaves_index_untouched(self):
        m = sample_manifest()
        self.build(m)
        before = (self.tmp / "out" / "index.json").read_bytes()
        again = snap.build(self.write_manifest(m), self.tmp / "out", "different-commit", now="2099-01-01T00:00:00Z")
        self.assertFalse(again["changed"])
        self.assertEqual((self.tmp / "out" / "index.json").read_bytes(), before)
        self.assertEqual(len(json.loads((self.tmp / "out" / "history.json").read_text(encoding="utf-8"))), 1)

    def test_changing_one_person_changes_exactly_one_people_shard(self):
        m = sample_manifest()
        a = self.build(m, out="a")
        m2 = copy.deepcopy(m)
        m2["people"][17]["status"] = "deceased"
        b = self.build(m2, out="b")
        self.assertNotEqual(a["version"], b["version"])
        files_a = {s["file"] for s in a["index"]["shards"]}
        files_b = {s["file"] for s in b["index"]["shards"]}
        changed = files_b - files_a
        self.assertEqual(len(changed), 1)
        self.assertTrue(next(iter(changed)).startswith("shards/people-"))
        self.assertEqual(len(files_a - files_b), 1)

    def test_verify_passes_and_detects_tampering(self):
        m = sample_manifest()
        manifest_path = self.write_manifest(m)
        snap.build(manifest_path, self.tmp / "out", "abc")
        self.assertEqual(snap.verify(self.tmp / "out", manifest_path), [])
        self.assertEqual(snap.main(["--verify", str(self.tmp / "out"), "--manifest", str(manifest_path)]), 0)

        # A manifest the snapshot does not publish fails verification.
        other = copy.deepcopy(m)
        other["people"].append({"id": "person-new", "name": "New"})
        self.assertTrue(snap.verify(self.tmp / "out", self.write_manifest(other, "other.json")))

        # A corrupted shard fails verification.
        index = json.loads((self.tmp / "out" / "index.json").read_text(encoding="utf-8"))
        victim = self.tmp / "out" / index["shards"][0]["file"]
        victim.write_bytes(snap.gzip_deterministic(b'{"kind":"people","records":[]}'))
        problems = snap.verify(self.tmp / "out", manifest_path)
        self.assertTrue(any("sha256" in p for p in problems))
        self.assertEqual(snap.main(["--verify", str(self.tmp / "out"), "--manifest", str(manifest_path)]), 1)

    def test_refuses_bad_manifest(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        cases = [bad]
        for i, broken in enumerate([[], {"people": [], "organizations": []},
                                    {"people": {}, "organizations": [], "connections": []}]):
            cases.append(self.write_manifest(broken, f"broken{i}.json"))
        for path in cases:
            with self.subTest(path=path.name):
                with self.assertRaises(snap.Refusal):
                    snap.build(path, self.tmp / "never", "abc")
                self.assertEqual(snap.main(["--manifest", str(path), "--out", str(self.tmp / "never")]), 2)
                self.assertFalse((self.tmp / "never" / "index.json").exists())

    def test_history_keeps_five_versions_and_prunes_older_shards(self):
        m = sample_manifest()
        versions = []
        for i in range(7):
            m = copy.deepcopy(m)
            m["people"][0]["prominence"] = 100 + i
            versions.append(self.build(m))
        history = json.loads((self.tmp / "out" / "history.json").read_text(encoding="utf-8"))
        self.assertEqual([h["version"] for h in history], [v["version"] for v in reversed(versions)][:5])
        on_disk = {f"shards/{p.name}" for p in (self.tmp / "out" / "shards").iterdir()}
        self.assertEqual(on_disk, {f for h in history for f in h["shards"]})
        for old in versions[:2]:  # shards unique to the two forgotten versions are gone
            gone = {s["file"] for s in old["index"]["shards"]} - on_disk
            self.assertEqual(len(gone), 1)
        for recent in versions[2:]:
            self.assertTrue({s["file"] for s in recent["index"]["shards"]} <= on_disk)

    def test_large_organizations_split_by_id_hash(self):
        m = sample_manifest(5)
        m["organizations"] = [{"id": f"org-{i}", "name": "x" * 5000} for i in range(600)]  # ~3 MB raw
        result = self.build(m)
        orgs = [s for s in result["index"]["shards"] if s["kind"] == "organizations"]
        self.assertGreater(len(orgs), 1)
        self.assertEqual(sum(s["records"] for s in orgs), 600)
        self.assertEqual(snap.verify(self.tmp / "out", self.tmp / "manifest.json"), [])


if __name__ == "__main__":
    unittest.main()
