# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Seizure size from stated quantities: numbers and arithmetic in code, judgement in the model.

`size_from_text` returns "record", "major", "notable" or "small" when the text states a quantity (or record
wording), and None when it does not, so the caller can fall back to the model's Score answer.

Thresholds (match the Live Wire eval labels):
  weight: < 100 kg small, 100 kg to < 1500 kg notable, >= 1500 kg major
  pills/tablets: < 10,000 small, 10,000 to < 1,000,000 notable, >= 1,000,000 major
Money amounts ("$5 million", "worth 3 million euros", "2 million pounds worth") are not quantities.
"""
from __future__ import annotations

import re

_RECORD = re.compile(r"\brecord\b|\b(?:largest|biggest)[\s-]+ever\b|\bunprecedented\b", re.I)

_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "twenty": 20, "fifty": 50, "hundred": 100}
_MULT = {"thousand": 1e3, "million": 1e6, "billion": 1e9}

# a number: 1,200 / 4.2 / 12 / "half a" / "a" / "one" ...; never directly after a letter, digit or currency sign
_NUM = (r"(?<![\w.,$£€])(?<!worth )(?<!valued at )(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
        r"|half\s+an?\b|(?:" + "|".join(_WORDS) + r")\b)")
_MUL = r"(?:\s*(?P<mult>thousand|million|billion)\b)?"

_KG_PER = [(r"metric\s+tons?|tonnes?|tons?|t", 1000.0), (r"kilograms?|kilos?|kgs?", 1.0),
           (r"pounds?|lbs?", 0.45359237), (r"grams?|g", 0.001)]
_UNIT = "|".join(f"(?P<u{i}>{pat})" for i, (pat, _) in enumerate(_KG_PER))
_WEIGHT = re.compile(_NUM + _MUL + r"\s*-?\s*(?:" + _UNIT + r")\b(?!\s+(?:worth|sterling)\b)", re.I)

_MONEY_WORDS = r"worth|euros?|dollars?|pounds?|pesos?|rupees?|baht|yuan|usd|eur|gbp|value|valued"
_PILLS = re.compile(_NUM + _MUL + r"\s+(?:(?!(?:" + _MONEY_WORDS + r")\b)[a-z-]+\s+){0,2}(?:pills?|tablets?)\b",
                    re.I)

# vague plurals with an unambiguous size class
_VAGUE_PILLS = re.compile(r"\bmillions\s+of\s+(?:[a-z-]+\s+){0,2}(?:pills|tablets)\b", re.I)
_VAGUE_TONNES = re.compile(r"(?:(?P<prev>[\w.,]+)[\s-]+)?\b(?:tonnes|tons)\s+of\b", re.I)
_NUMERIC = re.compile(r"[\d.,]+|thousand|million|billion|half|" + "|".join(_WORDS), re.I)


def _value(m: re.Match) -> float:
    raw = m.group("num").lower()
    if raw[0].isdigit():
        v = float(raw.replace(",", ""))
    elif raw.startswith("half"):
        v = 0.5
    else:
        v = float(_WORDS[raw])
    if m.group("mult"):
        v *= _MULT[m.group("mult").lower()]
    return v


def _level(v: float, notable: float, major: float) -> int:
    return 2 if v >= major else 1 if v >= notable else 0


def size_from_text(text: str) -> str | None:
    """Return the seizure size class stated in `text`, or None if it states no quantity and no record wording."""
    if not text:
        return None
    if _RECORD.search(text):
        return "record"
    levels: list[int] = []
    for m in _WEIGHT.finditer(text):
        unit_i = next(i for i in range(len(_KG_PER)) if m.group(f"u{i}"))
        levels.append(_level(_value(m) * _KG_PER[unit_i][1], 100, 1500))
    for m in _PILLS.finditer(text):
        levels.append(_level(_value(m), 10_000, 1_000_000))
    if _VAGUE_PILLS.search(text):
        levels.append(2)
    for m in _VAGUE_TONNES.finditer(text):  # "tonnes of cocaine" with no number before it
        if not (m.group("prev") and _NUMERIC.fullmatch(m.group("prev"))):
            levels.append(2)
    if not levels:
        return None
    return ["small", "notable", "major"][max(levels)]
