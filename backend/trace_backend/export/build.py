# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T7: precompute every API payload as JSON in data/processed/api/ so the demo never waits on a model.

`--fixtures` additionally regenerates contracts/fixtures/ by calling the live FastAPI app (TestClient),
so fixtures always match both the contract and real output.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .. import config, db
from ..sources import SOURCES
from ..wb.indicators import ROLE_LABELS

log = logging.getLogger(__name__)
OUT = config.API_DIR
MIN_PRED_PROBABILITY = 0.5


def _clean(o):
    """Make numpy/pandas values JSON-safe (NaN -> None)."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if o is pd.NA or o is pd.NaT:
        return None
    return o


def dump(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(_clean(obj), separators=(",", ":")), encoding="utf-8")


def _num(v, nd=4):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v) else round(float(v), nd)


# ------------------------------------------------------------------ edges
def _signals(r) -> dict:
    return {"seizures": bool(r.sig_seizures), "price_gradient": bool(r.sig_price_gradient),
            "oc_index": bool(r.sig_oc_index), "news": bool(r.sig_news), "cultivation": bool(r.sig_cultivation)}


def observed_edges(edges: pd.DataFrame) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    act = edges[edges["active"]]
    for r in act.itertuples():
        out.setdefault(int(r.year), []).append({
            "id": f"{r.drug}:{r.from_iso3}:{r.to_iso3}", "from": r.from_iso3, "to": r.to_iso3, "drug": r.drug,
            "year": int(r.year), "volume_norm": _num(r.volume_norm), "kg": _num(r.kg, 1), "cases": int(r.cases),
            "confidence": float(r.confidence), "signals": _signals(r), "is_emerging": bool(r.is_emerging),
            "probability": None, "change_pct": _num(r.change_pct, 1), "drivers": []})
    for y in out:
        out[y].sort(key=lambda e: -e["volume_norm"])
    return out


def predicted_edges(preds: pd.DataFrame) -> dict[int, list[dict]]:
    p = preds[preds["probability"] >= MIN_PRED_PROBABILITY]
    y = int(preds["year"].iloc[0])
    rows = [{
        "id": f"{r.drug}:{r.from_iso3}:{r.to_iso3}", "from": r.from_iso3, "to": r.to_iso3, "drug": r.drug,
        "year": y, "volume_norm": _num(r.volume_norm_pred), "kg": _num(r.kg_pred, 1), "cases": None,
        "confidence": float(r.confidence) if pd.notna(r.confidence) else 0.0, "signals": _signals(r),
        "is_emerging": bool(r.is_emerging_pred), "probability": _num(r.probability),
        "change_pct": _num(r.change_pct_pred, 1), "drivers": json.loads(r.drivers)} for r in p.itertuples()]
    rows.sort(key=lambda e: -e["volume_norm"])
    return {y: rows}


# ------------------------------------------------------------------ risk
def risk_payload(risk: pd.DataFrame, countries: pd.DataFrame) -> tuple[dict, dict]:
    names = countries.set_index("iso3")[["name", "region"]]
    trends = {iso3: [{"year": int(y), "score": float(s)} for y, s in zip(g["year"], g["score"], strict=True)]
              for iso3, g in risk.sort_values("year").groupby("iso3")}
    boards, details = {}, {}
    for y, g in risk.groupby("year"):
        rows = []
        for r in g.sort_values("rank").itertuples():
            rows.append({"iso3": r.iso3, "name": names.at[r.iso3, "name"], "region": names.at[r.iso3, "region"],
                         "exposure": float(r.exposure), "vulnerability": float(r.vulnerability),
                         "protection": float(r.protection), "score": float(r.score), "rank": int(r.rank),
                         "tier": r.tier, "delta_1y": _num(r.delta_1y, 1),
                         "top_drug": r.top_drug if isinstance(r.top_drug, str) else None,
                         "trend": [t for t in trends[r.iso3] if t["year"] <= int(y)][-10:]})
            det = json.loads(r.details)
            details.setdefault(r.iso3, {})[str(int(y))] = {
                "year": int(y), "exposure": float(r.exposure), "vulnerability": float(r.vulnerability),
                "protection": float(r.protection), "score": float(r.score), "rank": int(r.rank), "tier": r.tier,
                **det, "trend": [t for t in trends[r.iso3] if t["year"] <= int(y)]}
        boards[str(int(y))] = rows
    return boards, details


# ------------------------------------------------------------------ prices
def price_series(prices: pd.DataFrame, countries: pd.DataFrame) -> list[dict]:
    names = countries.set_index("iso3")["name"]
    out = []
    for (iso3, drug, level), g in prices.sort_values("year").groupby(["iso3", "drug", "level"]):
        g = g.dropna(subset=["usd_g"])
        if g.empty:
            continue
        pts = [{"year": int(y), "value": round(float(v), 2), "purity_pct": _num(pp, 1)}
               for y, v, pp in zip(g["year"], g["usd_g"], g["purity_pct"], strict=True)]
        yoy = None
        if len(pts) >= 2 and pts[-1]["year"] - pts[-2]["year"] == 1 and pts[-2]["value"]:
            yoy = round((pts[-1]["value"] / pts[-2]["value"] - 1) * 100, 1)
        src = "unodc_wdr_annex"
        out.append({"iso3": iso3, "name": names.get(iso3, iso3), "drug": drug, "level": level, "unit": "USD/g",
                    "points": pts, "latest": pts[-1]["value"], "yoy_change_pct": yoy, "source": src})
    return out


# ------------------------------------------------------------------ indicators
def indicators_payload() -> tuple[dict, dict]:
    long = db.read_table("wb_indicators").dropna(subset=["value"])
    meta = db.read_table("wb_indicator_meta")
    meta = meta[meta["public"]]
    long = long[long["code"].isin(meta["code"])]
    by_country: dict[str, dict[str, list]] = {}
    for (iso3, code), g in long.sort_values("year").groupby(["iso3", "code"]):
        by_country.setdefault(iso3, {})[code] = [[int(y), float(v)] for y, v in zip(g["year"], g["value"], strict=True)]
    m = {r.code: {"source_id": int(r.source_id), "name": r.label, "unit": r.unit, "role": r.role,
                  "forward_fill": bool(r.forward_fill), "feature": r.feature} for r in meta.itertuples()}
    return by_country, m


# ------------------------------------------------------------------ briefings (template, data-driven)
def briefing(iso3: str, name: str, risk_row: dict | None, out_edges: list, in_edges: list, hr: dict | None,
             cult: list) -> str:
    parts = []
    if risk_row:
        parts.append(f"{name} ranks #{risk_row['rank']} of 217 on spillover risk in {risk_row['year']} "
                     f"(score {risk_row['score']:.0f}, {risk_row['tier']}).")
    if cult:
        last = cult[-1]
        crop = "coca" if last["crop"] == "coca" else "opium poppy"
        if last["hectares"]:
            parts.append(f"It cultivates {crop} ({last['hectares']:,.0f} ha in {last['year']}, UNODC).")
    if out_edges:
        top = sorted(out_edges, key=lambda e: -(e["kg"] or 0))[:2]
        parts.append("Main outbound corridors: " + ", ".join(f"{e['drug']} to {e['to']}" for e in top) + ".")
    if in_edges:
        top = sorted(in_edges, key=lambda e: -(e["kg"] or 0))[:2]
        parts.append("Main inbound corridors: " + ", ".join(f"{e['drug']} from {e['from']}" for e in top) + ".")
    if hr:
        have = [lbl for k, lbl in (("nsp", "syringe programmes"), ("oat", "opioid agonist therapy"),
                                   ("naloxone", "take-home naloxone"), ("dcr", "drug consumption rooms")) if hr.get(k)]
        missing = [lbl for k, lbl in (("nsp", "syringe programmes"), ("oat", "opioid agonist therapy"),
                                      ("naloxone", "take-home naloxone")) if hr.get(k) is False]
        if have:
            parts.append("Harm reduction in place: " + ", ".join(have) + ".")
        if missing:
            parts.append("Gaps to close before flows grow: " + ", ".join(missing) + ".")
    else:
        parts.append("No Harm Reduction International record of harm reduction services.")
    return " ".join(parts)


# ------------------------------------------------------------------ meta
def sources_freshness() -> list[dict]:
    wb = json.loads((config.PROCESSED / "wb_manifest.json").read_text(encoding="utf-8"))
    ing = json.loads((config.PROCESSED / "ingest_manifest.json").read_text(encoding="utf-8"))["sources"]
    wdi = [i for i in wb["indicators"] if i["source_id"] == 2]
    wgi = [i for i in wb["indicators"] if i["source_id"] == 3]
    out = []
    for sid, rows in (("wb_wdi", wdi), ("wb_wgi", wgi)):
        out.append({**SOURCES[sid], "status": "cached" if all(r["from_cache"] for r in rows) else "live",
                    "retrieved_at": min(r["retrieved_at"] for r in rows), "last_updated": rows[0]["lastupdated"],
                    "latest_year": max(r["latest_year"] or 0 for r in rows),
                    "note": f"{len(rows)} indicators, all pages, nulls kept"})
    for sid, extra in (("unodc_ids", None), ("unodc_wdr_annex", 2024), ("gitoc_ocindex", 2025), ("hri_gshr", 2024),
                       ("cepii_geodist", None)):
        s = ing.get(sid, {})
        st = s.get("status", "unavailable")
        out.append({**SOURCES[sid], "status": "cached" if st in ("cached", "live") and sid != "gdelt" else st,
                    "retrieved_at": s.get("retrieved_at"), "last_updated": None,
                    "latest_year": extra if sid != "unodc_ids" else 2026,
                    "note": s.get("note") or s.get("error") or ""})
    out.append({**SOURCES["unodc_routes"], "status": "cached", "retrieved_at": None, "last_updated": "2026-09-26",
                "latest_year": 2024, "note": f"{ing.get('corridors_seed', {}).get('rows', 0)} documented corridors"})
    return out


def run(fixtures: bool = False) -> dict:
    config.ensure_dirs()
    now = datetime.now(UTC).isoformat(timespec="seconds")
    countries = db.read_table("countries")
    edges = db.read_table("edges")
    preds = db.read_table("predictions")
    risk = db.read_table("risk_scores")

    ctry = [{"iso3": r.iso3, "iso2": r.iso2, "name": r.name, "region": r.region, "income_group": r.income_group,
             "capital": r.capital, "lat": _num(r.lat), "lon": _num(r.lon)} for r in countries.itertuples()]
    dump("countries.json", ctry)
    obs = observed_edges(edges)
    pred = predicted_edges(preds)
    dump("routes_observed.json", {str(k): v for k, v in obs.items()})
    dump("routes_predicted.json", {str(k): v for k, v in pred.items()})
    boards, details = risk_payload(risk, countries)
    dump("risk.json", boards)
    dump("risk_details.json", details)
    ps = price_series(db.read_table("prices"), countries)
    dump("prices.json", ps)
    ind, ind_meta = indicators_payload()
    dump("indicators.json", ind)
    dump("indicator_meta.json", {"codes": ind_meta, "roles": ROLE_LABELS})
    oc = db.read_table("oc_index")
    dump("oc_index.json", {iso3: sorted([{"edition": int(r.edition), "criminality": _num(r.criminality, 2),
                                          "resilience": _num(r.resilience, 2),
                                          "markets": {"cocaine": _num(r.cocaine, 2), "heroin": _num(r.heroin, 2),
                                                      "cannabis": _num(r.cannabis, 2),
                                                      "synthetic": _num(r.synthetic, 2)},
                                          "source": "gitoc_ocindex"} for r in g.itertuples()],
                                        key=lambda x: x["edition"]) for iso3, g in oc.groupby("iso3")})
    from ..model.spillover import PROT, protection
    hri = protection(db.read_table("harm_reduction"))
    hr = {r.iso3: {"year": 2024, **{k: (None if pd.isna(getattr(r, k)) else bool(getattr(r, k)))
                                    for k in ("nsp", "oat", "naloxone", "dcr", "prison_programs")},
                   "coverage_score": float(r.protection), "source": "hri_gshr"} for r in hri.itertuples()}
    dump("harm_reduction.json", hr)
    cult = db.read_table("cultivation")
    cu = {iso3: [{"iso3": iso3, "crop": r.crop, "year": int(r.year), "hectares": _num(r.hectares, 0),
                  "production_t": _num(r.production_t, 1)} for r in g.sort_values(["crop", "year"]).itertuples()]
          for iso3, g in cult.groupby("iso3")}
    dump("cultivation.json", cu)
    ab = json.loads(db.read_table("afghan_ban")["json"].iloc[0])
    dump("afghan_ban.json", ab)

    latest_obs = max(obs)
    fut = max(pred)
    brief = {}
    last_edges = obs[latest_obs]
    for c in ctry:
        rr = next((r for r in boards[str(fut)] if r["iso3"] == c["iso3"]), None)
        rr = {**rr, "year": fut} if rr else None
        brief[c["iso3"]] = briefing(c["iso3"], c["name"], rr, [e for e in last_edges if e["from"] == c["iso3"]],
                                    [e for e in last_edges if e["to"] == c["iso3"]], hr.get(c["iso3"]),
                                    [x for x in cu.get(c["iso3"], []) if x["hectares"]])
    dump("briefings.json", brief)

    meta = {"drugs": [{"id": d, "label": config.DRUG_LABELS[d], "harm_weight": config.HARM_WEIGHTS[d]}
                      for d in config.DRUGS],
            "observed_years": sorted(obs), "predicted_years": sorted(pred),
            "risk_years": sorted(int(y) for y in boards), "latest_observed_year": latest_obs,
            "model_version": config.MODEL_VERSION, "livewire_classifier": "jev-1.13.0" if config.TYPESAFE_API_KEY
            else "mock", "sources": sources_freshness(), "generated_at": now, "prot_weights": PROT}
    dump("meta.json", meta)
    metrics = json.loads((config.PROCESSED / "metrics.json").read_text(encoding="utf-8"))
    dump("metrics.json", metrics)
    log.info("exported API JSON to %s (%d observed years, %d predicted edges)", OUT, len(obs), len(pred[fut]))
    if fixtures:
        from .fixtures import regenerate
        regenerate()
    return {"out": str(OUT), "observed_years": sorted(obs), "predicted_year": fut}
