# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Verify source shards, extend v1, audit lineage, and package the v2 release."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from coverage import write_report
import manage

ROOT = Path(__file__).resolve().parent
REPO = "WillieTheWhale/CDC_2026"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_shards(directory: Path, shard_manifest: Path) -> tuple[dict, list[Path]]:
    manifest = json.loads(shard_manifest.read_text())
    require(manifest["base_release_tag"] == "data-2026-09-26-v1", "Unexpected base release")
    require(manifest["release_tag"] == "data-2026-09-26-v2", "Unexpected v2 release")
    paths = []
    for item in manifest["shards"]:
        path = directory / item["filename"]
        require(path.is_file(), f"Missing shard {path}")
        require(path.stat().st_size == item["bytes"] and manage.digest(path) == item["sha256"],
                f"Shard checksum mismatch: {path}")
        manage.inspect(path)
        paths.append(path)
    require(len(paths) == 4 and len(set(paths)) == 4, "Expected four distinct new shards")
    return manifest, paths


def audit(db: Path) -> dict:
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as con:
        table_names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"wb_indicators", "seizures_raw", "health_prevalence", "health_pwid",
                    "health_treatment_coverage", "health_cdc_overdose", "market_derived",
                    "market_observations", "market_cells", "research_values",
                    "research_value_inputs", "research_model_results", "evidence_claims",
                    "collection_shards"}
        require(required.issubset(table_names), f"Missing tables: {sorted(required-table_names)}")
        shard_count = con.execute("SELECT count(*) FROM collection_shards").fetchone()[0]
        require(shard_count == 7, f"Expected 7 contributing shards, got {shard_count}")
        lineage_gaps = con.execute("""SELECT count(*) FROM research_values v WHERE
            v.support_count != (SELECT count(*) FROM research_value_inputs i
             WHERE i.metric_id=v.metric_id) OR v.first_publication_year > v.last_publication_year""").fetchone()[0]
        require(lineage_gaps == 0, "Research support count/publication lineage mismatch")
        require(con.execute("SELECT count(*) FROM research_values WHERE metric_key='retail_wholesale_price_ratio'").fetchone()[0] == 0,
                "Rejected coarse price ratios must not be displayed")
        research_counts = dict(con.execute("SELECT metric_key,count(*) FROM research_values GROUP BY metric_key"))
        require(research_counts.get("seizure_edition_revision_pct") == 1642, "Revision denominator changed")
        require(research_counts.get("cocaine_seizure_next_homicide") == 1428, "Model sample changed")
        metric_counts = dict(con.execute("SELECT metric_code,count(*) FROM market_derived GROUP BY metric_code"))
        require(metric_counts.get("retail_wholesale_price_ratio") == 449, "Exact-product ratio count changed")
        require(metric_counts.get("purity_adjusted_price_usd_per_pure_g") == 476,
                "Purity-adjusted price count changed")
        observation_ids = {r[0] for r in con.execute("SELECT observation_id FROM market_observations")}
        for (inputs_json,) in con.execute("SELECT inputs_json FROM market_derived"):
            for name, value in json.loads(inputs_json).items():
                if name.endswith("_observation_id"):
                    require(value in observation_ids, f"Missing market source observation {value}")
        coverage_natures = dict(con.execute(
            "SELECT nature_code,count(*) FROM health_treatment_coverage GROUP BY nature_code"))
        require(coverage_natures.get("M") == 2316 and coverage_natures.get("C") == 174,
                "Modeled/country treatment coverage distinction changed")
        suppressed = con.execute("""SELECT count(*) FROM health_cdc_overdose WHERE
            suppressed_or_unavailable=1 AND (reported_value IS NOT NULL OR predicted_value IS NOT NULL)""").fetchone()[0]
        require(suppressed == 0, "Suppressed CDC values must remain NULL")
        evidence_count = con.execute("SELECT count(*) FROM evidence_claims").fetchone()[0]
        require(evidence_count == 8, "Evidence catalog count changed")
        model_count = con.execute("SELECT count(*) FROM research_model_results").fetchone()[0]
        require(model_count == 1, "Expected one preregistered research model")
        return {"shards": shard_count, "research": research_counts, "market": metric_counts,
                "treatment_coverage_nature": coverage_natures, "evidence_claims": evidence_count,
                "model_results": model_count, "lineage_gaps": lineage_gaps}


def assemble(base: Path, shards_dir: Path, shard_manifest: Path, output: Path,
             archive: Path, manifest: Path, coverage_report: Path) -> dict:
    sources, paths = verify_shards(shards_dir, shard_manifest)
    base_manifest = json.loads((ROOT / "snapshot.json").read_text())
    require(base_manifest["release_tag"] == sources["base_release_tag"],
            "Checkout must carry the immutable v1 base manifest")
    require(base.stat().st_size == base_manifest["database"]["bytes"] and
            manage.digest(base) == base_manifest["database"]["sha256"],
            "Base SQLite does not match the v1 published database")
    manage.extend(base, paths, output)
    qa = audit(output)
    write_report(output, coverage_report)
    snapshot = manage.snapshot(output, archive, manifest, sources["release_tag"], REPO)
    require(snapshot["schema_version"] == 2, "Expected v2 schema version")
    return {"qa": qa, "archive": snapshot["archive"], "database": snapshot["database"],
            "table_count": len(snapshot["tables"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--shards-dir", type=Path, required=True)
    parser.add_argument("--shard-manifest", type=Path, default=ROOT / "shards_v2.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(assemble(**vars(args)), indent=2))
