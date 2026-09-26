# AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"""Merge independent collectors and distribute a verified, immutable SQLite snapshot.

Only the coordinator writes the canonical database. Raw downloads and response JSON
are reproducibility caches; the SQLite archive is the collected-data source of truth.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "work/trace.sqlite"
DEFAULT_SHARDS = [ROOT / "work" / f"{name}.sqlite" for name in ("world_bank", "unodc", "context")]
AI_NOTICE = "AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md."


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inspect(db: Path) -> dict:
    path = db
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as con:
        result = con.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            raise ValueError(f"SQLite integrity failure: {result}")
        foreign_keys = con.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise ValueError(f"Broken foreign keys: {foreign_keys[:10]}")
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        tables = {}
        for (name,) in rows:
            columns = [r[1] for r in con.execute(f"PRAGMA table_info({quote(name)})")]
            count = con.execute(f"SELECT count(*) FROM {quote(name)}").fetchone()[0]
            tables[name] = {"rows": count, "columns": columns}
            if "year" in columns:
                bounds = con.execute(f"SELECT min(year),max(year) FROM {quote(name)}").fetchone()
                tables[name]["first_year"], tables[name]["last_year"] = bounds
        return {"integrity_check": "ok", "foreign_key_check": "ok", "tables": tables}


def merge(shards: list[Path], output: Path) -> dict:
    if not shards or len(set(p.resolve() for p in shards)) != len(shards):
        raise ValueError("Provide distinct completed shards")
    for shard in shards:
        if not shard.is_file() or shard.resolve() == output.resolve():
            raise ValueError(f"Invalid shard: {shard}")
        inspect(shard)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".sqlite.part")
    temporary.unlink(missing_ok=True)
    try:
        with sqlite3.connect(temporary, uri=True) as con:
            con.execute("PRAGMA journal_mode=DELETE")
            con.execute("PRAGMA user_version=1")
            con.execute("CREATE TABLE collection_shards (name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, merged_at TEXT NOT NULL)")
            con.execute("CREATE TABLE collection_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            con.executemany("INSERT INTO collection_metadata VALUES (?, ?)", [
                ("ai_assistance", AI_NOTICE), ("storage_engine", "SQLite"),
                ("history_policy", "Keep all source-native years and nulls; no backcasts or future-to-past survey fills"),
            ])
            con.commit()
            known = {"collection_shards", "collection_metadata"}
            for shard in shards:
                con.execute("ATTACH DATABASE ? AS incoming", (shard.resolve().as_uri() + "?mode=ro",))
                schema = con.execute("SELECT type,name,sql FROM incoming.sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 WHEN 'view' THEN 2 ELSE 3 END").fetchall()
                names = {name for _, name, sql in schema if sql}
                if known.intersection(names):
                    raise ValueError(f"Shard schema name collision: {sorted(known.intersection(names))}")
                with con:
                    for kind, name, sql in schema:
                        if not sql:
                            continue
                        con.execute(sql)
                        if kind == "table":
                            con.execute(f"INSERT INTO main.{quote(name)} SELECT * FROM incoming.{quote(name)}")
                    con.execute("INSERT INTO collection_shards VALUES (?, ?, ?, ?)",
                                (shard.name, digest(shard), shard.stat().st_size, datetime.now(timezone.utc).isoformat()))
                con.execute("DETACH DATABASE incoming")
                known.update(names)
            con.execute("PRAGMA optimize")
        report = inspect(temporary)
        os.replace(temporary, output)
        return report
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def snapshot(db: Path, archive: Path, manifest: Path, tag: str, repository: str) -> dict:
    report = inspect(db)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".part")
    with db.open("rb") as src, temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
    os.replace(temporary, archive)
    data = {
        "_ai_assistance": AI_NOTICE, "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": repository, "release_tag": tag,
        "url": f"https://github.com/{repository}/releases/download/{tag}/{archive.name}",
        "archive": {"filename": archive.name, "bytes": archive.stat().st_size, "sha256": digest(archive)},
        "database": {"filename": "trace.sqlite", "bytes": db.stat().st_size, "sha256": digest(db)},
        **report,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, indent=2) + "\n")
    return data


def download(manifest: Path, output: Path) -> dict:
    data = json.loads(manifest.read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and digest(output) == data["database"]["sha256"]:
        return inspect(output)
    archive = output.with_suffix(".sqlite.gz.part")
    temporary = output.with_suffix(".sqlite.part")
    try:
        request = Request(data["url"], headers={"User-Agent": "TRACE historical data collector"})
        with urlopen(request, timeout=120) as response, archive.open("wb") as f:
            shutil.copyfileobj(response, f, 1024 * 1024)
        if archive.stat().st_size != data["archive"]["bytes"] or digest(archive) != data["archive"]["sha256"]:
            raise ValueError("Downloaded archive does not match the published checksum")
        with gzip.open(archive, "rb") as src, temporary.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        if temporary.stat().st_size != data["database"]["bytes"] or digest(temporary) != data["database"]["sha256"]:
            raise ValueError("Extracted SQLite database does not match the published checksum")
        report = inspect(temporary)
        os.replace(temporary, output)
        return report
    finally:
        archive.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("merge")
    p.add_argument("--shards", nargs="+", type=Path, default=DEFAULT_SHARDS)
    p.add_argument("--output", type=Path, default=DEFAULT_DB)
    p = sub.add_parser("inspect")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p = sub.add_parser("snapshot")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--archive", type=Path, default=ROOT / "work/trace.sqlite.gz")
    p.add_argument("--manifest", type=Path, default=ROOT / "snapshot.json")
    p.add_argument("--tag", required=True)
    p.add_argument("--repository", default="WillieTheWhale/CDC_2026")
    p = sub.add_parser("download")
    p.add_argument("--manifest", type=Path, default=ROOT / "snapshot.json")
    p.add_argument("--output", type=Path, default=DEFAULT_DB)
    args = vars(parser.parse_args())
    command = args.pop("command")
    print(json.dumps(globals()[command](**args), indent=2))


if __name__ == "__main__":
    main()
