# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Check source selection, numerical formulas and evidence-row lineage."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from data_collection import research


class ResearchLineageTests(unittest.TestCase):
    def test_revisions_prices_and_lagged_pair_are_reconstructible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            u, w, out, report = [root / name for name in
                                 ("unodc.sqlite", "wb.sqlite", "research.sqlite", "report.md")]
            with sqlite3.connect(u) as con:
                con.executescript("""
                    CREATE TABLE unodc_sources(source_id TEXT,url TEXT,edition INTEGER);
                    CREATE TABLE seizures_annex(iso3 TEXT,year INTEGER,drug TEXT,kg REAL,source TEXT,edition INTEGER);
                    CREATE TABLE prices(iso3 TEXT,drug TEXT,level TEXT,year INTEGER,usd_g REAL,source TEXT,basis TEXT,upstream_estimate INTEGER);
                    CREATE TABLE unodc_seizure_observations(source_id TEXT,sheet TEXT,row_no INTEGER,iso3 TEXT,year INTEGER,drug TEXT,quantity REAL,unit TEXT,kg_trace_equivalent REAL);
                """)
                con.executemany("INSERT INTO unodc_sources VALUES (?,?,?)", [
                    ("old", "https://source.test/old", 2012),
                    ("new", "https://source.test/new", 2026),
                ])
                con.executemany("INSERT INTO seizures_annex VALUES (?,?,?,?,?,?)", [
                    ("COL", 2009, "cocaine", 10.0, "old", 2012),
                    ("COL", 2009, "cocaine", 12.0, "new", 2026),
                ])
                con.executemany("INSERT INTO unodc_seizure_observations VALUES (?,?,?,?,?,?,?,?,?)", [
                    ("old", "sheet", 3, "COL", 2009, "cocaine", 10.0, "Kilogram", 10.0),
                    ("new", "sheet", 4, "COL", 2009, "cocaine", 12.0, "Kilogram", 12.0),
                ])
                con.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)", [
                    ("COL", "cocaine", "retail", 2009, 8.0, "new", "typical", 0),
                    ("COL", "cocaine", "wholesale", 2009, 4.0, "new", "typical", 0),
                ])
            with sqlite3.connect(w) as con:
                con.executescript("""
                    CREATE TABLE wb_indicators(iso3 TEXT,year INTEGER,code TEXT,source_id INTEGER,value REAL,request_id TEXT,lastupdated TEXT);
                    CREATE TABLE wb_downloads(request_id TEXT,url TEXT);
                """)
                con.execute("INSERT INTO wb_downloads VALUES (?,?)", ("req", "https://api.worldbank.org/example"))
                con.execute("INSERT INTO wb_indicators VALUES (?,?,?,?,?,?,?)",
                            ("COL", 2010, "VC.IHR.PSRC.P5", 2, 7.0, "req", "2026-09-25"))
            result = research.build(out, w, u, report)
            self.assertEqual((result["revision_rows"], result["coarse_price_pair_candidates_rejected"],
                              result["regression_rows"]), (1, 1, 1))
            with sqlite3.connect(out) as con:
                rows = dict(con.execute("SELECT metric_key,value FROM research_values"))
                self.assertAlmostEqual(rows["seizure_edition_revision_pct"], 20.0)
                self.assertNotIn("retail_wholesale_price_ratio", rows)
                self.assertAlmostEqual(rows["cocaine_seizure_next_homicide"], 7.0)
                self.assertEqual(con.execute("SELECT count(*) FROM research_value_inputs").fetchone()[0], 7)
                self.assertEqual(con.execute("SELECT count(*) FROM research_value_inputs "
                                             "WHERE source_url IS NULL").fetchone()[0], 0)
                pair = con.execute("SELECT seizure_year,outcome_year FROM research_regression_samples").fetchone()
                self.assertEqual(pair, (2009, 2010))
                published = con.execute("SELECT first_publication_year,last_publication_year "
                                        "FROM research_values WHERE metric_key='seizure_edition_revision_pct'").fetchone()
                self.assertEqual(published, (2012, 2026))
                wb_publication = con.execute("SELECT publication_year FROM research_value_inputs "
                                             "WHERE source_table='wb_indicators'").fetchone()[0]
                self.assertIsNone(wb_publication)  # lastupdated is not a publication year.


if __name__ == "__main__":
    unittest.main()
