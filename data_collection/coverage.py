# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Audit observed historical support without requiring a balanced source panel."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent
SPINE_START, SPINE_END = 1990, 2024
CORE = ("gdp", "population", "gdp_pc_ppp", "trade_gdp", "homicide_rate", "hiv_incidence")


def bounds(con: sqlite3.Connection, table: str) -> tuple[int | None, int | None, int]:
    return con.execute(f'SELECT min(year), max(year), count(*) FROM "{table}"').fetchone()


def yearly(con: sqlite3.Connection, table: str) -> dict[int, int]:
    return dict(con.execute(f'SELECT year, count(*) FROM "{table}" GROUP BY year'))


def write_report(db: Path, output: Path) -> None:
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"countries", "wb_indicators", "wb_indicator_meta", "wb_coverage",
                    "prices", "seizures_annex", "seizures_ids", "cultivation",
                    "oc_index", "harm_reduction", "health_prevalence", "health_pwid",
                    "health_treatment", "health_treatment_coverage", "health_cdc_overdose",
                    "market_observations", "market_derived", "research_values", "evidence_claims"}
        if missing := required - tables:
            raise ValueError(f"Coverage report requires merged database; missing {sorted(missing)}")
        countries = con.execute("SELECT count(*) FROM countries").fetchone()[0]
        variables = con.execute("SELECT count(*) FROM wb_indicator_meta").fetchone()[0]
        total, observed = con.execute("SELECT count(*),count(value) FROM wb_indicators").fetchone()
        wb_first, wb_last = con.execute(
            "SELECT min(year),max(year) FROM wb_indicators WHERE value IS NOT NULL").fetchone()
        features = con.execute("""SELECT m.feature,c.first_non_null_year,c.last_non_null_year,
            c.countries_with_data,c.non_null_rows FROM wb_coverage c JOIN wb_indicator_meta m
            USING(code,source_id) ORDER BY c.first_non_null_year,m.feature""").fetchall()
        annual = {r[0]: (r[1], r[2]) for r in con.execute("""
            SELECT year,count(DISTINCT CASE WHEN value IS NOT NULL THEN code || ':' || source_id END),
                count(value) FROM wb_indicators GROUP BY year""")}
        core_counts = dict(con.execute("""SELECT m.feature,count(*) FROM wb_indicators w
            JOIN wb_indicator_meta m USING(code,source_id)
            WHERE w.value IS NOT NULL AND w.year BETWEEN ? AND ?
            AND m.feature IN (?,?,?,?,?,?) GROUP BY m.feature""",
            (SPINE_START, SPINE_END, *CORE)))
        market_years = {r[0]: (r[1], r[2]) for r in con.execute("""
            WITH available AS (
                SELECT w.iso3,w.year,
                    MAX(CASE WHEN m.feature='gdp' THEN 1 ELSE 0 END) AS gdp,
                    MAX(CASE WHEN m.feature='population' THEN 1 ELSE 0 END) AS pop,
                    MAX(CASE WHEN m.feature IN ('homicide_rate','hiv_incidence') THEN 1 ELSE 0 END) AS harm
                FROM wb_indicators w JOIN wb_indicator_meta m USING(code,source_id)
                WHERE w.value IS NOT NULL AND w.year BETWEEN ? AND ?
                AND m.feature IN ('gdp','population','homicide_rate','hiv_incidence')
                GROUP BY w.iso3,w.year
            ) SELECT year,SUM(gdp*pop),SUM(gdp*pop*harm) FROM available GROUP BY year""",
            (SPINE_START, SPINE_END))}
        source_windows = [
            ("World Bank non-null values", (wb_first, wb_last, observed)),
            ("UNODC normalized prices", bounds(con, "prices")),
            ("UNODC national seizure totals", bounds(con, "seizures_annex")),
            ("UNODC individual seizure aggregates", bounds(con, "seizures_ids")),
            ("UNODC cultivation", bounds(con, "cultivation")),
            ("OC Index editions", bounds(con, "oc_index")),
            ("HRI service editions", bounds(con, "harm_reduction")),
            ("UNODC national drug-use prevalence", bounds(con, "health_prevalence")),
            ("UNODC PWID/infection observations", bounds(con, "health_pwid")),
            ("UNODC treatment contacts", bounds(con, "health_treatment")),
            ("UN SDG 3.5.1 treatment coverage", bounds(con, "health_treatment_coverage")),
            ("CDC 12-month-ending overdose observations", con.execute(
                "SELECT min(end_year),max(end_year),count(*) FROM health_cdc_overdose").fetchone()),
            ("UNODC source price/purity observations", bounds(con, "market_observations")),
            ("Exact-product market derived values", bounds(con, "market_derived")),
            ("Research values with source-row links", bounds(con, "research_values")),
        ]
        price_years = {r[0]: (r[1], r[2], r[3]) for r in con.execute("""
            SELECT year,count(*),count(DISTINCT iso3),sum(upstream_estimate)
            FROM prices GROUP BY year""")}
        annex_years = yearly(con, "seizures_annex")
        ids_years = yearly(con, "seizures_ids")
        modeled_coverage, country_coverage = con.execute("""
            SELECT sum(nature_code='M'),sum(nature_code='C') FROM health_treatment_coverage""").fetchone()
        cdc_suppressed = con.execute("SELECT sum(suppressed_or_unavailable) FROM health_cdc_overdose").fetchone()[0]
        evidence_claims = con.execute("SELECT count(*) FROM evidence_claims").fetchone()[0]

    lines = [
        "<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->",
        "# Historical coverage and analysis windows", "",
        f"Generated {datetime.now(timezone.utc).isoformat()} from the verified merged SQLite archive.", "",
        "## Decision", "",
        f"**Long-history spine: {SPINE_START}–{SPINE_END} ({SPINE_END-SPINE_START+1} calendar years).** "
        "World Bank market-size and public-health series have observed values throughout this interval. "
        "UNODC published national drug-price series also span it. In 1990 those price rows "
        "cover 17 named Western/Central European countries plus the United States, and some are "
        "source-provided estimates, flagged in the table below. Regional averages are not copied "
        "into country records. "
        "This supports source-specific longitudinal analysis; it does not imply every country, drug "
        "or indicator is measured every year. "
        "Use available country-years and report each result's denominator.", "",
        f"**Archive: all original years.** World Bank non-null values span {wb_first}–{wb_last} "
        f"across {variables} indicators and {countries} current economies. Its {total:,} country "
        f"observations include {total-observed:,} explicit nulls. No source is truncated to the "
        "first year of a newer supplement.", "",
        "**Later supplements keep their actual dates.** National seizure annexes, individual seizure "
        "cases, cultivation, OC Index and HRI services enter only where their source supports them. "
        "An analysis using reported seizures has a shorter documented window than the price "
        "and World Bank analyses. Seizure country alone does not reveal a trade route. "
        "Edition-based context never becomes a historical backtest predictor "
        "by carrying its newer values backward.", "",
        "There is no requirement that all variables overlap. Missing values stay null; the collection "
        "does not impute, interpolate or backcast. A later model must document feature availability, "
        "publication lag and its training-only missing-data policy. Retrospective source releases "
        "alone are not a point-in-time backtest archive.", "",
        "## Source windows in the collected database", "",
        "| Source table | First observed year | Latest observed year | Records |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, (start, end, count) in source_windows:
        lines.append(f"| {name} | {start or '—'} | {end or '—'} | {count:,} |")
    lines += ["", "The additional source windows represent different populations, units and "
              "publication vintages. UN SDG 3.5.1 treatment coverage has "
              f"{modeled_coverage:,} officially modeled and {country_coverage:,} country-data records; "
              f"the CDC overdose table retains {cdc_suppressed:,} suppressed/unavailable NULL rows. "
              "CDC rows are rolling 12-month periods, not monthly death increments, and drug "
              "categories overlap. Market values are source-price observations or exact-product "
              "descriptive derivations, not trade flows. "
              f"The {evidence_claims} cited evidence claims are multiyear statements or policy dates, "
              "not annual measured routes.", ""]
    lines += ["", "## World Bank long-history indicators", "",
              f"Non-null country-years within {SPINE_START}–{SPINE_END}; individual gaps remain in SQLite.", "",
              "| Indicator | Non-null country-years |", "| --- | ---: |"]
    for feature in CORE:
        lines.append(f"| {feature} | {core_counts.get(feature, 0):,} |")
    lines += ["", "## Year-by-year spine support", "",
              "GDP + population counts economies with both market-size observations. The proxy column "
              "also requires either general-population homicide or HIV incidence; these are contextual "
              "harm measures, not drug-specific outcomes. Other columns count observed source "
              "records, not matched country-years. National seizure records are edition-specific and "
              "can overlap; never sum them without choosing an edition. Source estimate counts "
              "identify values the UNODC source itself flags as estimates. Zero means no reported "
              "observation, not zero activity.", "",
              "| Year | WB variables | WB values | GDP + population economies | With homicide or HIV proxy | Price records | Price economies | Source price estimates | National seizure edition records | IDS country/drug aggregates |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for year in range(SPINE_START, SPINE_END + 1):
        wb_vars, wb_values = annual.get(year, (0, 0))
        market, harm = market_years.get(year, (0, 0))
        price_records, price_countries, price_estimates = price_years.get(year, (0, 0, 0))
        lines.append(f"| {year} | {wb_vars} | {wb_values:,} | {market or 0} | {harm or 0} | "
                     f"{price_records:,} | {price_countries} | {price_estimates or 0} | "
                     f"{annex_years.get(year, 0):,} | "
                     f"{ids_years.get(year, 0):,} |")
    lines += ["", "## All World Bank variables", "",
              "| Variable | First observed | Latest observed | Economies ever observed | Non-null values |",
              "| --- | ---: | ---: | ---: | ---: |"]
    lines.extend("| " + " | ".join(map(str, row)) + " |" for row in features)
    lines += ["", "## Provenance", "",
              "- [World Bank source IDs, API provenance and licenses](world_bank.md)",
              "- [UNODC files, units and collection limits](unodc.md)",
              "- [OC Index, HRI editions and CEPII context](context_sources.md)",
              "- [Drug-specific health and treatment sources](health.md)",
              "- [Exact-product prices, purity and retrieval limits](markets.md)",
              "- [Published corridor context and policy milestones](evidence.md)",
              "- [Retrospective research and source-row evidence](research_findings.md)",
              "- [Verified snapshot manifest and table counts](../snapshot.json)", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "work/trace.sqlite")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/coverage.md")
    args = parser.parse_args()
    write_report(args.db, args.output)
