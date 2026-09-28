# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Harm Reduction International, Global State of Harm Reduction 2024, Table 1 (per-country services).

Extracted from the report PDF with pdfplumber. Each row is a country followed by ten marks
(check = yes, cross = no, nd = no data).
"""
from __future__ import annotations

import logging
import re

import pandas as pd
import pdfplumber

from .. import config
from .http import fetch

log = logging.getLogger(__name__)
URL = "https://hri.global/wp-content/uploads/2024/10/HRI-GSHR-2024_Full-Report_Final.pdf"
PATH = config.RAW / "hri" / "HRI-GSHR-2024_Full-Report_Final.pdf"
COLUMNS = ["policy", "nsp", "oat", "dcr", "naloxone", "naloxone_peer", "safer_smoking", "stimulant_rx",
           "nsp_prison", "oat_prison"]
MARK = r"(✓|✕|✗|nd)"
ROW = re.compile(rf"^(?P<name>[^\W\d_][\w .,'()\-’&]+?)\s+(?P<marks>(?:{MARK}\s*){{10}})$")


def download(refresh: bool = False) -> str:
    return fetch(URL, PATH, refresh=refresh)


def _val(m: str):
    return True if m == "✓" else False if m in ("✕", "✗") else None


def load(resolve) -> pd.DataFrame:
    rows, in_table = [], False
    with pdfplumber.open(PATH) as pdf:
        for page in pdf.pages[8:30]:
            text = page.extract_text() or ""
            if "TABLE 1" in text:
                in_table = True
            if not in_table:
                continue
            if "TABLE 2" in text and "TABLE 1" not in text:
                break
            lines = [ln.strip() for ln in text.splitlines()]
            for i, line in enumerate(lines):
                m = ROW.match(line)
                if not m:
                    continue
                marks = re.findall(MARK, m.group("marks"))
                name = m.group("name").strip()
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                # wrapped names ("Bosnia and" / "Herzegovina") continue on the next line without marks
                if (nxt and not re.search(MARK, nxt) and not nxt.isupper() and len(nxt.split()) <= 3
                        and not nxt.startswith(("THE GLOBAL", "TABLE", "Country"))):
                    name = f"{name} {nxt}"
                rec = {"country_name": name, **{c: _val(v) for c, v in zip(COLUMNS, marks,
                                                                                              strict=True)}}
                rows.append(rec)
    df = pd.DataFrame(rows).drop_duplicates("country_name")
    df["iso3"] = df["country_name"].map(resolve)
    df = df.dropna(subset=["iso3"]).drop_duplicates("iso3")
    df["prison_programs"] = df[["nsp_prison", "oat_prison"]].apply(
        lambda r: True if (r == True).any() else (False if r.notna().all() else None), axis=1)  # noqa: E712
    df["year"] = 2024
    log.info("HRI table 1: %d countries", len(df))
    return df.reset_index(drop=True)
