<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# DOJ document-to-person pilot review — 2026-09-26

The companion `doj-pilot-2026-09-26.json` is a **review queue only**. It is outside the top-level People fixture directory and never enters `manifest.json`. The script queries titles containing six organization names found in TRACE's existing curated network research, but title matches are only document discovery. No organization membership, person-to-person edge, drug type, legal status date, geographic association, image, or event date is inferred from a title or article publication date.

## Source, terms, and reproduction

- [DOJ News API documentation](https://www.justice.gov/developer/api-documentation/api_v1) permits JSON press-release retrieval, documents `parameters[title]`, and caps pages at 50. It warns that more than four requests per second may degrade service or be blocked. The importer waits at least 350 ms between requests.
- [DOJ legal policies](https://www.justice.gov/legalpolicies) say DOJ site information is public domain unless otherwise indicated. Attached photographs can have separate rights; this pilot stores **no images**. It stores short normalized source spans, a source article URL and UUID, publication date, and tentative legal event label. It omits article bodies, birth dates, street addresses, arrest locations, and coordinates.
- This is an archived result from the original sentence-only importer. The expanded importer now requires an explicit checkpoint path and produces the separate `doj-expanded-pilot-2026-09-26.json` review queue. The API is live, so later fresh crawls can differ as releases are added or corrected.

## Measured pilot

The bounded run made **10 API requests** and fetched **295 distinct press releases**. Query result counts were: Sinaloa Cartel 204, Jalisco New Generation 4, Clan del Golfo 14, Gulf Cartel 35, Los Zetas 36, and Cártel de Jalisco Nueva Generación 6. The script emitted **49 tentative event mentions** from **38 articles**, representing **33 distinct name strings**, not 33 verified unique people. Event labels: 24 guilty-plea reports, 13 sentencing reports, 9 conviction reports, and 3 charge reports. No arrest or sanction mention survived the strict same-span drug-context filter.

### Manual spot-check

I read the source span and official article URL for the following **25 distinct name strings** in the fixed pilot output. A `direct` verdict means the span itself names a human subject, says the tentative legal event, and mentions a drug or drug proceeds. It does **not** establish identity resolution, current status, seniority, network role, or suitability for the People map. `Partial` means the span uses only a surname or family-name pair; these need full-name resolution from the source article before any profile can be made.

| Candidate position (1-based) | Extracted name | Event in span | Name form |
|---:|---|---|---|
| 1 | Vasquez Hernandez | direct plea | Partial |
| 2 | Jaime Huerta-Tizoc | direct plea | Full |
| 3 | Jesus Manuel Salazar-Nunez | direct sentencing | Full |
| 4 | Guzman Loera | direct conviction | Partial |
| 10 | Jason Alto | direct plea | Full |
| 11 | Mario Burgueno | direct plea | Full |
| 12 | Alicia Pierce | direct plea | Full |
| 16 | Roberto Gallegos-Lechuga | direct sentencing | Full |
| 17 | Juan Manuel Alvarez-Inzunza | direct sentencing | Full |
| 18 | Genaro Garcia Luna | direct conviction | Full |
| 19 | Jose Leyva-Martinez | direct sentencing | Full |
| 20 | SINOHE ANTONIO ARAJUO MEZA | direct sentencing | Full |
| 21 | Salazar Flores | direct charge | Partial |
| 22 | Hector Alejandro Paez Garcia | direct plea | Full |
| 23 | Guzman Lopez | direct plea | Partial |
| 25 | Ovidio Guzman Lopez | direct plea | Full |
| 30 | Francisco Mendoza | direct sentencing | Full |
| 31 | Jose Alberto Camarena Rocha | direct sentencing | Full |
| 33 | Anselmo Nava-Sanchez | direct sentencing | Full |
| 35 | Gerardo Julio Rueda Torres | direct plea | Full |
| 36 | Torres Caranton | direct plea | Partial |
| 37 | Aurelio Cano Flores | direct conviction | Full |
| 38 | Lerma Plata | direct charge | Partial |
| 43 | Ediel Lopez Falcon | direct sentencing | Full |
| 49 | Ruben Oseguera-Gonzalez | direct sentencing | Full |

**Measured span-level event precision on this purposive 25-item sample: 25/25 (100%).** Full-name form in the same span: **19/25 (76%)**. This is a small, non-random spot-check of surfaced matches; it does not estimate recall, population precision, unique-person identity precision, or publication readiness. The current pilot has **zero automatically publishable profiles**.

## Failure modes and gate before publication

During development, the broader matcher incorrectly captured place names (for example, a residence after `of`), nicknames in quoted text, sentence openers, and firearms-only events that happened to contain “trafficker” or “Cartel.” The final script rejects those observed patterns and requires a named subject, legal verb, and drug term in the same source span. It still misses many valid releases whose person and event are in separate sentences, whose grammar differs, or whose source uses another language. A name string can appear in several releases; an article can describe an old case, and its publication date is not the arrest, charge, plea, or sentencing date. Before promotion, a reviewer must open the full article, confirm the complete identity and exact event date, review later status changes, verify any senior role or organization relationship from an explicit claim, and record image rights separately. A charge remains an allegation.
