# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""External ingest helpers: drug mapping, country names, seizure combination, HRI row parsing."""
import pandas as pd
import pytest

from trace_backend.ingest.hri import ROW
from trace_backend.ingest.names import CountryResolver
from trace_backend.ingest.run import combine_seizures
from trace_backend.ingest.unodc_annex import OPIUM_TO_HEROIN, map_drug, strip_footnotes

COUNTRIES = pd.DataFrame({"iso3": ["BOL", "IRN", "TUR", "COD", "COG", "CIV", "MMR", "USA"],
                          "name": ["Bolivia", "Iran, Islamic Rep.", "Turkiye", "Congo, Dem. Rep.", "Congo, Rep.",
                                   "Cote d'Ivoire", "Myanmar", "United States"]})


@pytest.mark.parametrize("group,name,drug", [
    ("Cocaine-type", "Cocaine hydrochloride", "cocaine"),
    ("Cocaine-type", '"Crack" cocaine', "cocaine"),
    ("Cocaine-type", "Coca leaf", None),
    ("Opioids", "Heroin", "heroin"),
    ("Opioids", "Opium", "heroin"),
    ("Amphetamine-type stimulants", "Methamphetamine", "meth"),
    ("Amphetamine-type stimulants", "4-Fluoromethamphetamine (4-FMA)", None),
    ("Cannabis-type drugs", "Cannabis herb (marijuana)", "cannabis"),
    ("Cannabis-type drugs", "Cannabis plants", None),
    ("Cannabis-type drugs", "AM-2201", None),
])
def test_map_drug(group, name, drug):
    assert map_drug(group, name)[0] == drug


def test_opium_converted_to_heroin_equivalent():
    assert map_drug("Opioids", "Opium")[1] == pytest.approx(1 / OPIUM_TO_HEROIN)


@pytest.mark.parametrize("raw,iso3", [
    ("Bolivia (Plurinational State of)", "BOL"), ("Iran (Islamic Republic of)", "IRN"), ("Türkiye", "TUR"),
    ("Democratic Republic of the Congo", "COD"), ("Congo", "COG"), ("Côte d'Ivoire", "CIV"),
    ("United States of America", "USA"), ("Taiwan", None),
])
def test_country_resolver(raw, iso3):
    assert CountryResolver(COUNTRIES)(raw) == iso3


def test_strip_footnotes():
    assert strip_footnotes("Myanmar  b, c") == "Myanmar"
    assert strip_footnotes("Colombia") == "Colombia"


def test_hri_row_regex():
    m = ROW.match("Kenya ✓ ✓ ✓ ✕ ✓ ✓ ✕ ✕ ✕ ✓")
    assert m and m.group("name") == "Kenya"
    assert not ROW.match("Country/territory Explicit At least")


def test_combine_seizures_backcast_is_bounded():
    annex = pd.DataFrame({"iso3": ["COL"] * 3, "year": [2015, 2016, 2017], "drug": ["cocaine"] * 3,
                          "kg": [100.0, 110.0, 120.0]})
    ids = pd.DataFrame({"iso3": ["COL"] * 5, "year": [2011, 2012, 2015, 2016, 2017], "drug": ["cocaine"] * 5,
                        "kg": [1000.0, 1.0, 10.0, 10.0, 10.0]})
    out = combine_seizures(annex, ids).set_index("year")
    assert out.loc[2011, "kg"] == pytest.approx(300.0)       # index 100 clipped to 3
    assert out.loc[2012, "kg"] == pytest.approx(100.0 / 3)   # index 0.1 clipped to 1/3
    assert out.loc[2013, "basis"] == "carried_back"
    assert out.loc[2016, "basis"] == "annex"
