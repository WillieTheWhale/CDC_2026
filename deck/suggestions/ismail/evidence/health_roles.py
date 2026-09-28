# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Does being on a drug route go with more local use, more HIV among people who inject, and less
treatment? Tests the deck's claim that "transit countries become consumer markets".

Roles come from the documented corridor table (backend/trace_backend/seed/corridors.csv, all countries):
producer = cultivates the crop (cocaine: coca; heroin: opium poppy) at >= 1,000 ha in 2011+;
transit = has documented inbound AND outbound corridors for the drug; destination = inbound only;
off-route = no documented corridor for that drug.
Health data: team's trace.sqlite v2 (UNODC WDR 2026 annex prevalence and PWID tables; UN SDG 3.5.1).
Cross-sectional and descriptive: latest observation per country, compared with and without an income
adjustment (rank regression on log GDP per capita). Not causal.
"""
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy.stats import kruskal, mannwhitneyu, spearmanr

DB, SEED = sys.argv[1], sys.argv[2]
c = sqlite3.connect(DB)
seed = pd.read_csv(SEED, comment="#")
cult = pd.read_sql("select iso3, crop, year, hectares from cultivation", c)
gdp = pd.read_sql("select iso3, avg(value) g from wb_indicators where code='NY.GDP.PCAP.PP.KD' and year between 2015 and 2023 group by iso3", c).set_index("iso3").g
countries = pd.read_sql("select iso3, name from countries", c).set_index("iso3").name


def roles(drug, crop):
    s = seed[seed.drug == drug]
    outs, ins = set(s["from"]), set(s["to"])
    prod = set(cult[(cult.crop == crop) & (cult.year >= 2011) & (cult.hectares >= 1000)].iso3)
    r = pd.Series("off-route", index=countries.index)
    r[r.index.isin(ins)] = "destination"
    r[r.index.isin(ins & outs)] = "transit"
    r[r.index.isin(outs - ins)] = "transit"  # departure-only non-producers are staging countries
    r[r.index.isin(prod)] = "producer"
    return r


prev = pd.read_sql("""select iso3, year, substance, age_group, value_pct from health_prevalence
    where population='general_population' and reference_period='past_year' and sex='all' and value_pct is not null""", c)
top_age = prev.age_group.value_counts().index[0]
prev = prev[prev.age_group == top_age]


def latest(df, sub):
    d = df[df.substance == sub].sort_values("year").groupby("iso3").tail(1).set_index("iso3")
    return d.value_pct


def adjust(y):
    """Residual of rank(y) on rank(log GDP pc): what's left after income."""
    d = pd.concat([y, np.log(gdp)], axis=1, keys=["y", "g"]).dropna()
    ry, rg = d.y.rank(), d.g.rank()
    b = np.polyfit(rg, ry, 1)
    return ry - np.polyval(b, rg)


def table(y, role, label):
    d = pd.concat([y.rename("y"), role.rename("role")], axis=1, join="inner").dropna()
    res = adjust(d.y)
    d["adj"] = res
    out = d.groupby("role").agg(n=("y", "size"), median=("y", "median"), income_adjusted_rank=("adj", "mean")).round(2)
    groups = [g.adj.dropna() for _, g in d.groupby("role") if len(g) > 2]
    p = kruskal(*groups).pvalue if len(groups) > 1 else np.nan
    t = d[d.role == "transit"].adj.dropna(); o = d[d.role == "off-route"].adj.dropna()
    p2 = mannwhitneyu(t, o).pvalue if len(t) > 2 and len(o) > 2 else np.nan
    print(f"\n{label}  (latest year per country; age group {top_age})")
    print(out.to_string())
    print(f"  income-adjusted difference across roles p={p:.2g}; transit vs off-route p={p2:.2g}")
    return out.assign(measure=label, p_roles=p, p_transit_vs_offroute=p2)


pd.set_option("display.width", 200)
coc, her = roles("cocaine", "coca"), roles("heroin", "opium_poppy")
outs = [table(latest(prev, "Cocaine"), coc, "Cocaine, past-year use % of adults"),
        table(latest(prev, "Opiates"), her, "Opiates, past-year use % of adults")]

pwid = pd.read_sql("select iso3, year, metric, value, unit, sex from health_pwid where value is not null", c)
print("\nPWID metrics:", pwid.metric.value_counts().head(8).to_dict())
hiv = pwid[(pwid.metric.str.contains("hiv", case=False)) & (pwid.sex.isin(["all", "total"]) | pwid.sex.isna())]
hiv = hiv.sort_values("year").groupby("iso3").tail(1).set_index("iso3").value
outs.append(table(hiv, her, "HIV prevalence among people who inject drugs, %"))

tc = pd.read_sql("select iso3, year, substance_group, sex, value_pct, nature_code from health_treatment_coverage where value_pct is not null", c)
print("\nTreatment coverage groups:", tc.substance_group.value_counts().to_dict(), tc.sex.value_counts().to_dict())
allg = tc[(tc.sex == "BOTHSEX") & (tc.substance_group == "DRUG_TOTAL")]
cov = allg.sort_values("year").groupby("iso3").tail(1).set_index("iso3").value_pct
anyrole = pd.Series("off-route", index=countries.index)
for r in (coc, her):
    anyrole[(r == "destination") & (anyrole == "off-route")] = "destination"
for r in (coc, her):
    anyrole[r == "transit"] = "transit"
for r in (coc, her):
    anyrole[r == "producer"] = "producer"
outs.append(table(cov, anyrole, "Treatment coverage for drug use disorders, % (SDG 3.5.1)"))
pd.concat(outs).to_csv("out/health_by_role.csv")
