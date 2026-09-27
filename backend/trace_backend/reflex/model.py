# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reflex model: per-option cross-encoder with calibrated softmax heads.

For each option/level (and yes/no for Noul) the encoder reads (state, hypothesis) and emits one scalar
s = logit[entailment] - logit[contradiction]. Probabilities are softmax(s / T_type) over that question's options,
with one temperature per primitive fitted on held-out data after training (calibration, docs/REFLEX_SPEC.md R8).

Two interchangeable backends share the request handling, softmax, temperatures and confidence (`_SystemOne`):

- `Reflex` (torch + transformers): training, evaluation, local development.
- `ReflexOnnx` (onnxruntime + tokenizers + numpy, no torch): production. The graph comes from
  scripts/export_reflex_onnx.py; the session is created on the first call, so loading the classifier is free.

`Reflex.load()` picks the ONNX backend when TRACE_REFLEX_BACKEND=onnx or when torch is not installed.
Importing this module never imports torch.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import threading
import time
from pathlib import Path

from .. import config
from .types import (
    Question,
    SystemOneResponse,
    from_dict,
    make_answer,
    option_hypotheses,
    render_state,
)

log = logging.getLogger(__name__)

BASE = "cross-encoder/nli-deberta-v3-xsmall"
MAX_LEN = 320
WEIGHTS_DIR = config.DATA / "reflex" / "model"
ONNX_DIR = config.DATA / "reflex" / "onnx"
ONNX_FILES = ("model.emb8.onnx", "model.onnx", "model.int8-ffn.onnx", "model.int8.onnx")  # preference order without reflex.json hint


def __getattr__(name):  # `from .model import ReflexNet` (train.py) without importing torch here
    if name == "ReflexNet":
        from .net import ReflexNet
        return ReflexNet
    raise AttributeError(name)


def backend_choice() -> str:
    """'onnx' or 'torch': TRACE_REFLEX_BACKEND wins; otherwise torch if installed, else onnx."""
    b = os.environ.get("TRACE_REFLEX_BACKEND", "").strip().lower()
    if b in ("onnx", "torch"):
        return b
    has_torch = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("transformers") is not None
    return "torch" if has_torch else "onnx"


def _softmax(xs: list[float], t: float) -> list[float]:
    import numpy as np
    z = np.asarray(xs, dtype=np.float64) / t
    e = np.exp(z - z.max())
    return (e / e.sum()).tolist()


class _SystemOne:
    """Request handling shared by both backends: pair construction, temperature softmax, answers."""

    model_id: str
    temps: dict[str, float]
    backend = "?"

    def raw_scores(self, pairs: list[tuple[str, str]], batch: int = 64) -> list[float]:
        raise NotImplementedError

    def _count_tokens(self, pairs: list[tuple[str, str]]) -> int:
        raise NotImplementedError

    def system_one(self, state, questions: dict, model: str | None = None) -> SystemOneResponse:
        """Evaluate one state against every question (all option pairs scored in one batched pass)."""
        t0 = time.perf_counter()
        st = render_state(state)
        qs = {k: from_dict(q) for k, q in questions.items()}
        plan, pairs = [], []
        for qid, q in qs.items():
            keys, hyps = option_hypotheses(q)
            plan.append((qid, q, keys, len(pairs), len(hyps)))
            pairs.extend((st, h) for h in hyps)
        scores = self.raw_scores(pairs)
        answers = {}
        for qid, q, keys, start, n in plan:
            probs = _softmax(scores[start:start + n], self.temps.get(q.type, 1.0))
            answers[qid] = make_answer(q, keys, probs)
        n_tok = self._count_tokens(pairs)
        return SystemOneResponse(self.model_id, answers, {"input_tokens": n_tok, "pairs": len(pairs),
                                                          "latency_ms": round(1000 * (time.perf_counter() - t0), 1)})

    def logits_for(self, state, q: Question) -> list[float]:
        _, hyps = option_hypotheses(q)
        st = render_state(state)
        return self.raw_scores([(st, h) for h in hyps])

    def probs_for(self, state, q: Question) -> list[float]:
        """Temperature-scaled probabilities for one question (evaluation / parity checks)."""
        return _softmax(self.logits_for(state, q), self.temps.get(q.type, 1.0))


class Reflex(_SystemOne):
    """Torch backend (training, evaluation). `Reflex.load()` may return a `ReflexOnnx` instead; same API."""

    backend = "torch"

    def __init__(self, net, tok, temps: dict[str, float] | None = None, model_id: str = "reflex-0.1.0",
                 device: str | None = None):
        import torch
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net, self.tok = net.eval().to(device), tok
        self.temps = temps or {"choice": 1.0, "score": 1.0, "noul": 1.0}
        self.model_id, self.device = model_id, device

    # ------------------------------------------------------------------ loading / saving
    @classmethod
    def load(cls, path: Path | str | None = None, base_if_missing: bool = False,
             backend: str | None = None) -> Reflex | ReflexOnnx:
        if (backend or backend_choice()) == "onnx":
            return ReflexOnnx.load(path)
        from transformers import AutoTokenizer

        from .net import ReflexNet
        p = Path(path) if path else WEIGHTS_DIR
        if (p / "reflex.json").exists():
            meta = json.loads((p / "reflex.json").read_text(encoding="utf-8"))
            tok = AutoTokenizer.from_pretrained(p)
            net = ReflexNet(str(p))
            return cls(net, tok, meta.get("temperatures"), meta.get("model_id", "reflex-0.1.0"))
        if not base_if_missing:
            raise FileNotFoundError(f"no trained Reflex at {p}; run `uv run trace reflex-train`")
        return cls(ReflexNet(BASE), AutoTokenizer.from_pretrained(BASE), None, "reflex-base-untrained")

    def save(self, path: Path | str | None = None, extra: dict | None = None) -> Path:
        p = Path(path) if path else WEIGHTS_DIR
        p.mkdir(parents=True, exist_ok=True)
        self.net.enc.save_pretrained(p)
        self.tok.save_pretrained(p)
        (p / "reflex.json").write_text(json.dumps({"model_id": self.model_id, "base": BASE, "max_len": MAX_LEN,
                                                   "temperatures": self.temps, **(extra or {})}, indent=2), "utf-8")
        return p

    # ------------------------------------------------------------------ scoring
    def raw_scores(self, pairs: list[tuple[str, str]], batch: int = 64) -> list[float]:
        import torch
        out = []
        with torch.no_grad():
            for i in range(0, len(pairs), batch):
                chunk = pairs[i:i + batch]
                enc = self.tok([a for a, _ in chunk], [b for _, b in chunk], truncation="only_first",
                               max_length=MAX_LEN, padding=True, return_tensors="pt").to(self.device)
                out.extend(self.net(**enc).float().cpu().tolist())
        return out

    def _count_tokens(self, pairs: list[tuple[str, str]]) -> int:
        return sum(len(self.tok(a, b, truncation="only_first", max_length=MAX_LEN)["input_ids"]) for a, b in pairs)


