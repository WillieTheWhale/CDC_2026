# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Safeguards for edition-specific service data and geographic code mapping."""
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_sources import CEPII_CODE_FIX, Resolver, columns_for, parse_mark


def test_hri_unmeasured_fields_and_unknown_marks_stay_null():
    assert columns_for(2008) == ["policy", "nsp", "oat"]
    assert "dcr" not in columns_for(2008)
    assert "nsp_prison" not in columns_for(2014)
    assert "naloxone_peer" not in columns_for(2016)
    assert "naloxone" not in columns_for(2020)
    assert "naloxone" in columns_for(2022)
    assert parse_mark(None, 2008) == (None, "not_collected_in_edition", "")
    assert parse_mark("nd", 2024) == (None, "unknown", "")
    assert parse_mark("nk", 2010) == (None, "unknown", "")
    assert parse_mark("✕", 2024) == (0, "no", "")
    assert parse_mark("✓", 2024) == (1, "yes", "")
    assert parse_mark("✓a", 2020) == (1, "qualified_yes", "a")
    assert parse_mark("✕a", 2020) == (0, "qualified_no", "a")
    assert parse_mark("3", 2016) == (1, "yes", "")
    assert parse_mark("7", 2016) == (0, "no", "")


def test_literal_hri_typo_corrections_preserve_source_name():
    countries = pd.DataFrame([
        {"name": "Tunisia", "iso3": "TUN"},
        {"name": "Azerbaijan", "iso3": "AZE"},
        {"name": "Kyrgyz Republic", "iso3": "KGZ"},
        {"name": "San Marino", "iso3": "SMR"},
        {"name": "Tanzania", "iso3": "TZA"},
    ])
    resolver = Resolver(countries)
    for printed, code in [("Tunisa", "TUN"), ("Azerbijan", "AZE"),
                          ("Krygyzstan", "KGZ"), ("San Marí", "SMR")]:
        assert resolver.resolve(printed) == (code, "explicit_typo_correction", code)
    assert resolver.resolve("Tanzania (Zanzibar)") == (None, "subnational_not_merged", "TZA")
    assert resolver.resolve("Taiwan") == (None, "outside_world_bank_scope", "TWN")
    assert resolver.resolve("unknown place")[0] is None


def test_cepii_legacy_states_are_not_assigned_to_successors():
    assert CEPII_CODE_FIX == {"ROM": "ROU", "ZAR": "COD", "TMP": "TLS", "PAL": "PSE"}
    assert "YUG" not in CEPII_CODE_FIX
    assert "ANT" not in CEPII_CODE_FIX
