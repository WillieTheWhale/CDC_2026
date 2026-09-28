# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""`trace prepare`: derive model inputs from the canonical SQLite archive (data_collection/work/trace.sqlite).

The archive is observational and read-only. This stage writes derived, model-specific tables to the derived DB:

- wb_panel             wide country-year World Bank panel, bounded forward-fill with *_imputed flags
- seizures_country     national seizure kg (heroin-equivalent for opiates) per iso3-year-drug, 2006-2024:
                       for each country-year-drug the LATEST annex edition that reports that year wins
                       (later editions revise earlier ones; no edition is carried into years it does not cover)
- model_distances      all World Bank country pairs: CEPII GeoDist where available, great-circle distance
                       between World Bank capitals plus a documented contiguity list for newer states
- model_prices         one price per iso3-drug-level-year: current annex > 2015 > 2012 editions > long series
- model_protection     HRI services per country and edition year (no backfill before a country's first edition)
- model_cannabis_regulation  first effective year per country (national or subnational)
- corridors_seed       documented corridors (backend/trace_backend/seed/corridors.csv)
Also writes data/processed/wb_manifest.json and ingest_manifest.json (provenance for /api/meta).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .. import config, db
from ..wb.indicators import INDICATORS
from ..wb.ingest import build_panel
from .cepii import EXTRA_CONTIG, haversine

log = logging.getLogger(__name__)
PRICE_PRIORITY = [("prices", 4), ("hist2015", 3), ("hist2012", 2), ("price_ts", 1)]
PROT_FIELDS = ["nsp", "oat", "naloxone", "dcr", "prison_programs", "policy"]


def _archive_meta() -> dict:
    snap = json.loads((config.REPO / "data_collection" / "snapshot.json").read_text(encoding="utf-8"))
    return {"release_tag": snap["release_tag"], "url": snap["url"], "sha256": snap["database"]["sha256"],
            "created_at": snap["created_at"]}


def seizures_country() -> pd.DataFrame:
    a = db.read_table("seizures_annex").dropna(subset=["kg", "year", "drug", "iso3"])
    a = a[(a["year"] >= config.ROUTE_YEAR_MIN) & (a["year"] <= 2024)]
    a = a.sort_values("edition").groupby(["iso3", "year", "drug"], as_index=False).last()
    a["basis"] = "annex_" + a["edition"].astype(int).astype(str)
    return a[["iso3", "year", "drug", "kg", "basis", "edition", "source"]]


def model_distances(countries: pd.DataFrame) -> pd.DataFrame:
    d = db.read_table("distances")
    d = d[d["from_iso3"].isin(countries["iso3"]) & d["to_iso3"].isin(countries["iso3"])]
    d = d.groupby(["from_iso3", "to_iso3"], as_index=False)[["dist", "contig", "comlang_off", "colony"]].first()
    codes = sorted(countries["iso3"])
    full = pd.MultiIndex.from_product([codes, codes], names=["from_iso3", "to_iso3"]).to_frame(index=False)
    full = full[full["from_iso3"] != full["to_iso3"]].merge(d, on=["from_iso3", "to_iso3"], how="left")
    ll = countries.set_index("iso3")[["lat", "lon"]]
    miss = full["dist"].isna()
    a, b = ll.reindex(full.loc[miss, "from_iso3"]).values, ll.reindex(full.loc[miss, "to_iso3"]).values
    full.loc[miss, "dist"] = haversine(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    full["dist_imputed"] = miss
    full[["contig", "comlang_off", "colony"]] = full[["contig", "comlang_off", "colony"]].fillna(0).astype(int)
    extra = {(x, y) for x, y in EXTRA_CONTIG} | {(y, x) for x, y in EXTRA_CONTIG}
    full.loc[full[["from_iso3", "to_iso3"]].apply(tuple, axis=1).isin(extra), "contig"] = 1
    return full.dropna(subset=["dist"]).reset_index(drop=True)


def model_prices() -> pd.DataFrame:
    p = db.read_table("prices").dropna(subset=["usd_g"])
    p["priority"] = [next((v for k, v in PRICE_PRIORITY if str(s).startswith(k)), 0) for s in p["source"]]
    p = p.sort_values("priority").groupby(["iso3", "drug", "level", "year"], as_index=False).last()
    p = p[(p["usd_g"] > 0) & (p["usd_g"] < 5000)]
    return p[["iso3", "drug", "level", "year", "usd_g", "purity_pct", "source", "basis"]]


def model_protection() -> pd.DataFrame:
    h = db.read_table("harm_reduction")
    h = h[h["mapping_status"].isin(["exact_or_explicit_alias", "explicit_typo_correction"])].dropna(subset=["iso3"])
    h = h.sort_values("year").groupby(["iso3", "year"], as_index=False).last()
    return h[["iso3", "country_name", "year", *PROT_FIELDS, "naloxone_peer", "safer_smoking", "stimulant_rx",
              "nsp_prison", "oat_prison", "source_id", "pdf_page"]]


def model_cannabis_regulation() -> pd.DataFrame:
    r = db.read_table("cannabis_regulation").dropna(subset=["iso3", "year_effective"])
    r["national"] = r["scope"].eq("national")
    g = r.groupby("iso3").agg(year_effective=("year_effective", "min"), national=("national", "any"),
                              jurisdictions=("jurisdiction", "nunique")).reset_index()
    g["scope"] = np.where(g["national"], "national", "subnational")
    g["source"] = "unodc_wdr_annex_11.1"
    return g[["iso3", "year_effective", "scope", "jurisdictions", "source"]]


def run(refresh: bool = False) -> dict:
    if not db.archive_available():
        raise db.ArchiveMissing(f"SQLite archive missing at {config.ARCHIVE_PATH}. "
                                "Run `python3 data_collection/manage.py download` first.")
    config.ensure_dirs()
    now = datetime.now(UTC).isoformat(timespec="seconds")
    arch = _archive_meta()
    countries = db.read_table("countries")
    wb = db.read_table("wb_indicators", "year >= ?", (config.YEAR_MIN,))
    out = {"wb_panel": build_panel(wb, countries), "seizures_country": seizures_country(),
           "model_distances": model_distances(countries), "model_prices": model_prices(),
           "model_protection": model_protection(), "model_cannabis_regulation": model_cannabis_regulation(),
           "corridors_seed": pd.read_csv(config.SEED / "corridors.csv", comment="#").rename(
               columns={"from": "from_iso3", "to": "to_iso3"})}
    seed = out["corridors_seed"]
    out["corridors_seed"] = seed[seed["from_iso3"].isin(countries["iso3"]) & seed["to_iso3"].isin(countries["iso3"])]
    for name, df in out.items():
        db.write_table(name, df)
        log.info("%-26s %7d rows", name, len(df))

    cov = db.read_table("wb_coverage")
    meta = db.read_table("wb_indicator_meta")
    dl = db.query("SELECT MIN(retrieved_at) AS r FROM archive.wb_downloads")["r"].iloc[0]
    wb_manifest = {
        "generated_at": now, "archive": arch, "api_base": "https://api.worldbank.org/v2",
        "retrieval": "programmatic; format=json; explicit source ids; all pages; nulls kept (data_collection/world_bank.py)",
        "indicators": [{"code": r.code, "source_id": int(r.source_id), "rows": int(r.rows),
                        "non_null_rows": int(r.non_null_rows), "economies_with_data": int(r.countries_with_data),
                        "first_year": r.first_non_null_year, "latest_year": r.last_non_null_year,
                        "retrieved_at": dl, "from_cache": True,
                        "lastupdated": None} for r in cov.itertuples()],
        "countries": {"rows": len(countries)}, "indicator_meta_rows": len(meta),
    }
    (config.PROCESSED / "wb_manifest.json").write_text(json.dumps(wb_manifest, indent=2, default=str), "utf-8")
    src = db.read_table("unodc_sources")
    ctx = db.read_table("context_sources")
    ids = db.read_table("seizures_ids")
    sz = out["seizures_country"]
    sources = {
        "unodc_wdr_annex": {"status": "cached", "retrieved_at": src["retrieved_at"].max(),
                            "editions": sorted(int(e) for e in src["edition"].dropna().unique()),
                            "seizure_years": [int(sz["year"].min()), int(sz["year"].max())],
                            "note": "WDR annex editions 2012, 2015, 2020, 2026; latest edition per country-year"},
        "unodc_ids": {"status": "cached", "retrieved_at": src["retrieved_at"].max(),
                      "cases": int(ids["cases"].sum()),
                      "note": ("Public IDS release has no departure/transit/destination fields; used for case "
                               "counts. Edges come from documented corridors (see BLOCKERS.md).")},
        "gitoc_ocindex": {"status": "cached", "retrieved_at": ctx["retrieved_at"].max(), "editions": [2021, 2023, 2025]},
        "hri_gshr": {"status": "cached", "retrieved_at": ctx["retrieved_at"].max(),
                     "editions": sorted(int(y) for y in out["model_protection"]["year"].unique())},
        "cepii_geodist": {"status": "cached", "retrieved_at": ctx["retrieved_at"].max(),
                          "imputed_pairs": int(out["model_distances"]["dist_imputed"].sum())},
        "corridors_seed": {"status": "live", "rows": len(out["corridors_seed"])},
    }
    (config.PROCESSED / "ingest_manifest.json").write_text(
        json.dumps({"generated_at": now, "archive": arch, "sources": sources}, indent=2, default=str), "utf-8")
    log.info("prepared model inputs from archive %s", arch["release_tag"])
    return {k: len(v) for k, v in out.items()}


__all__ = ["run", "INDICATORS"]
