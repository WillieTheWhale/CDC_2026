# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Source registry for citations in API `meta` responses (see docs/DATA_SOURCES.md)."""
from __future__ import annotations

SOURCES: dict[str, dict] = {
    "wb_wdi": {"id": "wb_wdi", "name": "World Bank World Development Indicators (API source 2)",
               "url": "https://api.worldbank.org/v2/sources/2",
               "citation": "World Bank, World Development Indicators, via Indicators API v2 (CC BY 4.0)."},
    "wb_wgi": {"id": "wb_wgi", "name": "World Bank Worldwide Governance Indicators (API source 3)",
               "url": "https://api.worldbank.org/v2/sources/3",
               "citation": "World Bank, Worldwide Governance Indicators, via Indicators API v2 (CC BY 4.0)."},
    "unodc_ids": {"id": "unodc_ids", "name": "UNODC Individual Drug Seizures (IDS), public release",
                  "url": "https://dmp.unodc.org/downloadIDS",
                  "citation": "UNODC Drugs Monitoring Platform, Individual Drug Seizures 2011-2026."},
    "unodc_wdr_annex": {"id": "unodc_wdr_annex", "name": "UNODC World Drug Report 2026, statistical annex",
                        "url": "https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html",
                        "citation": "UNODC, World Drug Report 2026, Statistical Annex (tables 6.x, 7.1, 8.1, 8.3, 11.1)."},
    "unodc_routes": {"id": "unodc_routes", "name": "UNODC / EUDA documented trafficking corridors (TRACE transcription)",
                     "url": "https://github.com/WillieTheWhale/CDC_2026/blob/main/backend/trace_backend/seed/corridors.csv",
                     "citation": "Transcribed from WDR 2026 annex route maps 7.2-7.4 and UNODC/EUDA reports; see seed/README.md."},
    "gitoc_ocindex": {"id": "gitoc_ocindex", "name": "GI-TOC Global Organized Crime Index (2021, 2023, 2025)",
                      "url": "https://ocindex.net/downloads",
                      "citation": "Global Initiative Against Transnational Organized Crime, Global Organized Crime Index."},
    "hri_gshr": {"id": "hri_gshr", "name": "Harm Reduction International, Global State of Harm Reduction 2024",
                 "url": "https://hri.global/wp-content/uploads/2024/10/HRI-GSHR-2024_Full-Report_Final.pdf",
                 "citation": "Harm Reduction International (2024), The Global State of Harm Reduction, Table 1."},
    "cepii_geodist": {"id": "cepii_geodist", "name": "CEPII GeoDist",
                      "url": "https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=6",
                      "citation": "Mayer and Zignago (2011), Notes on CEPII's distances measures: the GeoDist database."},
    "natural_earth": {"id": "natural_earth", "name": "Natural Earth 1:10m populated places and admin-0 label points",
                      "url": "https://github.com/nvkelso/natural-earth-vector",
                      "citation": "Natural Earth (public domain), ne_10m_populated_places_simple and "
                                  "ne_10m_admin_0_countries; placement anchors for the estimated-flow layer only."},
    "gdelt": {"id": "gdelt", "name": "GDELT DOC 2.0 API", "url": "https://api.gdeltproject.org/api/v2/doc/doc",
              "citation": "The GDELT Project, DOC 2.0 API (article metadata and publication dates)."},
    # Evidence drilldown (SQLite v2 research, market and health layers)
    "trace_research_v2": {"id": "trace_research_v2", "name": "TRACE research layer (SQLite v2 research_* tables)",
                          "url": "https://github.com/WillieTheWhale/CDC_2026/blob/main/data_collection/schema_v2.md",
                          "citation": "TRACE retrospective research values, each linked to its exact source rows."},
    "unodc_wdr_editions": {"id": "unodc_wdr_editions",
                           "name": "UNODC World Drug Report statistical annex, editions 2012, 2015, 2020 and 2026",
                           "url": "https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026.html",
                           "citation": "UNODC, World Drug Report statistical annexes (seizure and price/purity "
                                       "workbooks, each edition as published)."},
    "unodc_wdr_health": {"id": "unodc_wdr_health", "name": "UNODC World Drug Report 2026 annex 1.2 and 1.4 (prevalence)",
                         "url": "https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026.html",
                         "citation": "UNODC, World Drug Report 2026, Statistical Annex tables 1.2 and 1.4."},
    "un_sdg_351": {"id": "un_sdg_351", "name": "UN SDG indicator 3.5.1 treatment intervention coverage",
                   "url": "https://unstats.un.org/SDGAPI/v1/sdg/Indicator/Data?indicator=3.5.1&pageSize=5000",
                   "citation": "UN Statistics Division / UNODC, SDG Global Database, indicator 3.5.1 (SH_SUD_TREAT)."},
    "cdc_vsrr_overdose": {"id": "cdc_vsrr_overdose", "name": "CDC NCHS VSRR provisional drug overdose death counts",
                          "url": "https://data.cdc.gov/api/views/xkb8-kh2a.json",
                          "citation": "CDC National Center for Health Statistics, Vital Statistics Rapid Release, "
                                      "Provisional Drug Overdose Death Counts (xkb8-kh2a)."},
}


def refs(*ids: str) -> list[dict]:
    return [SOURCES[i] for i in ids]
