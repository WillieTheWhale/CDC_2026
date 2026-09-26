# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Checks that derived market values join only compatible source observations."""
import json
import sqlite3
import unittest

from build import derive, schema, unit_and_value


class MarketDerivationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        schema(self.db)

    def tearDown(self):
        self.db.close()

    def observation(self, obs_id, source="prices", iso="FRA", year=2024,
                    substance="Cocaine hydrochloride", form="hydrochloride",
                    level="retail", measure="price", value=80, unit="usd_per_gram"):
        self.db.execute("""INSERT INTO market_observations(
            observation_id,source_id,sheet,row_no,col_no,iso3,country,year,
            substance,form,market_level,measure,basis,original_value,original_unit,
            normalized_value,normalized_unit,original_text,publisher_estimate,source_row_ref)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (obs_id,source,"Prices in USD" if measure == "price" else "Purities",
             obs_id,1,iso,"France",year,substance,form,level,measure,"typical",
             value,unit,value,unit,str(value),0,f"{source}:R{obs_id}"))

    def test_normalization_never_converts_incompatible_units(self):
        self.assertEqual(unit_and_value("price", "Kilograms", 5000), ("usd_per_gram", 5))
        self.assertEqual(unit_and_value("price", "Tablets", 5), ("usd_per_tablet", 5))
        self.assertEqual(unit_and_value("price", "Litres", 5), (None, None))

    def test_exact_match_and_lineage(self):
        self.observation(1)
        self.observation(2, measure="purity", value=40, unit="percent")
        self.observation(3, level="wholesale", value=20000 / 1000)
        self.observation(4, year=2023, measure="purity", value=90, unit="percent")
        self.observation(5, form="crack", measure="purity", value=90, unit="percent")
        derive(self.db, "test")
        out = {r[0]: (r[1], json.loads(r[2])) for r in self.db.execute(
            "SELECT metric_code,value,inputs_json FROM market_derived")}
        self.assertAlmostEqual(out["purity_adjusted_price_usd_per_pure_g"][0], 200)
        self.assertEqual(out["purity_adjusted_price_usd_per_pure_g"][1]["purity_observation_id"], 2)
        self.assertAlmostEqual(out["retail_wholesale_price_ratio"][0], 4)

    def test_conflicting_reported_values_are_not_averaged(self):
        self.observation(1, value=80)
        self.observation(2, value=85)
        self.observation(3, measure="purity", value=40, unit="percent")
        self.observation(4, level="wholesale", value=20)
        derive(self.db, "test")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM market_derived").fetchone()[0], 0)

    def test_cannabis_potency_is_not_treated_as_purity(self):
        self.observation(1, substance="Cannabis resin (hashish)", form="resin")
        self.observation(2, substance="Cannabis resin (hashish)", form="resin",
                         measure="purity", value=20, unit="percent")
        derive(self.db, "test")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM market_derived").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
