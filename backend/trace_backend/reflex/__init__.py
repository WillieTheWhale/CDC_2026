# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reflex: TRACE's own System One decision model, built to the published Jev specification.

    from trace_backend.reflex import Reflex, Choice, Score, Noul
    rx = Reflex.load()
    r = rx.system_one(state="Ecuador seizes 4 t of cocaine bound for Belgium",
                      questions={"drug": Choice("Which drug?", {"cocaine": None, "heroin": None})})
    r.answers["drug"].choice, r.answers["drug"].confidence

See docs/REFLEX_SPEC.md for the requirements, design, and the Reflex Parity Scale.
"""
from .types import Choice, ChoiceAnswer, Noul, NoulAnswer, Score, ScoreAnswer, SystemOneResponse, confidence

MODEL_ID = "reflex-0.1.0"

__all__ = ["MODEL_ID", "Choice", "Score", "Noul", "ChoiceAnswer", "ScoreAnswer", "NoulAnswer", "SystemOneResponse",
           "confidence", "Reflex"]


def __getattr__(name):  # lazy: torch is only imported when the model is used
    if name == "Reflex":
        from .model import Reflex
        return Reflex
    raise AttributeError(name)
