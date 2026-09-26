<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Context sources: OC Index, harm reduction, and geography

Collected 2026-09-26 into `data_collection/work/context.sqlite`. The shard passes `PRAGMA integrity_check`. Every source download has an original URL, final URL, retrieval timestamp, SHA-256 checksum, byte count, citation and license note in `context_sources`; cached source files are untracked. The checksum is over the downloaded file bytes. The source rows and original country labels remain queryable alongside the mapped observations.

| Source/table | Original coverage | Stored rows | Interpretation |
| --- | --- | ---: | --- |
| [Global Organized Crime Index](https://ocindex.net/downloads), `oc_index` | 2021, 2023, 2025; 193 UN member states per edition | 579 | Three observed scores per country. No annual values between editions. `context_ocindex_raw` preserves 21,423 workbook cells. |
| [Harm Reduction International, Global State of Harm Reduction](https://hri.global/flagship-research/the-global-state-of-harm-reduction/), `harm_reduction` | 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024 | 1,206 | Country/territory table observations from nine PDF editions. `context_hri_cells` preserves 12,060 source cells and `context_hri_raw_rows` preserves 1,333 extracted table rows, including headings and totals. |
| [CEPII GeoDist](https://visiadata.cepii.fr/CEPII/fr/bdd_modele/bdd_modele_item.asp?id=6), `distances` | Static dyadic geography, cited to Mayer and Zignago (2011) | 50,176 | 224 × 224 directed pairs, including self-pairs; distances are in kilometres. This is geographic context, not a yearly observation or observed drug route. Raw dyads and 238 original geo records are retained. |

## Coverage and missingness

HRI has 82, 94, 97, 101, 100, 161, 173, 199 and 199 country/territory rows respectively for the editions above. Of the 1,206 rows, 1,190 map to a current World Bank country/economy code. Nine Taiwan rows are retained with `outside_world_bank_scope`; seven Zanzibar rows are retained with `subnational_not_merged` and are not silently assigned to Tanzania. Four printed source spelling errors are explicitly mapped while keeping the original names: `Tunisa` → TUN (2010), `Azerbijan` → AZE and `Krygyzstan` → KGZ (2018), and `San Marí` → SMR (2024). No HRI country names remain unresolved.

The HRI columns are edition-specific. `policy`, `nsp` and `oat` begin in 2008; `dcr` in 2010; prison OAT/NSP in 2016; peer naloxone in 2018; take-home naloxone, safer smoking kits and stimulant prescription in 2022. Earlier unmeasured fields are **NULL** with `not_collected_in_edition`, not false. A printed `nd`/`nk` is NULL with `unknown`. Printed checks and crosses are 1 and 0; qualified marks keep the qualifier and note in `context_hri_cells`. `prison_programs` is a derived three-valued field: true if either prison service is true, false only if both are explicitly false, otherwise NULL. The source editions are snapshots, so values are not carried forward or backward to missing years.

The table-cell counts match the PDF's printed global total in all available comparisons except two: 2020 `policy` has 88 checked country/territory rows against a printed total of 87; 2022 `oat` has 88 checked rows against a printed total of 87. Both one-count differences are recorded as `source_total_discrepancy` in `context_hri_checks`. The printed cells and totals are preserved; no observation is changed to force agreement. Earlier editions have no extractable printed global-total row in the selected table and are marked `no_printed_total`. The PDF table snapshots may differ from newer figures on HRI's web summaries.

OC Index has no unmapped country names. `criminality`, `resilience`, and cocaine, heroin, cannabis and synthetic-drug trade scores are taken from each edition's workbook sheet. These are index scores, not drug quantities. The official site provides the workbook under [Open data](https://ocindex.net/downloads); no separately named data license was found on that page.

For CEPII, 41,209 directed pairs have both endpoints in the current World Bank country table. The raw CEPII codes are always retained. Only one-to-one code updates `ROM`→ROU, `ZAR`→COD, `TMP`→TLS and `PAL`→PSE are applied, affecting 1,776 directed pairs. Former Yugoslavia (`YUG`) and Netherlands Antilles (`ANT`) remain historic entities; 892 dyads involving them are flagged as legacy-state pairs. No distance is imputed or assigned to successor countries. CEPII lists [Etalab 2.0](https://visiadata.cepii.fr/CEPII/fr/bdd_modele/bdd_modele_item.asp?id=6) as its GeoDist license and requests the citation: Mayer, T. and Zignago, S. (2011), *Notes on CEPII's distances measures: the GeoDist database*, CEPII Working Paper 2011-25.

## Download verification

| Source | Original download | SHA-256 |
| --- | --- | --- |
| OC Index | https://ocindex.net/assets/downloads/global_oc_index.xlsx | `0bdfe8943de5a82bd4f709f92c91c596de5c60a192dca463bc722d88be7b55f5` |
| HRI 2008 | https://hri.global/wp-content/uploads/2022/10/GSHRFullReport1-1.pdf | `805e5e52a24f40f48fa1ab74f0c4826ee67dcc130cd4a7f1ff85319479a11d51` |
| HRI 2010 | https://www.hri.global/files/2010/06/29/GlobalState2010_Web.pdf | `3f926dee1f025d62427271c1e4865e42e6c5c127229d6df7c71ba868a01fd241` |
| HRI 2012 | https://hri.global/wp-content/uploads/2014/08/GlobalState2012_Web.pdf | `02c03ac25f276e2ce341a82380d680eaa686a0a6cf9090e4f00e15bcfc023606` |
| HRI 2014 | https://hri.global/wp-content/uploads/2022/10/GSHR2014-2.pdf | `5542ed2fecc0b9f14a701581d203f1b766e700cf3abd4fef2054d9077cdf2310` |
| HRI 2016 | https://hri.global/wp-content/uploads/2022/10/GSHR2016_14nov-2.pdf | `69993db41dbcd850894aacc2b95e26dc49edfaa08713d94bc9813ea1b9b9e121` |
| HRI 2018 | https://hri.global/wp-content/uploads/2022/10/global-state-harm-reduction-2018.pdf | `51f806fce0a2f2027b740d6e4acedc8629f342d4d3813a7c06a3a1d865c80bf2` |
| HRI 2020 | https://hri.global/wp-content/uploads/2022/10/Global_State_HRI_2020_BOOK_FA_Web-1.pdf | `18c79d4bcaf1b1ec6401154fdf664e2324f503ca8cbb30eb17ae177963d02d02` |
| HRI 2022 | https://hri.global/wp-content/uploads/2022/11/HRI_GSHR-2022_Full-Report_Final-1.pdf | `4ba9be294ae2c654c4fdf607c6d5248d3a5189f61e7d17dddc8cb80593134275` |
| HRI 2024 | https://hri.global/wp-content/uploads/2024/10/HRI-GSHR-2024_Full-Report_Final.pdf | `f57aa7d4ecdd230d66c0fb485634003f4b44a7bc554632dc90b29c80f4a76b92` |
| CEPII dyadic | https://www.cepii.fr/distance/dist_cepii.zip | `1854825bab1abe7197f6e47295a7ced5f72c83bc95076768f733c4969ed86780` |
| CEPII geography | https://www.cepii.fr/distance/geo_cepii.xls | `aa43be56e85a0f67459dc2fd1e841710b600b6133cde76536c42bac07c35c9d9` |

Rebuild from the checked cache with `backend/.venv/bin/python data_collection/context_sources.py`; use `--refresh` to request fresh source files. Verification: `backend/.venv/bin/python -m pytest data_collection/tests/test_context_sources.py -q` (3 passed), followed by the collector's row-count, uniqueness, source-total and SQLite integrity checks. The shard is ready for the collection coordinator to merge into `trace.sqlite`.
