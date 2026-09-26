# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T3: download and load every external source into DuckDB; record status in ingest_manifest.json.

A source that cannot be downloaded never stops the run: its status becomes `unavailable` and the
downstream steps use documented fallbacks (see docs/BLOCKERS.md).
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .. import config, db
from . import cepii, hri, ocindex, unodc_annex, unodc_ids
from .names import CountryResolver

log = logging.getLogger(__name__)
SEED_CORRIDORS = config.SEED / "corridors.csv"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _try(name: str, status: dict, fn, *a, **kw):
    try:
        out = fn(*a, **kw)
        return out
    except Exception as exc:  # a blocker never stops the run
        log.error("%s failed: %s", name, exc)
        log.debug(traceback.format_exc())
        status[name] = {"status": "unavailable", "error": str(exc)[:300], "retrieved_at": None}
        return None


def combine_seizures(annex: pd.DataFrame, ids: pd.DataFrame | None) -> pd.DataFrame:
    """Country-year-drug seizure kg, 2011-2024.

    2015-2024: WDR annex 7.1 (official ARQ + government totals).
    2011-2014: calibrated backcast. The first annex value is scaled by the public IDS growth index
    (IDS kg in year y / mean IDS kg over the first three annex years), clipped to [1/3, 3]; where IDS
    has no data for the country and drug, the first annex value is carried back. Basis is flagged per row.
    """
    a = annex[(annex["year"] >= config.ROUTE_YEAR_MIN) & (annex["year"] <= 2024)].copy()
    a["basis"] = "annex"
    first_year = int(a["year"].min())
    pre = list(range(config.ROUTE_YEAR_MIN, first_year))
    first = a.sort_values("year").groupby(["iso3", "drug"], as_index=False).first()[["iso3", "drug", "kg"]]
    idx = pd.Series(dtype=float)
    if ids is not None and len(ids):
        base = ids[ids["year"].between(first_year, first_year + 2)].groupby(["iso3", "drug"])["kg"].mean()
        early = ids[ids["year"].isin(pre)].set_index(["iso3", "drug", "year"])["kg"]
        idx = (early / base.reindex(early.index.droplevel("year")).values).replace([np.inf, -np.inf], np.nan)
        idx = idx.dropna().clip(1 / 3, 3)
    rows = []
    for r in first.itertuples():
        for y in pre:
            g = idx.get((r.iso3, r.drug, y))
            rows.append({"iso3": r.iso3, "year": y, "drug": r.drug, "kg": r.kg * (g if g is not None else 1.0),
                         "basis": "ids_calibrated" if g is not None else "carried_back"})
    out = pd.concat([a[["iso3", "year", "drug", "kg", "basis"]], pd.DataFrame(rows)], ignore_index=True)
    return out.sort_values(["iso3", "drug", "year"]).reset_index(drop=True)