def find_onnx(path: Path | str | None = None) -> tuple[Path, dict]:
    """(model file, reflex.json) from `path`, else data/reflex/model (deploy layout), else data/reflex/onnx."""
    dirs = [Path(path)] if path else [WEIGHTS_DIR, ONNX_DIR]
    for d in dirs:
        if not (d / "reflex.json").exists():
            continue
        meta = json.loads((d / "reflex.json").read_text(encoding="utf-8"))
        hint = (meta.get("onnx") or {}).get("file")
        for name in ([hint] if hint else []) + list(ONNX_FILES):
            if (d / name).exists() and (d / "tokenizer.json").exists():
                return d / name, meta
    raise FileNotFoundError(f"no Reflex ONNX model (reflex.json + tokenizer.json + *.onnx) in {', '.join(map(str, dirs))}; "
                            "run scripts/export_reflex_onnx.py")


class ReflexOnnx(_SystemOne):
    """Torch-free backend: onnxruntime + tokenizers + numpy. Same pairs, scores, softmax and confidence as Reflex.

    Construction only reads reflex.json (model_id, temperatures); the tokenizer and InferenceSession are created on
    the first scoring call (thread-safe), so the API's cold start does not pay for the model.
    """

    backend = "onnx"

    def __init__(self, model_path: Path, meta: dict, threads: int | None = None):
        self.model_path, self.meta = Path(model_path), meta
        self.model_id = meta.get("model_id", "reflex-0.1.0")
        self.temps = meta.get("temperatures") or {"choice": 1.0, "score": 1.0, "noul": 1.0}
        self.max_len = int(meta.get("max_len", MAX_LEN))
        self.threads = threads if threads is not None else int(os.environ.get("TRACE_REFLEX_THREADS", "0") or 0)
        self.device = "cpu"
        self._sess = self._tok = None
        self._lock = threading.Lock()
        self.load_seconds: float | None = None

    @classmethod
    def load(cls, path: Path | str | None = None) -> ReflexOnnx:
        model_path, meta = find_onnx(path)
        missing = [m for m in ("onnxruntime", "tokenizers", "numpy") if importlib.util.find_spec(m) is None]
        if missing:
            raise ImportError(f"Reflex ONNX backend needs {', '.join(missing)} (uv pip install '.[reflex-onnx]')")
        return cls(model_path, meta)

    @property
    def loaded(self) -> bool:
        return self._sess is not None

    def warm(self) -> ReflexOnnx:
        """Create the tokenizer and session now (first call does this automatically)."""
        if self._sess is None:
            with self._lock:
                if self._sess is None:
                    t0 = time.perf_counter()
                    import onnxruntime as ort
                    from tokenizers import Tokenizer

                    tok = Tokenizer.from_file(str(self.model_path.parent / "tokenizer.json"))
                    tok.enable_truncation(max_length=self.max_len, strategy="only_first")
                    tok.no_padding()
                    so = ort.SessionOptions()
                    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                    if self.threads:
                        so.intra_op_num_threads = self.threads
                    so.log_severity_level = 3
                    self._sess = ort.InferenceSession(str(self.model_path), so, providers=["CPUExecutionProvider"])
                    self._tok = tok
                    self.load_seconds = round(time.perf_counter() - t0, 3)
                    log.info("Reflex ONNX %s (%s) loaded in %.2fs", self.model_id, self.model_path.name,
                             self.load_seconds)
        return self

    def _encode(self, pairs: list[tuple[str, str]]):
        return self.warm()._tok.encode_batch([(a, b) for a, b in pairs])

    def raw_scores(self, pairs: list[tuple[str, str]], batch: int = 64) -> list[float]:
        import numpy as np
        out: list[float] = []
        for i in range(0, len(pairs), batch):
            enc = self._encode(pairs[i:i + batch])
            width = max(len(e.ids) for e in enc)
            ids = np.zeros((len(enc), width), dtype=np.int64)  # [PAD] = 0, right padding as the HF tokenizer
            mask = np.zeros((len(enc), width), dtype=np.int64)
            for r, e in enumerate(enc):
                ids[r, :len(e.ids)] = e.ids
                mask[r, :len(e.ids)] = 1
            (score,) = self._sess.run(["score"], {"input_ids": ids, "attention_mask": mask})
            out.extend(score.astype(np.float32).tolist())
        return out

    def _count_tokens(self, pairs: list[tuple[str, str]]) -> int:
        return sum(len(e.ids) for e in self._encode(pairs))
