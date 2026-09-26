# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Generate hand-crafted T0 contract fixtures in contracts/fixtures/.

These are *illustrative* fixtures (plausible numbers, real country codes) so the
frontend can build before the pipeline runs. Once the pipeline has run, prefer
`python -m trace_backend.export --fixtures`, which rewrites fixtures from real output.

The countries fixture is pulled live from the World Bank API (/country), falling
back to a small built-in list if the API is unreachable.
"""
from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "contracts" / "fixtures"
NOW = "2026-09-26T12:00:00Z"
MODEL_VERSION = "trace-0.1.0-fixture"

SOURCES = {
    "wb_wdi": {"id": "wb_wdi", "name": "World Bank World Development Indicators (source 2)",
               "url": "https://api.worldbank.org/v2/sources/2"},
    "wb_wgi": {"id": "wb_wgi", "name": "World Bank Worldwide Governance Indicators (source 3)",
               "url": "https://api.worldbank.org/v2/sources/3"},
    "unodc_wdr_annex": {"id": "unodc_wdr_annex", "name": "UNODC World Drug Report statistical annex",
                        "url": "https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html"},
    "unodc_ids": {"id": "unodc_ids", "name": "UNODC Individual Drug Seizures (IDS)",
                  "url": "https://dmp.unodc.org/downloadIDS"},
    "gitoc_ocindex": {"id": "gitoc_ocindex", "name": "GI-TOC Global Organized Crime Index",
                      "url": "https://ocindex.net"},
    "hri_gshr": {"id": "hri_gshr", "name": "Harm Reduction International, Global State of Harm Reduction 2024",
                 "url": "https://hri.global/flagship-research/the-global-state-of-harm-reduction/"},
    "cepii_geodist": {"id": "cepii_geodist", "name": "CEPII GeoDist",
                      "url": "https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=6"},
    "gdelt": {"id": "gdelt", "name": "GDELT DOC 2.0 API", "url": "https://api.gdeltproject.org/api/v2/doc/doc"},
}


def meta(*source_ids: str, notes: list[str] | None = None) -> dict:
    m = {"generated_at": NOW, "model_version": MODEL_VERSION,
         "sources": [SOURCES[s] for s in source_ids]}
    if notes:
        m["notes"] = notes
    return m


def dump(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", name)


# ---------------------------------------------------------------- countries
FALLBACK_COUNTRIES = [
    ("COL", "CO", "Colombia", "Latin America & Caribbean", "Upper middle income", "Bogota", 4.61, -74.08),
    ("ECU", "EC", "Ecuador", "Latin America & Caribbean", "Upper middle income", "Quito", -0.23, -78.52),
]


def fetch_countries() -> list[dict]:
    url = "https://api.worldbank.org/v2/country?format=json&per_page=400"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            meta_, rows = json.loads(r.read())
        out = []
        for c in rows:
            if c["region"]["value"].strip() == "Aggregates":
                continue
            lat = float(c["latitude"]) if c["latitude"] else None
            lon = float(c["longitude"]) if c["longitude"] else None
            out.append({"iso3": c["id"], "iso2": c["iso2Code"], "name": c["name"],
                        "region": c["region"]["value"].strip(),
                        "income_group": c["incomeLevel"]["value"].strip(),
                        "capital": c["capitalCity"] or None, "lat": lat, "lon": lon})
        return sorted(out, key=lambda c: c["iso3"])
    except Exception as exc:  # pragma: no cover - network fallback
        print("World Bank unreachable, using fallback list:", exc)
        return [dict(zip(["iso3", "iso2", "name", "region", "income_group", "capital", "lat", "lon"], c))
                for c in FALLBACK_COUNTRIES]


# ---------------------------------------------------------------- routes
# (from, to, drug, kg_2024, cases, confidence, emerging)
OBSERVED = [
    ("COL", "ECU", "cocaine", 98000, 412, 92, False),
    ("ECU", "BEL", "cocaine", 44000, 138, 90, False),
    ("ECU", "NLD", "cocaine", 31000, 101, 88, False),
    ("ECU", "ESP", "cocaine", 26000, 95, 86, False),
    ("COL", "PAN", "cocaine", 52000, 204, 84, False),
    ("PAN", "USA", "cocaine", 21000, 66, 71, False),
    ("COL", "MEX", "cocaine", 38000, 150, 80, False),
    ("MEX", "USA", "cocaine", 29000, 310, 83, False),
    ("PER", "BRA", "cocaine", 17000, 88, 69, False),
    ("BRA", "PRT", "cocaine", 9000, 57, 66, False),
    ("BOL", "PRY", "cocaine", 12000, 41, 58, True),
    ("PRY", "BEL", "cocaine", 6000, 12, 44, True),
    ("AFG", "IRN", "heroin", 6100, 780, 90, False),
    ("AFG", "PAK", "heroin", 3900, 402, 86, False),
    ("IRN", "TUR", "heroin", 4200, 233, 82, False),
    ("TUR", "BGR", "heroin", 1300, 58, 70, False),
    ("BGR", "SRB", "heroin", 600, 21, 55, False),
    ("PAK", "ARE", "heroin", 800, 44, 52, False),
    ("MMR", "THA", "heroin", 2900, 310, 85, True),
    ("MMR", "LAO", "heroin", 1700, 96, 74, True),
    ("MMR", "CHN", "heroin", 1500, 188, 72, False),
    ("THA", "MYS", "heroin", 900, 77, 61, True),
    ("MEX", "USA", "meth", 71000, 1860, 95, False),
    ("MMR", "THA", "meth", 88000, 2410, 93, False),
    ("MMR", "LAO", "meth", 61000, 530, 88, False),
    ("LAO", "VNM", "meth", 9000, 140, 64, True),
    ("THA", "MYS", "meth", 17000, 420, 76, False),
    ("MYS", "AUS", "meth", 2500, 38, 57, True),
    ("MAR", "ESP", "cannabis", 310000, 5200, 94, False),
    ("ESP", "FRA", "cannabis", 64000, 1320, 81, False),
    ("MEX", "USA", "cannabis", 38000, 900, 78, False),
    ("PRY", "BRA", "cannabis", 120000, 2100, 87, False),
    ("ALB", "ITA", "cannabis", 22000, 310, 66, False),
]

DRIVER_LIB = {
    "cocaine": [("lag_log_kg", "Last year's volume on this corridor"),
                ("port_teu_origin", "Origin container port capacity (TEU)"),
                ("cultivation_origin", "Coca cultivation upstream"),
                ("gdp_dest", "Destination market size (GDP)")],
    "heroin": [("cultivation_origin", "Opium poppy cultivation upstream"),
               ("lag_log_kg", "Last year's volume on this corridor"),
               ("contig", "Shared border"),
               ("price_gap", "Price gap destination vs origin")],
    "meth": [("lag_log_kg", "Last year's volume on this corridor"),
             ("oc_synthetic_origin", "Synthetic drug market score at origin (OC Index)"),
             ("contig", "Shared border"),
             ("pop_dest", "Destination population")],
    "cannabis": [("lag_log_kg", "Last year's volume on this corridor"),
                 ("dist", "Distance (km)"),
                 ("legal_dest", "Destination cannabis regulation"),
                 ("gdp_pc_dest", "Destination income per capita")],
}


def signals(conf: float, drug: str, emerging: bool) -> dict:
    return {"seizures": True, "price_gradient": conf > 60, "oc_index": conf > 50,
            "news": conf > 80 or emerging, "cultivation": drug in ("cocaine", "heroin") and conf > 70}


def vol_norm(kg: float, drug: str) -> float:
    total = sum(e[3] for e in OBSERVED if e[2] == drug)
    return round(min(1.0, math.log1p(kg) / math.log1p(total) * (0.35 + 0.65 * kg / max(e[3] for e in OBSERVED if e[2] == drug))), 3)


def edge(e, year: int, mode: str, scale: float = 1.0, prob: float | None = None, idx: int = 0) -> dict:
    f, t, drug, kg, cases, conf, emerg = e
    kg2 = round(kg * scale)
    drivers = []
    if mode == "predicted":
        sign = [1, -1, 1, -1]
        for i, (feat, label) in enumerate(DRIVER_LIB[drug][:3]):
            c = round((0.9 - 0.25 * i) * (1 if (idx + i) % 3 else -0.5) * sign[i % 2] * (1 if scale >= 1 else -1), 3)
            drivers.append({"feature": feat, "label": label, "contribution": c, "direction": "up" if c > 0 else "down"})
    return {"id": f"{drug}:{f}:{t}", "from": f, "to": t, "drug": drug, "year": year,
            "volume_norm": vol_norm(kg2, drug), "kg": kg2,
            "cases": cases if mode == "observed" else None, "confidence": conf,
            "signals": signals(conf, drug, emerg), "is_emerging": emerg,
            "probability": prob, "change_pct": round((scale - 1) * 100, 1) if mode == "predicted" else round(8.0 - idx % 7 * 3.1, 1),
            "drivers": drivers}


def routes_fixtures():
    obs = [edge(e, 2024, "observed", idx=i) for i, e in enumerate(OBSERVED)]
    dump("routes_observed.json", {"meta": meta("unodc_ids", "unodc_wdr_annex", "gitoc_ocindex", "wb_wdi"),
                                  "data": {"year": 2024, "mode": "observed", "drug": None, "edges": obs}})
    pred = []
    for i, e in enumerate(OBSERVED):
        scale = 1.0 + ((i * 37) % 21 - 8) / 100 + (0.25 if e[6] else 0)
        prob = round(min(0.99, 0.55 + e[5] / 250 + (0.05 if e[6] else 0)), 3)
        pred.append(edge(e, 2025, "predicted", scale=scale, prob=prob, idx=i))
    dump("routes_predicted.json", {"meta": meta("unodc_ids", "unodc_wdr_annex", "gitoc_ocindex", "wb_wdi", "wb_wgi", "cepii_geodist"),
                                   "data": {"year": 2025, "mode": "predicted", "drug": None, "edges": pred}})
    return obs


# ---------------------------------------------------------------- risk
RISK = [  # iso3, name, region, exposure, vulnerability, protection, top_drug
    ("ECU", "Ecuador", "Latin America & Caribbean", 91, 64, 22, "cocaine"),
    ("LAO", "Lao PDR", "East Asia & Pacific", 72, 71, 12, "meth"),
    ("MMR", "Myanmar", "East Asia & Pacific", 88, 83, 30, "meth"),
    ("HND", "Honduras", "Latin America & Caribbean", 69, 74, 10, "cocaine"),
    ("GTM", "Guatemala", "Latin America & Caribbean", 66, 70, 11, "cocaine"),
    ("PRY", "Paraguay", "Latin America & Caribbean", 70, 58, 15, "cannabis"),
    ("PAN", "Panama", "Latin America & Caribbean", 78, 45, 18, "cocaine"),
    ("GNB", "Guinea-Bissau", "Sub-Saharan Africa", 55, 82, 5, "cocaine"),
    ("THA", "Thailand", "East Asia & Pacific", 84, 41, 48, "meth"),
    ("PAK", "Pakistan", "South Asia", 63, 72, 35, "heroin"),
    ("COL", "Colombia", "Latin America & Caribbean", 93, 57, 40, "cocaine"),
    ("BGR", "Bulgaria", "Europe & Central Asia", 52, 44, 38, "heroin"),
    ("MEX", "Mexico", "Latin America & Caribbean", 90, 52, 46, "meth"),
    ("IRN", "Iran, Islamic Rep.", "Middle East, North Africa, Afghanistan & Pakistan", 74, 61, 71, "heroin"),
    ("BEL", "Belgium", "Europe & Central Asia", 76, 22, 82, "cocaine"),
]


def risk_rows():
    rows = []
    for iso3, name, region, ex, vu, pr, drug in RISK:
        score = round(0.45 * ex + 0.35 * vu + 0.20 * (100 - pr), 1)
        rows.append([iso3, name, region, ex, vu, pr, drug, score])
    rows.sort(key=lambda r: -r[-1])
    out = []
    for rank, r in enumerate(rows, 1):
        iso3, name, region, ex, vu, pr, drug, score = r
        trend = [{"year": y, "score": round(score - (2024 - y) * (1.3 if rank % 2 else -0.4) + (y % 3) * 0.7, 1)}
                 for y in range(2015, 2025)]
        trend[-1]["score"] = score
        tier = "critical" if score >= 75 else "high" if score >= 65 else "elevated" if score >= 55 else "moderate" if score >= 40 else "low"
        out.append({"iso3": iso3, "name": name, "region": region, "exposure": ex, "vulnerability": vu,
                    "protection": pr, "score": score, "rank": rank, "tier": tier,
                    "delta_1y": round(score - trend[-2]["score"], 1), "top_drug": drug, "trend": trend})
    return out


def risk_fixture(rows):
    dump("risk.json", {"meta": meta("wb_wdi", "wb_wgi", "hri_gshr", "unodc_ids"),
                       "data": {"year": 2024, "weights": {"exposure": 0.45, "vulnerability": 0.35, "protection": 0.2},
                                "rows": rows}})


# ---------------------------------------------------------------- prices
def price_series(iso3, name, drug, level, base, growth, purity=None, start=2014):
    pts = []
    for i, y in enumerate(range(start, 2025)):
        v = round(base * (1 + growth) ** i * (1 + 0.04 * math.sin(i)), 2)
        p = {"year": y, "value": v, "purity_pct": (round(purity + 1.5 * math.cos(i), 1) if purity else None)}
        pts.append(p)
    latest = pts[-1]["value"]
    yoy = round((latest / pts[-2]["value"] - 1) * 100, 1)
    return {"iso3": iso3, "name": name, "drug": drug, "level": level, "unit": "USD/g",
            "points": pts, "latest": latest, "yoy_change_pct": yoy, "source": "unodc_wdr_annex"}


def prices():
    return [
        price_series("COL", "Colombia", "cocaine", "wholesale", 1.6, 0.03, 80),
        price_series("COL", "Colombia", "cocaine", "retail", 4.1, 0.02, 45),
        price_series("ESP", "Spain", "cocaine", "retail", 62.0, 0.01, 58),
        price_series("BEL", "Belgium", "cocaine", "wholesale", 34.0, -0.01, 72),
        price_series("USA", "United States", "cocaine", "retail", 118.0, 0.0, 55),
        price_series("AFG", "Afghanistan", "heroin", "wholesale", 2.4, 0.08),
        price_series("TUR", "Turkiye", "heroin", "wholesale", 14.0, 0.04),
        price_series("GBR", "United Kingdom", "heroin", "retail", 58.0, 0.01, 40),
        price_series("THA", "Thailand", "meth", "retail", 9.5, -0.05),
        price_series("USA", "United States", "meth", "retail", 42.0, -0.06),
        price_series("CAN", "Canada", "cannabis", "retail", 7.8, -0.04),
        price_series("MAR", "Morocco", "cannabis", "wholesale", 1.1, 0.02),
    ]


# ---------------------------------------------------------------- country
def wb(code, sid, year, value, name, unit, imputed=False):
    return {"code": code, "source_id": sid, "year": year, "value": value, "name": name, "unit": unit, "imputed": imputed}


def country_fixture(countries, obs_edges, rows, price_list):
    col = next((c for c in countries if c["iso3"] == "COL"), None) or {
        "iso3": "COL", "iso2": "CO", "name": "Colombia", "region": "Latin America & Caribbean",
        "income_group": "Upper middle income", "capital": "Bogota", "lat": 4.60987, "lon": -74.082}
    risk_row = next(r for r in rows if r["iso3"] == "COL")
    indicators = [
        {"role": "governance", "label": "Governance", "indicators": [
            wb("GOV_WGI_RL.EST", 3, 2024, -0.42, "Rule of Law: Estimate", "index (-2.5 to 2.5)"),
            wb("GOV_WGI_CC.EST", 3, 2024, -0.31, "Control of Corruption: Estimate", "index (-2.5 to 2.5)"),
            wb("GOV_WGI_GE.EST", 3, 2024, -0.12, "Government Effectiveness: Estimate", "index (-2.5 to 2.5)"),
            wb("GOV_WGI_PV.EST", 3, 2024, -0.63, "Political Stability and Absence of Violence: Estimate", "index (-2.5 to 2.5)")]},
        {"role": "logistics", "label": "Connectivity", "indicators": [
            wb("IS.SHP.GOOD.TU", 2, 2023, 5210000, "Container port traffic", "TEU"),
            wb("IS.AIR.PSGR", 2, 2023, 38100000, "Air transport, passengers carried", "passengers"),
            wb("NE.TRD.GNFS.ZS", 2, 2024, 40.2, "Trade", "% of GDP"),
            wb("LP.LPI.OVRL.XQ", 2, 2022, 2.9, "Logistics performance index: Overall", "1-5", imputed=True)]},
        {"role": "gravity", "label": "Market size", "indicators": [
            wb("NY.GDP.MKTP.CD", 2, 2024, 418500000000, "GDP (current US$)", "US$"),
            wb("NY.GDP.PCAP.PP.KD", 2, 2024, 17800, "GDP per capita, PPP (constant 2021 international $)", "int$"),
            wb("SP.POP.TOTL", 2, 2024, 52886000, "Population, total", "people")]},
        {"role": "vulnerability", "label": "Vulnerability", "indicators": [
            wb("SL.UEM.1524.ZS", 2, 2024, 18.9, "Unemployment, youth total (% of labor force ages 15-24)", "%"),
            wb("SL.UEM.NEET.ZS", 2, 2023, 23.4, "Share of youth not in education, employment or training", "%"),
            wb("SI.POV.DDAY", 2, 2023, 7.1, "Poverty headcount ratio at $3.00 a day (2021 PPP)", "% of population"),
            wb("SI.POV.GINI", 2, 2023, 53.9, "Gini index", "index"),
            wb("SH.XPD.CHEX.PC.CD", 2, 2022, 552.0, "Current health expenditure per capita", "US$"),
            wb("FX.OWN.TOTL.ZS", 2, 2021, 59.7, "Account ownership", "% age 15+"),
            wb("BX.TRF.PWKR.DT.GD.ZS", 2, 2024, 2.8, "Personal remittances, received", "% of GDP")]},
        {"role": "outcome", "label": "Harm outcomes", "indicators": [
            wb("VC.IHR.PSRC.P5", 2, 2022, 26.1, "Intentional homicides", "per 100,000 people"),
            wb("SH.HIV.INCD.ZS", 2, 2023, 0.2, "Incidence of HIV, ages 15-49", "per 1,000 uninfected"),
            wb("VC.BTL.DETH", 2, 2023, 312, "Battle-related deaths", "people"),
            wb("SM.POP.RHCR.EA", 2, 2024, 2810000, "Refugee population by country of asylum", "people"),
            wb("SM.POP.RHCR.EO", 2, 2024, 118000, "Refugee population by country of origin", "people")]},
    ]
    detail = lambda items: [{"feature": f, "label": l, "value": v, "contribution": c} for f, l, v, c in items]
    risk = {
        "year": 2024, "exposure": risk_row["exposure"], "vulnerability": risk_row["vulnerability"],
        "protection": risk_row["protection"], "score": risk_row["score"], "rank": risk_row["rank"],
        "tier": risk_row["tier"], "exposure_by_drug": {"cocaine": 88.0, "cannabis": 9.0, "heroin": 2.0, "meth": 1.0},
        "exposure_detail": detail([("inbound_cocaine", "Inbound + transit cocaine volume", 0.21, 18.5),
                                   ("outbound_cocaine", "Outbound cocaine volume", 0.92, 22.1),
                                   ("cultivation", "Coca cultivation (ha)", 253000, 11.3)]),
        "vulnerability_detail": [
            {"feature": "youth_unemployment", "label": "Youth unemployment", "value": 18.9, "contribution": 9.2,
             "provenance": wb("SL.UEM.1524.ZS", 2, 2024, 18.9, "Unemployment, youth total", "%")},
            {"feature": "gini", "label": "Inequality (Gini)", "value": 53.9, "contribution": 12.4,
             "provenance": wb("SI.POV.GINI", 2, 2023, 53.9, "Gini index", "index")},
            {"feature": "rule_of_law", "label": "Governance (rule of law)", "value": -0.42, "contribution": 8.1,
             "provenance": wb("GOV_WGI_RL.EST", 3, 2024, -0.42, "Rule of Law: Estimate", "index")}],
        "protection_detail": detail([("nsp", "Needle and syringe programmes", 1, 25.0),
                                     ("oat", "Opioid agonist therapy", 1, 15.0),
                                     ("naloxone", "Take-home naloxone", 0, 0.0),
                                     ("dcr", "Drug consumption rooms", 0, 0.0)]),
        "trend": risk_row["trend"],
    }
    profile = {
        "country": col, "year": 2024, "indicators": indicators,
        "routes": {"inbound": [e for e in obs_edges if e["to"] == "COL"],
                   "outbound": [e for e in obs_edges if e["from"] == "COL"]},
        "prices": [p for p in price_list if p["iso3"] == "COL"],
        "oc_index": {"edition": 2025, "criminality": 7.75, "resilience": 5.13,
                     "markets": {"cocaine": 10.0, "heroin": 4.5, "cannabis": 7.5, "synthetic": 5.5},
                     "source": "gitoc_ocindex"},
        "harm_reduction": {"year": 2024, "nsp": True, "oat": True, "naloxone": False, "dcr": False,
                           "prison_programs": False, "coverage_score": 40.0, "source": "hri_gshr"},
        "risk": risk,
        "cultivation": [{"iso3": "COL", "crop": "coca", "year": y, "hectares": h, "production_t": None}
                        for y, h in [(2016, 146000), (2017, 171000), (2018, 169000), (2019, 154000),
                                     (2020, 143000), (2021, 204000), (2022, 230000), (2023, 253000)]],
        "briefing": ("Colombia remains the world's largest coca producer (253,000 ha in 2023). Most outbound "
                     "cocaine now exits via Ecuador toward European ports. Harm reduction coverage is partial: "
                     "syringe programmes and OAT exist, take-home naloxone does not."),
    }
    dump("country_COL.json", {"meta": meta("wb_wdi", "wb_wgi", "unodc_ids", "unodc_wdr_annex", "gitoc_ocindex", "hri_gshr"),
                              "data": profile})


# ---------------------------------------------------------------- simulate
def simulate_fixtures():
    req = {"scenario": "Colombia cuts coca 50%", "shocks": [], "year": 2025}
    dump("simulate_request.json", req)
    edges = [
        ("COL", "ECU", "cocaine", 0.95, 0.71, 98000, 61000, 0.97, 0.93),
        ("COL", "PAN", "cocaine", 0.72, 0.52, 52000, 33000, 0.9, 0.84),
        ("COL", "MEX", "cocaine", 0.64, 0.47, 38000, 24500, 0.88, 0.8),
        ("PER", "BRA", "cocaine", 0.48, 0.55, 17000, 20400, 0.79, 0.83),
        ("BOL", "PRY", "cocaine", 0.38, 0.45, 12000, 14800, 0.66, 0.72),
    ]
    data = {
        "scenario": "Colombia cuts coca 50%", "parsed_by": "rules",
        "shocks": [{"type": "cultivation", "iso3": "COL", "drug": "cocaine", "value": 0.5}], "year": 2025,
        "edges_changed": [{"from": f, "to": t, "drug": d, "baseline_volume_norm": bv, "scenario_volume_norm": sv,
                           "baseline_kg": bk, "scenario_kg": sk, "baseline_probability": bp,
                           "scenario_probability": sp, "delta_pct": round((sk / bk - 1) * 100, 1)}
                          for f, t, d, bv, sv, bk, sk, bp, sp in edges],
        "risk_deltas": [
            {"iso3": "ECU", "name": "Ecuador", "baseline_score": 69.2, "scenario_score": 63.0, "delta": -6.2, "baseline_rank": 3, "scenario_rank": 6},
            {"iso3": "COL", "name": "Colombia", "baseline_score": 70.0, "scenario_score": 65.1, "delta": -4.9, "baseline_rank": 2, "scenario_rank": 4},
            {"iso3": "PRY", "name": "Paraguay", "baseline_score": 63.8, "scenario_score": 66.0, "delta": 2.2, "baseline_rank": 8, "scenario_rank": 7},
            {"iso3": "BRA", "name": "Brazil", "baseline_score": 55.1, "scenario_score": 56.9, "delta": 1.8, "baseline_rank": 19, "scenario_rank": 17},
        ],
        "summary": ("Halving Colombian coca output cuts cocaine through the Ecuador corridor by about 38%. "
                    "Supply partly shifts to Peru and Bolivia via Brazil and Paraguay, raising their exposure."),
        "warnings": ["Scenario effects are model estimates, not forecasts of policy outcomes."],
    }
    dump("simulate.json", {"meta": meta("unodc_ids", "unodc_wdr_annex", "wb_wdi"), "data": data})


# ---------------------------------------------------------------- afghan ban
def afghan_fixture():
    afg = {2018: 263000, 2019: 163000, 2020: 224000, 2021: 177000, 2022: 233000, 2023: 10800, 2024: 12800}
    mmr = {2018: 37300, 2019: 33100, 2020: 29500, 2021: 30200, 2022: 40100, 2023: 47000, 2024: 45200}
    series = [
        {"id": "afg_cultivation", "label": "Afghanistan opium poppy cultivation", "unit": "ha",
         "points": [{"year": y, "value": v} for y, v in afg.items()]},
        {"id": "mmr_cultivation", "label": "Myanmar opium poppy cultivation", "unit": "ha",
         "points": [{"year": y, "value": v} for y, v in mmr.items()]},
        {"id": "sea_share", "label": "Share of heroin corridor volume in SE Asia", "unit": "share",
         "points": [{"year": y, "value": v} for y, v in
                    [(2018, 0.21), (2019, 0.22), (2020, 0.2), (2021, 0.22), (2022, 0.24), (2023, 0.39), (2024, 0.44)]]},
    ]
    edges = [
        ("AFG", "IRN", 0.92, 0.41, 0.35, True), ("AFG", "PAK", 0.71, 0.33, 0.3, True),
        ("IRN", "TUR", 0.66, 0.4, 0.44, True), ("MMR", "THA", 0.44, 0.63, 0.71, True),
        ("MMR", "LAO", 0.31, 0.47, 0.52, True), ("MMR", "CHN", 0.35, 0.41, 0.37, True),
        ("THA", "MYS", 0.18, 0.26, 0.29, True), ("PAK", "ARE", 0.22, 0.17, 0.24, False),
    ]
    data = {
        "title": "Afghanistan 2022 opium ban",
        "summary": ("Train the route model through 2021, inject a 95% cut in Afghan opium cultivation, and compare "
                    "predicted heroin corridors with what 2023-2024 data later showed."),
        "ban_year": 2022, "train_through": 2021,
        "shock": {"type": "cultivation", "iso3": "AFG", "drug": "heroin", "value": 0.05},
        "series": series,
        "edges": [{"from": f, "to": t, "drug": "heroin", "before": b, "predicted": p, "actual": a,
                   "direction_correct": dc} for f, t, b, p, a, dc in edges],
        "metrics": {"direction_accuracy": 0.875, "spearman": 0.81, "n_edges": 8,
                    "sea_share_before": 0.22, "sea_share_predicted": 0.36, "sea_share_actual": 0.39},
        "verdict": ("The model shifted heroin volume toward Myanmar-linked Southeast Asian corridors, matching the "
                    "direction later data showed on 7 of 8 major edges."),
    }
    dump("afghan_ban.json", {"meta": meta("unodc_wdr_annex", "unodc_ids"), "data": data})


# ---------------------------------------------------------------- metrics
def metrics_fixture():
    data = {
        "model_version": MODEL_VERSION,
        "backtest": {
            "train_through": 2019, "test_years": [2020, 2021, 2022, 2023, 2024],
            "hurdle": {"auc": 0.87, "spearman": 0.71, "precision_at_20": 0.55, "n": 4120},
            "gravity_baseline": {"auc": 0.74, "spearman": 0.52, "precision_at_20": 0.3, "n": 4120},
            "per_drug": {"cocaine": {"auc": 0.89, "spearman": 0.74, "precision_at_20": 0.6, "n": 1210},
                         "heroin": {"auc": 0.84, "spearman": 0.66, "precision_at_20": 0.5, "n": 880},
                         "meth": {"auc": 0.86, "spearman": 0.7, "precision_at_20": 0.55, "n": 930},
                         "cannabis": {"auc": 0.88, "spearman": 0.73, "precision_at_20": 0.55, "n": 1100}},
            "per_year": {str(y): {"auc": round(0.89 - 0.01 * i, 2), "spearman": round(0.74 - 0.015 * i, 2),
                                  "precision_at_20": 0.55, "n": 824} for i, y in enumerate(range(2020, 2025))},
            "top_features": [{"feature": "lag_log_kg", "label": "Last year's volume on this corridor", "mean_abs_shap": 1.42},
                             {"feature": "cultivation_origin", "label": "Cultivation upstream", "mean_abs_shap": 0.51},
                             {"feature": "gdp_dest", "label": "Destination market size (GDP)", "mean_abs_shap": 0.38},
                             {"feature": "contig", "label": "Shared border", "mean_abs_shap": 0.33},
                             {"feature": "port_teu_origin", "label": "Origin container port capacity", "mean_abs_shap": 0.27}],
        },
        "afghan_ban": {"direction_accuracy": 0.875, "spearman": 0.81,
                       "verdict": "Direction of the heroin shift toward Southeast Asia reproduced on 7 of 8 edges."},
        "spillover": {
            "hypothesis": "Predicted route exposure predicts a significant rise in homicide or HIV incidence within 3 years, beyond vulnerability alone.",
            "outcome": "homicide rate up >= 20% or HIV incidence up >= 20% within 3 years",
            "n": 1830, "auc_vulnerability_only": 0.61, "auc_with_exposure": 0.66, "exposure_coef": 0.34,
            "lr_p_value": 0.004, "supported": True,
            "statement": "Exposure adds predictive power beyond vulnerability (AUC 0.61 to 0.66, likelihood-ratio p = 0.004).",
            "by_outcome": {"homicide": {"n": 1560, "auc_vulnerability_only": 0.6, "auc_with_exposure": 0.65, "lr_p_value": 0.006},
                           "hiv": {"n": 1320, "auc_vulnerability_only": 0.63, "auc_with_exposure": 0.64, "lr_p_value": 0.21}},
        },
        "livewire": {"classifier": "mock", "n_labeled": 100,
                     "field_accuracy": {"is_event": 0.86, "event_type": 0.74, "drug": 0.88, "origin": 0.61,
                                        "destination": 0.64, "size": 0.58},
                     "note": "Mock keyword classifier; Jev accuracy will be reported once a key is available."},
    }
    dump("metrics.json", {"meta": meta("unodc_ids", "wb_wdi", "wb_wgi", "gdelt"), "data": data})


# ---------------------------------------------------------------- livewire
EVENTS = [
    ("Ecuador navy seizes 4.2 tonnes of cocaine bound for Belgium", "seizure", "cocaine", "ECU", None, "BEL", "record", 0.86, False, None, 0.91, -1.83, -78.18),
    ("Thai police intercept 12 million meth pills near Myanmar border", "seizure", "meth", "MMR", None, "THA", "major", 0.83, False, None, 0.97, 15.87, 100.99),
    ("Spanish Guardia Civil dismantles hashish network in Cadiz", "arrest_or_indictment", "cannabis", "MAR", None, "ESP", "notable", 0.72, False, None, 0.95, 36.53, -6.29),
    ("Cocaine shipment from Paraguay found in Antwerp container", "seizure", "cocaine", "PRY", None, "BEL", "major", 0.78, True, "Edge PRY->BEL had 7% model probability", 0.07, 50.85, 4.35),
    ("Mexico passes reform on synthetic drug precursors", "law_or_policy_change", "fentanyl", "MEX", None, None, "notable", 0.69, False, None, None, 19.43, -99.13),
    ("Heroin haul on Iran-Turkey border tops 600 kg", "seizure", "heroin", "IRN", None, "TUR", "major", 0.81, False, None, 0.88, 38.96, 35.24),
]


def livewire_events():
    out = []
    for i, (title, et, drug, o, tr, d, size, conf, anom, reason, eprob, lat, lon) in enumerate(EVENTS):
        out.append({"id": f"gdelt-fixture-{i:03d}", "published_at": f"2026-09-26T{10 + i:02d}:15:00Z",
                    "title": title, "url": f"https://example.org/news/{i}", "source_domain": "example.org",
                    "language": "English", "event_type": et, "drug": drug, "origin": o, "transit": tr,
                    "destination": d, "size": size, "is_event": round(min(0.99, conf + 0.08), 2),
                    "route_mentioned": 0.85 if d else 0.2, "confidence": conf, "is_anomaly": anom,
                    "anomaly_reason": reason, "edge_probability": eprob, "classifier": "mock", "lat": lat, "lon": lon})
    return out


def livewire_fixtures():
    ev = livewire_events()
    dump("livewire.json", {"meta": meta("gdelt"), "data": {"classifier": "mock", "events": list(reversed(ev))}})
    frames = [{"type": "hello", "data": {"classifier": "mock", "poll_minutes": 15, "server_time": NOW, "backlog": ev[:2]}}]
    for e in ev[2:]:
        frames.append({"type": "anomaly" if e["is_anomaly"] else "event", "data": e})
    frames.append({"type": "heartbeat", "data": {"server_time": NOW, "next_poll_at": "2026-09-26T12:15:00Z", "events_total": len(ev)}})
    dump("ws_livewire.json", frames)


# ---------------------------------------------------------------- command
def command_fixtures():
    dump("command_request.json", {"text": "shock afg cultivation -95%"})
    dump("command.json", {"meta": meta(), "data": {
        "text": "shock afg cultivation -95%", "intent": "shock",
        "params": {"drug": "heroin", "iso3": "AFG", "iso3_b": None, "year": None, "limit": None, "predict": None,
                   "shocks": [{"type": "cultivation", "iso3": "AFG", "drug": "heroin", "value": 0.05}]},
        "confidence": 0.97, "parser": "rules", "message": "Shock: Afghanistan opium cultivation x0.05"}})


# ---------------------------------------------------------------- meta
def meta_fixture():
    srcs = [
        {**SOURCES["wb_wdi"], "status": "live", "retrieved_at": NOW, "last_updated": "2026-07-13", "latest_year": 2025},
        {**SOURCES["wb_wgi"], "status": "live", "retrieved_at": NOW, "last_updated": "2026-09-25", "latest_year": 2025},
        {**SOURCES["unodc_ids"], "status": "unavailable", "retrieved_at": None, "last_updated": None, "latest_year": None,
         "note": "Download requires registration; edges built from annex and published route tables."},
        {**SOURCES["unodc_wdr_annex"], "status": "cached", "retrieved_at": NOW, "last_updated": "2026-06-26", "latest_year": 2024},
        {**SOURCES["gitoc_ocindex"], "status": "cached", "retrieved_at": NOW, "last_updated": "2025", "latest_year": 2025},
        {**SOURCES["hri_gshr"], "status": "fallback", "retrieved_at": NOW, "last_updated": "2024-10", "latest_year": 2024},
        {**SOURCES["cepii_geodist"], "status": "cached", "retrieved_at": NOW, "last_updated": None, "latest_year": None},
        {**SOURCES["gdelt"], "status": "live", "retrieved_at": NOW, "last_updated": None, "latest_year": 2026},
    ]
    data = {"drugs": [{"id": "cocaine", "label": "Cocaine / crack", "harm_weight": 1.0},
                      {"id": "heroin", "label": "Heroin / opiates", "harm_weight": 1.3},
                      {"id": "meth", "label": "Methamphetamine", "harm_weight": 1.1},
                      {"id": "cannabis", "label": "Cannabis", "harm_weight": 0.3}],
            "observed_years": list(range(2011, 2025)), "predicted_years": [2025], "risk_years": list(range(2012, 2026)),
            "latest_observed_year": 2024, "model_version": MODEL_VERSION, "livewire_classifier": "mock",
            "sources": srcs}
    dump("meta.json", {"meta": meta("wb_wdi", "wb_wgi"), "data": data})


def main():
    countries = fetch_countries()
    dump("countries.json", {"meta": meta("wb_wdi"), "data": countries})
    obs = routes_fixtures()
    rows = risk_rows()
    risk_fixture(rows)
    pl = prices()
    dump("prices.json", {"meta": meta("unodc_wdr_annex"), "data": {"series": pl}})
    country_fixture(countries, obs, rows, pl)
    simulate_fixtures()
    afghan_fixture()
    metrics_fixture()
    livewire_fixtures()
    command_fixtures()
    meta_fixture()


if __name__ == "__main__":
    main()
