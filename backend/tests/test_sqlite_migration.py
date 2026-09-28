# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""SQLite adapter (derived DB + read-only archive) and archive-derived model inputs."""
import sqlite3

import numpy as np
import pandas as pd
import pytest

from trace_backend import config, db
from trace_backend.ingest import prepare
from trace_backend.model.spillover import protection, protection_at


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    arch = tmp_path / "archive.sqlite"
    with sqlite3.connect(arch) as con:
        pd.DataFrame([("COL", 2015, "cocaine", 100.0, "hist2015_x", 2015), ("COL", 2015, "cocaine", 120.0, "prices", 2026),
                      ("COL", 2012, "cocaine", 90.0, "hist2012_x", 2012)],
                     columns=["iso3", "year", "drug", "kg", "source", "edition"]).to_sql("seizures_annex", con, index=False)
    con.close()
    monkeypatch.setattr(config, "ARCHIVE_PATH", arch)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "derived.sqlite")
    return arch


def test_read_from_archive_write_to_derived(dbs):
    assert db.table_exists("seizures_annex")
    db.write_table("edges_test", pd.DataFrame({"a": [1, 2], "flag": [True, False]}))
    out = db.read_table("edges_test")
    assert out["flag"].dtype == bool and out["flag"].tolist() == [True, False]
    with sqlite3.connect(dbs) as con:  # archive untouched
        names = {r[0] for r in con.execute("select name from sqlite_master")}
    assert "edges_test" not in names


def test_archive_is_read_only(dbs):
    with db.connect() as con, pytest.raises(sqlite3.OperationalError):
        con.execute("insert into archive.seizures_annex values ('X', 2000, 'meth', 1, 's', 2000)")


def test_latest_edition_wins_per_country_year(dbs, monkeypatch):
    monkeypatch.setattr(config, "ROUTE_YEAR_MIN", 2006)
    s = prepare.seizures_country().set_index("year")
    assert s.loc[2015, "kg"] == 120.0 and s.loc[2015, "edition"] == 2026
    assert s.loc[2012, "kg"] == 90.0  # older edition kept for a year the newer one does not report


def test_protection_normalised_by_reported_fields():
    h = pd.DataFrame([{"iso3": "A", "year": 2010, "nsp": 1, "oat": 1, "naloxone": None, "dcr": None,
                       "prison_programs": None, "policy": 1}])
    assert protection(h)["protection"].iloc[0] == 100.0  # untracked fields are not counted as missing services


def test_protection_no_backfill_before_first_edition():
    hri = protection(pd.DataFrame([{"iso3": "A", "year": 2012, "nsp": 1, "oat": 0, "naloxone": np.nan, "dcr": 0,
                                    "prison_programs": 0, "policy": 1}]))
    grid = pd.DataFrame({"iso3": ["A", "A", "A"], "year": [2010, 2012, 2015]})
    p = protection_at(hri, grid)
    assert np.isnan(p.loc[0, "protection"]) and p.loc[1, "hri_year"] == 2012 and p.loc[2, "hri_year"] == 2012
