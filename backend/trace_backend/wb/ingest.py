# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""LEGACY (pre-SQLite): not used by `trace pipeline`; the canonical data is the SQLite archive built by data_collection/.
T2: pull every World Bank indicator in docs/DATA_SOURCES.md into DuckDB with provenance.

Tables written
- countries          iso3, iso2, name, region, income_group, capital, lat, lon (aggregates dropped)
- wb_indicators      long: iso3, year, code, source_id, value (nulls kept), obs_status, lastupdated, retrieved_at
- wb_indicator_meta  code, source_id, feature, role, name, unit, source_org, source_note
- wb_panel           wide country-year panel of features, forward-filled with *_imputed flags (model input)
Also writes data/processed/wb_manifest.json.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pandas as pd

from .. import config, db
from .client import WorldBankClient
from .indicators import INDICATORS

log = logging.getLogger(__name__)
DATE_RANGE = f"{config.YEAR_MIN}:{datetime.now(UTC).year}"
# forward-fill horizon (years) for sparse series; LPI is surveyed every few years
FFILL_LIMIT = {"lpi_overall": 8, "lpi_customs": 8, "poverty": 5, "gini": 5, "account_ownership": 4,
               "youth_neet": 3}
DEFAULT_FFILL = 2


def _countries(client: WorldBankClient) -> tuple[pd.DataFrame, dict]:
    res = client.countries()
    rows = []
    for c in res.records:
        rows.append({
            "iso3": c["id"], "iso2": c["iso2Code"], "name": c["name"],
            "region": (c["region"]["value"] or "").strip(),
            "region_id": c["region"]["id"],
            "income_group": (c["incomeLevel"]["value"] or "").strip(),
            "capital": c["capitalCity"] or None,
            "lat": float(c["latitude"]) if c["latitude"] else None,
            "lon": float(c["longitude"]) if c["longitude"] else None,
            "is_aggregate": (c["region"]["value"] or "").strip() == "Aggregates",
        })
    df = pd.DataFrame(rows)
    n_agg = int(df["is_aggregate"].sum())
    countries = df[~df["is_aggregate"]].drop(columns="is_aggregate").sort_values("iso3").reset_index(drop=True)
    manifest = {"endpoint": "/country", "api_url": res.url, "retrieved_at": res.retrieved_at,
                "rows": len(countries), "aggregates_dropped": n_agg, "from_cache": res.from_cache}
    return countries, manifest


def _indicator_rows(client: WorldBankClient, ind, country_codes: set[str]) -> tuple[pd.DataFrame, dict]:
    res = client.indicator(ind.code, ind.source_id, DATE_RANGE)
    rows = []
    for r in res.records:
        iso3 = r.get("countryiso3code") or ""
        if iso3 not in country_codes:
            continue  # aggregate or unmapped entity
        try:
            year = int(str(r["date"])[:4])
        except (TypeError, ValueError):
            continue
        v = r.get("value")
        rows.append({"iso3": iso3, "year": year, "code": ind.code, "source_id": ind.source_id,
                     "value": float(v) if v is not None else None,
                     "obs_status": r.get("obs_status") or None,
                     "lastupdated": res.lastupdated, "retrieved_at": res.retrieved_at})
    df = pd.DataFrame(rows, columns=["iso3", "year", "code", "source_id", "value", "obs_status", "lastupdated",
                                     "retrieved_at"])
    nn = df.dropna(subset=["value"])
    latest = int(nn["year"].max()) if len(nn) else None
    typical = int(nn.groupby("iso3")["year"].max().median()) if len(nn) else None
    manifest = {"code": ind.code, "source_id": ind.source_id, "feature": ind.feature, "role": ind.role,
                "api_url": res.url, "pages": res.pages, "api_total_records": res.total,
                "retrieved_at": res.retrieved_at, "lastupdated": res.lastupdated, "rows": len(df),
                "non_null_rows": len(nn), "economies_with_data": int(nn["iso3"].nunique()) if len(nn) else 0,
                "latest_year": latest, "typical_latest_year": typical, "from_cache": res.from_cache}
    return df, manifest


def build_panel(long: pd.DataFrame, countries: pd.DataFrame) -> pd.DataFrame:
    """Wide iso3-year panel with bounded forward-fill and imputed flags."""
    feat = {i.code: i.feature for i in INDICATORS}
    wide = (long.dropna(subset=["value"]).assign(feature=lambda d: d["code"].map(feat))
            .pivot_table(index=["iso3", "year"], columns="feature", values="value", aggfunc="first"))
    years = range(config.YEAR_MIN, int(long["year"].max()) + 1)
    idx = pd.MultiIndex.from_product([sorted(countries["iso3"]), years], names=["iso3", "year"])
    wide = wide.reindex(idx)
    out = wide.copy()
    for f in [i.feature for i in INDICATORS]:
        if f not in out:
            out[f] = float("nan")
            wide[f] = float("nan")
        lim = FFILL_LIMIT.get(f, DEFAULT_FFILL)
        out[f] = out.groupby(level="iso3")[f].ffill(limit=lim)
        out[f"{f}_imputed"] = wide[f].isna() & out[f].notna()
    return out.reset_index()


def run(refresh: bool = False) -> dict:
    config.ensure_dirs()
    client = WorldBankClient(cache_dir=config.CACHE / "wb", refresh=refresh)
    countries, cmeta = _countries(client)
    codes = set(countries["iso3"])
    log.info("countries: %d economies (%d aggregates dropped)", len(countries), cmeta["aggregates_dropped"])

    frames, manifests, metas = [], [], []
    for ind in INDICATORS:
        df, m = _indicator_rows(client, ind, codes)
        frames.append(df)
        manifests.append(m)
        md = client.indicator_metadata(ind.code, ind.source_id)
        metas.append({"code": ind.code, "source_id": ind.source_id, "feature": ind.feature, "role": ind.role,
                      "label": ind.label, "name": md.get("name") or ind.label, "unit": ind.unit,
                      "source_name": (md.get("source") or {}).get("value"),
                      "source_org": md.get("sourceOrganization"), "source_note": md.get("sourceNote"),
                      "public": ind.public, "forward_fill": ind.forward_fill})
        log.info("%-22s src=%d rows=%5d non-null=%5d latest=%s", ind.code, ind.source_id, m["rows"],
                 m["non_null_rows"], m["latest_year"])
        if m["non_null_rows"] == 0:
            log.error("indicator %s returned no data; check code/source", ind.code)

    long = pd.concat(frames, ignore_index=True)
    panel = build_panel(long, countries)
    db.write_table("countries", countries)
    db.write_table("wb_indicators", long)
    db.write_table("wb_indicator_meta", pd.DataFrame(metas))
    db.write_table("wb_panel", panel)

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "api_base": "https://api.worldbank.org/v2",
        "date_range": DATE_RANGE,
        "retrieval": "programmatic; format=json; explicit source ids; all pages; nulls kept",
        "countries": cmeta,
        "indicators": manifests,
        "totals": {"rows": len(long), "non_null_rows": int(long["value"].notna().sum()),
                   "indicators": len(INDICATORS)},
        "terms": "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets (CC BY 4.0)",
    }
    (config.PROCESSED / "wb_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("wb_indicators: %d rows (%d non-null); manifest written", len(long), manifest["totals"]["non_null_rows"])
    return manifest
