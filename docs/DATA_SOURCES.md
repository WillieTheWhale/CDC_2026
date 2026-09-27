# Data Sources (verified 2026-09-26; retrieval results added by the backend build)

Every World Bank code below was checked against the live API on 2026-09-26. "Latest" = most recent year with any non-null value; "typical" = median latest year across economies. Always read `skills/world-bank-indicators-api/SKILL.md` before calling the API.

## World Bank Indicators API (required core)

Base: `https://api.worldbank.org/v2`. No key. Always pass `format=json` and an explicit `source`.

### Gotchas found during verification
1. **Governance codes were renamed.** `CC.EST`, `RL.EST`, `GE.EST`, `PV.EST` now live only in the WDI archives (source 57) and return nothing current. Use `GOV_WGI_*.EST` with `source=3`. Standard errors are available as `GOV_WGI_*.SE`.
2. **Refugee codes moved.** `SM.POP.REFG` / `SM.POP.REFG.OR` are archive-only. Use `SM.POP.RHCR.EA` (by asylum country) and `SM.POP.RHCR.EO` (by origin), source 2.
3. `SP.POP.1524.TO.UN` returned nothing; do not use.
4. Liner shipping connectivity (`IS.SHP.GCNW.XQ`) stops at 2021; excluded.
5. Logistics Performance Index is surveyed every few years (latest 2022); forward-fill and flag it.
6. The country list includes about 45 aggregates; filter with `region.value == "Aggregates"`.
7. The Women, Business and the Law index (`SG.LAW.INDX`) only exists in the archive source 57 (not needed for TRACE).

### Indicators used

| Role | Name | Code | Source | Latest | Notes |
|---|---|---|---|---|---|
| Governance | Control of Corruption | `GOV_WGI_CC.EST` | 3 | 2025 | 216 economies |
| Governance | Rule of Law | `GOV_WGI_RL.EST` | 3 | 2025 | detection-bias control |
| Governance | Government Effectiveness | `GOV_WGI_GE.EST` | 3 | 2025 | |
| Governance | Political Stability / No Violence | `GOV_WGI_PV.EST` | 3 | 2025 | |
| Logistics | LPI overall | `LP.LPI.OVRL.XQ` | 2 | 2022 | forward-fill |
| Logistics | LPI customs efficiency | `LP.LPI.CUST.XQ` | 2 | 2022 | detection-bias control |
| Logistics | Container port traffic (TEU) | `IS.SHP.GOOD.TU` | 2 | 2024 | sea capacity |
| Logistics | Air passengers carried | `IS.AIR.PSGR` | 2 | 2023 | air capacity |
| Logistics | Trade (% of GDP) | `NE.TRD.GNFS.ZS` | 2 | 2025 | |
| Gravity | GDP (current US$) | `NY.GDP.MKTP.CD` | 2 | 2025 | |
| Gravity | GDP per capita, PPP (constant) | `NY.GDP.PCAP.PP.KD` | 2 | 2025 | |
| Gravity | Population | `SP.POP.TOTL` | 2 | 2025 | |
| Vulnerability | Youth unemployment 15-24 | `SL.UEM.1524.ZS` | 2 | 2025 | |
| Vulnerability | Youth NEET share | `SL.UEM.NEET.ZS` | 2 | 2025 | typical 2024 |
| Vulnerability | Poverty at $3.00/day (2021 PPP) | `SI.POV.DDAY` | 2 | 2025 | typical 2022, sparse |
| Vulnerability | Gini index | `SI.POV.GINI` | 2 | 2025 | typical 2021, sparse |
| Vulnerability | Health expenditure per capita | `SH.XPD.CHEX.PC.CD` | 2 | 2024 | typical 2023 |
| Vulnerability | Account ownership | `FX.OWN.TOTL.ZS` | 2 | 2024 | cash economy proxy |
| Vulnerability | Remittances (% GDP) | `BX.TRF.PWKR.DT.GD.ZS` | 2 | 2025 | |
| Outcome | Intentional homicides per 100k | `VC.IHR.PSRC.P5` | 2 | 2023 | typical 2022 |
| Outcome | HIV incidence 15-49 per 1,000 | `SH.HIV.INCD.ZS` | 2 | 2024 | |
| Outcome | Battle-related deaths | `VC.BTL.DETH` | 2 | 2024 | conflict |
| Outcome | Refugees by asylum country | `SM.POP.RHCR.EA` | 2 | 2025 | |
| Outcome | Refugees by origin | `SM.POP.RHCR.EO` | 2 | 2025 | |
| Metadata | Region, income group, capital lat/long | `/country?format=json&per_page=400` | n/a | n/a | map placement |

