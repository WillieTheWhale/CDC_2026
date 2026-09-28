# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reflex v0.2 data: size normalisation rule and the committed Claude-written headline set."""
import json

import pytest

from trace_backend.reflex.data import DRUG_OPTS, EVENT_TYPES, LLM_DIR, normalise_size


@pytest.mark.parametrize("title,given,expected", [
    ("Czech customs seize 1 tonne of cocaine", "major", "notable"),
    ("Police seize 250 pounds of meth", "small", "notable"),
    ("Customs seize 2.3 tons of cocaine", "notable", "major"),
    ("Police find 40kg of heroin", "notable", "small"),
    ("Record 5 kg haul at the border", "small", "record"),
    ("Recordings show smugglers loading 20 kg", "notable", "small"),
    ("Police seize heroin worth millions", "notable", "notable"),  # no weight: label kept
])
def test_normalise_size(title, given, expected):
    assert normalise_size({"event_type": "seizure", "title": title, "size": given}) == expected


def test_non_seizure_size_untouched():
    assert normalise_size({"event_type": "violence", "title": "2 tonnes", "size": "small"}) == "small"


def test_committed_llm_batches_are_valid():
    files = sorted(LLM_DIR.glob("batch_*.jsonl"))
    assert len(files) >= 7
    n = 0
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            n += 1
            assert set(r) >= {"title", "is_event", "event_type", "drug", "origin", "destination", "size",
                              "route_mentioned"}
            assert r["event_type"] in EVENT_TYPES and r["drug"] in DRUG_OPTS
    assert n >= 2900
