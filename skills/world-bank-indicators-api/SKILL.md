---
name: world-bank-indicators-api
description: Retrieve, interpret, and build with World Bank Indicators API v2 time-series data, indicator catalogs, country and aggregate definitions, and source metadata. Use for World Bank indicator research or programmatic data access; use separate API documentation for Projects, Finances, Climate, or Data Catalog datasets.
---

# World Bank Indicators API

Use `https://api.worldbank.org/v2/` for Indicators API calls. V1 is retired, and V2 needs no API key. Prefer `format=json` for programmatic work. The documentation is at the [World Bank Data Help Desk](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation).

## Working approach

1. Identify the requested measure, geography, years, and intended comparison. Discover the exact indicator code and source before fetching data. The same code can belong to multiple sources; set `source=<id>` when needed. Use the [core API reference](references/indicators-v2.md) for discovery, country/aggregate queries, options, and response handling.
2. Retrieve every page indicated by response metadata. Preserve `null` observations, original period labels, units, country versus aggregate status, source ID, and `lastupdated` when present. Treat `mrv` (latest periods) differently from `mrnev` (latest nonempty observations). Do not treat missing values as zero or assume the latest year has data.
3. Check indicator descriptions, methodology, coverage, source organization, and footnotes before interpreting or combining series. For deeper source concepts, metadata, SDMX, and downloads, read the [advanced API reference](references/advanced-and-formats.md).
4. For a delivered analysis or dataset, state the indicator code, source, geography, time range, units, retrieval date, and API URL or reproducible query. Review the [World Bank dataset terms](https://data.worldbank.org/summary-terms-of-use) and the selected dataset's own license or terms before redistribution or commercial use; third-party data can carry distinct terms.

Build queries with URL encoding, timeouts, bounded retries for transient failures, and caching appropriate to the application. Inspect HTTP status, content type, and the API error body: API responses and pagination fields differ across query families. Recheck the linked official documentation and a small live call when current behavior matters.

The screenshot that motivated this skill describes a project requirement to retrieve data programmatically. Apply that requirement only when working on that project; the API skill itself supports other World Bank indicator tasks too.
