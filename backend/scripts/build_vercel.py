# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Build a self-contained Vercel deployment of the TRACE API into backend/.vercel_deploy/ (gitignored).

    .venv/Scripts/python scripts/build_vercel.py
    cd .vercel_deploy && vercel deploy --prod

The package contains the backend code, the precomputed API JSON, the trained route model, and a slim SQLite
database (the derived tables plus the two archive tables the simulator reads: countries, cultivation, plus the
evidence-drilldown tables, see copy_evidence). The 1.2 GB canonical archive is NOT deployed. Live Wire uses the keyword classifier (no torch) and does not poll GDELT.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from trace_backend import config  # noqa: E402

OUT = BACKEND / ".vercel_deploy"
ARCHIVE_TABLES = ["countries", "cultivation"]
# Evidence drilldown (trace_backend/api/evidence.py): small tables copied whole, same names as in the archive.
EVIDENCE_WHOLE = ["research_values", "research_metric_definitions", "research_value_inputs",
                  "research_regression_samples", "research_model_results", "market_derived", "market_metric_definitions",
                  "market_observations", "market_sources", "health_prevalence", "health_sources", "health_raw_rows",
                  "health_treatment_coverage", "evidence_claims", "evidence_sources", "seizures_annex",
                  "unodc_sources", "wb_indicator_meta"]
EVIDENCE_DROP_COLS = {"health_cdc_overdose": ["source_row_json"],  # 50 MB of raw JSON; every field is kept as columns
                      "wb_downloads": ["payload_gzip"]}          # raw API payloads; the URL/checksum is the provenance
REQUIREMENTS = """fastapi>=0.111
pandas>=2.2
numpy>=1.26
scipy>=1.12
scikit-learn>=1.4
lightgbm>=4.3
statsmodels>=0.14
joblib>=1.3
requests>=2.31
python-dotenv>=1.0
pydantic>=2
"""
APP = '''# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Vercel entrypoint for the TRACE API (FastAPI)."""
import os

os.environ.setdefault("TRACE_CLASSIFIER", "mock")
os.environ.setdefault("TRACE_LIVEWIRE_POLL", "0")
os.environ.setdefault("TRACE_PEOPLE_REMOTE", "1")  # re-read People from GitHub main (bundled copy as fallback)


def _preload_libgomp() -> None:
    """LightGBM needs libgomp.so.1, which Vercel's Python runtime lacks. scikit-learn's wheel vendors one under a
    hashed soname; copy it to /tmp with the soname rewritten to libgomp.so.1 (same length, NUL-padded) and load it
    globally so lib_lightgbm.so resolves against it."""
    import ctypes
    import glob
    import importlib.util
    from pathlib import Path

    try:
        ctypes.CDLL("libgomp.so.1")
        return
    except OSError:
        pass
    libs = Path(importlib.util.find_spec("sklearn").origin).parents[1] / "scikit_learn.libs"
    src = Path(sorted(glob.glob(str(libs / "libgomp-*.so*")))[0])
    old = src.name.encode()
    data = src.read_bytes().replace(old + b"\\0", b"libgomp.so.1".ljust(len(old) + 1, b"\\0"))
    dst = Path("/tmp/trace_gomp/libgomp.so.1")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    ctypes.CDLL(str(dst), mode=ctypes.RTLD_GLOBAL)


_preload_libgomp()

from trace_backend.api.app import app  # noqa: E402,F401
'''
VERCEL_JSON = """{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "fastapi"
}
"""
PYPROJECT = """[project]
name = "trace-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
""" + "".join(f'    "{r}",\n' for r in REQUIREMENTS.split()) + """]

[tool.vercel]
entrypoint = "app:app"
"""


