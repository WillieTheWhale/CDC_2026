# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""DuckDB helpers: one local database, tables written from pandas frames."""
from __future__ import annotations

from contextlib import contextmanager

import duckdb
import pandas as pd

from . import config


@contextmanager
def connect(read_only: bool = False):
    config.ensure_dirs()
    con = duckdb.connect(str(config.DB_PATH), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def write_table(name: str, df: pd.DataFrame) -> int:
    with connect() as con:
        con.register("_df", df)
        con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _df')
        con.unregister("_df")
    return len(df)


def read_table(name: str) -> pd.DataFrame:
    with connect(read_only=True) as con:
        return con.execute(f'SELECT * FROM "{name}"').df()


def table_exists(name: str) -> bool:
    if not config.DB_PATH.exists():
        return False
    with connect(read_only=True) as con:
        return bool(con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()[0])
