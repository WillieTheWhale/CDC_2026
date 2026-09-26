# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Check that the frontend export retains SQLite values and their lineage."""

import json
import math
import os
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "frontend/public/data/observed-v2"
SHARDS = Path(os.environ.get("TRACE_SHARDS_DIR", str(ROOT / "data_collection/work")))


class ObservedExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overview = json.loads((EXPORT / "overview.json").read_text())
        cls.countries = [json.loads(path.read_text()) for path in sorted((EXPORT / "countries").glob("*.json"))]

    def test_published_identity_and_complete_source_counts(self):
        manifest = json.loads((ROOT / "data_collection/snapshot.json").read_text())
        self.assertEqual(self.overview["snapshot"]["databaseSha256"], manifest["database"]["sha256"])
        counts = {}
        for country in self.countries:
            for row in country["observations"]:
                counts[row["domain"]] = counts.get(row["domain"], 0) + 1
                self.assertEqual(row["iso3"], country["iso3"])
                self.assertTrue(row["sourceUrl"].startswith("http"))
                self.assertNotIn("risk_score", row["domain"])
        self.assertEqual(sum(counts.values()), 49063)
        self.assertEqual(sum(len(c["researchValues"]) for c in self.countries), 3070)
        self.assertEqual(sum(len(c["researchSamples"]) for c in self.countries), 1428)
        self.assertEqual(len(self.overview["evidenceClaims"]), 8)
        self.assertEqual(len(self.overview["researchModelResults"]), 1)
        shard_manifest = json.loads((ROOT / "data_collection/shards_v2.json").read_text())
        self.assertEqual(self.overview["snapshot"]["inputShards"],
                         {row["filename"]: row["sha256"] for row in shard_manifest["shards"]})

    def test_market_derived_inputs_point_to_exact_source_observations(self):
        for country in self.countries:
            by_id = {row.get("observationId"): row for row in country["observations"] if row["domain"] == "market_price"}
            for row in country["observations"]:
                if row["domain"] != "market_derived":
                    continue
                self.assertTrue(row["inputObservationIds"])
                for observation_id in row["inputObservationIds"]:
                    source = by_id[observation_id]
                    self.assertEqual(row["year"], source["year"])
                    self.assertEqual(row["sourceUrl"], source["sourceUrl"])
                    self.assertIsNotNone(source["sourceRow"]["rowNo"])
                    self.assertEqual(source["basis"], "typical")
                    self.assertEqual(row["substance"], source["substance"])
                    self.assertEqual(row["form"], source["form"])
                numeric = row["inputs"]
                if row["metric"] == "retail_wholesale_price_ratio":
                    self.assertEqual(row["unit"], "ratio")
                    self.assertTrue(math.isclose(
                        row["value"], numeric["retail_usd_per_gram"] / numeric["wholesale_usd_per_gram"],
                        rel_tol=1e-11))
                    self.assertEqual(by_id[numeric["retail_observation_id"]]["unit"], "usd_per_gram")
                    self.assertEqual(by_id[numeric["retail_observation_id"]]["marketLevel"], "retail")
                    self.assertEqual(by_id[numeric["wholesale_observation_id"]]["marketLevel"], "wholesale")
                elif row["metric"] == "purity_adjusted_price_usd_per_pure_g":
                    self.assertEqual(row["unit"], "usd_per_pure_gram")
                    self.assertTrue(math.isclose(
                        row["value"], numeric["price_usd_per_gram"] / (numeric["purity_percent"] / 100),
                        rel_tol=1e-11))
                    self.assertEqual(by_id[numeric["price_observation_id"]]["unit"], "usd_per_gram")
                    self.assertEqual(by_id[numeric["purity_observation_id"]]["unit"], "percent")
                else:
                    self.fail(f"Unexpected derived metric {row['metric']}")
            for source in by_id.values():
                self.assertIn("basis", source)
                self.assertEqual(source["publisherEstimate"], source["status"] == "publisher estimate")
                self.assertNotIn("lower", source)
                self.assertNotIn("upper", source)
                if source["originalUnit"] != source["unit"]:
                    self.assertIn("originalLower", source)
                    self.assertIn("originalUpper", source)

    def test_research_links_and_reported_nulls(self):
        for country in self.countries:
            for metric in country["researchValues"]:
                self.assertEqual(metric["supportCount"], len(metric["inputs"]))
                self.assertEqual(metric["iso3"], country["iso3"])
                for item in metric["inputs"]:
                    self.assertTrue(item["sourceKey"])
                    self.assertNotEqual(item["sourceUrl"], "")
        overdose = json.loads((EXPORT / "us-overdose.json").read_text())
        self.assertEqual(len(overdose), 1632)
        self.assertTrue(all(row["periodKind"] == "12 month-ending" for row in overdose))
        for row in overdose:
            if "suppressed/unavailable" in row["status"]:
                self.assertIsNone(row["reportedValue"])
                self.assertIsNone(row["predictedValue"])
        ranged_pwid = [row for country in self.countries for row in country["observations"]
                       if row["domain"] == "pwid" and row["year"] is None and row.get("yearText")]
        self.assertTrue(ranged_pwid)
        self.assertTrue(all("denominator" in row and "injectingDefinition" in row
                            and "sampleSize" in row and "reference" in row
                            and "attribution" in row for row in ranged_pwid))

    @unittest.skipUnless((SHARDS / "health.sqlite").exists() and (SHARDS / "markets.sqlite").exists(),
                         "Published source shards not present locally")
    def test_export_row_counts_match_source_sqlite(self):
        for shard, table, domain in [
            ("health", "health_prevalence", "prevalence"),
            ("markets", "market_observations", "market_price"),
        ]:
            db = sqlite3.connect(f"file:{SHARDS / (shard + '.sqlite')}?mode=ro", uri=True)
            expected = db.execute(f"SELECT COUNT(*) FROM {table} WHERE iso3 IS NOT NULL").fetchone()[0]
            actual = sum(sum(row["domain"] == domain for row in country["observations"]) for country in self.countries)
            self.assertEqual(actual, expected)
            db.close()


if __name__ == "__main__":
    unittest.main()
