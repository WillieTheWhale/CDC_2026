<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# SQLite v2 backend handoff: source-to-value drilldown

The published `trace.sqlite` remains the observational source of truth. The verified v2 database has 61 tables and keeps the original 37 v1 tables in place. Additional shards supply drug-specific health observations, exact-product market measurements and a small retrospective research layer. Backend code should open the SQLite file read-only, preserve its observation years and source editions, and keep existing API response shapes unless the contract owner changes them. The backend's current DuckDB adapter is not compatible with this file merely by changing its path.

## Derived value → formula → inputs → source

`research_values.metric_id` is the stable external key for research drilldown. It joins to `research_metric_definitions.metric_key` for the versioned formula and selection rule, and to `research_value_inputs.metric_id` for every input. `support_count` is the number of linked input rows, including the aggregate and its underlying source rows; it is **not** a count of independent countries. `source_key` identifies a row in the named source table. UNODC seizure aggregates have both a `seizures_annex` link and each contributing `unodc_seizure_observations` workbook row. The latter key includes `source_id|sheet|row_no`; original cells are in `unodc_cells` for that source/sheet/row. The workbook's publication edition and the observation year are separate fields. World Bank `lastupdated` is retained in the input transformation text and is not asserted to be an exact publication year.

```sql
SELECT v.metric_id, v.iso3, v.drug, v.year, v.value, v.support_count,
       d.version, d.formula, d.selection_rule, d.interpretation,
       i.role, i.source_table, i.source_key, i.source_url,
       i.publication_year, i.observation_year, i.input_value, i.input_unit,
       i.transform
FROM research_values v
JOIN research_metric_definitions d USING (metric_key)
JOIN research_value_inputs i USING (metric_id)
WHERE v.metric_id = :metric_id
ORDER BY i.role, i.source_table, i.source_key;
```

`research_regression_samples.metric_id` links each included model observation to its two source types. `research_model_results` stores the one prespecified model's coefficient, clustered standard error, interval, sample size and caveat. The model is a retrospective association between reported cocaine seizures and next-year *general-population* homicide. It is neither route validation nor a prospective forecast test. See [the full finding](reports/research_model.md).

`market_derived.derived_id` is the stable key for exact-product price/purity values. `market_derived.inputs_json` contains the contributing `market_observations.observation_id` values and numeric inputs. Join the observation's `(source_id,sheet,row_no)` to `market_cells` to show original workbook cells, and `source_id` to `market_sources` for URL, checksum and edition. The 449 retail/wholesale ratios are a descriptive unit-price contrast, not a margin or route gradient. The 476 purity-adjusted prices are nominal USD per pure gram and may combine different samples. **Do not display** the rejected coarse-drug price ratios from the research feasibility audit; they are absent from `research_values`.

```sql
SELECT d.derived_id, d.metric_code, d.iso3, d.year, d.substance, d.form,
       d.market_level, d.value, d.unit, d.formula, d.inputs_json,
       s.url, s.edition
FROM market_derived d JOIN market_sources s USING (source_id)
WHERE d.derived_id = :derived_id;
```

Health observations retain source-native coordinates. For example, `health_prevalence` keeps population, exact age group, sex, reference period, value/bounds, method and estimate status; `(source_id,sheet,row_no,cell_no)` joins to `health_raw_rows` and `health_sources`. `health_treatment_coverage` separates officially modeled (`nature_code='M'`) from country reported (`'C'`) UN SDG 3.5.1 percentages. `health_cdc_overdose` is a 12-month-ending provisional jurisdiction series, with suppressed/unavailable values retained as NULL. Its rolling periods overlap and must not be added across months. Drug-class death counts also overlap because one death can involve multiple drugs; do not add class counts into an all-overdose total. The CDC `Synthetic opioids (T40.4)` category is broader than fentanyl alone and must retain its exact label. The 2024 adult prevalence data are sparse and are not a complete country ranking.

```sql
SELECT p.iso3, p.year, p.substance, p.reference_period,
       p.population, p.age_group, p.sex, p.value_pct, p.low_pct, p.high_pct,
       p.estimate_status, p.source_method, s.url, s.edition_year,
       p.sheet, p.row_no, p.cell_no
FROM health_prevalence p JOIN health_sources s USING (source_id)
WHERE p.iso3 = :iso3 AND p.reference_period = 'past_year'
ORDER BY p.year, p.substance;
```

The suggested backend drilldown response should carry `value`, `unit`, `formula`, `support_count`, `observation_year`, `source_publication_year` (nullable), `source_title`, `source_url`, `source_key`, `quality_flags`, and `caveat`, plus per-input roles and values. Do not substitute the collection date for a source publication date. Link cited World Bank values to their `wb_downloads.url`, indicator code, source ID and `lastupdated` metadata. A public interface should label modeled health estimates and provisional/suppressed overdose records explicitly.

The source tables do not contain observed origin/transit/destination legs for the public IDS cases. National seizures indicate where a seizure was recorded. Avoid showing predicted route exposure as direct observed evidence and avoid rankings of weak enforcement or evasion opportunities.

`evidence_claims` adds eight source-cited narrative context records: four multiyear UNODC reported-departure statements and four cannabis-policy milestones. A claim links to `evidence_sources` and carries original excerpt, exact locator, observation window or effective date, publication year, geographic scope and caveat. These statements may annotate a candidate corridor or explain a policy timeline. They are not measured annual bilateral flows, independent route ground truth or causal identification for a policy effect.
