# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Agriculture and drug crops.

1. Producer profile: do coca/opium producers differ from other countries (and from income peers) on
   World Bank agriculture indicators (means 2011-2023, pulled live from the World Bank API)?
2. Legal crop prices vs drug crops: does a fall in the real price of the main legal cash crop come
   before a rise in coca / opium area (year-over-year log changes, Spearman, lag 0 and 1)?
Data: out/wb_ag_means.json (World Bank API, source 2), out/pinksheet_real_1995_2025.json (Pink Sheet),
cultivation + countries from the team's trace.sqlite release (UNODC).
"""
import json
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr

DB = sys.argv[1] if len(sys.argv) > 1 else "trace.sqlite"
c = sqlite3.connect(DB)
countries = pd.read_sql("select iso3, name, income_group from countries", c).set_index("iso3")
cult = pd.read_sql("select iso3, crop, year, hectares from cultivation", c)
producers = sorted(cult[(cult.year >= 2011) & (cult.hectares >= 1000)].iso3.unique())

LABELS = {"NV.AGR.TOTL.ZS": "Agriculture, % of GDP", "SL.AGR.EMPL.ZS": "Farm jobs, % of employment",
          "SP.RUR.TOTL.ZS": "Rural population, %", "AG.YLD.CREL.KG": "Cereal yield, kg/ha",
          "AG.LND.AGRI.ZS": "Agricultural land, % of area", "AG.LND.FRST.ZS": "Forest, % of area",
          "forest_chg_pp": "Forest change 2011-21, pp", "TX.VAL.FOOD.ZS.UN": "Food, % of goods exports",
          "SN.ITK.DEFC.ZS": "Undernourishment, %"}
ag = pd.DataFrame(json.load(open("out/wb_ag_means.json"))).T
ag = ag[ag.index.isin(countries.index)]  # drop World Bank aggregates
ag["producer"] = ag.index.isin(producers)
ag["income"] = countries.income_group.reindex(ag.index)
peers = ag[ag.income.isin(ag.loc[ag.producer, "income"].unique())]


def compare(df, other_label):
    rows = []
    for k, lab in LABELS.items():
        a, b = df.loc[df.producer, k].dropna(), df.loc[~df.producer, k].dropna()
        rows.append({"indicator": lab, "producers": round(a.median(), 1), other_label: round(b.median(), 1),
                     "n": f"{len(a)}/{len(b)}", "p": float(f"{mannwhitneyu(a, b).pvalue:.2g}")})
    return pd.DataFrame(rows)


pd.set_option("display.width", 200)
print("Producers:", producers)
t1, t2 = compare(ag, "all others"), compare(peers, "income peers")
print(t1.to_string(index=False)); print(); print(t2.to_string(index=False))
t1.merge(t2[["indicator", "income peers", "p"]], on="indicator", suffixes=("", "_peers")).to_csv(
    "out/agri_producer_profile.csv", index=False)
print("\nProducer detail:\n", ag.loc[producers, list(LABELS)].round(1).to_string())

# ---- 2. legal crop prices vs drug crop area ----
ps = json.load(open("out/pinksheet_real_1995_2025.json"))
px = pd.DataFrame(ps["data"], columns=ps["cols"]).set_index("year")
PAIRS = [("COL", "coca", "Coffee, Arabica"), ("PER", "coca", "Coffee, Arabica"), ("BOL", "coca", "Coffee, Arabica"),
         ("COL", "coca", "Cocoa"), ("PER", "coca", "Cocoa"), ("AFG", "opium_poppy", "Wheat, US HRW"),
         ("MMR", "opium_poppy", "Rice, Thai 5%"), ("LAO", "opium_poppy", "Rice, Thai 5%"),
         ("MEX", "opium_poppy", "Maize")]
rows, pooled = [], []
for iso, crop, comm in PAIRS:
    s = cult[(cult.iso3 == iso) & (cult.crop == crop)].groupby("year").hectares.sum().sort_index()
    s = s[s > 0]
    d = pd.DataFrame({"area": np.log(s)}).join(np.log(px[comm]).rename("price"), how="inner")
    d = d.reindex(range(d.index.min(), d.index.max() + 1))
    dd = d.diff()
    for lag in (0, 1):
        x = pd.concat([dd.area, dd.price.shift(lag)], axis=1).dropna()
        if len(x) < 8:
            continue
        r, p = spearmanr(x.iloc[:, 0], x.iloc[:, 1])
        rows.append({"country": iso, "crop": crop, "legal crop": comm, "lag_years": lag,
                     "years": f"{int(x.index.min())}-{int(x.index.max())}", "n": len(x),
                     "spearman_r": round(r, 2), "p": round(p, 3)})
        if lag == 1 and comm.startswith("Coffee"):
            pooled.append(x.assign(iso=iso))
res = pd.DataFrame(rows)
print("\nYear-over-year change in drug-crop area vs change in legal crop price (real):")
print(res.to_string(index=False))
res.to_csv("out/agri_price_vs_cultivation.csv", index=False)
pc = pd.concat(pooled)
r, p = spearmanr(pc.iloc[:, 0], pc.iloc[:, 1])
print(f"\nPooled coca (COL, PER, BOL) vs coffee price a year earlier: r={r:.2f}, p={p:.3f}, n={len(pc)}")