def _copy(con: sqlite3.Connection, table: str, where: str = "", cols: list[str] | None = None) -> int:
    """archive.table -> main.table (optionally filtered / column-subset), keeping its DDL and indexes."""
    con.execute(f'DROP TABLE IF EXISTS main."{table}"')
    if cols is None:
        ddl = con.execute("SELECT sql FROM archive.sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
        con.execute(ddl)
        con.execute(f'INSERT INTO main."{table}" SELECT * FROM archive."{table}" AS t {where}')
    else:
        sel = ", ".join(f'"{c}"' for c in cols)
        con.execute(f'CREATE TABLE main."{table}" AS SELECT {sel} FROM archive."{table}" AS t {where}')
    for (idx,) in con.execute("SELECT sql FROM archive.sqlite_master WHERE type='index' AND tbl_name=? "
                              "AND sql IS NOT NULL", (table,)).fetchall():
        try:
            con.execute(idx)
        except sqlite3.OperationalError:  # index on a dropped column
            pass
    return con.execute(f'SELECT count(*) FROM main."{table}"').fetchone()[0]


def copy_evidence(con: sqlite3.Connection) -> dict[str, int]:
    """Copy the evidence tables into the slim DB: small tables whole, big ones only where a drilldown input needs them.

    unodc_cells / unodc_seizure_observations: the workbook rows linked from research_value_inputs.
    market_cells: the workbook rows of the observations named in market_derived.inputs_json.
    wb_indicators: the World Bank rows linked from research_value_inputs.
    """
    counts = {t: _copy(con, t) for t in EVIDENCE_WHOLE}
    for t, drop in EVIDENCE_DROP_COLS.items():
        cols = [r[1] for r in con.execute(f'PRAGMA archive.table_info("{t}")') if r[1] not in drop]
        counts[t] = _copy(con, t, cols=cols)
    con.execute("CREATE TEMP TABLE _rows(source_id TEXT, sheet TEXT, row_no INTEGER, PRIMARY KEY(source_id, sheet, row_no))")
    keys = set()
    for (k,) in con.execute("SELECT DISTINCT source_key FROM main.research_value_inputs "
                            "WHERE source_table = 'unodc_seizure_observations'"):
        sid, rest = k.split(":", 1)[1].split("|", 1)
        sheet, row = rest.rsplit("|", 1)
        keys.add((sid, sheet, int(row)))
    con.executemany("INSERT INTO temp._rows VALUES (?, ?, ?)", sorted(keys))
    hit = ("WHERE EXISTS (SELECT 1 FROM temp._rows k WHERE k.source_id = t.source_id AND k.sheet = t.sheet "
           "AND k.row_no = t.row_no)")
    counts["unodc_seizure_observations"] = _copy(con, "unodc_seizure_observations", hit)
    con.execute("CREATE INDEX IF NOT EXISTS main.unodc_seizure_row ON unodc_seizure_observations(source_id, sheet, row_no)")
    counts["unodc_cells"] = _copy(con, "unodc_cells", hit)
    con.execute("DELETE FROM temp._rows")
    con.execute("""INSERT OR IGNORE INTO temp._rows SELECT o.source_id, o.sheet, o.row_no FROM main.market_observations o
                   JOIN main.market_derived d, json_each(d.inputs_json) j
                   ON j.key GLOB '*_observation_id' AND o.observation_id = j.value""")
    counts["market_cells"] = _copy(con, "market_cells", hit)
    con.execute("DROP TABLE temp._rows")
    counts["wb_indicators"] = _copy(con, "wb_indicators", """WHERE EXISTS (SELECT 1 FROM main.research_value_inputs i
        WHERE i.source_table = 'wb_indicators' AND i.source_key = 'wb_indicators:' || t.iso3 || '|' || t.year || '|'
        || t.code || '|' || t.source_id)""")
    return counts


IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "llm_data", "results", "tests")


def build() -> Path:
    OUT.mkdir(exist_ok=True)
    for child in OUT.iterdir():  # empty in place (keeps .vercel, the project link, and works if OUT is a cwd)
        if child.name == ".vercel":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(BACKEND / "trace_backend", OUT / "trace_backend", ignore=IGNORE)
    data = OUT / "data"
    for sub in ("raw", "cache"):
        (data / sub).mkdir(parents=True)
        (data / sub / ".keep").write_text("", encoding="utf-8")
    shutil.copytree(config.PROCESSED / "api", data / "processed" / "api")
    (data / "processed" / "models").mkdir(parents=True)
    shutil.copy(config.PROCESSED / "models" / "hurdle.joblib", data / "processed" / "models" / "hurdle.joblib")
    for f in ("metrics.json", "wb_manifest.json", "ingest_manifest.json"):
        if (config.PROCESSED / f).exists():
            shutil.copy(config.PROCESSED / f, data / "processed" / f)
    people = config.REPO / "frontend" / "data" / "people" / "manifest.json"  # read-only; frontend team curates it
    if people.exists():
        (data / "people").mkdir()
        shutil.copy(people, data / "people" / "manifest.json")
    db = data / "derived.sqlite"
    shutil.copy(config.DB_PATH, db)
    with sqlite3.connect(db.resolve().as_uri(), uri=True) as con:  # uri=True so ATTACH accepts ?mode=ro
        con.execute("ATTACH DATABASE ? AS archive", (config.ARCHIVE_PATH.resolve().as_uri() + "?mode=ro",))
        for t in ARCHIVE_TABLES:
            con.execute(f'DROP TABLE IF EXISTS main."{t}"')
            con.execute(f'CREATE TABLE main."{t}" AS SELECT * FROM archive."{t}"')
        for t, n in copy_evidence(con).items():
            print(f"  evidence {t}: {n} rows")
        con.commit()
        con.execute("DETACH DATABASE archive")
        con.execute("VACUUM")
    con.close()
    (OUT / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (OUT / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (OUT / "app.py").write_text(APP, encoding="utf-8")
    (OUT / "vercel.json").write_text(VERCEL_JSON, encoding="utf-8")
    (OUT / ".python-version").write_text("3.12\n", encoding="utf-8")
    return OUT


if __name__ == "__main__":
    out = build()
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    db_mb = (out / "data" / "derived.sqlite").stat().st_size / 1e6
    print(f"built {out} ({size / 1e6:.1f} MB; derived.sqlite {db_mb:.1f} MB)")
