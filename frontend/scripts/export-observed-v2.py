# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Export source-preserved, read-only SQLite observations for the frontend.

The verified published shards are accepted independently so a low-disk workstation
does not need to restore the 1.2 GB canonical archive. A restored canonical DB
can also be passed for all four arguments. No model or route fixtures enter this
export. Run from the repository root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "frontend/public/data/observed-v2"
MANIFEST = json.loads((ROOT / "data_collection/snapshot.json").read_text())
SHARDS = json.loads((ROOT / "data_collection/shards_v2.json").read_text())


def rows(db: sqlite3.Connection, sql: str):
    return [dict(row) for row in db.execute(sql)]


def connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError(f"SQLite integrity check failed: {path}")
    return db


def check_shard(path: Path, filename: str) -> None:
    expected = next((item for item in SHARDS["shards"] if item["filename"] == filename), None)
    if not expected:
        raise ValueError(f"No pinned checksum for {filename}")
    if path.stat().st_size != expected["bytes"]:
        raise ValueError(f"Incorrect size for {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected["sha256"]:
        raise ValueError(f"Incorrect SHA-256 for {path}")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


def clean_row(row: dict, **extra):
    return {**{k: v for k, v in row.items() if v is not None}, **extra}


def source_info(db: sqlite3.Connection, table: str):
    return {row["source_id"]: dict(row) for row in db.execute(f"SELECT * FROM {table}")}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("health", "markets", "research", "evidence"):
        parser.add_argument(f"--{name}", type=Path, default=ROOT / f"data_collection/work/{name}.sqlite")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verify-shards", action="store_true", help="Retained for CLI compatibility; source verification is always required")
    args = parser.parse_args()
    paths = [getattr(args, name).resolve() for name in ("health", "markets", "research", "evidence")]
    if len(set(paths)) == 1:
        path = paths[0]
        if path.stat().st_size != MANIFEST["database"]["bytes"]:
            raise ValueError("Canonical SQLite size differs from release manifest")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != MANIFEST["database"]["sha256"]:
            raise ValueError("Canonical SQLite SHA-256 differs from release manifest")
    else:
        for name in ("health", "markets", "research", "evidence"):
            check_shard(getattr(args, name), f"{name}.sqlite")

    dbs = {name: connect(getattr(args, name)) for name in ("health", "markets", "research", "evidence")}
    health, markets, research, evidence = (dbs[name] for name in ("health", "markets", "research", "evidence"))
    health_sources = source_info(health, "health_sources")
    market_sources = source_info(markets, "market_sources")
    evidence_sources = source_info(evidence, "evidence_sources")
    sources = {}
    for prefix, collection in (("health", health_sources), ("market", market_sources), ("evidence", evidence_sources)):
        for key, item in collection.items():
            sources[f"{prefix}:{key}"] = {
                "title": item.get("title") or item.get("citation") or key,
                "publisher": item.get("publisher") or "UNODC",
                "url": item["url"],
                "publicationYear": item.get("edition_year", item.get("edition", item.get("publication_year"))),
                "caveat": item.get("caveat"),
            }

    countries: dict[str, dict] = defaultdict(lambda: {"observations": [], "researchValues": [], "researchSamples": []})
    counts: dict[str, Counter] = defaultdict(Counter)
    market_catalog: Counter = Counter()

    def add(iso3: str | None, observation: dict):
        if iso3:
            countries[iso3]["observations"].append(observation)
            counts[iso3][observation["domain"]] += 1
            if observation["domain"] in ("market_price", "market_derived"):
                market_catalog[(iso3, observation.get("substance"), observation.get("form"), observation.get("year"), observation.get("marketLevel"), observation["metric"])] += 1

    def health_record(row: dict, domain: str, value_key: str, unit: str, metric_key: str, id_suffix: str):
        src = health_sources[row["source_id"]]
        record = {
            "id": f"{domain}:{row['source_id']}:{id_suffix}", "domain": domain,
            "iso3": row["iso3"], "year": row.get("year"), "metric": row[metric_key],
            "value": row[value_key], "unit": unit,
            "sourceId": f"health:{row['source_id']}", "sourceUrl": src["url"],
            "publicationYear": src.get("edition_year"),
        }
        if "sheet" in row:
            record["sourceRow"] = {"sheet": row["sheet"], "rowNo": row["row_no"]}
            if "cell_no" in row:
                record["sourceRow"]["cellNo"] = row["cell_no"]
        return record

    for row in rows(health, "SELECT * FROM health_prevalence WHERE iso3 IS NOT NULL"):
        record = health_record(row, "prevalence", "value_pct", "%", "substance", f"{row['sheet']}:{row['row_no']}:{row['cell_no']}")
        record.update({"substance": row["substance"], "yearText": row["year_text"],
                       "population": row["population"], "ageGroup": row["age_group"],
                       "sex": row["sex"], "referencePeriod": row["reference_period"], "lower": row["low_pct"],
                       "upper": row["high_pct"], "status": row["estimate_status"], "method": row["source_method"],
                       "attribution": row["source_attribution"], "caveat": row["notes"] or row["adjustment_note"]})
        add(row["iso3"], record)

    for row in rows(health, "SELECT * FROM health_pwid WHERE iso3 IS NOT NULL"):
        record = health_record(row, "pwid", "value", row["unit"], "metric", f"{row['sheet']}:{row['row_no']}:{row['cell_no']}")
        record.update({"yearText": row["year_text"], "sex": row["sex"], "ageGroup": row["age_group"],
                       "lower": row["low"], "upper": row["high"], "denominator": row["denominator"],
                       "status": row["estimate_status"], "geographicCoverage": row["geographic_coverage"],
                       "injectingDefinition": row["injecting_definition"], "sampleSize": row["sample_size"],
                       "reference": row["reference"], "attribution": row["attribution"],
                       "method": row["method"], "caveat": row["notes"]})
        add(row["iso3"], record)

    for row in rows(health, "SELECT * FROM health_treatment WHERE iso3 IS NOT NULL"):
        record = health_record(row, "treatment_contacts", "persons_treated", "persons treated", "drug_group", f"{row['sheet']}:{row['row_no']}")
        record.update({"substance": row["drug"], "sex": row["sex"], "yearText": row["year_text"],
                       "referencePeriod": row["specified_reference_year"],
                       "caveat": "Primary-drug treatment contacts; group and child drug rows can overlap."})
        add(row["iso3"], record)

    for row in rows(health, "SELECT * FROM health_treatment_coverage WHERE iso3 IS NOT NULL"):
        record = health_record(row, "treatment_coverage", "value_pct", "%", "substance_group", str(row["source_row_no"]))
        record.update({"substance": row["substance_group"], "sex": row["sex"], "lower": row["lower_pct"],
                       "upper": row["upper_pct"], "status": row["nature_meaning"] or row["nature_code"],
                       "attribution": row["source_attribution"], "caveat": row["footnotes_json"]})
        record["sourceRow"] = {"rowNo": row["source_row_no"]}
        add(row["iso3"], record)

    for row in rows(markets, "SELECT * FROM market_observations WHERE iso3 IS NOT NULL"):
        src = market_sources[row["source_id"]]
        value = row["normalized_value"] if row["normalized_value"] is not None else row["original_value"]
        unit = row["normalized_unit"] or row["original_unit"] or "source unit unavailable"
        add(row["iso3"], {
            "id": f"market_price:{row['observation_id']}", "observationId": row["observation_id"], "domain": "market_price",
            "iso3": row["iso3"], "year": row["year"], "metric": row["measure"], "substance": row["substance"],
            "form": row["form"], "marketLevel": row["market_level"], "value": value, "unit": unit,
            "basis": row["basis"],
            "originalValue": row["original_value"], "originalUnit": row["original_unit"], "originalText": row["original_text"],
            "originalLower": row["minimum"], "originalUpper": row["maximum"],
            "status": "publisher estimate" if row["publisher_estimate"] else "source observation",
            "sourceId": f"market:{row['source_id']}", "sourceUrl": src["url"], "publicationYear": src["edition"],
            "sourceRow": {"sheet": row["sheet"], "rowNo": row["row_no"], "cellNo": row["col_no"]},
            "caveat": "Source price or purity observation; not a trade flow.",
        })

    for row in rows(markets, "SELECT * FROM market_derived"):
        src = market_sources[row["source_id"]]
        inputs = json.loads(row["inputs_json"])
        add(row["iso3"], {
            "id": f"market_derived:{row['derived_id']}", "derivedId": row["derived_id"], "domain": "market_derived",
            "iso3": row["iso3"], "year": row["year"], "metric": row["metric_code"],
            "substance": row["substance"], "form": row["form"], "marketLevel": row["market_level"],
            "value": row["value"], "unit": row["unit"], "formula": row["formula"], "inputs": inputs,
            "inputObservationIds": [v for k, v in inputs.items() if k.endswith("observation_id")],
            "sourceId": f"market:{row['source_id']}", "sourceUrl": src["url"], "publicationYear": src["edition"],
            "status": "descriptive derived value", "caveat": "Matched exact product, year and sale level; nominal values can combine different source samples. Ratio is not a margin or route gradient.",
        })

    definitions = {row["metric_key"]: row for row in rows(research, "SELECT * FROM research_metric_definitions")}
    inputs: dict[str, list[dict]] = defaultdict(list)
    for row in rows(research, "SELECT * FROM research_value_inputs ORDER BY metric_id, role, source_table, source_key"):
        inputs[row["metric_id"]].append({
            "role": row["role"], "sourceTable": row["source_table"], "sourceKey": row["source_key"],
            "sourceId": row["source_id"], "sourceUrl": row["source_url"],
            "publicationYear": row["publication_year"], "observationYear": row["observation_year"],
            "value": row["input_value"], "unit": row["input_unit"], "transform": row["transform"],
        })
    for row in rows(research, "SELECT * FROM research_values ORDER BY iso3, year, metric_key, metric_id"):
        if not row["iso3"]:
            continue
        definition = definitions[row["metric_key"]]
        countries[row["iso3"]]["researchValues"].append({
            "metricId": row["metric_id"], "metricKey": row["metric_key"], "iso3": row["iso3"],
            "drug": row["drug"], "year": row["year"], "value": row["value"], "unit": definition["unit"],
            "version": definition["version"], "label": definition["label"], "formula": definition["formula"],
            "selectionRule": definition["selection_rule"], "interpretation": definition["interpretation"],
            "supportCount": row["support_count"], "qualityFlags": row["quality_flags"],
            "firstPublicationYear": row["first_publication_year"], "lastPublicationYear": row["last_publication_year"],
            "inputs": inputs[row["metric_id"]],
        })
        counts[row["iso3"]]["research_values"] += 1

    for row in rows(research, "SELECT * FROM research_regression_samples ORDER BY iso3, seizure_year"):
        countries[row["iso3"]]["researchSamples"].append({
            "sampleId": row["sample_id"], "metricId": row["metric_id"],
            "iso3": row["iso3"], "seizureYear": row["seizure_year"], "outcomeYear": row["outcome_year"],
            "log1pSeizureKg": row["log1p_seizure_kg"], "homicidePer100k": row["homicide_per_100k"],
        })
        counts[row["iso3"]]["research_samples"] += 1

    us_overdose = []
    cdc_source = health_sources["cdc_xkb8_kh2a"]
    for row in rows(health, "SELECT * FROM health_cdc_overdose WHERE state='US' ORDER BY end_year,end_month,indicator"):
        us_overdose.append({
            "id": f"us-overdose:{row['end_year']}:{row['end_month']}:{row['indicator']}",
            "iso3": "USA", "period": f"{row['end_year']}-{row['end_month']:02d}", "periodKind": row["period"],
            "indicator": row["indicator"], "metricKind": row["metric_kind"], "unit": row["value_unit"],
            "reportedValue": row["reported_value"], "predictedValue": row["predicted_value"],
            "percentComplete": row["percent_complete"], "status": "provisional; suppressed/unavailable" if row["suppressed_or_unavailable"] else "provisional",
            "footnote": row["footnote"], "sourceId": "health:cdc_xkb8_kh2a", "sourceUrl": cdc_source["url"],
            "publicationYear": cdc_source.get("edition_year"),
        })

    claims = []
    for row in rows(evidence, "SELECT * FROM evidence_claims ORDER BY claim_id"):
        claims.append({
            "claimId": row["claim_id"], "claimType": row["claim_type"], "drug": row["drug"],
            "geographyFrom": row["geography_from"], "geographyTo": row["geography_to"],
            "geographyScope": row["geography_scope"], "observationStartYear": row["observation_start_year"],
            "observationEndYear": row["observation_end_year"], "policyEffectiveDate": row["policy_effective_date"],
            "publicationYear": row["publication_year"], "claim": row["normalized_claim"],
            "originalExcerpt": row["original_excerpt"], "sourceLocator": row["source_locator"],
            "evidenceBasis": row["evidence_basis"], "caveat": row["caveat"],
            "sourceId": f"evidence:{row['source_id']}", "sourceUrl": evidence_sources[row["source_id"]]["url"],
        })

    for iso3, content in sorted(countries.items()):
        write_json(args.out / "countries" / f"{iso3}.json", {"iso3": iso3, **content})
    write_json(args.out / "us-overdose.json", us_overdose)
    overview = {
        "snapshot": {"releaseTag": MANIFEST["release_tag"], "databaseSha256": MANIFEST["database"]["sha256"],
                     "inputShards": {entry["filename"]: entry["sha256"] for entry in SHARDS["shards"]},
                     "exportedAt": datetime.now(timezone.utc).isoformat(), "kind": "observed-source-export"},
        "sources": sources,
        "countrySummaries": [{"iso3": iso3, "counts": dict(counts[iso3])} for iso3 in sorted(countries)],
        "marketCatalog": [
            {"iso3": key[0], "substance": key[1], "form": key[2], "year": key[3],
             "marketLevel": key[4], "metric": key[5], "count": count}
            for key, count in sorted(market_catalog.items(), key=lambda pair: tuple(str(x) for x in pair[0]))
        ],
        "evidenceClaims": claims,
        "researchModelResults": [
            {"modelKey": row["model_key"], "specification": row["specification"],
             "outcome": row["outcome"], "predictor": row["predictor"], "coefficient": row["coefficient"],
             "standardError": row["standard_error"], "pValue": row["p_value"], "ciLow": row["ci_low"],
             "ciHigh": row["ci_high"], "n": row["n"], "countries": row["countries"],
             "firstPredictorYear": row["first_predictor_year"], "lastPredictorYear": row["last_predictor_year"],
             "clusterCount": row["cluster_count"], "rSquared": row["r_squared"],
             "caveat": row["caveat"], "computedAt": row["computed_at"]}
            for row in rows(research, "SELECT * FROM research_model_results")
        ],
        "researchDefinitions": [
            {"metricKey": row["metric_key"], "version": row["version"], "label": row["label"],
             "unit": row["unit"], "formula": row["formula"], "selectionRule": row["selection_rule"],
             "interpretation": row["interpretation"]}
            for row in definitions.values()
        ],
    }
    write_json(args.out / "overview.json", overview)
    for db in dbs.values():
        db.close()
    print(json.dumps({"countries": len(countries), "observations": sum(len(x["observations"]) for x in countries.values()),
                      "researchValues": sum(len(x["researchValues"]) for x in countries.values()),
                      "researchSamples": sum(len(x["researchSamples"]) for x in countries.values()),
                      "usOverdose": len(us_overdose), "evidenceClaims": len(claims),
                      "output": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