### Retrieval results (backend T2, 2026-09-26)
Pulled programmatically by `backend/trace_backend/wb/` (`uv run trace wb`): 217 economies (78 aggregates dropped), years 2005-2026, 108,528 rows (71,684 non-null; nulls kept). Per-indicator provenance (API URL, pages, `lastupdated`, `retrieved_at`) is written to `backend/data/processed/wb_manifest.json`.

| Code | Source | Non-null rows | Economies with data | Latest | Typical latest |
|---|---|---|---|---|---|
| GOV_WGI_CC.EST | 3 | 4,281 | 207 | 2025 | 2025 |
| GOV_WGI_RL.EST | 3 | 4,310 | 207 | 2025 | 2025 |
| GOV_WGI_GE.EST | 3 | 4,268 | 205 | 2025 | 2025 |
| GOV_WGI_PV.EST | 3 | 4,310 | 207 | 2025 | 2025 |
| LP.LPI.OVRL.XQ | 2 | 1,071 | 169 | 2022 | 2022 (forward-filled up to 8 years, flagged `imputed`) |
| LP.LPI.CUST.XQ | 2 | 1,071 | 169 | 2022 | 2022 (model control only; never exposed by the API) |
| IS.SHP.GOOD.TU | 2 | 2,232 | 168 | 2024 | 2024 |
| IS.AIR.PSGR | 2 | 2,886 | 172 | 2023 | 2023 |
| NE.TRD.GNFS.ZS | 2 | 3,743 | 192 | 2025 | 2025 |
| NY.GDP.MKTP.CD | 2 | 4,392 | 214 | 2025 | 2025 |
| NY.GDP.PCAP.PP.KD | 2 | 4,138 | 199 | 2025 | 2025 |
| SP.POP.TOTL | 2 | 4,557 | 217 | 2025 | 2025 |
| SL.UEM.1524.ZS | 2 | 3,913 | 187 | 2025 | 2025 |
| SL.UEM.NEET.ZS | 2 | 1,966 | 180 | 2025 | 2024 |
| SI.POV.DDAY | 2 | 1,542 | 168 | 2025 | 2021 |
| SI.POV.GINI | 2 | 1,542 | 168 | 2025 | 2021 |
| SH.XPD.CHEX.PC.CD | 2 | 3,632 | 193 | 2024 | 2023 |
| FX.OWN.TOTL.ZS | 2 | 705 | 161 | 2024 | 2024 |
| BX.TRF.PWKR.DT.GD.ZS | 2 | 3,593 | 191 | 2025 | 2024 |
| VC.IHR.PSRC.P5 | 2 | 2,487 | 193 | 2023 | 2022 |
| SH.HIV.INCD.ZS | 2 | 2,893 | 146 | 2024 | 2024 |
| VC.BTL.DETH | 2 | 657 | 71 | 2024 | 2024 |
| SM.POP.RHCR.EA | 2 | 3,515 | 187 | 2025 | 2025 |
| SM.POP.RHCR.EO | 2 | 3,980 | 203 | 2025 | 2025 |

Indicator metadata (name, unit, source organization, source note) is pulled from `/indicator/{code}?source={id}` into the DuckDB table `wb_indicator_meta`.

### Other World Bank facts gathered (useful context)
- 71 sources in the API, 87 databases in DataBank (some DataBank-only).
- WDI last updated 2026-07-13; Worldwide Governance Indicators 2026-09-25; Global Economic Monitor 2026-09-08 (the only near-live WB data: monthly and daily).
- Freshness pattern: GDP, inflation, unemployment, population through 2025; life expectancy and child mortality 2024; poverty and Gini typical 2021-2022; suicide rate stops at 2021.
- The API has **no illegal drug indicators**. Only alcohol (`SH.ALC.PCAP.LI`) and tobacco (`SH.PRV.SMOK`) exist. All drug data is external.
- World Bank procurement notices API exists (`search.worldbank.org/api/procnotices`, about 418,781 notices) but is not used by TRACE.

## External sources (cite all)

