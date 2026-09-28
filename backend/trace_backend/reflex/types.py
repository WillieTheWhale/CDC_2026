# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""System One request and answer types, mirroring the documented Jev interface (docs.typesafe.ai, primitives + API).

No torch here: these types, the serialiser, and the confidence formula are importable and testable on their own.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

JSON = Any  # string, object, array, or None (the documented EntryType)
MAX_CHOICE_OPTIONS = 255
MAX_SCORE_LEVELS = 10


def confidence(probs: list[float]) -> float:
    """TypeSafe's published confidence: (K * p_max - 1) / (K - 1), clipped to [0, 1]."""
    k = len(probs)
    if k < 2:
        return 1.0
    return float(min(1.0, max(0.0, (k * max(probs) - 1) / (k - 1))))


def render(x: JSON, indent: int = 0) -> str:
    """Deterministic text form of a string/object/array entry. Objects become `key: value` lines, arrays bullets."""
    pad = "  " * indent
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (int, float, bool)):
        return json.dumps(x)
    if isinstance(x, dict):
        lines = []
        for k, v in x.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(render(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {render(v)}")
        return "\n".join(lines)
    if isinstance(x, (list, tuple)):
        out = []
        for v in x:
            r = render(v, indent + 1)
            out.append(f"{pad}- {r.strip()}" if not isinstance(v, (dict, list)) else f"{pad}-\n{r}")
        return "\n".join(out)
    return str(x)


@dataclass
class Choice:
    instructions: JSON
    criteria: dict[str, JSON]
    type: str = "choice"

    def __post_init__(self):
        if not 2 <= len(self.criteria) <= MAX_CHOICE_OPTIONS:
            raise ValueError(f"Choice needs 2-{MAX_CHOICE_OPTIONS} options")


@dataclass
class Score:
    instructions: JSON
    criteria: list[JSON]
    type: str = "score"

    def __post_init__(self):
        if not 2 <= len(self.criteria) <= MAX_SCORE_LEVELS:
            raise ValueError(f"Score needs 2-{MAX_SCORE_LEVELS} levels")


@dataclass
class NoulCriteria:
    true: JSON = None
    false: JSON = None


@dataclass
class Noul:
    instructions: JSON
    criteria: NoulCriteria | dict | None = None
    type: str = "noul"

    def crit(self) -> NoulCriteria:
        c = self.criteria
        if isinstance(c, dict):
            return NoulCriteria(c.get("true"), c.get("false"))
        return c or NoulCriteria()


Question = Choice | Score | Noul


def from_dict(q: dict | Question) -> Question:
    """Accept the HTTP-API dict form ({'type': 'choice', 'instructions': ..., 'criteria': ...})."""
    if isinstance(q, (Choice, Score, Noul)):
        return q
    t = q["type"]
    if t == "choice":
        return Choice(q.get("instructions"), dict(q["criteria"]))
    if t == "score":
        return Score(q.get("instructions"), list(q["criteria"]))
    if t == "noul":
        return Noul(q.get("instructions"), q.get("criteria"))
    raise ValueError(f"unknown question type {t}")


# ------------------------------------------------------------------ hypotheses (what the encoder reads per option)
def option_hypotheses(q: Question) -> tuple[list[str], list[str]]:
    """(keys, hypothesis texts). Each option/level is judged on its own: no level numbers, no neighbours."""
    instr = render(q.instructions).strip()
    head = f"Question: {instr}\n" if instr else ""
    if isinstance(q, Choice):
        keys = list(q.criteria)
        hyps = []
        for k, v in q.criteria.items():
            d = render(v).strip()
            hyps.append(f"{head}Answer: {k}" + (f"\n{d}" if d else ""))
        return keys, hyps
    if isinstance(q, Score):
        keys = [str(i) for i in range(len(q.criteria))]
        return keys, [f"{head}Answer: {render(v).strip()}" for v in q.criteria]
    c = q.crit()
    t, f = render(c.true).strip(), render(c.false).strip()
    return ["yes", "no"], [f"{head}Answer: yes" + (f". {t}" if t else ""), f"{head}Answer: no" + (f". {f}" if f else "")]


def render_state(state: JSON) -> str:
    return render(state).strip()


# ------------------------------------------------------------------ answers
@dataclass
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float
    type: str = "choice"


@dataclass
class ScoreAnswer:
    score: float
    probabilities: dict[int, float]
    legend: dict[int, JSON]
    confidence: float
    type: str = "score"


@dataclass
class NoulAnswer:
    noul: float
    type: str = "noul"


Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer


def make_answer(q: Question, keys: list[str], probs: list[float]) -> Answer:
    if isinstance(q, Choice):
        i = max(range(len(probs)), key=probs.__getitem__)
        return ChoiceAnswer(keys[i], {k: round(p, 4) for k, p in zip(keys, probs, strict=True)},
                            round(confidence(probs), 4))
    if isinstance(q, Score):
        return ScoreAnswer(round(sum(i * p for i, p in enumerate(probs)), 4),
                           {i: round(p, 4) for i, p in enumerate(probs)}, dict(enumerate(q.criteria)),
                           round(confidence(probs), 4))
    return NoulAnswer(round(probs[0], 4))


@dataclass
class SystemOneResponse:
    model: str
    answers: dict[str, Answer]
    usage: dict = field(default_factory=dict)

    @property
    def choices(self):
        return {k: a for k, a in self.answers.items() if isinstance(a, ChoiceAnswer)}

    @property
    def scores(self):
        return {k: a for k, a in self.answers.items() if isinstance(a, ScoreAnswer)}

    @property
    def nouls(self):
        return {k: a for k, a in self.answers.items() if isinstance(a, NoulAnswer)}

    def to_dict(self) -> dict:
        def ans(a):
            d = dict(a.__dict__)
            if isinstance(a, ScoreAnswer):
                d["probabilities"] = {str(k): v for k, v in a.probabilities.items()}
                d["legend"] = {str(k): v for k, v in a.legend.items()}
            return d
        return {"model": self.model, "answers": {k: ans(a) for k, a in self.answers.items()}, "usage": self.usage}
