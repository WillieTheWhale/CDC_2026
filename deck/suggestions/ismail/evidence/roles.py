# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Classify every country as producer / transit / destination per drug and year.

Input: TRACE API export (routes_observed.json, cultivation.json). Works on the committed
20-country sample (backend/tests/data/api_sample) or the full export (backend/data/processed/api).

Method
- in_kg / out_kg: sum of corridor volumes entering / leaving the country for that drug-year.
- prod_kg: cultivation-based production at origin (coca ha x 7 kg/ha cocaine; opium t x 100 kg
  heroin-equivalent), same constants as backend/trace_backend/model/edges.py.
- role:
    producer     prod_kg > 0, or it only sends (in_kg == 0, out_kg > 0)
    destination  out_share = out/(in+out) < 0.20
    transit      otherwise (substantial flow both in and out)
- hub_share: (in_kg + out_kg) as a share of all corridor volume for that drug-year, i.e. how
  central the country is in that drug's network.
- emerging: hub_share averaged over the latest 3 years is >= 1.5x the prior 3 years and >= 3%.
Caveat: corridor kg is seizure-anchored, so a country that seizes more also looks bigger.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

COCA_KG_PER_HA = 7.0
OPIUM_T_TO_HEROIN_KG = 100.0
DEST_MAX_OUT_SHARE = 0.20


def load(api_dir: Path):
    routes = json.loads((api_dir / "routes_observed.json").read_text())
    rows = [e for yr in routes.values() for e in yr]
    edges = pd.DataFrame(rows)[["from", "to", "drug", "year", "kg", "confidence"]]
    cult = json.loads((api_dir / "cultivation.json").read_text())
    crows = [r for lst in cult.values() for r in lst]
    c = pd.DataFrame(crows)
    c["drug"] = c["crop"].map({"coca": "cocaine", "opium_poppy": "heroin"})
    c["prod_kg"] = c.apply(
        lambda r: (r["hectares"] or 0) * COCA_KG_PER_HA if r["drug"] == "cocaine"
        else (r.get("production_t") or 0) * OPIUM_T_TO_HEROIN_KG, axis=1)
    prod = c.groupby(["iso3", "drug", "year"], as_index=False)["prod_kg"].sum()
    countries = pd.DataFrame(json.loads((api_dir / "countries.json").read_text()))
    return edges, prod, countries


def classify(edges: pd.DataFrame, prod: pd.DataFrame) -> pd.DataFrame:
    inflow = edges.groupby(["to", "drug", "year"])["kg"].sum().rename("in_kg")
    inflow.index.names = ["iso3", "drug", "year"]
    outflow = edges.groupby(["from", "drug", "year"])["kg"].sum().rename("out_kg")
    outflow.index.names = ["iso3", "drug", "year"]
    df = pd.concat([inflow, outflow], axis=1).fillna(0).reset_index()
    df = df.merge(prod, on=["iso3", "drug", "year"], how="left").fillna({"prod_kg": 0})
    tot = edges.groupby(["drug", "year"])["kg"].sum().rename("drug_total") * 2  # each kg counted at both ends
    df = df.merge(tot.reset_index(), on=["drug", "year"], how="left")
    df["out_share"] = (df["out_kg"] / (df["in_kg"] + df["out_kg"])).fillna(0)
    df["hub_share"] = ((df["in_kg"] + df["out_kg"]) / df["drug_total"]).fillna(0)

    def role(r):
        if r["prod_kg"] > 0 or (r["in_kg"] == 0 and r["out_kg"] > 0):
            return "producer"
        if r["out_share"] < DEST_MAX_OUT_SHARE:
            return "destination"
        return "transit"

    df["role"] = df.apply(role, axis=1)
    return df.drop(columns="drug_total").sort_values(["iso3", "drug", "year"]).reset_index(drop=True)


def emerging(df: pd.DataFrame, window: int = 3, ratio: float = 1.5, floor: float = 0.03) -> pd.DataFrame:
    out = []
    last = df["year"].max()
    for (iso, drug), g in df.groupby(["iso3", "drug"]):
        s = g.set_index("year")["hub_share"].reindex(range(df["year"].min(), last + 1), fill_value=0)
        recent = s.loc[last - window + 1:last].mean()
        prior = s.loc[last - 2 * window + 1:last - window].mean()
        # year the rise started: first year in the last 6 whose share exceeds prior mean by 50%
        start = next((y for y in range(last - 2 * window + 1, last + 1) if s.loc[y] >= ratio * max(prior, 1e-9)), None)
        out.append({"iso3": iso, "drug": drug, "prior_share": round(prior, 4), "recent_share": round(recent, 4),
                    "ratio": round(recent / prior, 2) if prior > 0 else None,
                    "emerging": bool(recent >= floor and (prior == 0 or recent / prior >= ratio)),
                    "rise_start": start})
    return pd.DataFrame(out).sort_values("recent_share", ascending=False)


def role_switches(df: pd.DataFrame) -> pd.DataFrame:
    """Years where a country's role for a drug changes (after smoothing 1-year blips)."""
    res = []
    for (iso, drug), g in df.groupby(["iso3", "drug"]):
        roles = g.set_index("year")["role"]
        prev = None
        for y, r in roles.items():
            nxt = roles.get(y + 1)
            if prev is not None and r != prev and (nxt is None or nxt == r):
                res.append({"iso3": iso, "drug": drug, "year": y, "from_role": prev, "to_role": r})
            if nxt is None or nxt == r or prev is None:
                prev = r
    return pd.DataFrame(res)


if __name__ == "__main__":
    api = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/home/claude/CDC_2026/backend/tests/data/api_sample")
    edges, prod, countries = load(api)
    roles = classify(edges, prod)
    roles.to_csv("out/roles.csv", index=False)
    em = emerging(roles)
    em.to_csv("out/emerging.csv", index=False)
    sw = role_switches(roles)
    sw.to_csv("out/role_switches.csv", index=False)
    latest = roles[roles.year == roles.year.max()]
    print(latest.pivot_table(index="iso3", columns="drug", values="role", aggfunc="first").fillna("-"))
    print("\nEmerging hubs:\n", em[em.emerging].to_string(index=False))
    print("\nRole switches:\n", sw.to_string(index=False))
