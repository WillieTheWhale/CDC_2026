# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Check evidence-source checksums, source locators and contextual claim boundaries."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from collect import CACHE, OUTPUT, page_text


def verify():
    assert OUTPUT.exists()
    with sqlite3.connect(OUTPUT.as_uri()+"?mode=ro",uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
        sources=db.execute("SELECT source_id,sha256,source_format FROM evidence_sources").fetchall()
        assert len(sources)==3
        for sid,sha,kind in sources:
            path=CACHE/(sid+(".xlsx" if kind=="xlsx" else ".html"))
            with path.open("rb") as handle:
                assert hashlib.file_digest(handle,"sha256").hexdigest()==sha
            if kind=="html":
                body=page_text(path)
                for excerpt, in db.execute("SELECT original_excerpt FROM evidence_claims WHERE source_id=?",(sid,)):
                    assert excerpt in body,(sid,excerpt)
        assert db.execute("SELECT count(*) FROM evidence_claims").fetchone()[0]==8
        assert db.execute("SELECT count(*) FROM evidence_claims WHERE claim_type='published_aggregate_corridor_context' AND observation_start_year=2020 AND observation_end_year=2024").fetchone()[0]==2
        assert db.execute("SELECT count(*) FROM evidence_claims WHERE claim_type='published_aggregate_corridor_context' AND observation_start_year=2021 AND observation_end_year=2024").fetchone()[0]==2
        assert db.execute("SELECT count(*) FROM evidence_claims WHERE claim_type='published_policy_milestone' AND policy_effective_date IS NOT NULL").fetchone()[0]==4
        assert db.execute("SELECT count(*) FROM evidence_claims WHERE caveat='' OR source_locator=''").fetchone()[0]==0
        print("evidence catalog verified: 3 sources, 8 claims")


if __name__=="__main__":verify()
