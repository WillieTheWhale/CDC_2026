# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Build a self-contained Vercel deployment of the TRACE API into backend/.vercel_deploy/ (gitignored).

    .venv/Scripts/python scripts/build_vercel.py
    cd .vercel_deploy && vercel deploy --prod

The package contains the backend code, the precomputed API JSON, the trained route model, and a slim SQLite
database (the derived tables plus the two archive tables the simulator reads: countries, cultivation, plus the
evidence-drilldown tables, see copy_evidence). The 1.2 GB canonical archive is NOT deployed. Live Wire does not poll
GDELT; it classifies with Reflex through the torch-free ONNX backend (onnxruntime + tokenizers): the chosen ONNX variant,
tokenizer.json and reflex.json go to data/reflex/model/, and the session is created on the first Live Wire read.
Build the ONNX files first with scripts/export_reflex_onnx.py (the build stops if they are missing; pass
--no-reflex to deploy the keyword mock instead, which /api/meta then reports).
"""
from __future__ import annotations

import argparse
import os
import json
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
                  "health_pwid", "health_treatment",
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
REFLEX_REQUIREMENTS = """onnxruntime>=1.20
tokenizers>=0.20
"""
APP = '''# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Vercel entrypoint for the TRACE API (FastAPI)."""
import os

os.environ.setdefault("TRACE_CLASSIFIER", "{classifier}")
os.environ.setdefault("TRACE_REFLEX_BACKEND", "onnx")  # Reflex through onnxruntime; torch is not deployed
os.environ.setdefault("TRACE_REFLEX_URL", "{reflex_url}")  # the separate TRACE Reflex function (reflex-remote)
os.environ.setdefault("TRACE_LIVEWIRE_POLL", "0")
os.environ.setdefault("TRACE_PEOPLE_REMOTE", "1")  # re-read People from GitHub main (bundled copy as fallback)

# LightGBM's libgomp shim (trace_backend/native.py) runs lazily on the first simulator request, not at cold start.
# onnxruntime does not need it (its CPU build uses its own thread pool, no OpenMP). The Reflex ONNX session is created
# on the first Live Wire read (trace_backend/reflex/model.py ReflexOnnx), so other endpoints' cold start is unchanged.

