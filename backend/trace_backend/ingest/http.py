# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reproducible downloads for external sources (raw files stay out of git)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (TRACE research project; CDC 2026)"}

MAGIC = {".xlsx": b"PK", ".zip": b"PK", ".pdf": b"%PDF", ".xls": b"\xd0\xcf\x11\xe0"}


def fetch(url: str, dest: Path, refresh: bool = False, timeout: float = 600, retries: int = 3) -> str:
    """Download url to dest. Returns 'cached', 'downloaded', or raises. Validates file magic bytes."""
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(retries):
        try:
            with requests.get(url, headers=UA, timeout=timeout, stream=True) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            magic = MAGIC.get(dest.suffix.lower())
            if magic and not tmp.read_bytes()[:4].startswith(magic):
                tmp.unlink(missing_ok=True)
                raise ValueError(f"{url} did not return a {dest.suffix} file (login page or 404?)")
            tmp.replace(dest)
            log.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
            return "downloaded"
        except (requests.RequestException, ValueError) as exc:
            last = exc
            log.warning("download failed (%d/%d) %s: %s", attempt + 1, retries, url, exc)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"could not download {url}: {last}")