| Source | What it gives TRACE | Access |
|---|---|---|
| UNODC Drugs Monitoring Platform, Individual Drug Seizures (IDS) | Case-level seizures: drug, quantity, date, seizure country, departure/transit/destination, transport mode. **Builds the route network.** | Public environment includes IDS, downloadable as Excel: https://dmp.unodc.org/downloadIDS . Restricted tier (government/partner only) not needed. May require free registration; verify. Access policy: https://dmp.unodc.org/access-policy |
| UNODC World Drug Report 2026 statistical annex | 8.1 prices and purities, 8.2 wholesale and retail prices USD, 8.3 cocaine/heroin price series (W. Europe, US), 6.1.1 coca cultivation, 6.1.2 coca eradication, 6.2.1 opium poppy cultivation, 1.x prevalence of use, 4.1 people who inject drugs with HIV/HCV/HBV, 11.1 cannabis regulation by country | https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html |
| UNODC Data Portal | Seizure, price, purity dashboards; metadata PDF; regional mapping xlsx | https://data.unodc.org/datareport/drug-seizure |
| UNODC crop surveys | Afghanistan Opium Survey 2023/2024/2025, Myanmar Opium Survey 2024 (natural experiment facts) | https://www.unodc.org/documents/crop-monitoring/ |
| Global Organized Crime Index 2025 (GI-TOC) | Scores for 193 UN states, 3 editions (2021, 2023, 2025), 15 criminal markets incl. heroin, cocaine, cannabis, synthetic drugs; resilience pillars | https://ocindex.net (download section) |
| Harm Reduction International, Global State of Harm Reduction 2024 | Per-country yes/no: needle and syringe programs (93 countries), opioid agonist therapy (94), drug consumption rooms (18), take-home naloxone (34), prison programs | PDF table: https://hri.global/wp-content/uploads/2024/10/HRI-GSHR-2024_Full-Report_Final.pdf (extract with pdfplumber) |
| US Customs and Border Protection | Monthly seizure weights by drug (fentanyl, meth, cocaine, heroin, marijuana); currency seizure dashboard | https://www.cbp.gov/newsroom/stats/drug-seizure-statistics (data on CBP Data Portal) |
| CDC provisional overdose deaths | Monthly US deaths by drug class | data.cdc.gov (VSRR provisional drug overdose) |
| GDELT | Global news stream for the Live Wire | https://api.gdeltproject.org/api/v2/doc/doc |
| CEPII GeoDist | Bilateral distances, contiguity | https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=6 |
| Natural Earth | Country shapes (frontend) | https://www.naturalearthdata.com |
| Stretch: ACLED | Near-real-time violence events | free account |
| Stretch: EU Drugs Agency (EUDA) | European prices, purity, wastewater | https://www.euda.europa.eu |
| Stretch: Global Burden of Disease (IHME) | Drug use disorder deaths | https://vizhub.healthdata.org/gbd-results/ |

### How each external source was actually used (backend T3, 2026-09-26)
Every download is scripted in `backend/trace_backend/ingest/` (`uv run trace ingest`). Raw files stay in the gitignored `backend/data/raw/`. Status per source is in `backend/data/processed/ingest_manifest.json` and in `GET /api/meta`.

