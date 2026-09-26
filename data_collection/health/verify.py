# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Audit the completed health shard against downloaded source files and semantics."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from collect import OUTPUT, CACHE


def verify(path: Path = OUTPUT):
    assert path.exists(), f"Missing shard: {path}"
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        counts = dict(db.execute("SELECT source_id,count(*) FROM health_source_files GROUP BY source_id"))
        assert len(counts) == 9 and counts["cdc_xkb8_kh2a"] >= 18, counts
        for source_id, filename, _, _, digest, size in db.execute(
            "SELECT source_id,part_name,url,retrieved_at,sha256,bytes FROM health_source_files"
        ):
            source_file = CACHE / filename
            assert source_file.exists() and source_file.stat().st_size == size, (source_id, filename)
            with source_file.open("rb") as handle:
                assert hashlib.file_digest(handle, "sha256").hexdigest() == digest, filename
        for table in ("health_prevalence", "health_pwid", "health_treatment", "health_treatment_coverage", "health_regional_estimates"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0, table
        assert db.execute("SELECT min(year),max(year) FROM health_prevalence").fetchone() == (1991, 2024)
        assert db.execute("SELECT count(*) FROM health_prevalence WHERE value_pct<0 OR value_pct>100").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM health_prevalence WHERE value_pct=0").fetchone()[0] > 0
        assert db.execute("SELECT count(*) FROM health_pwid WHERE value<0 OR (unit LIKE 'percent%' AND value>100)").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM health_treatment WHERE persons_treated<0").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM health_cdc_overdose").fetchone()[0] >= 80000
        assert db.execute("SELECT count(*) FROM health_treatment_coverage WHERE nature_code='M'").fetchone()[0] > 0
        assert db.execute("SELECT count(*) FROM health_treatment_coverage WHERE nature_code='C'").fetchone()[0] > 0
        assert db.execute("SELECT count(*) FROM health_treatment_coverage WHERE value_pct<0 OR value_pct>100").fetchone()[0] == 0
        assert db.execute("SELECT count(distinct period) FROM health_cdc_overdose").fetchone()[0] == 1
        assert db.execute("SELECT period FROM health_cdc_overdose LIMIT 1").fetchone()[0] == "12 month-ending"
        assert db.execute("SELECT count(*) FROM health_cdc_overdose WHERE suppressed_or_unavailable=1 AND (reported_value IS NOT NULL OR predicted_value IS NOT NULL)").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM health_cdc_overdose WHERE metric_kind='drug_specification_fraction' AND value_unit!='percent'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM health_cdc_overdose WHERE metric_kind='drug_involved_overdose' AND value_unit!='deaths'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM health_cdc_overdose WHERE end_month=12 AND end_year=2024 AND state='US' AND indicator='Number of Drug Overdose Deaths' AND reported_value IS NOT NULL").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM health_regional_estimates WHERE estimate_status!='published_model_estimate'").fetchone()[0] == 0
        print("health shard verified:", path)
        for table in ("health_sources", "health_source_files", "health_raw_rows", "health_prevalence", "health_pwid", "health_treatment", "health_treatment_coverage", "health_regional_estimates", "health_cdc_overdose"):
            print(table, db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    verify()
