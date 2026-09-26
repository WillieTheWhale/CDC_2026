# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""RealJevClassifier: TypeSafe AI System One ("Jev"), pinned to jev-1.13.0.

Activated automatically when TYPESAFE_API_KEY is set (pip extra: `uv sync --extra jev`). Any SDK error falls back
to the mock for that article so the Live Wire never stops. The SDK surface follows the TypeSafe docs as of
2026-09 (`TypeSafeClient.system_one(state=..., questions={...})`); verify when the key arrives.
"""
from __future__ import annotations

import logging

from .. import config
from .base import DRUGS, EVENT_TYPES, NOT_STATED, SIZES, Classification, JevClassifier
from .mock import MockJevClassifier

log = logging.getLogger(__name__)


class RealJevClassifier(JevClassifier):
    name = config.JEV_MODEL

    def __init__(self, countries: list[dict]):
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient  # optional dependency

        self._Choice, self._Noul, self._Score = Choice, Noul, Score
        self.client = TypeSafeClient(api_key=config.TYPESAFE_API_KEY)
        # Choice supports up to 255 options: ~217 economies + not_stated fits.
        self.name_to_iso = {c["name"]: c["iso3"] for c in countries}
        self.country_options = [*self.name_to_iso.keys(), NOT_STATED]
        self.fallback = MockJevClassifier()

    def _questions(self) -> dict:
        C, N, S = self._Choice, self._Noul, self._Score
        return {
            "is_event": N("Does the article describe a specific drug seizure, bust, arrest, lab, or policy change?"),
            "event_type": C("What kind of event is it?", options=EVENT_TYPES),
            "drug": C("Which drug is mainly involved?", options=DRUGS),
            "origin": C("Which country did the drugs come from? not_stated if the article does not say.",
                        options=self.country_options),
            "transit": C("Which country did the drugs pass through? not_stated if not said.",
                         options=self.country_options),
            "destination": C("Which country were the drugs going to? not_stated if not said.",
                             options=self.country_options),
            "size": S("How large is the event?", levels=SIZES),
            "route_mentioned": N("Does the article mention where the drugs came from or were going?"),
        }

    def classify(self, title: str, text: str = "") -> Classification:
        try:
            resp = self.client.system_one(model=config.JEV_MODEL, state=f"{title}\n\n{text}"[:6000],
                                          questions=self._questions())
            a = resp.answers

            def iso(name: str):
                ch = a[name].choice
                return None if ch in (None, NOT_STATED) else self.name_to_iso.get(ch)

            size_score = float(a["size"].score)
            size = SIZES[min(int(round(size_score * (len(SIZES) - 1))), len(SIZES) - 1)]
            conf = float(min(a["is_event"].confidence, a["event_type"].confidence, a["drug"].confidence))
            orig, dest = iso("origin"), iso("destination")
            return Classification(
                is_event=float(a["is_event"].noul), event_type=a["event_type"].choice,
                event_type_conf=float(a["event_type"].confidence), drug=a["drug"].choice,
                drug_conf=float(a["drug"].confidence), origin=orig, transit=iso("transit"), destination=dest,
                location=dest or orig, size=size, size_score=size_score,
                route_mentioned=float(a["route_mentioned"].noul), confidence=conf)
        except Exception as exc:  # never stop the wire
            log.warning("Jev call failed, using mock for this article: %s", exc)
            return self.fallback.classify(title, text)


def get_classifier(countries: list[dict] | None = None) -> JevClassifier:
    if config.TYPESAFE_API_KEY:
        try:
            return RealJevClassifier(countries or [])
        except ImportError:
            log.warning("TYPESAFE_API_KEY set but typesafe-sdk not installed (uv sync --extra jev); using mock")
    return MockJevClassifier()
