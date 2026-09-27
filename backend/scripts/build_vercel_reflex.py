# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Build the TRACE Reflex service: Reflex (ONNX, torch-free) + the grounding guardrails as its own small Vercel function.

    .venv/Scripts/python scripts/build_vercel_reflex.py
    cd .vercel_reflex && vercel deploy --prod

Why a separate function: the main API bundle (scientific stack + evidence database) plus the ONNX model and onnxruntime
exceed Vercel's 500 MB function limit. The service ships only fastapi, numpy, onnxruntime and tokenizers, the model
(external-data files, each < 100 MB) and the country catalogue the guardrails read. The main API calls it through
`jev.remote.RemoteReflexClassifier` (TRACE_CLASSIFIER=reflex-remote, TRACE_REFLEX_URL).

Endpoints: GET /api/health, POST /api/classify {title, text?} -> the grounded classification (same payload as the
main API's POST /api/livewire/classify). Nothing is stored.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))
from build_vercel import IGNORE, copy_reflex_onnx, pyproject  # noqa: E402

from trace_backend import config  # noqa: E402

OUT = BACKEND / ".vercel_reflex"
REQUIREMENTS = """fastapi>=0.111
pydantic>=2
numpy>=1.26
python-dotenv>=1.0
onnxruntime>=1.20
tokenizers>=0.20
"""
APP = '''# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""TRACE Reflex service: Reflex (ONNX) + grounding guardrails behind POST /api/classify. Nothing is stored."""
import json
import os
import threading
import time

os.environ.setdefault("TRACE_REFLEX_BACKEND", "onnx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from trace_backend import config  # noqa: E402
from trace_backend.jev.grounding import MIN_CONFIDENCE, ground, passes_wire  # noqa: E402

app = FastAPI(title="TRACE Reflex", version="0.2.0",
              description="TRACE's own System One classifier (Reflex, ONNX) with grounding guardrails.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_origin_regex=r"https://.*\\.vercel\\.app", allow_methods=["GET", "POST"], allow_headers=["*"])
_lock, _clf = threading.Lock(), None


def classifier():
    """Created on first use: the ONNX session loads lazily (health checks and cold starts stay cheap)."""
    global _clf
    with _lock:
        if _clf is None:
            from trace_backend.jev.reflex_client import ReflexClassifier
            rows = json.loads((config.API_DIR / "countries.json").read_text(encoding="utf-8"))
            _clf = ReflexClassifier(countries=rows)
        return _clf


class ClassifyIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    text: str = Field("", max_length=2000)


@app.get("/api/health")
def health():
    meta = json.loads((config.DATA / "reflex" / "model" / "reflex.json").read_text(encoding="utf-8"))
    return {"status": "ok", "model_id": meta.get("model_id"), "backend": "onnx", "loaded": _clf is not None}


@app.post("/api/classify")
def classify(body: ClassifyIn):
    t0 = time.perf_counter()
    try:
        clf = classifier()
        c = ground(clf.classify(body.title, body.text), body.title, body.text)
    except Exception as exc:  # surface, never guess
        raise HTTPException(status_code=503, detail=f"Reflex unavailable: {type(exc).__name__}: {str(exc)[:200]}")
    return {"meta": {"model_version": clf.name, "notes": ["Grounded: countries, drugs and sizes must be stated."]},
            "data": {"classifier": clf.name, "on_wire": passes_wire(c, MIN_CONFIDENCE),
                     "latency_ms": round((time.perf_counter() - t0) * 1000), "classification": c.to_dict()}}
'''
VERCEL_JSON = """{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "fastapi"
}
"""


def build() -> Path:
    OUT.mkdir(exist_ok=True)
    for child in OUT.iterdir():  # empty in place, keep the .vercel project link
        if child.name != ".vercel":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(BACKEND / "trace_backend", OUT / "trace_backend", ignore=IGNORE)
    data = OUT / "data"
    for sub in ("raw", "cache"):
        (data / sub).mkdir(parents=True)
        (data / sub / ".keep").write_text("", encoding="utf-8")
    (data / "processed" / "api").mkdir(parents=True)
    shutil.copy(config.PROCESSED / "api" / "countries.json", data / "processed" / "api" / "countries.json")
    print(f"  reflex onnx: {copy_reflex_onnx(data)}")
    (OUT / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (OUT / "pyproject.toml").write_text(pyproject(REQUIREMENTS), encoding="utf-8")
    (OUT / "app.py").write_text(APP, encoding="utf-8")
    (OUT / "vercel.json").write_text(VERCEL_JSON, encoding="utf-8")
    (OUT / ".python-version").write_text("3.12\n", encoding="utf-8")
    return OUT


if __name__ == "__main__":
    out = build()
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file() and ".vercel" not in p.parts)
    big = [p.name for p in out.rglob("*") if p.is_file() and p.stat().st_size > 95e6]
    print(f"built {out} ({size / 1e6:.1f} MB){'; files over 95 MB: ' + ', '.join(big) if big else ''}")
