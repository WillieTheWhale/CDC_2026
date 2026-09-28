<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# UNODC historical collection

Collected 2026-09-26 from 29 public UNODC files. The verified shard is `data_collection/work/unodc.sqlite` (1,010,978,816 bytes). `PRAGMA integrity_check` returned `ok`, `PRAGMA foreign_key_check` returned no rows, and all 29 cached files matched the SHA-256 values in `unodc_sources`. `unodc_collection_issues` is empty.

## Observed coverage

| Table | Rows | Observed years | Meaning |
| --- | ---: | --- | --- |
| `seizures_raw` | 2,841,320 | 2011–2026 | Individual Drug Seizures (IDS) case records, including original public fields |
| `seizures_ids` | 3,055 | 2011–2026 | Country, year, drug summaries of mapped IDS records |
| `unodc_seizure_observations` | 42,766 | 2006–2024 | Published national seizure observations, kept by report edition |
| `seizures_annex` | 10,739 | 2006–2024 | National seizure totals by source edition, country, year and drug |
| `unodc_price_observations` | 17,504 | 1990–2024 | Published price and purity cells, including missing values and non-nominal series |
| `prices` | 5,349 | 1990–2024 | Positive nominal USD per gram retail or wholesale prices; 35 observed years |
| `unodc_cultivation_observations` | 1,426 | 1999–2025 | Published cultivation and opium-production cells, including blanks and alternate concepts |
| `cultivation` | 203 | 1999–2025 | Selected observed country, crop, year values: coca 2002–2024, opium poppy 1999–2025 |
| `cannabis_regulation` | 34 | 2012–2024 | Published national or subnational implementation dates |

The archive also retains 706,818 workbook and PDF table cells, five complete PDF page texts, source URLs, file hashes, retrieval timestamps, edition years, units, and source notes. The selected tables do not interpolate, carry forward, or backcast values. A missing source cell remains missing. Coverage is sparse across countries and series; these ranges do not imply a balanced country-year panel.

## Sources and interpretation

- [UNODC Drugs Monitoring Platform, public Individual Drug Seizures data](https://dmp.unodc.org/downloadIDS): three public workbooks cover 2011–2026. The published columns locate the seizure country, not shipment origin, transit, or destination. Consequently these cases cannot establish observed trade routes. 2026 is partial. Mass units are converted to kilograms only when the reported unit is convertible; tablets and similar counts remain null in the converted column. An opium-to-heroin equivalent is a project approximation and is labeled in `conversion`; retain original quantity and unit for analysis.
- [UNODC World Drug Report 2026 statistical annex](https://www.unodc.org/unodc/en/data-and-analysis/world-drug-report-2026-annex.html): country seizure, price, cultivation, opium production, and cannabis regulation workbooks. Annex prices are published as nominal USD per reported mass unit and normalized to USD per gram only when unit conversion is explicit. Source-specific ranges and purities remain in `unodc_price_observations`.
- [World Drug Report 2012](https://www.unodc.org/unodc/en/data-and-analysis/WDR-2012.html), [2015 statistical tables](https://www.unodc.org/wdr2015/en/maps-and-graphs.html), and [2020 statistical tables](https://wdr.unodc.org/wdr2020/en/maps-and-tables.html): archived price, seizure, and cultivation workbooks supply years absent from the latest annex. Rows from overlapping editions remain separate. The normalized price table selects the latest available edition for each country, drug, level and year. The national seizure table is deliberately **edition-specific**, so users must select an edition before combining overlapping years.
- [World Drug Report 2015 coca cultivation table](https://www.unodc.org/wdr2015/field/8.1._Coca_cultivation_production_and_eradication.pdf) and [opium cultivation and production table](https://www.unodc.org/wdr2015/field/8.2._Opium_cultivation_production_eradication.pdf): these extend observed coca area to 2002 and opium poppy area and oven-dry opium production to 1999. PDF cells and page text preserve source notes. The 2015 coca table reports both a Peru satellite-area series and, from 2011, a 31 December net-area series; the latter is selected in `cultivation`, while the overlapping satellite observation remains tagged `alternate_concept` in the observation table. The 2015 opium table notes revisions to Afghanistan’s 2006–2009 production figures; 2014 Myanmar survey coverage also differs from 2013. These are source comparability limits, not missing-data values to fill.

The normalized `cultivation.production_t` column refers to **oven-dry opium metric tons** for opium poppy, not heroin or cocaine production. It is null for coca. National seizure kilograms represent reported seizures, which depend on enforcement and reporting as well as underlying activity; they are not estimates of total trade volume. The IDS case set and national annex totals are different publication products and must not be added together.

## Reproduce and check

```sh
backend/.venv/bin/python data_collection/unodc.py --cached-only
backend/.venv/bin/python -m pytest data_collection/tests/test_unodc.py -q
```

The test run on 2026-09-26 passed all six collector checks. A full network refresh omits `--cached-only`; the collector downloads the public files sequentially with bounded retries and records each file hash. The local download cache was evicted after the verified shard and v1 release were produced; use a network refresh before attempting `--cached-only`. This report describes the verified shard above, not a guarantee that an upstream download will retain its current content or publication schedule.
