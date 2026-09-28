# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Route-level vs country-level: do drug corridors follow food trade once we account for
who exports and who imports?  All countries, 2019.

Corridors: backend/trace_backend/seed/corridors.csv (234 documented corridors from UNODC World Drug
Report route maps and texts; independent of seizure-based volume estimates).
Trade: UN Comtrade public API, SITC Rev.4, 2019. Exports reported by the origin; when the origin did
not report, the destination's reported imports (mirror) are used. Food = SITC section 0.
Distance/contiguity: CEPII (team's trace.sqlite release).
Three tests: (1) within origin, (2) within destination, (3) two-way fixed-effects logit.
Country-pair level only (TRACE design boundary: nothing on concealment or enforcement gaps).
"""
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm, wilcoxon

DB, SEED = sys.argv[1], sys.argv[2]
tr = pd.read_csv("out/comtrade_2019_s4_all.csv")
ref = pd.read_csv("out/comtrade_reporters.csv").set_index("id").iso3
tr["rep"] = tr.reporter.map(ref); tr["par"] = tr.partner.map(ref)
tr = tr.dropna(subset=["rep", "par"])
x = tr[tr.flow == "X"].rename(columns={"rep": "o", "par": "d"})
m = tr[tr.flow == "M"].rename(columns={"rep": "d", "par": "o"})  # mirror: importer's view
piv = lambda df: df.pivot_table(index=["o", "d"], columns="cmd", values="usd", aggfunc="sum")
X, M = piv(x), piv(m)
T = X.combine_first(M).rename(columns={"TOTAL": "exports", "0": "food"})
T = T[T.exports > 0].reset_index()
T["food"] = T.food.fillna(0)
T["food_share"] = (T.food / T.exports).clip(0, 1)
T["reported_by"] = np.where(pd.MultiIndex.from_frame(T[["o", "d"]]).isin(X.index), "origin", "mirror")

c = sqlite3.connect(DB)
dist = pd.read_sql("select iso_o o, iso_d d, dist, contig from distances", c).drop_duplicates(["o", "d"])
countries = set(pd.read_sql("select iso3 from countries", c).iso3)
T = T[T.o.isin(countries) & T.d.isin(countries) & (T.o != T.d)].merge(dist, on=["o", "d"], how="left")
T["dist"] = T.dist.fillna(T.dist.median()); T["contig"] = T.contig.fillna(0)

seed = pd.read_csv(SEED, comment="#")
cor = seed.groupby(["from", "to"]).drug.apply(set).to_dict()
T["corridor"] = [int((o, d) in cor) for o, d in zip(T.o, T.d)]
for dr in ["cocaine", "heroin", "meth", "cannabis"]:
    T[dr] = [int(dr in cor.get((o, d), set())) for o, d in zip(T.o, T.d)]
T["log_exports"] = np.log1p(T.exports / 1e6); T["log_dist"] = np.log(T.dist)
T.to_csv("out/trade_full_pairs.csv", index=False)
missing = [k for k in cor if not ((T.o == k[0]) & (T.d == k[1])).any()]
print(f"{len(T):,} country pairs with 2019 trade; {T.corridor.sum()} of {len(cor)} documented corridors matched "
      f"({len(missing)} have no recorded trade: {missing[:12]})")
print(f"mirror data used for {(T.reported_by=='mirror').mean():.0%} of pairs")
print("median food share: corridor pairs %.2f vs other pairs %.2f" %
      (T[T.corridor == 1].food_share.median(), T[T.corridor == 0].food_share.median()))


def within(df, group, target, var):
    d = []
    for k, g in df.groupby(group):
        if g[target].nunique() < 2:
            continue
        d.append(g.loc[g[target] == 1, var].median() - g.loc[g[target] == 0, var].median())
    d = np.array(d)
    return len(d), int((d > 0).sum()), float(np.median(d)), wilcoxon(d).pvalue if len(d) > 5 else np.nan


def fe_logit(df, target, lam=0.5):
    keep_o = df.groupby("o")[target].max(); keep_d = df.groupby("d")[target].max()
    s = df[df.o.isin(keep_o[keep_o == 1].index) & df.d.isin(keep_d[keep_d == 1].index)].copy()
    base = s[["log_exports", "food_share", "log_dist", "contig"]]
    base = (base - base.mean()) / base.std()
    fe = pd.concat([pd.get_dummies(s.o, prefix="o", drop_first=True),
                    pd.get_dummies(s.d, prefix="d", drop_first=True)], axis=1).astype(float)
    Xm = np.column_stack([np.ones(len(s)), base.values, fe.values]); y = s[target].values
    pen = np.r_[0, np.zeros(base.shape[1]), np.full(fe.shape[1], lam)]  # penalize only the fixed effects
    nll = lambda b: -(y * (Xm @ b) - np.logaddexp(0, Xm @ b)).sum() + (pen * b ** 2).sum()
    grad = lambda b: -Xm.T @ (y - 1 / (1 + np.exp(-(Xm @ b)))) + 2 * pen * b
    b = minimize(nll, np.zeros(Xm.shape[1]), jac=grad, method="L-BFGS-B").x
    pr = 1 / (1 + np.exp(-(Xm @ b)))
    H = Xm.T @ (Xm * (pr * (1 - pr))[:, None]) + np.diag(2 * pen + 1e-8)
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return len(s), int(y.sum()), {n: (np.exp(b[i + 1]), 2 * norm.sf(abs(b[i + 1] / se[i + 1])))
                                  for i, n in enumerate(base.columns)}


rows = []
for target in ["corridor", "cocaine", "heroin", "meth", "cannabis"]:
    o = within(T, "o", target, "food_share"); d = within(T, "d", target, "food_share")
    ev = within(T, "d", target, "log_exports")
    n, pos, res = fe_logit(T, target)
    rows.append({"drug": target, "corridors": int(T[target].sum()),
                 "same exporter: food share higher to corridor dests": f"{o[1]}/{o[0]} (p={o[3]:.2g})",
                 "same importer: food share higher from corridor origins": f"{d[1]}/{d[0]} (p={d[3]:.2g})",
                 "same importer: more total trade with corridor origins": f"{ev[1]}/{ev[0]} (p={ev[3]:.2g})",
                 "FE logit food share OR": f"{res['food_share'][0]:.2f} (p={res['food_share'][1]:.2g})",
                 "FE logit total exports OR": f"{res['log_exports'][0]:.2f} (p={res['log_exports'][1]:.2g})",
                 "FE logit shared border OR": f"{res['contig'][0]:.2f} (p={res['contig'][1]:.2g})",
                 "FE sample": f"{n:,} pairs, {pos} corridors"})
out = pd.DataFrame(rows)
out.to_csv("out/trade_full_results.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
print(out.T.to_string(header=False))
