<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# Person-region evidence audit

Run `node scripts/audit-person-regions.mjs --output data/people/audits/region-evidence-2026-09-26.json` from `frontend/` after fixture edits. The script examines top-level network fixtures, not the generated manifest or unpublished candidate queues. It counts each country association with a nonempty claim and period when supplied, plus a source URL matching a citable source on that person. Legacy associations without evidence remain visible and are counted as missing. Malformed evidence is counted as invalid.

The JSON report is a schema-coverage audit, **not** a source-content verification. A reviewer must still read each cited page and check that the named person's particular country association and timeframe follow from it. Do not infer physical presence from a delivery made on someone's behalf, an arrest, an intended destination, or a group's footprint. Countries are historical associations, not live locations.

The 2026-09-26 pilot manually backfills five Akasha Organization and two Sam Gor person-country claims. Hafeez's Kenya claim identifies only a cited supplier relationship involving a delivery in Kenya on his behalf; it does not claim he was present or belonged to the Akasha Organization. Tse Chi Lop's Australia claim describes the cited local operation through an Australian contact while he was based overseas. Roy Moo's association remains pending direct source verification.
