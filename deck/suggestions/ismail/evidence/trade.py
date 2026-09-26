# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Do drug corridors follow legal trade, and food trade in particular?

Unit: ordered country pairs among the 20 sample countries (380 pairs).
Outcome: the pair is an active TRACE corridor for any drug in 2015-2019 (and per drug).
Predictors: log total exports origin->destination in 2019 (UN Comtrade, HS, reported by origin),
food share of those exports (HS chapters 01-24), log distance and shared border (CEPII).
Country-pair level only: no product-level concealment analysis (TRACE design boundary).
"""
import json
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm, mannwhitneyu

DB = sys.argv[1] if len(sys.argv) > 1 else "trace.sqlite"
ct = pd.read_csv("out/comtrade_2019_exports.csv", dtype={"cmd": str})
tot = ct[ct.cmd == "TOTAL"].set_index(["reporter", "partner"]).usd
food = ct[ct.cmd != "TOTAL"].groupby(["reporter", "partner"]).usd.sum()
fruit = ct[ct.cmd == "08"].set_index(["reporter", "partner"]).usd

B = json.load(open("out/bundle.json"))
isos = sorted(B["countries"])
pairs = pd.DataFrame([(a, b) for a in isos for b in isos if a != b], columns=["o", "d"])
key = pd.MultiIndex.from_frame(pairs)
pairs["exports"] = tot.reindex(key).fillna(0).values
pairs["food"] = food.reindex(key).fillna(0).values
pairs["fruit"] = fruit.reindex(key).fillna(0).values
pairs["food_share"] = np.where(pairs.exports > 0, pairs.food / pairs.exports.clip(lower=1), 0)
dist = pd.read_sql("select iso_o, iso_d, dist, contig from distances", sqlite3.connect(DB)).drop_duplicates(["iso_o", "iso_d"])
pairs = pairs.merge(dist, left_on=["o", "d"], right_on=["iso_o", "iso_d"], how="left").drop(columns=["iso_o", "iso_d"])
pairs["dist"] = pairs.dist.fillna(pairs.dist.median()); pairs["contig"] = pairs.contig.fillna(0)

active = {}
for e in B["edges"]:
    if any(float(v) > 0 for y, v in e["kg"].items() if 2015 <= int(y) <= 2019):
        active.setdefault((e["from"], e["to"]), set()).add(e["drug"])
pairs["corridor"] = [int((o, d) in active) for o, d in zip(pairs.o, pairs.d)]
for drug in ["cocaine", "heroin", "meth", "cannabis"]:
    pairs[drug] = [int(drug in active.get((o, d), set())) for o, d in zip(pairs.o, pairs.d)]


def logit(y, X, names):
    X = np.column_stack([np.ones(len(X)), X])
    nll = lambda b: -(y * (X @ b) - np.logaddexp(0, X @ b)).sum()
    b = minimize(nll, np.zeros(X.shape[1]), method="BFGS").x
    p = 1 / (1 + np.exp(-(X @ b)))
    H = X.T @ (X * (p * (1 - p))[:, None])
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    z = b / se
    return pd.DataFrame({"term": ["const"] + names, "coef": b.round(3), "odds_ratio": np.exp(b).round(2),
                         "p": (2 * norm.sf(abs(z))).round(4)})


pairs["log_exports"] = np.log1p(pairs.exports / 1e6)  # US$ millions
pairs["log_dist"] = np.log(pairs.dist)
pairs["food_share_10pp"] = pairs.food_share * 10
names = ["log_exports", "food_share_10pp", "log_dist", "contig"]
X = (pairs[names] - pairs[names].mean()) / pairs[names].std()  # standardized for stable fit
pd.set_option("display.width", 200)
print(f"{len(pairs)} ordered pairs, {pairs.corridor.sum()} active corridors 2015-2019")
g = pairs.groupby("corridor")[["exports", "food_share"]].median()
print("Median exports (US$ m) and food share by corridor status:\n", (g.assign(exports=g.exports / 1e6)).round(3))
print("Mann-Whitney exports p =", f"{mannwhitneyu(pairs[pairs.corridor==1].exports, pairs[pairs.corridor==0].exports).pvalue:.2g}",
      "| food share p =", f"{mannwhitneyu(pairs[pairs.corridor==1].food_share, pairs[pairs.corridor==0].food_share).pvalue:.2g}")
out = []
for target in ["corridor", "cocaine", "heroin", "meth", "cannabis"]:
    m = logit(pairs[target].values, X.values, names).assign(model=target, n_pos=int(pairs[target].sum()))
    out.append(m)
    print(f"\nLogit: {target} (n positive {int(pairs[target].sum())}), standardized predictors")
    print(m.drop(columns="model").to_string(index=False))
pd.concat(out).to_csv("out/trade_corridor_logit.csv", index=False)
pairs.to_csv("out/trade_pairs.csv", index=False)
coc = pairs[pairs.cocaine == 1].sort_values("food_share", ascending=False)
print("\nCocaine corridors, food share of legal exports on the same pair:\n",
      coc[["o", "d", "food_share"]].assign(exports_m=(coc.exports / 1e6).round(0)).round(2).to_string(index=False))