def run(refresh: bool = False) -> dict:
    config.ensure_dirs()
    countries = db.read_table("countries")
    resolve = CountryResolver(countries)
    status: dict[str, dict] = {}
    now = _now()

    # --- UNODC WDR annex
    dl = _try("unodc_wdr_annex", status, unodc_annex.download, refresh)
    annex_seiz = None
    if dl is not None:
        status["unodc_wdr_annex"] = {"status": "cached" if all(v == "cached" for v in dl.values()) else "live",
                                     "retrieved_at": now, "files": list(unodc_annex.FILES.values()),
                                     "url": "https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html"}
        annex_seiz = _try("unodc_wdr_annex", status, unodc_annex.seizures)
        cult = _try("unodc_wdr_annex", status, unodc_annex.cultivation, resolve)
        pr = _try("unodc_wdr_annex", status, unodc_annex.prices, resolve)
        reg = _try("unodc_wdr_annex", status, unodc_annex.cannabis_regulation)
        for name, df in [("cultivation", cult), ("prices", pr), ("cannabis_regulation", reg)]:
            if df is not None:
                db.write_table(name, df)
                status["unodc_wdr_annex"][f"{name}_rows"] = len(df)
        if annex_seiz is not None:
            db.write_table("seizures_annex", annex_seiz)
            status["unodc_wdr_annex"]["seizures_rows"] = len(annex_seiz)

    # --- UNODC IDS (public release: seizure country only)
    ids_agg = None
    dl = _try("unodc_ids", status, unodc_ids.download, refresh)
    if dl is not None:
        loaded = _try("unodc_ids", status, unodc_ids.load)
        if loaded is not None:
            raw, route_cols = loaded
            db.write_table("seizures_raw", raw)
            ids_agg = unodc_ids.aggregate(raw)
            db.write_table("seizures_ids", ids_agg)
            hops = unodc_ids.route_hops(raw, resolve)
            db.write_table("ids_hops", hops)
            status["unodc_ids"] = {
                "status": "cached" if all(v == "cached" for v in dl.values()) else "live", "retrieved_at": now,
                "url": "https://dmp.unodc.org/downloadIDS", "cases": len(raw), "route_columns": route_cols,
                "hops": len(hops),
                "note": ("Public IDS release has no departure/transit/destination fields; used for node volumes "
                         "and 2011-2014 backcast. Edges come from documented corridors (see BLOCKERS.md).")
                if not route_cols else "Route fields present; hops built from IDS."}

    if annex_seiz is not None:
        seiz = combine_seizures(annex_seiz, ids_agg)
        db.write_table("seizures_country", seiz)
        log.info("seizures_country: %d rows; basis counts %s", len(seiz), seiz["basis"].value_counts().to_dict())

    # --- GI-TOC OC Index
    if _try("gitoc_ocindex", status, ocindex.download, refresh) is not None:
        oc = _try("gitoc_ocindex", status, ocindex.load, resolve)
        if oc is not None:
            db.write_table("oc_index", oc)
            status["gitoc_ocindex"] = {"status": "live", "retrieved_at": now, "url": ocindex.URL, "rows": len(oc),
                                       "editions": sorted(oc["edition"].unique().tolist())}

    # --- HRI
    if _try("hri_gshr", status, hri.download, refresh) is not None:
        h = _try("hri_gshr", status, hri.load, resolve)
        if h is not None:
            db.write_table("harm_reduction", h)
            status["hri_gshr"] = {"status": "live", "retrieved_at": now, "url": hri.URL, "rows": len(h),
                                  "method": "pdfplumber text extraction of Table 1"}

    # --- CEPII
    if _try("cepii_geodist", status, cepii.download, refresh) is not None:
        d = _try("cepii_geodist", status, cepii.load, countries)
        if d is not None:
            db.write_table("distances", d)
            status["cepii_geodist"] = {"status": "live", "retrieved_at": now, "url": cepii.URL, "pairs": len(d),
                                       "imputed_pairs": int(d["dist_imputed"].sum())}
    if not db.table_exists("distances"):  # fallback: great-circle from World Bank capitals, no contiguity
        ll = countries.dropna(subset=["lat", "lon"])
        m = ll.merge(ll, how="cross", suffixes=("_o", "_d"))
        m = m[m["iso3_o"] != m["iso3_d"]]
        dist = cepii.haversine(m["lat_o"].values, m["lon_o"].values, m["lat_d"].values, m["lon_d"].values)
        db.write_table("distances", pd.DataFrame({"from_iso3": m["iso3_o"].values, "to_iso3": m["iso3_d"].values,
                                                  "dist": dist, "contig": 0, "comlang_off": 0, "colony": 0,
                                                  "dist_imputed": True}))
        status.setdefault("cepii_geodist", {})["status"] = "fallback"

    # --- corridor seed
    seed = pd.read_csv(SEED_CORRIDORS, comment="#")
    seed = seed[seed["from"].isin(countries["iso3"]) & seed["to"].isin(countries["iso3"])]
    db.write_table("corridors_seed", seed.rename(columns={"from": "from_iso3", "to": "to_iso3"}))
    status["corridors_seed"] = {"status": "live", "rows": len(seed), "path": "backend/trace_backend/seed/corridors.csv"}

    manifest = {"generated_at": now, "sources": status, "unmatched_country_names": sorted(resolve.unmatched)}
    (config.PROCESSED / "ingest_manifest.json").write_text(json.dumps(manifest, indent=2, default=str),
                                                           encoding="utf-8")
    log.info("ingest done: %s", {k: v.get("status") for k, v in status.items()})
    return manifest


__all__ = ["run", "combine_seizures", "np"]
