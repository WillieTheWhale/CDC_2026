# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""SQLite access (migrated from DuckDB, 2026-09-26, per the owner's choice of SQLite as canonical storage).

Two databases:
- archive (read-only): the canonical collected-data SQLite from data_collection/ (config.ARCHIVE_PATH).
- derived (read-write, config.DB_PATH): model inputs derived from the archive, edges, predictions, risk.
  Derived tables are kept separate from the observational archive, as data_collection/README.md asks.

`read_table(name)` looks in the derived database first, then the archive. `write_table` always writes to the
derived database. Column dtypes that SQLite cannot hold (bool) are recorded in `_dtypes` and restored on read.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import TYPE_CHECKING

from . import config

if TYPE_CHECKING:  # pandas is imported on first use so the read-only API endpoints never load it
    import pandas as pd

DTYPES = "_dtypes"


class ArchiveMissing(FileNotFoundError):
    pass


def archive_available() -> bool:
    return config.ARCHIVE_PATH.exists()


@contextmanager
def connect(read_only: bool = False):
    """Connection to the derived DB with the archive attached as schema `archive` (read-only)."""
    config.ensure_dirs()
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    mode = "ro" if read_only and config.DB_PATH.exists() else "rwc"
    con = sqlite3.connect(config.DB_PATH.resolve().as_uri() + f"?mode={mode}", uri=True)  # uri=True lets ATTACH use ?mode=ro
    try:
        if archive_available():
            con.execute("ATTACH DATABASE ? AS archive", (config.ARCHIVE_PATH.resolve().as_uri() + "?mode=ro",))
        yield con
    finally:
        con.close()  # explicit close: Windows keeps files locked otherwise


def schema_of(con: sqlite3.Connection, name: str) -> str | None:
    """Schema (main = derived, then archive) that holds table `name`, or None."""
    return _schema_of(con, name)


def _schema_of(con: sqlite3.Connection, name: str) -> str | None:
    for schema in ("main", "archive"):
        try:
            hit = con.execute(f"SELECT 1 FROM {schema}.sqlite_master WHERE type IN ('table','view') AND name = ?",
                              (name,)).fetchone()
        except sqlite3.OperationalError:
            continue
        if hit:
            return schema
    return None


def table_exists(name: str) -> bool:
    if not config.DB_PATH.exists() and not archive_available():
        return False
    with connect(read_only=True) as con:
        return _schema_of(con, name) is not None


def read_table(name: str, where: str | None = None, params: tuple = ()) -> pd.DataFrame:
    import pandas as pd

    with connect(read_only=True) as con:
        schema = _schema_of(con, name)
        if schema is None:
            if not archive_available():
                raise ArchiveMissing(f"table {name!r} not found and archive missing at {config.ARCHIVE_PATH}; "
                                     "run `python3 data_collection/manage.py download`")
            raise KeyError(f"table {name!r} not found in derived DB or archive")
        sql = f'SELECT * FROM {schema}."{name}"' + (f" WHERE {where}" if where else "")
        df = pd.read_sql_query(sql, con, params=params)
        if schema == "main" and _schema_of(con, DTYPES) == "main":
            for col, dt in con.execute(f"SELECT column, dtype FROM {DTYPES} WHERE tbl = ?", (name,)):
                if col in df and dt == "bool":
                    df[col] = df[col].map(lambda v: None if v is None or pd.isna(v) else bool(v)).astype(
                        "bool" if df[col].notna().all() else "object")
        return df


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    import pandas as pd

    with connect(read_only=True) as con:
        return pd.read_sql_query(sql, con, params=params)


def write_table(name: str, df: pd.DataFrame) -> int:
    import pandas as pd

    df = df.copy()
    bools = [c for c in df.columns if df[c].dtype == bool or
             (df[c].dtype == object and df[c].dropna().map(type).eq(bool).all() and df[c].notna().any())]
    for c in bools:
        df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else int(bool(v)))
    with connect() as con:
        df.to_sql(name, con, schema="main", if_exists="replace", index=False, chunksize=5000)
        con.execute(f"CREATE TABLE IF NOT EXISTS {DTYPES} (tbl TEXT, column TEXT, dtype TEXT)")
        con.execute(f"DELETE FROM {DTYPES} WHERE tbl = ?", (name,))
        con.executemany(f"INSERT INTO {DTYPES} VALUES (?, ?, 'bool')", [(name, c) for c in bools])
        con.commit()
    return len(df)
