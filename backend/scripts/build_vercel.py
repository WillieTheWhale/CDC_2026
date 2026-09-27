# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Build a self-contained Vercel deployment of the TRACE API into backend/.vercel_deploy/ (gitignored).

    .venv/Scripts/python scripts/build_vercel.py
    cd .vercel_deploy && vercel deploy --prod

The package contains the backend code, the precomputed API JSON, the trained route model, and a slim SQLite
database (the derived tables plus the two archive tables the simulator reads: countries, cultivation). The 1.2 GB
canonical archive is NOT deployed. Live Wire uses the keyword classifier (no torch) and does not poll GDELT.
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
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "llm_data", "results", "seed", "tests")


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
    print(f"built {out} ({size / 1e6:.1f} MB)")
