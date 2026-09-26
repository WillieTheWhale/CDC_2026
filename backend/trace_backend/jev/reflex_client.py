# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""ReflexClassifier: the Live Wire classifier backed by Reflex, TRACE's own System One model (docs/REFLEX_SPEC.md).

Asks the same seven typed questions as the Jev client in one request. Country questions are Choices over the
countries the headline mentions plus `not_stated`: extraction in code, judgement by the model, which is the
approach TypeSafe's jaggedness guide recommends ("extract possible options ... and let the model pick").
"""
from __future__ import annotations

import re

from .base import Classification, JevClassifier
from .mock import _find

SIZES = ["small", "notable", "major", "record"]


class ReflexClassifier(JevClassifier):
    def __init__(self, countries: list[dict] | None = None, model=None):
        from ..reflex import Reflex
        from ..reflex.data import DRUG_OPTS, EVENT_TYPES, SIZE_LEVELS, _names
        self.rx = model or Reflex.load()
        self.name = self.rx.model_id
        if countries is None:
            from .. import db
            countries = db.read_table("countries").to_dict("records")
        self.short, _ = _names(countries)
        self.EVENT_TYPES, self.DRUG_OPTS, self.SIZE_LEVELS = EVENT_TYPES, DRUG_OPTS, SIZE_LEVELS

    def questions(self, cands: list[str]) -> dict:
        from ..reflex import Choice, Noul, Score
        opts = {self.short.get(c, c): None for c in cands}
        opts["not_stated"] = "The article does not say"
        return {
            "is_event": Noul("Does the article describe a specific drug seizure, arrest, lab raid, violence, "
                             "corruption case or policy change?"),
            "event_type": Choice("What kind of event does the article report?", dict(self.EVENT_TYPES)),
            "drug": Choice("Which drug is mainly involved?", dict(self.DRUG_OPTS)),
            "origin": Choice("Which country did the drugs come from, according to the article?", dict(opts)),
            "destination": Choice("Which country were the drugs seized in or going to, according to the article?",
                                  dict(opts)),
            "size": Score("How large is the seizure?", list(self.SIZE_LEVELS)),
            "route_mentioned": Noul("Does the article say where the drugs came from or were going?"),
        }

    def classify(self, title: str, text: str = "") -> Classification:
        state = re.sub(r"\s+", " ", f"{title}. {text}".strip())[:1500]
        cands = list(dict.fromkeys(iso for _, iso in _find(state)))[:8]
        r = self.rx.system_one(state, self.questions(cands))
        a = r.answers
        back = {self.short.get(c, c): c for c in cands}
        orig = back.get(a["origin"].choice)
        dest = back.get(a["destination"].choice)
        if orig and orig == dest:
            orig = None
        size_score = a["size"].score / 3
        conf = (a["is_event"].noul + a["event_type"].confidence + a["drug"].confidence) / 3
        return Classification(
            is_event=a["is_event"].noul, event_type=a["event_type"].choice,
            event_type_conf=a["event_type"].confidence, drug=a["drug"].choice, drug_conf=a["drug"].confidence,
            origin=orig, transit=None, destination=dest, location=dest or orig or (cands[0] if cands else None),
            size=SIZES[int(round(a["size"].score))], size_score=round(size_score, 3),
            route_mentioned=a["route_mentioned"].noul, confidence=round(conf, 3))
