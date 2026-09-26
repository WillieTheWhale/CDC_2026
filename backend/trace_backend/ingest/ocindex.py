# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""GI-TOC Global Organized Crime Index (2021, 2023, 2025 editions). https://ocindex.net/downloads"""
from __future__ import annotations

import re

import pandas as pd

from .. import config
from .http import fetch

URL = "https://ocindex.net/assets/downloads/global_oc_index.xlsx"
PATH = config.RAW / "gitoc" / "global_oc_index.xlsx"


def download(refresh: bool = False) -> str:
    return fetch(URL, PATH, refresh=refresh)


def _col(df: pd.DataFrame, pattern: str) -> pd.Series:
    for c in df.columns:
        if re.match(pattern, str(c).strip(), re.I):
            return pd.to_numeric(df[c], errors="coerce")
    return pd.Series(float("nan"), index=df.index)


def load(resolve) -> pd.DataFrame:
    xl = pd.ExcelFile(PATH, engine="calamine")
    frames = []
    for sheet in xl.sheet_names:
        m = re.match(r"(\d{4})_dataset", sheet)
        if not m:
            continue
        df = xl.parse(sheet)
        out = pd.DataFrame({
            "iso3": df["Country"].map(resolve), "country_name": df["Country"], "edition": int(m.group(1)),
            "criminality": _col(df, r"criminality avg"), "resilience": _col(df, r"resilience( avg)?[.,]?$"),
            "cocaine": _col(df, r"cocaine trade"), "heroin": _col(df, r"heroin trade"),
            "cannabis": _col(df, r"cannabis trade"), "synthetic": _col(df, r"synthetic drug trade"),
        })
        frames.append(out.dropna(subset=["iso3"]))
    return pd.concat(frames, ignore_index=True).drop_duplicates(["iso3", "edition"])
