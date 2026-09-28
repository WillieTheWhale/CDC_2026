# Indicators API v2: source concepts, metadata, SDMX, and adjacent APIs

Reviewed against World Bank documentation and representative live calls on 2026-09-26. These query families use different response shapes from ordinary observation queries. Check the response's status and content type, then validate its body.

## Advanced multidimensional data

Start with `/sources?format=json` to find a source ID. `/sources/2/concepts/data?format=json` lists data dimensions such as `Country`, `Series`, and `Time`; `/sources/2/country/data?format=json` lists variables in one dimension. A more specific data path combines source, dimension, and value, ending in `/data`. The [advanced data queries page](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886686-advanced-data-api-queries) gives an archival example:

`/sources/57/country/ALB/series/SP.POP.TOTL/time/yr1975/version/199704/data?format=json`

Use the actual concepts and variable codes returned for the selected source; not every source has a `Version` dimension. The page labels advanced data and JSON-stat queries beta. Advanced JSON is an object with pagination keys and a nested `source`/`concept` or `source`/`data` tree, not the usual `[metadata, records]` array. Page through it where indicated.

## Metadata and search

The [metadata queries page](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886695-metadata-api-queries) defines `Source`, `Concept`, `Metatype`, and `Metadata`. Useful calls include:

| Need | Path with `?format=json` appended |
| --- | --- |
| Metadata concepts for WDI | `/sources/2/concepts/metadata` |
| Metatypes for WDI | `/sources/2/metatypes` |
| Metatypes within country concept | `/sources/2/concepts/country/metatypes` |
| All metadata for one country | `/sources/2/country/JPN/metadata` |
| All metadata for one indicator | `/sources/2/series/SP.POP.TOTL/metadata` |
| A particular metatype for multiple countries | `/sources/2/country/USA;JPN/metatypes/incomegroup/metadata` |
| Metadata keyword search | `/sources/2/search/solid%20fuel` |
| Search one concept or metatype | `/sources/2/concepts/country/search/united`; `/sources/2/metatypes/region/search/south` |

Search terms belong in the URL path and must be encoded. Metadata JSON uses an object with pagination fields and nested `source -> concept -> variable -> metatype` arrays. Metatypes vary by source and concept, so discover them rather than assuming a fixed schema. The page also documents `downloadformat=csv` or `excel` for metadata downloads.

For an indicator analysis, check its `sourceNote`, `sourceOrganization`, and relevant metadata such as definition, methodology, periodicity, aggregation method, and footnotes. An empty metadata field is not proof that a concept does not exist elsewhere.

## SDMX REST

The [SDMX page](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886701-sdmx-api-queries) documents WDI access, with these structure discovery endpoints:

- `/sdmx/rest/dataflow`
- `/sdmx/rest/codelist/wb`
- `/sdmx/rest/datastructure/wb`

Data pattern: `/sdmx/rest/data/WDI/{frequency}.{series}.{country}/?startperiod=2010&endPeriod=2015`. Its example for Afghanistan population is `/sdmx/rest/data/WDI/A.SP_POP_TOTL.AFG/?startperiod=2011&endPeriod=2011`; note SDMX's `SP_POP_TOTL` code rather than the ordinary Indicators path's `SP.POP.TOTL`. An empty dimension requests all members within the other constraints. The documentation caps one call at **15,000 data points including nulls**. Keep requests bounded by geography, series, and period.

The page documents generic SDMX-ML 2.1 by default, `Accept: application/vnd.sdmx.structurespecificdata+xml` for structure-specific XML, and `Accept: application/vnd.sdmx.data+json;version=1.0.0-wd` for JSON. In a live sample on 2026-09-26, the server returned generic XML even with both alternate `Accept` headers. Treat those alternate formats as documented capabilities to verify with a small request before depending on them. Parse the returned content type, not the requested header.

## Errors and neighboring World Bank APIs

The [error-code page](https://datahelpdesk.worldbank.org/knowledgebase/articles/898620-api-error-codes) lists service unavailable (105/503), invalid version or method (110/112), unsupported format (111), missing or invalid parameters (115/120), unknown endpoint (140), unsupported language (150), and unexpected error (199/500). Diagnose both HTTP status and body; V1 endpoints are retired.

The [Developer Information overview](https://datahelpdesk.worldbank.org/knowledgebase/articles/889386-developer-information-overview) distinguishes Indicators from Projects, Finances, Climate, and Data Catalog APIs. The [Data Catalog API page](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886698-data-catalog-api) links to [provisional catalog API documentation](https://gist.github.com/tgherzog/e6090f9b2ba74f49f75b228f5c7169b9) at `datacatalogapi.worldbank.org`. That separate API covers dataset lists and searches, dataset/indicator/resource metadata, and resource downloads. Use it when the task asks about catalog datasets or files, not as a substitute for `api.worldbank.org/v2` indicator observations. Its published notes describe pagination with `$top` and `$skip` and warn that resource files can be large.

The documentation also links a [Stata `wbopendata` module](https://datahelpdesk.worldbank.org/knowledgebase/articles/889464-wbopendata-stata-module-to-access-world-bank-data). It is an optional client for Stata work, not an Indicators API endpoint. Follow its current package instructions if a user chooses Stata; otherwise direct HTTP queries remain sufficient.
