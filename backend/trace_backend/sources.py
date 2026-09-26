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
    "gdelt": {"id": "gdelt", "name": "GDELT DOC 2.0 API", "url": "https://api.gdeltproject.org/api/v2/doc/doc",
              "citation": "The GDELT Project, DOC 2.0 API (article metadata and publication dates)."},
}


def refs(*ids: str) -> list[dict]:
    return [SOURCES[i] for i in ids]
