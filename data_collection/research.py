# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Build a small, row-traceable retrospective evidence shard from source shards."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
SCHEMA_VERSION = 1


def metric_id(formula: str, key: str) -> str:
    return hashlib.sha256(f"{formula}|{key}".encode()).hexdigest()[:24]


def source_key(table: str, *parts: object) -> str:
    return table + ":" + "|".join(str(p) for p in parts)


SCHEMA = """
CREATE TABLE research_metric_definitions (
 metric_key TEXT PRIMARY KEY, version INTEGER NOT NULL, label TEXT NOT NULL,
 unit TEXT NOT NULL, formula TEXT NOT NULL, selection_rule TEXT NOT NULL,
 interpretation TEXT NOT NULL);
CREATE TABLE research_values (
 metric_id TEXT PRIMARY KEY, metric_key TEXT NOT NULL REFERENCES research_metric_definitions(metric_key),
 iso3 TEXT, drug TEXT, year INTEGER, value REAL NOT NULL,
 numerator REAL, denominator REAL, support_count INTEGER NOT NULL CHECK(support_count > 0),
 first_publication_year INTEGER, last_publication_year INTEGER,
 quality_flags TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE research_value_inputs (
 metric_id TEXT NOT NULL REFERENCES research_values(metric_id), role TEXT NOT NULL,
 source_table TEXT NOT NULL, source_key TEXT NOT NULL, source_id TEXT,
 source_url TEXT, publication_year INTEGER, observation_year INTEGER,
 input_value REAL, input_unit TEXT, transform TEXT,
 PRIMARY KEY(metric_id,role,source_table,source_key));
CREATE TABLE research_regression_samples (
 sample_id TEXT PRIMARY KEY, metric_id TEXT NOT NULL REFERENCES research_values(metric_id),
 iso3 TEXT NOT NULL, seizure_year INTEGER NOT NULL, outcome_year INTEGER NOT NULL,
 log1p_seizure_kg REAL NOT NULL, homicide_per_100k REAL NOT NULL);
CREATE TABLE research_model_results (
 model_key TEXT PRIMARY KEY, specification TEXT NOT NULL,
 outcome TEXT NOT NULL, predictor TEXT NOT NULL,
 coefficient REAL, standard_error REAL, p_value REAL,
 ci_low REAL, ci_high REAL, n INTEGER NOT NULL, countries INTEGER NOT NULL,
 first_predictor_year INTEGER, last_predictor_year INTEGER,
 cluster_count INTEGER NOT NULL, r_squared REAL,
 caveat TEXT NOT NULL, computed_at TEXT NOT NULL);
CREATE INDEX research_values_lookup ON research_values(metric_key,iso3,drug,year);
CREATE INDEX research_inputs_source ON research_value_inputs(source_table,source_key);
CREATE INDEX research_sample_country_year ON research_regression_samples(iso3,seizure_year);
"""


DEFINITIONS = [
 ("seizure_edition_revision_pct", 1, "Published national seizure revision", "%", 
  "100 * (newest_edition_kg - oldest_edition_kg) / oldest_edition_kg",
  "Same ISO3, drug and observation year; at least two editions, oldest kg > 0; retain both edition inputs",
  "Source revision, not a real-world flow change. Country-of-seizure reporting and enforcement matter."),
 ("cocaine_seizure_next_homicide", 1, "Cocaine seizures and next-year homicide pair", "per 100,000",
  "value = World Bank general-population homicide rate in year t+1; model predictor = log(1 + UNODC cocaine seizure kg at t)",
  "Latest published annex edition for country/year/drug; matched non-null World Bank next-year homicide; observed years only",
  "Ecological, retrospective association. No route exposure or drug-specific mortality is observed."),
]


def attach(con: sqlite3.Connection, wb: Path, unodc: Path) -> None:
    con.execute("ATTACH DATABASE ? AS wb", (wb.resolve().as_uri() + "?mode=ro",))
    con.execute("ATTACH DATABASE ? AS u", (unodc.resolve().as_uri() + "?mode=ro",))


