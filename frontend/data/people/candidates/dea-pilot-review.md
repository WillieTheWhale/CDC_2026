<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# DEA All Fugitives: unpublished review pilot

Audited 2026-09-26. Official index: https://www.dea.gov/fugitives/all . This is a discovery queue, not a set of TRACE People profiles. It contains DEA's allegations, not adjudicated findings; an index card alone does not prove current fugitive status, organization membership, operating country, or a dated event.

## Measured index

- Navigated all 52 pages of the rendered official index in Chrome: **517 unique profile URLs**, matching the displayed result count. This is an observed count on 2026-09-26, not a promise of 517 usable profiles.
- **329/517** index cards contain explicit drug or substance wording under the conservative classifier in `import-dea-review.py`; **188/517** lack this wording. The latter include money-laundering-only cards, generic "Conspiracy," citation-only 21 USC entries, misspellings such as "Cociane," and malformed concatenated text. Therefore 329 is a wording count, not the number of actual drug cases; 188 cannot all be labeled non-drug.
- **512/517** cards rendered an image. No photo was imported. Image presence does not establish creator, ownership, license, identity, or permission for reuse.

## Source and rights limits

The index and detail pages are official DEA pages. DEA describes its publication approval process at https://www.dea.gov/resources/accessibility-and-policy . The DOJ legal policy at https://www.justice.gov/legalpolicies says DOJ site information is generally public domain unless indicated otherwise, but it expressly confines its notice to the DOJ website and warns that photos and graphics from third parties can retain copyright. The DEA fugitive pages sampled showed no file-level creator, credit, or reuse license for their portraits. The pilot uses short factual allegation text with attribution to the exact DEA URL; it leaves `photo_url` and `photo_license` null. A future image must be checked at its original file/source, including creator, identity, credit, and license, before use.

The sampled detail pages showed no publication or last-updated date in visible page content or date metadata. A DOB `time` element and dates embedded in image paths are **not** source-publication dates. `capture_date` is the day of this observation, separate from `source_publication_date` and `source_last_updated`, which remain null. The site does not establish whether a listing is current as of the observation day; current wanted status must be independently verified before any TRACE status claim.

No private address, precise whereabouts, NCIC identifier, physical description, or live location from the profile tables is kept in the snapshot or queue. `Jurisdiction`, a `Last Known Address`, and "frequents" statements do not establish historical operating country. The queue never assigns an organization, operating country, or graph edge.

## Purposive profile check

Checked **29** detail pages spread from index positions 0 through 516, including explicit drug wording, generic/citation-only entries, money-laundering-only entries, a misspelled offense, and the no-image card. The index name and alleged-offense span matched the detail heading/value in **29/29** after whitespace normalization. Of these 29, **18/18** classifier-positive cards visibly contain explicit drug/substance wording; the other **11** are ambiguous or lack such wording and were not called non-drug. This checks extraction fidelity and positive wording precision in a purposive sample; it is not a statistical estimate of all 517 and does not validate the underlying allegations.

Detail pages with an extractable source publication/updated date: **0/29**. Directly stated organization affiliation in the profile allegation or notes: **0/29**. Directly stated historical operating country in those fields: **0/29**. Nine had a nonempty Notes field; examples were "Use Caution," "Armed and Dangerous," or a place/residence statement, none of which establishes network membership or operations. These findings are specific to the sampled fields and pages.

## Pilot and reproducibility

`dea-index-pilot.snapshot.json` preserves 12 official index cards selected across positive and ambiguous cases. Their names and allegation text were among the 29 detail-page checks. Run:

```sh
python3 frontend/scripts/import-dea-review.py \
  --input frontend/data/people/candidates/dea-index-pilot.snapshot.json \
  --output /tmp/dea-pilot-recomputed.json
cmp /tmp/dea-pilot-recomputed.json frontend/data/people/candidates/dea-pilot-2026-09-26.json
```

Measured pilot output: **12 review candidates**, **6** with explicit drug wording, **6** without it, **0** auto-publishable People profiles. The generated file stays outside the published People manifest.

To capture a future larger snapshot, open the official index in a browser and collect only each `.teaser-content` card's `h3 a` name/href and `.teaser__text` exact text, following the visible `Next` links. Record the capture date and official index URL. Do not collect `.teaser__media` image URLs or profile-table personal fields. Direct non-browser HTTPS requests from this environment received HTTP 403 from DEA's CDN; the importer deliberately consumes a cited, browser-observed snapshot rather than bypassing site controls. The capture step and all resulting allegations require fresh manual verification before publication.

## Publication gate

For any candidate, separately verify current legal status, allegation chronology and outcome, a named organization's link in a direct source, and a country-level *historical operating* association. Treat later acquittals, dismissals, arrests, or sanctions changes as controlling updates. Add portraits only with file-level rights and identity evidence. Until then, keep these records in review only.
