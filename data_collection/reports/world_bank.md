<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# World Bank complete-history collection

Generated 2026-09-26T18:34:27+00:00. Programmatic API v2 retrieval, explicit WDI source 2 and WGI source 3.

24/24 registry indicators; 308,796 country observations including nulls; 127,606 non-null values.
Observed history extends **1960–2025**. The intersection of variable first/last observed bounds is **2011–2022**; this is an envelope, not an annually complete panel.
Years in which all 24 indicators have at least one non-null country observation: **2014, 2022**.
Country-year combinations with all 24 variables observed concurrently: **1**.

Retain the entire history in the database. For analysis, choose a task-specific cohort and record each value’s observation year. Sparse surveys do not justify cutting older observations or backward-filling future observations. This collector performs no filling, imputation or model-panel selection.

The source time dimensions and every no-date observation page were fetched and checked. No fixed starting year, `date`, `mrv`, `mrnev` or `gapfill` is used. Current country classifications are not historical borders. Aggregate and otherwise unmatched source observations remain directly queryable in `wb_excluded_observations` and preserved in compressed original responses, outside the country-observation table. Unmapped source entities with blank source country codes retain their source names; no ISO code is invented.

| Indicator | Source | Feature | First non-null | Last non-null | Non-null rows | Economies | All rows | Unmatched source rows |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| GOV_WGI_CC.EST | 3 | control_corruption | 1996 | 2025 | 5408 | 207 | 5589 | 243 |
| GOV_WGI_GE.EST | 3 | gov_effectiveness | 1996 | 2025 | 5373 | 205 | 5589 | 243 |
| GOV_WGI_PV.EST | 3 | political_stability | 1996 | 2025 | 5462 | 207 | 5589 | 243 |
| GOV_WGI_RL.EST | 3 | rule_of_law | 1996 | 2025 | 5503 | 207 | 5589 | 243 |
| NY.GDP.MKTP.CD | 2 | gdp | 1960 | 2025 | 11764 | 214 | 14322 | 0 |
| NY.GDP.PCAP.PP.KD | 2 | gdp_pc_ppp | 1990 | 2025 | 6977 | 199 | 14322 | 0 |
| SP.POP.TOTL | 2 | population | 1960 | 2025 | 14292 | 217 | 14322 | 0 |
| IS.AIR.PSGR | 2 | air_passengers | 1970 | 2023 | 7929 | 185 | 14322 | 0 |
| IS.SHP.GOOD.TU | 2 | port_teu | 2005 | 2024 | 2232 | 168 | 14322 | 0 |
| LP.LPI.CUST.XQ | 2 | lpi_customs | 2007 | 2022 | 1071 | 169 | 14322 | 0 |
| LP.LPI.OVRL.XQ | 2 | lpi_overall | 2007 | 2022 | 1071 | 169 | 14322 | 0 |
| NE.TRD.GNFS.ZS | 2 | trade_gdp | 1960 | 2025 | 9029 | 194 | 14322 | 0 |
| SH.HIV.INCD.ZS | 2 | hiv_incidence | 1990 | 2024 | 5053 | 146 | 14322 | 0 |
| SM.POP.RHCR.EA | 2 | refugees_asylum | 1960 | 2025 | 7511 | 189 | 14322 | 0 |
| SM.POP.RHCR.EO | 2 | refugees_origin | 1960 | 2025 | 7365 | 203 | 14322 | 0 |
| VC.BTL.DETH | 2 | battle_deaths | 1989 | 2024 | 1212 | 109 | 14322 | 0 |
| VC.IHR.PSRC.P5 | 2 | homicide_rate | 1990 | 2023 | 4065 | 196 | 14322 | 0 |
| BX.TRF.PWKR.DT.GD.ZS | 2 | remittances_gdp | 1970 | 2025 | 7114 | 199 | 14322 | 0 |
| FX.OWN.TOTL.ZS | 2 | account_ownership | 2011 | 2024 | 705 | 161 | 14322 | 0 |
| SH.XPD.CHEX.PC.CD | 2 | health_exp_pc | 2000 | 2024 | 4559 | 193 | 14322 | 0 |
| SI.POV.DDAY | 2 | poverty | 1963 | 2025 | 2430 | 171 | 14322 | 0 |
| SI.POV.GINI | 2 | gini | 1963 | 2025 | 2430 | 171 | 14322 | 0 |
| SL.UEM.1524.ZS | 2 | youth_unemployment | 1991 | 2025 | 6531 | 187 | 14322 | 0 |
| SL.UEM.NEET.ZS | 2 | youth_neet | 1970 | 2025 | 2520 | 182 | 14322 | 0 |

## Coverage and provenance

`wb_coverage_year` stores per-indicator/year non-null counts. `wb_coverage` stores bounds, country counts, pagination totals and excluded row counts. `wb_source_periods` records the source-native time dimension.
`wb_downloads` stores exact query URLs, original retrieval timestamps, SHA-256 checksums, content types, and the complete original response compressed with gzip. The checksum applies to decompressed bytes. `wb_indicators.request_id` joins to this provenance; `lastupdated` retains the API source update date. Original period labels, nulls, observation status, decimals and footnotes are retained.
`wb_indicator_meta` stores the API name, project unit, API unit, source organization, source note, full advanced metadata and source-specific license fields. A blank API unit is not interpreted as unitless. `public=0` for the customs detection-bias control; it must not become a public ranking or route-avoidance feature.

## Sources and reproducibility

- [Indicators API documentation](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)
- [World Bank dataset terms](https://data.worldbank.org/summary-terms-of-use); per-series license fields must be honored.
- Registry: `backend/trace_backend/wb/indicators.py` (read only).
- Rebuild: `python3 data_collection/world_bank.py`; `--refresh` refetches all pages. A default rerun verifies and uses the checksummed cache.
- Rate control: serial HTTP requests at least one second apart; bounded retries for 429/5xx/network errors, honoring `Retry-After`.
