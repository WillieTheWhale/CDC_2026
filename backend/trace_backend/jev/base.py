# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""JevClassifier interface (SYSTEM_DESIGN section 7). Implementations: MockJevClassifier, RealJevClassifier."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

EVENT_TYPES = ["seizure", "arrest_or_indictment", "lab_dismantled", "law_or_policy_change", "violence", "corruption",
               "other"]
DRUGS = ["cocaine", "heroin", "meth", "cannabis", "fentanyl", "other", "unclear"]
SIZES = ["small", "notable", "major", "record"]
NOT_STATED = "not_stated"


@dataclass
class Classification:
    is_event: float            # Noul: P(article describes a specific seizure, bust, or policy change)
    event_type: str            # Choice
    event_type_conf: float
    drug: str                  # Choice
    drug_conf: float
    origin: str | None         # Choice over ISO3 + not_stated (None = not stated)
    transit: str | None
    destination: str | None
    location: str | None       # country where it happened (for the map pin)
    size: str                  # Score -> label
    size_score: float          # 0..1 fractional score
    route_mentioned: float     # Noul
    confidence: float          # overall calibrated confidence
    size_stated: bool = True   # False: the text states no quantity or record wording, so size is "not stated"
    dropped: tuple = ()        # guardrail log: "origin:COL", "drug:heroin" ... predictions removed as ungrounded

    def to_dict(self) -> dict:
        return asdict(self)


class JevClassifier(ABC):
    name: str = "abstract"

    @abstractmethod
    def classify(self, title: str, text: str = "") -> Classification:
        """Classify one article. Dates never come from the classifier (Jev treats dates as text)."""
