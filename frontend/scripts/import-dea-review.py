# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Convert a captured DEA index-card snapshot into an unpublished review queue.

This deliberately does not fetch DEA pages: ordinary CLI requests returned HTTP 403
in the research environment. Capture visible card fields from the official site and
save them as JSON with source, captured_at, and rows. This tool validates that
snapshot and produces candidate allegations, never published People profiles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

PREFIX = "Wanted for the following alleged federal violations:"
EXPLICIT_DRUG = re.compile(
    r"(?:\bdrugs?\b|controlled substanc|narcotic|cocaine|heroin|fentanyl|"
    r"methamphetamin|amphetamine|marijuana|marihuana|cannabis|opioid|"
    r"opium|\bMDMA\b|ecstasy|oxycodone|hydrocodone|morphine|ketamine|"
    r"\bLSD\b|phencyclidine|\bPCP\b|crack|poppy|precursor|pseudoephedrine)",
    re.I,
)


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "www.dea.gov":
        raise ValueError(f"not an official DEA HTTPS URL: {url}")
    if not parsed.path.startswith("/fugitives/") or parsed.path == "/fugitives/all":
        raise ValueError(f"not a DEA fugitive profile URL: {url}")


def import_snapshot(snapshot: dict) -> dict:
    if snapshot.get("source") != "https://www.dea.gov/fugitives/all":
        raise ValueError("snapshot must identify the official DEA All Fugitives index")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot.get("captured_at", "")):
        raise ValueError("snapshot requires a capture date; this is not a source date")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("snapshot requires nonempty rows")
    candidates = []
    seen = set()
    for row in rows:
        name, span, url = (row.get(key) for key in ("name", "offense", "url"))
        if not all(isinstance(item, str) and item.strip() for item in (name, span, url)):
            raise ValueError("each row needs nonempty name, offense, and URL")
        validate_url(url)
        if url in seen:
            raise ValueError(f"duplicate profile URL: {url}")
        seen.add(url)
        if not span.startswith(PREFIX):
            raise ValueError(f"missing exact allegation label: {url}")
        offense = span[len(PREFIX) :].strip()
        if not offense:
            raise ValueError(f"missing alleged offense: {url}")
        candidates.append(
            {
                "candidate_id": "dea-" + hashlib.sha256(url.encode()).hexdigest()[:16],
                "full_name": name.strip(),
                "source_url": url,
                "source_span": span,
                "exact_alleged_offense": offense,
                "source_publication_date": None,
                "source_last_updated": None,
                "capture_date": snapshot["captured_at"],
                "explicit_drug_wording": bool(EXPLICIT_DRUG.search(offense)),
                "current_wanted_status": "unverified",
                "organization_affiliation": None,
                "historical_operating_country": None,
                "photo_url": None,
                "photo_license": None,
                "review_status": "human_review_required",
            }
        )
    return {
        "_about": "AI-assisted: generated with ChatGPT (OpenAI). See docs/AI_USAGE.md. Unpublished DEA review queue only; no current wanted status, organization, geography, or photo rights inferred.",
        "kind": "unpublished_dea_review_queue",
        "source_index": snapshot["source"],
        "capture_date": snapshot["captured_at"],
        "counts": {
            "cards": len(candidates),
            "explicit_drug_wording": sum(c["explicit_drug_wording"] for c in candidates),
            "without_explicit_drug_wording": sum(not c["explicit_drug_wording"] for c in candidates),
            "auto_publishable_profiles": 0,
        },
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.input.read_text())
    result = import_snapshot(snapshot)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