def build(output: Path, wb: Path, unodc: Path, report: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".sqlite.part")
    temp.unlink(missing_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    stats: dict = {}
    try:
        with sqlite3.connect(temp, uri=True) as con:
            con.execute("PRAGMA journal_mode=DELETE")
            con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            con.executescript(SCHEMA)
            con.executemany("INSERT INTO research_metric_definitions VALUES (?,?,?,?,?,?,?)", DEFINITIONS)
            attach(con, wb, unodc)
            sources = {r[0]: (r[1], r[2]) for r in con.execute("SELECT source_id,url,edition FROM u.unodc_sources")}
            seizure_components = defaultdict(list)
            for src, sheet, row_no, iso, year, drug, quantity, unit, kg in con.execute(
                    "SELECT source_id,sheet,row_no,iso3,year,drug,quantity,unit,kg_trace_equivalent "
                    "FROM u.unodc_seizure_observations WHERE iso3 IS NOT NULL "
                    "AND kg_trace_equivalent IS NOT NULL"):
                seizure_components[(src, iso, year, drug)].append((sheet, row_no, quantity, unit, kg))

            def seizure_inputs(role: str, iso: str, year: int, drug: str,
                               kg: float, src: str, edition: int) -> list[tuple]:
                url, pub = sources[src]
                components = seizure_components[(src, iso, year, drug)]
                if not components or abs(sum(row[4] for row in components) - kg) > 1e-5:
                    raise ValueError(f"Seizure aggregation has no matching raw-row proof: {src} {iso} {year} {drug}")
                result = [(role, "seizures_annex",
                           source_key("seizures_annex", iso, year, drug, edition),
                           src, url, pub, year, kg, "kg", "sum of linked source rows")]
                for sheet, row_no, quantity, unit, converted_kg in components:
                    result.append((f"{role}_source_row", "unodc_seizure_observations",
                                   source_key("unodc_seizure_observations", src, sheet, row_no),
                                   src, url, pub, year, quantity, unit,
                                   f"kg_trace_equivalent={converted_kg}; source workbook row; all cells in unodc_cells"))
                return result

            def value(key: str, iso3: str, drug: str, year: int, amount: float,
                      numerator: float | None, denominator: float | None,
                      inputs: list[tuple], flags: str = "") -> str:
                mid = metric_id(key, f"{iso3}|{drug}|{year}")
                pubs = [i[5] for i in inputs if i[5] is not None]
                con.execute("INSERT INTO research_values VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (mid, key, iso3, drug, year, amount, numerator, denominator,
                             len(inputs), min(pubs) if pubs else None, max(pubs) if pubs else None,
                             flags, now))
                con.executemany("INSERT INTO research_value_inputs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                [(mid, *i) for i in inputs])
                return mid

            # The published national annex has deliberate overlapping editions.
            groups = defaultdict(list)
            for iso, year, drug, kg, source, edition in con.execute(
                    "SELECT iso3,year,drug,kg,source,edition FROM u.seizures_annex "
                    "WHERE iso3 IS NOT NULL AND year IS NOT NULL AND kg IS NOT NULL "
                    "ORDER BY iso3,year,drug,edition"):
                groups[(iso, year, drug)].append((kg, source, edition))
            revision_values = []
            latest_cocaine = {}
            for (iso, year, drug), editions in groups.items():
                oldest, newest = editions[0], editions[-1]
                if drug == "cocaine" and newest[0] >= 0:
                    latest_cocaine[(iso, year)] = newest
                if len(editions) < 2 or oldest[0] <= 0 or newest[0] < 0:
                    continue
                inputs = []
                for role, (kg, src, edition) in (("oldest", oldest), ("newest", newest)):
                    inputs.extend(seizure_inputs(role, iso, year, drug, kg, src, edition))
                pct = 100.0 * (newest[0] - oldest[0]) / oldest[0]
                value("seizure_edition_revision_pct", iso, drug, year, pct,
                      newest[0] - oldest[0], oldest[0], inputs)
                revision_values.append(pct)
            stats["revision_rows"] = len(revision_values)
            stats["revision_nonzero_rows"] = sum(abs(x) > 1e-9 for x in revision_values)
            stats["revision_median_abs_pct"] = statistics.median(map(abs, revision_values)) if revision_values else None
            changed_revisions = [abs(x) for x in revision_values if abs(x) > 1e-9]
            stats["revision_changed_median_abs_pct"] = statistics.median(changed_revisions) if changed_revisions else None

            # Feasibility audit only: the coarse price table can mix distinct forms
            # within one drug/year/source. Publish no ratio from these candidates.
            pairs = defaultdict(dict)
            for iso, drug, level, year, price, source, basis, estimated in con.execute(
                    "SELECT iso3,drug,level,year,usd_g,source,basis,upstream_estimate "
                    "FROM u.prices WHERE usd_g > 0 AND level IN ('retail','wholesale')"):
                pairs[(iso, drug, year, source)][level] = (price, basis, estimated)
            stats["coarse_price_pair_candidates_rejected"] = sum(
                {"retail", "wholesale"}.issubset(levels) for levels in pairs.values())
            stats["price_candidate_keys"] = len(pairs)

            homicide = {(r[0], r[1]): r for r in con.execute(
                "SELECT iso3,year,code,source_id,value,request_id,lastupdated "
                "FROM wb.wb_indicators WHERE code='VC.IHR.PSRC.P5' AND value IS NOT NULL")}
            requests = {r[0]: r[1] for r in con.execute("SELECT request_id,url FROM wb.wb_downloads")}
            samples = []
            for (iso, year), (kg, src, pub) in sorted(latest_cocaine.items()):
                h = homicide.get((iso, year + 1))
                if not h or kg < 0 or not math.isfinite(kg) or not math.isfinite(h[4]):
                    continue
                url, edition = sources[src]
                inputs = seizure_inputs("predictor", iso, year, "cocaine", kg, src, pub)
                inputs += [
                    ("outcome", "wb_indicators", source_key("wb_indicators", iso, year+1, h[2], h[3]),
                     h[5], requests[h[5]], None,
                     year+1, h[4], "per 100,000",
                     f"next-year general-population homicide rate; World Bank lastupdated={h[6]}; retrieved in 2026"),
                ]
                mid = value("cocaine_seizure_next_homicide", iso, "cocaine", year, h[4],
                            h[4], None, inputs, "retrospective_latest_edition")
                sid = metric_id("regression-sample-v1", f"{iso}|{year}")
                con.execute("INSERT INTO research_regression_samples VALUES (?,?,?,?,?,?,?)",
                            (sid, mid, iso, year, year+1, math.log1p(kg), h[4]))
                samples.append((iso, year, math.log1p(kg), h[4]))
            stats["regression_rows"] = len(samples)
            stats["regression_countries"] = len({r[0] for r in samples})
            stats["regression_first_year"] = min((r[1] for r in samples), default=None)
            stats["regression_last_year"] = max((r[1] for r in samples), default=None)
            con.commit()
            con.execute("DETACH DATABASE wb")
            con.execute("DETACH DATABASE u")
        temp.replace(output)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(stats))
        return stats
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def render_report(stats: dict) -> str:
    lines = ["<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->",
             "# Retrospective TRACE evidence findings", "",
             "These are observed-source descriptions, not prospective forecasts or causal estimates. "
             "Every derived row is clickable through `research_values` → `research_value_inputs` "
             "to the source table key, URL, source publication year, observation year, "
             "aggregate input and original source-row values. "
             "Definitions and formula versions are in `research_metric_definitions`.", "",
             "## Preselected questions", "",
             f"- UNODC annex edition revisions: {stats['revision_rows']:,} matched country/drug/year rows "
             f"with at least two editions and positive oldest kilograms; "
             f"{stats['revision_nonzero_rows']:,} change and median absolute published revision is "
             f"{stats['revision_median_abs_pct']:.3g}% across all pairs "
             f"({stats['revision_changed_median_abs_pct']:.3g}% among changed pairs). "
             "This is a revision to reports, not inferred flow.",
             f"- Price-comparison feasibility: {stats['coarse_price_pair_candidates_rejected']:,} "
             f"of {stats['price_candidate_keys']:,} country/drug/year/source keys have positive "
             "prices at both levels, but the coarse drug labels can combine different product forms. "
             "The candidate ratios are rejected and absent from research_values. "
             "Use the 449 exact-product ratios in `market_derived`, which also links to raw workbook cells."]
    lines += [f"- Cocaine seizure / next-year general-population homicide model sample: "
              f"{stats['regression_rows']:,} country-years across {stats['regression_countries']} countries, "
              f"seizure years {stats['regression_first_year']}–{stats['regression_last_year']}. "
              "Run `research_model.py` for the fixed-effects coefficient and uncertainty.", "",
              "## Interpretation and data limits", "",
              "The seizure measure is country of seizure, not a route or estimated trade volume. "
              "A higher seizure total can reflect enforcement or reporting changes. The homicide outcome "
              "covers the general population and is not attributed to drugs. Both sources were retrieved "
              "in 2026, and the latest UNODC edition may revise earlier years. Thus the association "
              "is retrospective, ecological and noncausal. It cannot validate a live early-warning model.", "",
              "UNODC price category names may pool forms with different purity. Historical nominal USD/g "
              "can move with exchange rates and inflation. Even the stricter market-shard ratio "
              "does not resolve all sampling differences. Missing rows are not zero observations.", "",
              "## Reproduce", "",
              "```sh", "backend/.venv/bin/python data_collection/research.py",
              "backend/.venv/bin/python data_collection/research_model.py", "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=WORK / "research.sqlite")
    parser.add_argument("--wb", type=Path, default=WORK / "world_bank.sqlite")
    parser.add_argument("--unodc", type=Path, default=WORK / "unodc.sqlite")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/research_findings.md")
    args = parser.parse_args()
    print(json.dumps(build(**vars(args)), indent=2))
