<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# TRACE historical SQLite v2

This release preserves all 37 v1 source tables and adds official drug-specific health, treatment, price/purity, and cited context evidence. It includes versioned research formulas and row-level input links for source-to-value inspection.

New observations include UNODC national drug-use prevalence, injecting-related HIV/HCV/HBV, treatment contacts, UN SDG 3.5.1 treatment coverage, CDC provisional 12-month-ending overdose records, and original UNODC price/purity cells. The exact-product market layer has 449 retail/wholesale unit-price ratios and 476 purity-adjusted nominal prices, each linked to source observation IDs and workbook rows. The evidence catalog has eight cited multiyear departure or policy statements; none are annual bilateral flow measurements.

The prespecified retrospective country/year fixed-effects analysis finds no evidence of an association between reported cocaine-seizure kilograms and next-year general-population homicide under this specification (1,428 country-years, 144 countries; coefficient 0.0195, 95% CI −0.213 to 0.252, p = 0.869). This is noncausal, uses retrospectively revised source editions, and does not validate a route forecast. A broad coarse-drug price-ratio calculation was rejected because product forms did not match; rejected values are absent from the research table.

The `snapshot.json` asset includes both compressed and uncompressed SHA-256 hashes, table counts and source-shard checksums. `python3 data_collection/manage.py download` restores and verifies the SQLite file. `verify_remote` checks the published archive stream against both hashes without allocating a second database. The `coverage.md` asset lists actual source windows and missingness; see the repository's `data_collection/` reports and `schema_v2.md` for interpretation and drilldown queries.

Data and methods are AI-assisted with explicit citations in `docs/AI_USAGE.md`. All numeric source observations come from the cited publishers. Source terms and source-specific estimates, suppression, changing definitions and reporting limitations remain applicable. National seizures are country-of-seizure reports, not measured trade flows or routes. The archive contains no ranking of weak enforcement or evasion opportunities.
