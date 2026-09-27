# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""ReflexNet: the torch encoder + scalar option score (training and the torch inference backend only).

Kept apart from model.py so the ONNX backend never imports torch. `from trace_backend.reflex.model import ReflexNet`
still works (model.py forwards the name lazily).
"""
from __future__ import annotations

import torch
from transformers import AutoModelForSequenceClassification

BASE = "cross-encoder/nli-deberta-v3-xsmall"


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