| Source | Files | Used for | Notes |
|---|---|---|---|
| UNODC IDS (public) | `IDS-data-2011_17-May24.xlsx`, `IDS-data-2018-2022.xlsx`, `IDS-data-2023-2026.xlsx` from `dmp.unodc.org/sites/dmp.local/files/...` (no login needed) | 2.33M seizure cases -> country-year-drug totals; 2011-2014 backcast; destination case counts | **The public release has no departure/transit/destination fields**, so route hops cannot be built from it (the loader is ready if a release adds them). See `docs/BLOCKERS.md`. |
| UNODC WDR 2026 annex | 7.1 seizures 2015-2024; 6.1.1 coca; 6.2.1 opium; 6.2.2 opium production; 8.1 prices; 8.3 price series (W. Europe, US); 11.1 cannabis regulation; route maps 7.2-7.4 (PDF) | Node seizure volumes (primary), cultivation and production, price gradients and Market Board, legalization flags; corridor transcription | Opium converted to heroin-equivalent at 10:1; cocaine "total" rows preferred over components; coca leaf and bush excluded |
| UNODC/EUDA route publications | `backend/trace_backend/seed/corridors.csv` (234 corridors, citation key per row; keys in `seed/README.md`) | Candidate corridor list | Country-level endpoints are TRACE's transcription of UNODC/EUDA maps and texts |
| GI-TOC OC Index | `https://ocindex.net/assets/downloads/global_oc_index.xlsx` (2021, 2023, 2025 editions, 190 countries each) | Edge confidence signal, route-model features, country profiles | |
| HRI Global State of Harm Reduction 2024 | Full report PDF, Table 1 (pdfplumber) | Protection score (NSP, OAT, naloxone, DCR, prison programmes, policy), country profiles | 197 countries parsed: NSP 92, OAT 93, DCR 18, naloxone 34 (report: 93/94/18/34) |
| CEPII GeoDist | `https://www.cepii.fr/distance/dist_cepii.zip` | Distance, contiguity, common language (gravity) | 2004 codes remapped; missing pairs use great-circle distance between World Bank capitals |
| GDELT DOC 2.0 | live API | Live Wire article metadata and publication dates | Returned HTTP 429 or empty results from this network; the Live Wire replays synthetic sample headlines (`sample.trace.local`) and reports `fallback` |
| Evidence drilldown layer (SQLite v2 archive) | `research_values`/`research_value_inputs`, `market_derived`/`market_observations`/`market_cells`, `health_*`, `unodc_cells`, `wb_downloads` metadata | `/api/evidence/*`: value → formula → exact input rows → source URL, edition and observation year | The Vercel slim DB copies the evidence tables whole, and only the referenced `unodc_cells`/`market_cells` rows; no World Bank payloads |
| UN SDG indicator 3.5.1 (UNSD SDG API) | `health_treatment_coverage` | `/api/evidence/health/{iso3}` treatment coverage | Every row labelled officially modelled (`M`) or country reported (`C`) |
| CDC NCHS VSRR provisional overdose deaths (`xkb8-kh2a`) | `health_cdc_overdose` | `/api/evidence/overdose` | 12-month-ending provisional; overlapping periods and drug classes are never summed; suppressed values stay null; exact CDC labels |
| Route evidence (cited country pairs) | `backend/trace_backend/seed/route_evidence.csv` (51 pairs from 9 publications, transcribed from the frontend team's `frontend/lib/route-evidence.ts`) and `seed/evidence_claims.json` (4 UNODC WDR 2026 narrative claims) | `/api/route-evidence`, and `evidence_ids` on `/api/routes` edges | `pair_type` separates direct reported pairs from TRACE's interpreted corridors and regional narrative context; no volumes, no city-level geometry |

### Key facts for the natural experiment (with sources)
- After the April 2022 Taliban ban, Afghan opium production fell about 95 percent in 2023; Myanmar became the world's main source (UNODC Myanmar Opium Survey 2024).
- Afghan cultivation: about 232,000 ha in 2022; 12,800 ha in 2024 (+19 percent vs 2023) (UNODC).
- Myanmar production: 790 t (2022), 1,080 t (2023), 995 t (2024); Shan State 88 percent of Myanmar cultivation (UNODC).
- Afghan output estimated 296 t in 2024; prices about five times pre-ban average (Al Jazeera citing UNODC, Nov 2025).
- GI-TOC 2025: cocaine and synthetic drugs rising (cocaine market score 4.52 to 4.89, synthetics 4.62 to 5.14, 2021 to 2025); heroin down sharply; cannabis most widespread but declining with legalization.

## Reflex (TRACE's own System One model) training and evaluation data

Reflex is described in [REFLEX_SPEC.md](REFLEX_SPEC.md). Everything it learns from is free and openly published; nothing is paid for or scraped. Downloads are cached under the gitignored `backend/data/reflex/hf/`.

| Resource | Used as | Citation / licence |
|---|---|---|
| `cross-encoder/nli-deberta-v3-xsmall` | Pretrained starting weights (NLI cross-encoder) | He et al. (2021), DeBERTaV3; sentence-transformers cross-encoder, Apache-2.0 |
| BoolQ (`google/boolq`) | Noul training | Clark et al. (2019), NAACL; CC BY-SA 3.0 |
| MultiNLI (`nyu-mll/multi_nli`) | Noul training | Williams et al. (2018), NAACL; OANC / CC BY-SA 3.0 / CC BY 3.0 by genre |
| AG News (`fancyzhx/ag_news`) | Choice training | Zhang, Zhao and LeCun (2015), NeurIPS; academic, non-commercial |
| DBpedia-14 (`fancyzhx/dbpedia_14`) | Choice training | Zhang et al. (2015); DBpedia CC BY-SA 3.0 |
| Yahoo Answers topics (`community-datasets/yahoo_answers_topics`) | Choice training | Zhang et al. (2015); academic, non-commercial |
| Yelp reviews full (`Yelp/yelp_review_full`) | Score training | Zhang et al. (2015); Yelp Dataset terms (academic, non-commercial) |
| RTE (`nyu-mll/glue`, rte) | Zero-shot Noul test only | Dagan et al. (2006) and successors via GLUE (Wang et al. 2019) |
| Emotion (`dair-ai/emotion`) | Zero-shot Choice test only | Saravia et al. (2018), EMNLP |
| SST-5 (`SetFit/sst5`) | Zero-shot Score test only | Socher et al. (2013), EMNLP |
| UNODC IDS seizure records (SQLite archive) | TRACE-domain training headlines (country, city, drug, quantity, place and transport mode from real records) | UNODC Drugs Monitoring Platform; see UNODC rows above |
| TypeSafe documentation (docs.typesafe.ai, 59 pages) | Specification only (interface, output contract, confidence formula, calibration objective, failure modes). No TypeSafe code or weights | TypeSafe AI, retrieved 2026-09-26 |
