# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""World Bank profiles by trafficking role, and before/after snapshots for countries whose role grew.

Exploratory: on the 20-country sample, each role has only a handful of countries, so treat the
differences as descriptive. Rerun on the full export for real tests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import kruskal

KEY = {
    "VC.IHR.PSRC.P5": "Homicide rate (per 100k)",
    "GOV_WGI_RL.EST": "Rule of law (-2.5 to 2.5)",
    "GOV_WGI_CC.EST": "Control of corruption (-2.5 to 2.5)",
    "NY.GDP.PCAP.PP.KD": "GDP per capita, PPP",
    "SL.UEM.1524.ZS": "Youth unemployment (%)",
    "SI.POV.DDAY": "Poverty at $3/day (%)",
    "SH.XPD.CHEX.PC.CD": "Health spending per capita (US$)",
    "IS.SHP.GOOD.TU": "Container port traffic (TEU)",
    "NE.TRD.GNFS.ZS": "Trade (% of GDP)",
}


def wb_long(api: Path) -> pd.DataFrame:
    ind = json.loads((api / "indicators.json").read_text())
    rows = [(iso, code, y, v) for iso, d in ind.items() for code, s in d.items() for y, v in s]
    return pd.DataFrame(rows, columns=["iso3", "code", "year", "value"])


def role_profiles(roles: pd.DataFrame, wb: pd.DataFrame) -> pd.DataFrame:
    # One role per country-year: the role it plays for its biggest drug by throughput that year.
    r = roles.assign(thru=roles.in_kg + roles.out_kg).sort_values("thru").groupby(["iso3", "year"]).tail(1)
    wide = wb[wb.code.isin(KEY)].pivot_table(index=["iso3", "year"], columns="code", values="value").reset_index()
    m = r[["iso3", "year", "role"]].merge(wide, on=["iso3", "year"], how="left")
    # Country-years are not independent: average each country within each role it held, so every
    # country counts once per role in the test.
    m = m.groupby(["iso3", "role"], as_index=False).mean(numeric_only=True)
    out = []
    for code, label in KEY.items():
        groups = {role: g[code].dropna() for role, g in m.groupby("role")}
        p = None
        if all(len(v) > 2 for v in groups.values()) and len(groups) > 1:
            p = kruskal(*groups.values()).pvalue
        row = {"indicator": label, **{f"{k} (median)": round(v.median(), 2) for k, v in groups.items()},
               "kruskal_p": None if p is None else float(f"{p:.2g}")}
        row["countries"] = {k: sorted(m.loc[m.role == k, "iso3"].unique()) for k in groups}
        out.append(row)
    return pd.DataFrame(out)


def snapshot(wb: pd.DataFrame, iso: str, before: int, after: int) -> pd.DataFrame:
    s = wb[(wb.iso3 == iso) & wb.code.isin(KEY)]
    rows = []
    for code, label in KEY.items():
        x = s[s.code == code].set_index("year")["value"]
        b = x[x.index <= before].iloc[-1] if (x.index <= before).any() else None
        a = x[x.index <= after].iloc[-1] if (x.index <= after).any() else None
        rows.append({"indicator": label, f"{iso} {before}": b, f"{iso} {after}": a,
                     "change_%": None if not b or a is None else round(100 * (a - b) / abs(b), 1)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    api = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/home/claude/CDC_2026/backend/tests/data/api_sample")
    roles = pd.read_csv("out/roles.csv")
    wb = wb_long(api)
    prof = role_profiles(roles, wb)
    prof.to_csv("out/role_profiles.csv", index=False)
    pd.set_option("display.width", 200)
    print(prof.drop(columns="countries").to_string(index=False))
    print(prof.iloc[0]["countries"])
    for iso, b, a in [("ECU", 2015, 2023), ("MMR", 2019, 2023), ("COL", 2014, 2023)]:
        snap = snapshot(wb, iso, b, a)
        snap.to_csv(f"out/snapshot_{iso}.csv", index=False)
        print("\n", snap.to_string(index=False))
