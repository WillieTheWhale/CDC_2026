<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Market composition, price, purity and local signals

Collected 2026-09-26. Build with `backend/.venv/bin/python data_collection/markets/build.py`; output: `data_collection/work/markets.sqlite`. The builder reads the existing verified UNODC annex cache in `data_collection/work/unodc.sqlite` and uses no network request. Four derivation tests pass with `backend/.venv/bin/python -m unittest discover -s data_collection/markets -p 'test_*.py'`.

## Source and coverage

The shard contains 17,504 source price/purity observations across 12 [UNODC World Drug Report](https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html) current and historical workbooks, 166 ISO3 codes, 78 original substance labels and observation years 1990–2024. Each observation retains the source edition, workbook sheet, row and column, original country and substance text, sale level, price or purity concept, basis, original value/range/unit/text, and publisher-estimate flag. There are 155,830 copied workbook cells (including explicit blanks in market sheets), each with source row/column coordinates; `market_sources` retains the original URL, retrieval timestamp, SHA-256 and source licensing note. The shard is about 24 MiB.

The 2026 [price and purity workbook](https://www.unodc.org/documents/data-and-analysis/WDR_2026/Annex/8.1_Prices_and_purities_of_drugs.xlsx) contributes 6,503 observations from 2020–2024. The [2026 Western Europe/US price series](https://www.unodc.org/documents/data-and-analysis/WDR_2026/Annex/8.3_price_time_series_in_western_europe_and_united_states.xlsx) contributes 2,764 source observations with years 1990–2024. The 2012, 2015 and 2020 editions are retained as separate editions; overlapping publisher editions must not be counted as independent observations. The 1990 start is limited to the Western Europe/US series. It is **not** a 35-year global panel. Source workbooks and the creator's notes remain the authority on definitions and reuse; attribution to UNODC is required.

`market_observations` normalizes price values from USD/g and USD/kg to USD/g, USD/tablet to USD/tablet, and USD/unit to USD/unit. Purity `% (percent)` and `mg/tablet` are kept as distinct concepts. Liter, milliliter, ounce, pound, blank and unknown units are preserved in original fields without unsupported conversion. Historical source estimates remain flagged and never silently blended into the 2026-derived metrics.

## Derived metrics

`market_metric_definitions` gives formulas, eligibility, interpretation and caveats. `market_derived.inputs_json` lists each input observation ID and exact numeric input, so a value can be traced to the publisher's workbook cells. Derivation is limited to the 2026 annex's named product rows for cocaine hydrochloride, heroin, amphetamine powder, methamphetamine powder, MDMA, crack cocaine and fentanyl. Generic categories, precursors, cannabis potency, mixed market levels, unmatched years and conflicting repeated values are excluded from calculation while retained as source observations.

| Metric | Formula | Coverage | Interpretation |
| --- | --- | --- | --- |
| `purity_adjusted_price_usd_per_pure_g` | USD per gram / (purity percent / 100) | 476 country/product/level/year values, 53 countries, 2020–2024 | A descriptive nominal value using matched country, substance, form, sale level, year and edition. Price and purity may come from different samples or national methods. |
| `retail_wholesale_price_ratio` | retail USD per gram / wholesale USD per gram | 449 country/product/year values, 63 countries, 2020–2024 | A unit-price contrast. It is **not** a profit margin, transaction spread or cross-border price gradient. |

To inspect one value, join `market_derived.inputs_json` observation IDs to `market_observations`, then use `source_id`, `sheet` and `row_no` to find the original cells in `market_cells`. No inflation adjustment is applied. The source unit and year must appear alongside a displayed value.

## EUDA collection status

[EUDA Statistical Bulletin 2026 price, purity and potency](https://www.euda.europa.eu/data/stats2026/ppp_en) documents national annual retail and wholesale prices plus purity/potency by product form. Its [methods page](https://www.euda.europa.eu/data/stats2026/methods/ppp_en) says national reporting systems and average definitions vary, and some data may originate from local or one-off studies. It should not be assumed directly comparable across countries or joined to UNODC samples as if they were identical observations.

The [EUDA/SCORE wastewater study](https://www.euda.europa.eu/publications/pods/waste-water-analysis_en) offers site-level source CSVs for 2011–2025, including the 2026 [all-data table](https://www.euda.europa.eu/sites/default/files/data/data-nodes/33337/versions/5/ww2026-all-data_en.csv) and [site information table](https://www.euda.europa.eu/sites/default/files/data/data-nodes/33337/versions/5/ww2026-site-info-table_en.csv). EUDA explicitly permits reuse with EUDA and SCORE acknowledgment. The measurements are population-normalized **residue loads**, not consumption prevalence or dose counts; no excretion correction is applied. The 2025 study typically sampled one week in March–May, with about 115 cities, so this is a local sample window rather than a national annual observation. Zero may mean below quantification limit. Heroin lacks a stable specific wastewater biomarker; no heroin series should be inferred.

Official EUDA CSV downloads were unavailable in this environment: shell requests returned Cloudflare HTTP 403, and the direct link in Chrome reported `ERR_BLOCKED_BY_CLIENT`. `market_collection_status` records both sources as blocked; the shard includes no copied or inferred EUDA numeric values. The separate [EUDA European Drug Report 2026 source bundle](https://www.euda.europa.eu/data/source-data/edr/2026/complete_en) is listed under CC BY 4.0 except where noted, and exposes CSV links, but those downloads hit the same browser restriction. This is a retrieval limit, not a zero or missing-data claim.

## Use constraints

Price and purity are public health market signals, not estimates of trafficking flow. No country-pair or route flow is inferred from them. The source's repeated rows are retained, and the derived calculations require agreement among repeated values. The shard must not be used to rank weak enforcement or suggest evasion opportunities.
