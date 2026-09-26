# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Registry of every World Bank indicator TRACE uses (mirrors docs/DATA_SOURCES.md).

Codes were verified live on 2026-09-26. Governance uses GOV_WGI_*.EST with source 3;
refugees use SM.POP.RHCR.EA/EO (source 2). Never use archive source 57.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Indicator:
    code: str
    source_id: int
    role: str          # governance | logistics | gravity | vulnerability | outcome
    feature: str       # short snake_case name used in models
    label: str         # human label for the UI
    unit: str
    forward_fill: bool = False  # surveyed every few years (LPI): forward-fill and flag imputed
    public: bool = True         # shown in country profiles (False = model-only feature)


INDICATORS: list[Indicator] = [
    # Governance (WGI, source 3)
    Indicator("GOV_WGI_CC.EST", 3, "governance", "control_corruption", "Control of Corruption", "index (-2.5 to 2.5)"),
    Indicator("GOV_WGI_RL.EST", 3, "governance", "rule_of_law", "Rule of Law", "index (-2.5 to 2.5)"),
    Indicator("GOV_WGI_GE.EST", 3, "governance", "gov_effectiveness", "Government Effectiveness", "index (-2.5 to 2.5)"),
    Indicator("GOV_WGI_PV.EST", 3, "governance", "political_stability", "Political Stability / No Violence",
              "index (-2.5 to 2.5)"),
    # Logistics (WDI, source 2)
    Indicator("LP.LPI.OVRL.XQ", 2, "logistics", "lpi_overall", "Logistics Performance Index (overall)", "1-5",
              forward_fill=True),
    # Customs efficiency is a detection-bias control inside the model only. It is never exposed in
    # API responses or rankings (design boundary: do not show where enforcement is weak).
    Indicator("LP.LPI.CUST.XQ", 2, "logistics", "lpi_customs", "LPI customs efficiency", "1-5",
              forward_fill=True, public=False),
    Indicator("IS.SHP.GOOD.TU", 2, "logistics", "port_teu", "Container port traffic", "TEU"),
    Indicator("IS.AIR.PSGR", 2, "logistics", "air_passengers", "Air passengers carried", "passengers"),
    Indicator("NE.TRD.GNFS.ZS", 2, "logistics", "trade_gdp", "Trade", "% of GDP"),
    # Gravity
    Indicator("NY.GDP.MKTP.CD", 2, "gravity", "gdp", "GDP (current US$)", "US$"),
    Indicator("NY.GDP.PCAP.PP.KD", 2, "gravity", "gdp_pc_ppp", "GDP per capita, PPP (constant 2021 int$)", "int$"),
    Indicator("SP.POP.TOTL", 2, "gravity", "population", "Population", "people"),
    # Vulnerability
    Indicator("SL.UEM.1524.ZS", 2, "vulnerability", "youth_unemployment", "Youth unemployment (15-24)", "%"),
    Indicator("SL.UEM.NEET.ZS", 2, "vulnerability", "youth_neet", "Youth not in education, employment or training",
              "%"),
    Indicator("SI.POV.DDAY", 2, "vulnerability", "poverty", "Poverty at $3.00/day (2021 PPP)", "% of population"),
    Indicator("SI.POV.GINI", 2, "vulnerability", "gini", "Gini index", "index"),
    Indicator("SH.XPD.CHEX.PC.CD", 2, "vulnerability", "health_exp_pc", "Health expenditure per capita", "US$"),
    Indicator("FX.OWN.TOTL.ZS", 2, "vulnerability", "account_ownership", "Account ownership", "% age 15+"),
    Indicator("BX.TRF.PWKR.DT.GD.ZS", 2, "vulnerability", "remittances_gdp", "Personal remittances received",
              "% of GDP"),
    # Outcomes (validation targets for the spillover hypothesis)
    Indicator("VC.IHR.PSRC.P5", 2, "outcome", "homicide_rate", "Intentional homicides", "per 100,000"),
    Indicator("SH.HIV.INCD.ZS", 2, "outcome", "hiv_incidence", "HIV incidence (15-49)", "per 1,000 uninfected"),
    Indicator("VC.BTL.DETH", 2, "outcome", "battle_deaths", "Battle-related deaths", "people"),
    Indicator("SM.POP.RHCR.EA", 2, "outcome", "refugees_asylum", "Refugees by country of asylum", "people"),
    Indicator("SM.POP.RHCR.EO", 2, "outcome", "refugees_origin", "Refugees by country of origin", "people"),
]

BY_CODE = {i.code: i for i in INDICATORS}
BY_FEATURE = {i.feature: i for i in INDICATORS}
ROLE_LABELS = {"governance": "Governance", "logistics": "Connectivity", "gravity": "Market size",
               "vulnerability": "Vulnerability", "outcome": "Harm outcomes"}