from trace_backend.api.app import app  # noqa: E402,F401
'''
VERCEL_JSON = """{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "fastapi"
}
"""
def pyproject(reqs: str) -> str:
    return """[project]
name = "trace-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
""" + "".join(f'    "{r}",\n' for r in reqs.split()) + """]

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


def copy_reflex_onnx(data: Path) -> str:
    """ONNX Reflex (only the default variant named in data/reflex/onnx/reflex.json) -> data/reflex/model/, where
    jev.real.get_classifier looks for reflex.json, plus the precomputed eval.json that /api/metrics reports."""
    from trace_backend.reflex.model import ONNX_DIR
    meta_path = ONNX_DIR / "reflex.json"
    if not meta_path.exists():
        sys.exit(f"no ONNX Reflex in {ONNX_DIR}: run `.venv/Scripts/python scripts/export_reflex_onnx.py` first "
                 "(or build with --no-reflex to deploy the keyword mock)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model = (meta.get("onnx") or {}).get("file", "model.int8.onnx")
    dst = data / "reflex" / "model"
    dst.mkdir(parents=True)
    for f in (model, *(meta.get("onnx") or {}).get("external_data", []), "tokenizer.json", "reflex.json"):
        if not (ONNX_DIR / f).exists():
            sys.exit(f"missing {ONNX_DIR / f}; re-run scripts/export_reflex_onnx.py")
        shutil.copy(ONNX_DIR / f, dst / f)
    if (config.DATA / "reflex" / "eval.json").exists():
        shutil.copy(config.DATA / "reflex" / "eval.json", data / "reflex" / "eval.json")
    return f"{meta.get('model_id')} ({model}, {(dst / model).stat().st_size / 1e6:.1f} MB)"



PRECLASSIFY = r"""
import os, sys, json
sys.path.insert(0, ".")
import app  # noqa: F401  (sets the deployed env: Reflex via ONNX, no poller)
from trace_backend.api.livewire import state, STORE_PATH
lw = state()
lw.ensure_backlog()
lw._save()
events = json.loads(STORE_PATH.read_text(encoding="utf-8"))
print(json.dumps({"events": len(events), "classifiers": sorted({e.get("classifier") for e in events}),
                  "torch": "torch" in sys.modules}))
"""


def preclassify_livewire() -> dict:
    """Classify the Live Wire replay backlog once, with the packaged app itself (ONNX Reflex + grounding, exactly
    as deployed), and ship the result as the event store. The backlog is a fixed labelled sample and the model is
    deterministic, so this equals what the first reader would compute; it removes a ~15-60 s first-request stall on
    a 1-vCPU function."""
    import subprocess
    env = {**os.environ, "TRACE_LIVEWIRE_POLL": "0", "TRACE_PEOPLE_REMOTE": "0", "TRACE_REFLEX_THREADS": "0",
           "TRACE_ARCHIVE_PATH": str(OUT / "no-archive.sqlite"), "TRACE_DB_PATH": str(OUT / "data" / "derived.sqlite"),
           "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "-c", PRECLASSIFY], cwd=OUT, env=env, capture_output=True, text=True,
                         timeout=900)
    if out.returncode != 0:
        sys.exit("Live Wire pre-classification failed:\n" + out.stderr[-2000:])
    res = json.loads(out.stdout.strip().splitlines()[-1])
    if res["torch"] or res["classifiers"] != ["reflex-0.2.0"] or res["events"] < 1:
        sys.exit(f"Live Wire pre-classification produced unexpected output: {res}")
    return res

def build(reflex: bool = True, reflex_url: str = "https://trace-reflex.vercel.app") -> Path:
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
    from trace_backend.api.estimated_flows import precompute  # ship every year's arrow layer precomputed
    print(f"  estimated flows: {precompute(data / 'processed' / 'api' / 'estimated_flows')} layers")
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
    reqs = REQUIREMENTS + (REFLEX_REQUIREMENTS if reflex else "")
    if reflex:
        print(f"  reflex onnx: {copy_reflex_onnx(data)}")
    (OUT / "requirements.txt").write_text(reqs, encoding="utf-8")
    (OUT / "pyproject.toml").write_text(pyproject(reqs), encoding="utf-8")
    app = APP.replace("{reflex_url}", reflex_url)
    (OUT / "app.py").write_text(app.replace("{classifier}", "reflex" if reflex else "mock"), encoding="utf-8")
    if reflex:
        # Classify the Live Wire backlog with the real ONNX model in the package, then ship without the model and
        # onnxruntime (the API bundle would exceed Vercel's 500 MB function limit) and call the Reflex service instead.
        print(f"  live wire pre-classified: {preclassify_livewire()}")
        model_dir = data / "reflex" / "model"
        for f in model_dir.iterdir():
            if f.name != "reflex.json":
                f.unlink()
        (OUT / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
        (OUT / "pyproject.toml").write_text(pyproject(REQUIREMENTS), encoding="utf-8")
        (OUT / "app.py").write_text(app.replace("{classifier}", "reflex-remote"), encoding="utf-8")
        print(f"  live classifier: reflex-remote -> {reflex_url}")
    (OUT / "vercel.json").write_text(VERCEL_JSON, encoding="utf-8")
    (OUT / ".python-version").write_text("3.12\n", encoding="utf-8")
    return OUT


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-reflex", action="store_true", help="deploy the keyword mock instead of ONNX Reflex")
    ap.add_argument("--reflex-url", default=os.environ.get("TRACE_REFLEX_URL", "https://trace-reflex.vercel.app"),
                    help="the deployed Reflex service (scripts/build_vercel_reflex.py)")
    args = ap.parse_args()
    out = build(reflex=not args.no_reflex, reflex_url=args.reflex_url)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    db_mb = (out / "data" / "derived.sqlite").stat().st_size / 1e6
    print(f"built {out} ({size / 1e6:.1f} MB; derived.sqlite {db_mb:.1f} MB)")
