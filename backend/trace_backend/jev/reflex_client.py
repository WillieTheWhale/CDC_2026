# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""ReflexClassifier: the Live Wire classifier backed by Reflex, TRACE's own System One model (docs/REFLEX_SPEC.md).

Asks the same seven typed questions as the Jev client in one request. Country questions are Choices over the
countries the headline mentions plus `not_stated`: extraction in code, judgement by the model, which is the
approach TypeSafe's jaggedness guide recommends ("extract possible options ... and let the model pick").

With `grounded=True` (the default) the candidates come from `grounding.country_candidates` (names, aliases,
demonyms, states, cities and ports, capitalisation-checked) and every answer passes `grounding.ground`: countries
and drugs the text does not support are removed, size comes only from stated quantities. `grounded=False` is the
pre-guardrail behaviour, kept for the before/after benchmark (`jev/benchmark.py`).
"""
from __future__ import annotations

import re

from .base import Classification, JevClassifier
from .grounding import country_candidates, ground
from .mock import _find
from .quantity import size_from_text

SIZES = ["small", "notable", "major", "record"]


class ReflexClassifier(JevClassifier):
    def __init__(self, countries: list[dict] | None = None, model=None, grounded: bool = True):
        self.grounded = grounded
        from ..reflex import Reflex
        from ..reflex.data import DRUG_OPTS, EVENT_TYPES, SIZE_LEVELS, _names
        self.rx = model or Reflex.load()
        self.name = self.rx.model_id
        if countries is None:
            try:
                from .. import db
                countries = db.read_table("countries").to_dict("records")
            except Exception:  # no database (e.g. a Colab GPU runtime): the contract fixture has all 217 economies
                import json

                from ..contract import FIXTURES
                countries = json.loads((FIXTURES / "countries.json").read_text(encoding="utf-8"))["data"]
        self.short, _ = _names(countries)
        self.EVENT_TYPES, self.DRUG_OPTS, self.SIZE_LEVELS = EVENT_TYPES, DRUG_OPTS, SIZE_LEVELS

    def questions(self, cands: list[str]) -> dict:
        from ..reflex import Choice, Noul, Score
        opts = {self.short.get(c, c): None for c in cands}
        opts["not_stated"] = "The article does not say"
        q = {
            "is_event": Noul("Does the article describe a specific drug seizure, arrest, lab raid, violence, "
                             "corruption case or policy change?"),
            "event_type": Choice("What kind of event does the article report?", dict(self.EVENT_TYPES)),
            "drug": Choice("Which drug is mainly involved?", dict(self.DRUG_OPTS)),
            "size": Score("How large is the seizure?", list(self.SIZE_LEVELS)),
            "route_mentioned": Noul("Does the article say where the drugs came from or were going?"),
        }
        if cands:  # no country mentioned: nothing to choose between, so no country questions
            q["origin"] = Choice("Which country did the drugs come from, according to the article?", dict(opts))
            q["destination"] = Choice("Which country were the drugs seized in or going to, according to the article?",
                                      dict(opts))
        return q

    def classify(self, title: str, text: str = "") -> Classification:
        state = re.sub(r"\s+", " ", f"{title}. {text}".strip())[:1500]
        if self.grounded:
            cands = country_candidates(state)
        else:
            cands = list(dict.fromkeys(iso for _, iso in _find(state)))[:8]
        r = self.rx.system_one(state, self.questions(cands))
        a = r.answers
        back = {self.short.get(c, c): c for c in cands}
        orig = back.get(a["origin"].choice) if "origin" in a else None
        dest = back.get(a["destination"].choice) if "destination" in a else None
        if orig and orig == dest:
            orig = None
        size_score = a["size"].score / 3
        size = SIZES[int(round(a["size"].score))]
        if a["event_type"].choice == "seizure":  # stated quantities: arithmetic in code, not in the model
            stated = size_from_text(state)
            if stated:
                size, size_score = stated, SIZES.index(stated) / 3
        else:  # size is defined only for seizures; every other event is "small" by the label definition
            size, size_score = "small", 0.0
        conf = (a["is_event"].noul + a["event_type"].confidence + a["drug"].confidence) / 3
        c = Classification(
            is_event=a["is_event"].noul, event_type=a["event_type"].choice,
            event_type_conf=a["event_type"].confidence, drug=a["drug"].choice, drug_conf=a["drug"].confidence,
            origin=orig, transit=None, destination=dest, location=dest or orig or (cands[0] if cands else None),
            size=size, size_score=round(size_score, 3),
            route_mentioned=a["route_mentioned"].noul, confidence=round(conf, 3))
        if not self.grounded:
            return c
        return ground(c, title, text, drug_probs=dict(a["drug"].probabilities))
