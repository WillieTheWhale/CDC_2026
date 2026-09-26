# Indicators API v2: core calls

Reviewed against the World Bank Developer Information articles and representative live calls on 2026-09-26. Use the linked pages for the latest behavior. Base URL: `https://api.worldbank.org/v2`.

## Discover entities

| Need | Request path or example | What it returns |
| --- | --- | --- |
| Sources/databases | `/sources?format=json` | Source IDs, names, descriptions, data and metadata availability. Page through the result. |
| Countries and aggregate entries | `/country?format=json` | ISO/WB codes, region, income and lending groups, capital, coordinates. The list includes aggregates; identify them from `region.value == "Aggregates"` rather than treating every row as a country. |
| One country | `/country/USA?format=json` | Country definition and memberships. |
| Filter country list | `/country?region=LCN&format=json`, `/country?incomelevel=UMC&format=json`, `/country?lendingtype=IBD&format=json` | Members of an aggregate classification. |
| Aggregate definitions | `/region?format=json`, `/incomelevel?format=json`, `/lendingtype?format=json` | Codes and names. `/region/LCN` and semicolon-separated codes select definitions. |
| Indicators | `/indicator?format=json`, `/indicator/NY.GDP.MKTP.CD?source=2&format=json` | Code, name, unit, source, source note, source organization, topics. Specify source when a code appears in multiple databases. |
| Topics | `/topic?format=json`, `/topic/5?format=json` | Topic codes, names, notes. `/topic/5/indicator?format=json` or `/indicator?topic=5&format=json` lists its indicators. |
| Languages | `/languages?format=json` | Supported languages; prepend a code to the path, e.g. `/vi/country/VNM`, where translations exist. |

`/source/11/indicator/NY.GDP.MKTP.CD` is another documented form for selecting an indicator's source. Country or aggregate codes can occupy the same `country/{code}` position in observation queries. Look up aggregate definitions rather than inferring codes from labels.

## Retrieve observations

`/country/USA/indicator/SP.POP.TOTL?date=2000:2020&source=2&format=json` retrieves population observations. Use `country/all` for broad pulls, or semicolons for several geographies, e.g. `country/USA;CAN`. Several indicators can be separated with semicolons in `indicator/{code1};{code2}`, **with a single `source` ID**. The documentation limits multi-indicator calls to 60 indicators, 1,500 characters per path segment, and 4,000 characters in the URL. Split larger requests.

| Parameter | Meaning / caution |
| --- | --- |
| `date=2000` or `date=2000:2020` | One period or inclusive range. The API also documents monthly labels such as `2012M01`, quarterly labels such as `2013Q1`, and `YTD:2013` for applicable high-frequency series. |
| `page=N`, `per_page=N` | Pagination. Default `per_page` is 50. Read `pages` or `total`; do not assume one response is complete. |
| `mrv=N` | Most recent N periods, possibly with missing values. |
| `mrnev=N` | Most recent N nonempty values. Availability may differ among countries. |
| `gapfill=Y` | With `mrv`, backtracks within its window to fill missing periods. Record use of this option; it changes interpretation. |
| `frequency=M`, `Q`, or `Y` | Documented for high-frequency data with `mrv`; only use where the series supports it. |
| `footnote=y`, `ctrycode=y` | Include observation footnotes or World Bank country/aggregate code. |
| `scale=y` | Documented to scale values and return a scale field. A live XML call did this, while the same JSON call returned the raw value without a `scale` field. Verify the actual format and value before using scaled data. |
| `source=ID` | Select the database; especially important for multi-indicator requests or duplicated codes. |

`format=json` commonly returns `[metadata, records]`. Metadata includes `page`, `pages`, `per_page`, `total`, and often `sourceid` and `lastupdated`. These fields can be strings or numbers. Observation records include nested `indicator` and `country`, `countryiso3code`, `date`, numeric `value` or `null`, `unit`, `obs_status`, and `decimal`; optional fields appear only when requested. Preserve a forecast status or footnote instead of silently presenting the point as an ordinary observed value. Some sources use different frequencies and period labels.

The API does not provide a general sort parameter. Sort client-side after collecting pages when order matters. The documented default response is XML; request JSON explicitly. Handle an error response even when HTTP status is 200: an invalid indicator returned a JSON array containing `message`, and an unsupported format returned an XML `<wb:error>`. Handle service downtime with a timeout, modest retry, or cached data.

## Formats and delivery

`format=xml`, `json`, JSONP (requires `prefix`), and beta `jsonstat` are documented. The docs show `format=jsonP`, but a live call required lowercase `format=jsonp`. `downloadformat=csv`, `xml`, or `excel` produces file downloads; CSV downloads include data plus country and indicator metadata. A live CSV call returned a ZIP, while a live Excel call returned a direct XLS file. `dataformat=table` or `list` changes the layout of applicable downloaded indicator data. Do not parse a download as ordinary JSON. Confirm actual content type and archive contents.

## Interpretation and provenance

Read `/indicator/{code}?source={id}&format=json` for the series definition and source organization. For detailed methodological fields, use the metadata calls in [advanced-and-formats.md](advanced-and-formats.md). Country metadata can change over time, and the current `/country` classification is not automatically a historical classification. Aggregate rows are published series, not necessarily arithmetic sums of the countries you selected. Check the series' source note, units, aggregation method, and coverage before making that claim.

World Bank's development guidance recommends caching, graceful handling of outages, and testing request shapes. Data and licensing terms can vary by dataset and third-party provider.

## Official documentation read

- [About the Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)
- [V2 features and enhancements](https://datahelpdesk.worldbank.org/knowledgebase/articles/1886674-new-features-and-enhancements-in-the-v2-api)
- [Basic call structures](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures)
- [Country queries](https://datahelpdesk.worldbank.org/knowledgebase/articles/898590-country-api-queries)
- [Aggregate queries](https://datahelpdesk.worldbank.org/knowledgebase/articles/898614-aggregate-api-queries)
- [Indicator queries](https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries)
- [Topic queries](https://datahelpdesk.worldbank.org/knowledgebase/articles/898611-topic-api-queries)
- [Development best practices](https://datahelpdesk.worldbank.org/knowledgebase/articles/902064-development-best-practices)
