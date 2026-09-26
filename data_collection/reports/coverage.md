<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Historical coverage and analysis windows

Generated 2026-09-26T18:47:30.025232+00:00 from the verified merged SQLite archive.

## Decision

**Long-history spine: 1990–2024 (35 calendar years).** World Bank market-size and public-health series have observed values throughout this interval. UNODC published national drug-price series also span it. In 1990 those price rows cover 17 named Western/Central European countries plus the United States, and some are source-provided estimates, flagged in the table below. Regional averages are not copied into country records. This supports source-specific longitudinal analysis; it does not imply every country, drug or indicator is measured every year. Use available country-years and report each result's denominator.

**Archive: all original years.** World Bank non-null values span 1960–2025 across 24 indicators and 217 current economies. Its 308,796 country observations include 181,190 explicit nulls. No source is truncated to the first year of a newer supplement.

**Later supplements keep their actual dates.** National seizure annexes, individual seizure cases, cultivation, OC Index and HRI services enter only where their source supports them. An analysis using reported seizures has a shorter documented window than the price and World Bank analyses. Seizure country alone does not reveal a trade route. Edition-based context never becomes a historical backtest predictor by carrying its newer values backward.

There is no requirement that all variables overlap. Missing values stay null; the collection does not impute, interpolate or backcast. A later model must document feature availability, publication lag and its training-only missing-data policy. Retrospective source releases alone are not a point-in-time backtest archive.

## Source windows in the collected database

| Source table | First observed year | Latest observed year | Records |
| --- | ---: | ---: | ---: |
| World Bank non-null values | 1960 | 2025 | 127,606 |
| UNODC normalized prices | 1990 | 2024 | 5,349 |
| UNODC national seizure totals | 2006 | 2024 | 10,739 |
| UNODC individual seizure aggregates | 2011 | 2026 | 3,055 |
| UNODC cultivation | 1999 | 2025 | 203 |
| OC Index editions | 2021 | 2025 | 579 |
| HRI service editions | 2008 | 2024 | 1,206 |

## World Bank long-history indicators

Non-null country-years within 1990–2024; individual gaps remain in SQLite.

| Indicator | Non-null country-years |
| --- | ---: |
| gdp | 7,215 |
| population | 7,595 |
| gdp_pc_ppp | 6,792 |
| trade_gdp | 5,996 |
| homicide_rate | 4,065 |
| hiv_incidence | 5,053 |

## Year-by-year spine support

GDP + population counts economies with both market-size observations. The harm column also requires either homicide or HIV incidence. Other columns count observed source records, not matched country-years. National seizure records are edition-specific and can overlap; never sum them without choosing an edition. Source estimate counts identify values the UNODC source itself flags as estimates. Zero means no reported observation, not zero activity.

