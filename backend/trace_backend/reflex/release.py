# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Download the published Reflex weights (GitHub release) into data/reflex/model, verifying size and SHA-256.

    uv run trace reflex-download

An existing local model is moved to data/reflex/model_prev_<timestamp> rather than overwritten.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from .model import WEIGHTS_DIR

MANIFEST = Path(__file__).with_name("release.json")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(target: Path = WEIGHTS_DIR) -> dict:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp) / m["archive"]["filename"]
        req = urllib.request.Request(m["url"], headers={"User-Agent": "TRACE Reflex downloader"})
        with urllib.request.urlopen(req, timeout=300) as r, open(arc, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        if arc.stat().st_size != m["archive"]["bytes"] or _sha256(arc) != m["archive"]["sha256"]:
            raise ValueError("downloaded Reflex archive does not match the published size/SHA-256")
        staged = Path(tmp) / "model"
        with tarfile.open(arc) as tf:
            tf.extractall(staged, filter="data")
        missing = [c for c in m["contents"] if not (staged / c).exists()]
        if missing:
            raise ValueError(f"archive is missing {missing}")
        if target.exists():
            target.rename(target.with_name(f"{target.name}_prev_{time.strftime('%Y%m%d%H%M%S')}"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(target))
    return {"model_id": m["model_id"], "path": str(target), "sha256": m["archive"]["sha256"]}
