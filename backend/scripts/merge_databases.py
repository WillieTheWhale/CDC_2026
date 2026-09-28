# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Merge the canonical collected-data archive with the backend's own derived data into one SQLite file.

    .venv/Scripts/python scripts/merge_databases.py [--out PATH]

Inputs (both opened read-only):
  * the canonical archive, `data_collection/work/trace.sqlite` (the teammate's collected data, release
    data-2026-09-26-v2, also in the team Drive folder as trace.sqlite.gz);
  * the backend's derived store, `backend/data/derived.sqlite` (model inputs, corridor edges, predictions,
    risk scores, typed-column metadata), which the API reads first;
  * the committed route-evidence seeds in `trace_backend/seed/` (cited country pairs and their sources).

Output: `data_collection/work/database_new.sqlite` (gitignored) plus a gzipped copy. The archive's tables keep
their names and rows unchanged; derived and seed tables are added under their own names (a name collision is an
error, never an overwrite). A `merge_manifest` table records each table's origin, row count and input checksums.
The backend can serve from this single file: point TRACE_DB_PATH at it (derived tables live in `main`, which the
adapter reads first), with or without the archive attached.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from trace_backend import config  # noqa: E402

SEED = BACKEND / "trace_backend" / "seed"
SEED_TABLES = {"route_evidence": SEED / "route_evidence.csv", "route_evidence_sources": SEED / "route_evidence_sources.csv"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tables(con: sqlite3.Connection, schema: str = "main") -> list[str]:
    return [r[0] for r in con.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type='table' "
                                      "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def read_seed(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    rows = list(csv.reader(lines))
    return rows[0], rows[1:]


def merge(out: Path, archive: Path = config.ARCHIVE_PATH, derived: Path = config.DB_PATH) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".partial")
    shutil.copyfile(archive, tmp)  # archive copied byte for byte; the source file is never opened for writing
    now = datetime.now(UTC).isoformat(timespec="seconds")
    manifest: list[tuple] = []
    with sqlite3.connect(tmp.resolve().as_uri(), uri=True) as con:  # uri=True so ATTACH accepts ?mode=ro
        base = tables(con)
        for t in base:
            manifest.append((t, "archive", archive.name, con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]))
        con.execute("ATTACH DATABASE ? AS d", (derived.resolve().as_uri() + "?mode=ro",))
        for t in tables(con, "d"):
            if t in base:
                raise SystemExit(f"table {t!r} exists in both inputs; refusing to overwrite")
            ddl = con.execute("SELECT sql FROM d.sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0]
            con.execute(ddl)
            con.execute(f'INSERT INTO main."{t}" SELECT * FROM d."{t}"')
            manifest.append((t, "backend_derived", derived.name, con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]))
        con.commit()
        con.execute("DETACH DATABASE d")
        for t, path in SEED_TABLES.items():
            if t in base:
                raise SystemExit(f"seed table {t!r} collides with the archive")
            header, rows = read_seed(path)
            con.execute(f'CREATE TABLE "{t}" ({", ".join(f"{c!r} TEXT" for c in header)})'.replace("'", '"'))
            con.executemany(f'INSERT INTO "{t}" VALUES ({", ".join("?" * len(header))})', rows)
            manifest.append((t, "backend_seed", f"trace_backend/seed/{path.name}", len(rows)))
        con.execute("CREATE TABLE merge_manifest (table_name TEXT PRIMARY KEY, origin TEXT, input TEXT, rows INTEGER, "
                    "merged_at TEXT)")
        con.executemany("INSERT INTO merge_manifest VALUES (?,?,?,?,?)", [(*m, now) for m in manifest])
        con.execute("CREATE TABLE merge_inputs (input TEXT PRIMARY KEY, sha256 TEXT, bytes INTEGER, note TEXT)")
        con.executemany("INSERT INTO merge_inputs VALUES (?,?,?,?)", [
            (archive.name, sha256(archive), archive.stat().st_size,
             "canonical collected-data archive (release data-2026-09-26-v2)"),
            (derived.name, sha256(derived), derived.stat().st_size, "backend derived store (API model inputs and outputs)"),
            *[(f"seed/{p.name}", sha256(p), p.stat().st_size, "committed cited route-evidence seed") for p in SEED_TABLES.values()],
        ])
        con.commit()
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise SystemExit(f"integrity_check failed: {ok}")
    con.close()  # the with-block only commits; Windows cannot rename an open file
    tmp.replace(out)
    gz = out.with_name(out.name + ".gz")
    with open(out, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    counts: dict[str, int] = {}
    for _, origin, _, _ in manifest:
        counts[origin] = counts.get(origin, 0) + 1
    return {"out": str(out), "bytes": out.stat().st_size, "sha256": sha256(out), "gz": str(gz),
            "gz_bytes": gz.stat().st_size, "gz_sha256": sha256(gz), "tables": counts, "integrity": ok}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=config.REPO / "data_collection" / "work" / "database_new.sqlite")
    print(merge(ap.parse_args().out))
