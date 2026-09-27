# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""RemoteReflexClassifier: Reflex served by the separate TRACE Reflex service (scripts/build_vercel_reflex.py).

The main API's Vercel function cannot also hold the ONNX model and onnxruntime (500 MB function limit), so in
production Reflex runs as its own small function and the API calls it over HTTPS. The service applies the same
`ReflexClassifier` and grounding guardrails, so the answer is identical to running Reflex in-process. Stdlib only.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import fields

from .base import Classification, JevClassifier

_FIELDS = {f.name for f in fields(Classification)}


class RemoteReflexClassifier(JevClassifier):
    def __init__(self, url: str, model_id: str | None = None, timeout: float = 25.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.name = model_id or os.environ.get("TRACE_REFLEX_MODEL_ID", "reflex-0.2.0")

    def classify(self, title: str, text: str = "") -> Classification:
        body = json.dumps({"title": title[:300], "text": (text or "")[:2000]}).encode("utf-8")
        req = urllib.request.Request(f"{self.url}/api/classify", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "trace-api"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # errors propagate: callers decide the fallback
            d = json.loads(r.read().decode("utf-8"))["data"]["classification"]
        kw = {k: v for k, v in d.items() if k in _FIELDS}
        kw["dropped"] = tuple(kw.get("dropped") or ())
        return Classification(**kw)
