<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# Seed reference tables (committed, small, cited)

These are hand-curated reference tables, not raw data. They exist because the public UNODC
Individual Drug Seizures (IDS) release lists only the **country of seizure**; departure, transit,
and destination fields are restricted-tier (see `docs/BLOCKERS.md`).

## `corridors.csv`: documented trafficking corridors

One row per country-to-country corridor (`drug, from, to`) that UNODC or EUDA publications describe
as a main trafficking flow. `basis` is `map` (drawn on a UNODC route map), `text` (named in report
text), or `map+text`. The WDR route maps are drawn between regions and subregions; the
country-level endpoints are **our transcription** of the countries those maps and texts name as
departure, transit, or recipient countries, so treat them as indicative, as UNODC itself says.

Corridor **volumes are not taken from these documents.** Volumes are estimated each year from
real seizure totals (WDR annex table 7.1, calibrated IDS backcast) and cultivation, as described in
`trace_backend/model/edges.py`.

### Citation keys
| Key | Source |
|---|---|
| WDR2026-7.2.1 | UNODC, World Drug Report 2026, Statistical Annex 7.2.1 "Main methamphetamine trafficking flows as described in reported seizures, 2021-2024" ([link](https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html)) |
| WDR2026-7.3.1 | UNODC, World Drug Report 2026, Statistical Annex 7.3.1 "Main cocaine trafficking flows as described in reported seizures, 2021-2024" ([link](https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html)) |
| WDR2026-7.4.1 | UNODC, World Drug Report 2026, Statistical Annex 7.4.1 "Main heroin trafficking flows as described in reported seizures, 2021-2024" ([link](https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html)) |
| WDR2023-B2 | UNODC, World Drug Report 2023, Booklet 2 (contemporary issues / cannabis markets and trafficking) ([link](https://www.unodc.org/unodc/en/data-and-analysis/wdr-2023_booklet-2.html)) |
| WDR2023-B3 | UNODC, World Drug Report 2023, cocaine market chapter ([link](https://www.unodc.org/unodc/en/data-and-analysis/wdr-2023-online-segment.html)) |
| UNODC-GRC2023 | UNODC, Global Report on Cocaine 2023: Local dynamics, global challenges ([link](https://www.unodc.org/documents/data-and-analysis/cocaine/Global_cocaine_report_2023.pdf)) |
| UNODC-AOT2024 | UNODC Afghan opiate trafficking reports (Afghan Opiate Trade Project / AOTP updates, 2020-2024) ([link](https://www.unodc.org/unodc/en/data-and-analysis/aotp.html)) |
| UNODC-AFGMETH2023 | UNODC, Understanding illegal methamphetamine manufacture in Afghanistan (2023) ([link](https://www.unodc.org/documents/data-and-analysis/briefs/Methamphetamine_Manufacture_in_Afghanistan.pdf)) |
| UNODC-SEA2024 | UNODC, Synthetic Drugs in East and Southeast Asia: latest developments and challenges (2024) ([link](https://www.unodc.org/roseap/uploads/documents/Publications/2024/Synthetic_Drugs_in_East_and_Southeast_Asia_2024.pdf)) |
| UNODC-WA2023 | UNODC, West and Central Africa drug trafficking assessments (2023) ([link](https://www.unodc.org/westandcentralafrica/en/research-and-awareness.html)) |
| EUDA-EDM2024 | EUDA and Europol, EU Drug Markets analyses (cocaine 2022; heroin, methamphetamine, cannabis 2023-2024) ([link](https://www.euda.europa.eu/publications/eu-drug-markets_en)) |

## `route_evidence.csv`, `route_evidence_sources.csv`, `evidence_claims.json`: route evidence

Served by `/api/route-evidence` (`trace_backend/api/route_evidence.py`), which also links each
`/api/routes` edge to its supporting records (`evidence_ids`, direct pairs first).

- `route_evidence.csv` (51 rows) and `route_evidence_sources.csv` (9 publications) are transcribed
  exactly from `frontend/lib/route-evidence.ts`, the frontend team's ChatGPT-assisted curation. Each
  row is a country pair stated explicitly in the cited primary publication (UNODC Global Report on
  Cocaine 2023, UNODC Haiti assessment 2023, EUDA/Europol EU Drug Markets heroin 2024 and cannabis
  2023, UNODC Southern Route booklet 2024, UNODC Nigeria OCTA 2023, UNODC WDR 2026, INCB Report for
  2025, NCB India Annual Report 2023-24) at an exact locator. `period_start`/`period_end` are blank
  when the source gives no evidence period (a publication year is not an observation year).
  Record ids are `drug:FROM:TO:source_id`, as in the frontend. API `pair_type: direct_reported_pair`.
- `corridors.csv` rows are served as `pair_type: interpreted_corridor`: our transcription of
  regional maps and text, not pairs the sources list verbatim. Citation keys are expanded to the
  titles above; a URL is given only where the repo already cites one, otherwise the record's
  `source` is the TRACE transcription itself.
- `evidence_claims.json` is generated once from the archive's `evidence_claims` /
  `evidence_sources` tables (claim type `published_aggregate_corridor_context`, 4 UNODC WDR 2026
  statements) by `python -m trace_backend.api.route_evidence`, so the deploy needs no archive.
  Served as `pair_type: narrative_context` with regional `geography_from`/`geography_to` text and
  never converted to country pairs.

None of these carry volumes or city, road or port geometry; edge `kg` stays allocated seizure scale.
