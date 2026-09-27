# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reflex model: per-option cross-encoder with calibrated softmax heads.

For each option/level (and yes/no for Noul) the encoder reads (state, hypothesis) and emits one scalar
s = logit[entailment] - logit[contradiction]. Probabilities are softmax(s / T_type) over that question's options,
with one temperature per primitive fitted on held-out data after training (calibration, docs/REFLEX_SPEC.md R8).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .. import config
from .types import (
    Question,
    SystemOneResponse,
    from_dict,
    make_answer,
    option_hypotheses,
    render_state,
)

BASE = "cross-encoder/nli-deberta-v3-xsmall"
MAX_LEN = 320
WEIGHTS_DIR = config.DATA / "reflex" / "model"


class ReflexNet(torch.nn.Module):
    """Encoder + scalar option score. Initialised from an NLI cross-encoder (entail - contradict)."""

    def __init__(self, base: str = BASE):
        super().__init__()
        self.enc = AutoModelForSequenceClassification.from_pretrained(base)
        lab = {v.lower(): int(k) for k, v in self.enc.config.id2label.items()}
        self.i_ent, self.i_con = lab["entailment"], lab["contradiction"]

    def forward(self, **batch) -> torch.Tensor:
        lg = self.enc(**batch).logits
        return lg[:, self.i_ent] - lg[:, self.i_con]


class Reflex:
    def __init__(self, net: ReflexNet, tok, temps: dict[str, float] | None = None, model_id: str = "reflex-0.1.0",
                 device: str | None = None):
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net, self.tok = net.eval().to(device), tok
        self.temps = temps or {"choice": 1.0, "score": 1.0, "noul": 1.0}
        self.model_id, self.device = model_id, device

    # ------------------------------------------------------------------ loading / saving
    @classmethod
    def load(cls, path: Path | str | None = None, base_if_missing: bool = False) -> Reflex:
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
    @torch.no_grad()
    def raw_scores(self, pairs: list[tuple[str, str]], batch: int = 64) -> list[float]:
        out = []
        for i in range(0, len(pairs), batch):
            chunk = pairs[i:i + batch]
            enc = self.tok([a for a, _ in chunk], [b for _, b in chunk], truncation="only_first", max_length=MAX_LEN,
                           padding=True, return_tensors="pt").to(self.device)
            out.extend(self.net(**enc).float().cpu().tolist())
        return out

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
            t = self.temps.get(q.type, 1.0)
            probs = torch.softmax(torch.tensor(scores[start:start + n]) / t, dim=0).tolist()
            answers[qid] = make_answer(q, keys, probs)
        n_tok = sum(len(self.tok(a, b, truncation="only_first", max_length=MAX_LEN)["input_ids"]) for a, b in pairs)
        return SystemOneResponse(self.model_id, answers, {"input_tokens": n_tok, "pairs": len(pairs),
                                                          "latency_ms": round(1000 * (time.perf_counter() - t0), 1)})

    def logits_for(self, state, q: Question) -> list[float]:
        _, hyps = option_hypotheses(q)
        st = render_state(state)
        return self.raw_scores([(st, h) for h in hyps])