| Year | WB variables | WB values | GDP + population economies | With harm outcome | Price records | Price economies | Source price estimates | National seizure edition records | IDS country/drug aggregates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1990 | 14 | 1,533 | 192 | 163 | 72 | 18 | 22 | 0 | 0 |
| 1991 | 15 | 1,740 | 193 | 164 | 72 | 18 | 29 | 0 | 0 |
| 1992 | 15 | 1,826 | 194 | 166 | 72 | 18 | 23 | 0 | 0 |
| 1993 | 15 | 1,841 | 195 | 165 | 72 | 18 | 20 | 0 | 0 |
| 1994 | 15 | 1,890 | 196 | 167 | 72 | 18 | 18 | 0 | 0 |
| 1995 | 15 | 1,943 | 199 | 172 | 72 | 18 | 14 | 0 | 0 |
| 1996 | 19 | 2,699 | 199 | 176 | 72 | 18 | 5 | 0 | 0 |
| 1997 | 15 | 1,946 | 201 | 175 | 72 | 18 | 5 | 0 | 0 |
| 1998 | 19 | 2,739 | 202 | 172 | 72 | 18 | 4 | 0 | 0 |
| 1999 | 15 | 1,992 | 202 | 175 | 72 | 18 | 8 | 0 | 0 |
| 2000 | 20 | 2,994 | 204 | 178 | 72 | 18 | 16 | 0 | 0 |
| 2001 | 16 | 2,237 | 205 | 181 | 72 | 18 | 10 | 0 | 0 |
| 2002 | 20 | 3,047 | 209 | 185 | 72 | 18 | 12 | 0 | 0 |
| 2003 | 20 | 3,047 | 209 | 177 | 72 | 18 | 6 | 0 | 0 |
| 2004 | 20 | 3,112 | 209 | 184 | 102 | 34 | 12 | 0 | 0 |
| 2005 | 21 | 3,131 | 209 | 182 | 131 | 44 | 17 | 0 | 0 |
| 2006 | 21 | 3,152 | 210 | 187 | 135 | 47 | 17 | 450 | 0 |
| 2007 | 23 | 3,452 | 210 | 190 | 141 | 47 | 5 | 423 | 0 |
| 2008 | 21 | 3,197 | 211 | 196 | 203 | 70 | 12 | 438 | 0 |
| 2009 | 21 | 3,237 | 213 | 196 | 236 | 70 | 25 | 891 | 0 |
| 2010 | 23 | 3,741 | 213 | 195 | 372 | 83 | 27 | 820 | 0 |
| 2011 | 22 | 3,576 | 214 | 193 | 134 | 43 | 21 | 431 | 157 |
| 2012 | 23 | 3,749 | 212 | 189 | 139 | 42 | 23 | 430 | 175 |
| 2013 | 21 | 3,422 | 212 | 186 | 339 | 72 | 23 | 393 | 150 |
| 2014 | 24 | 3,915 | 213 | 187 | 72 | 18 | 16 | 412 | 133 |
| 2015 | 21 | 3,454 | 212 | 183 | 72 | 18 | 7 | 852 | 104 |
| 2016 | 23 | 3,771 | 211 | 178 | 72 | 18 | 20 | 859 | 123 |
| 2017 | 22 | 3,596 | 211 | 183 | 72 | 18 | 15 | 822 | 156 |
| 2018 | 23 | 3,795 | 211 | 184 | 72 | 18 | 15 | 838 | 223 |
| 2019 | 21 | 3,468 | 211 | 183 | 70 | 18 | 17 | 423 | 220 |
| 2020 | 21 | 3,394 | 210 | 180 | 395 | 85 | 12 | 394 | 247 |
| 2021 | 22 | 3,522 | 210 | 175 | 418 | 88 | 12 | 468 | 240 |
| 2022 | 24 | 3,667 | 209 | 169 | 417 | 87 | 22 | 465 | 286 |
| 2023 | 21 | 3,280 | 204 | 160 | 369 | 81 | 15 | 461 | 307 |
| 2024 | 20 | 2,917 | 200 | 133 | 380 | 80 | 24 | 469 | 248 |

## All World Bank variables

| Variable | First observed | Latest observed | Economies ever observed | Non-null values |
| --- | ---: | ---: | ---: | ---: |
| gdp | 1960 | 2025 | 214 | 11764 |
| population | 1960 | 2025 | 217 | 14292 |
| refugees_asylum | 1960 | 2025 | 189 | 7511 |
| refugees_origin | 1960 | 2025 | 203 | 7365 |
| trade_gdp | 1960 | 2025 | 194 | 9029 |
| gini | 1963 | 2025 | 171 | 2430 |
| poverty | 1963 | 2025 | 171 | 2430 |
| air_passengers | 1970 | 2023 | 185 | 7929 |
| remittances_gdp | 1970 | 2025 | 199 | 7114 |
| youth_neet | 1970 | 2025 | 182 | 2520 |
| battle_deaths | 1989 | 2024 | 109 | 1212 |
| gdp_pc_ppp | 1990 | 2025 | 199 | 6977 |
| hiv_incidence | 1990 | 2024 | 146 | 5053 |
| homicide_rate | 1990 | 2023 | 196 | 4065 |
| youth_unemployment | 1991 | 2025 | 187 | 6531 |
| control_corruption | 1996 | 2025 | 207 | 5408 |
| gov_effectiveness | 1996 | 2025 | 205 | 5373 |
| political_stability | 1996 | 2025 | 207 | 5462 |
| rule_of_law | 1996 | 2025 | 207 | 5503 |
| health_exp_pc | 2000 | 2024 | 193 | 4559 |
| port_teu | 2005 | 2024 | 168 | 2232 |
| lpi_customs | 2007 | 2022 | 169 | 1071 |
| lpi_overall | 2007 | 2022 | 169 | 1071 |
| account_ownership | 2011 | 2024 | 161 | 705 |

## Provenance

- [World Bank source IDs, API provenance and licenses](world_bank.md)
- [UNODC files, units and collection limits](unodc.md)
- [OC Index, HRI editions and CEPII context](context_sources.md)
- [Verified snapshot manifest and table counts](../snapshot.json)
