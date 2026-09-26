# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""MockJevClassifier: keyword and rule based stand-in for Jev until TYPESAFE_API_KEY exists."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .base import Classification, JevClassifier

DRUG_KW = [
    ("fentanyl", r"fentanyl|carfentanil|nitazene"),
    ("cocaine", r"cocaine|crack|coca paste|\bcoke\b"),
    ("heroin", r"heroin|opium|opiate|poppy|morphine"),
    ("meth", r"methamphetamine|\bmeth\b|crystal meth|yaba|shabu|\bice\b|meth pills|amphetamine"),
    ("cannabis", r"cannabis|marijuana|hashish|\bhash\b|\bweed\b|skunk"),
]
TYPE_KW = [
    ("lab_dismantled", r"\blab\b|laborator|superlab|dismantl|clandestine"),
    ("law_or_policy_change", r"legali[sz]|decriminali[sz]|\bban\b|bans\b|\blaw\b|\bbill\b|policy|regulat|reform|parliament|approv"),
    ("corruption", r"brib|corrupt"),
    ("violence", r"\bkill|shot|shooting|murder|massacre|clash|gunmen|violence|attack|dead\b|deaths"),
    ("arrest_or_indictment", r"arrest|charged|indict|extradit|sentenc|convict|detain|jailed|nabbed|busted"),
    ("seizure", r"seiz|intercept|haul|confiscat|found|discover|stash|shipment|consignment|smuggl|recover"),
]
PLACE_HINTS = {
    "antwerp": "BEL", "rotterdam": "NLD", "guayaquil": "ECU", "hamburg": "DEU", "algeciras": "ESP", "valencia": "ESP",
    "sydney": "AUS", "melbourne": "AUS", "bangkok": "THA", "karachi": "PAK", "tijuana": "MEX", "sinaloa": "MEX",
    "kabul": "AFG", "helmand": "AFG", "shan state": "MMR", "golden triangle": "MMR", "sicily": "ITA", "calabria": "ITA",
    "le havre": "FRA", "marseille": "FRA", "felixstowe": "GBR", "london": "GBR", "manila": "PHL", "hong kong": "HKG",
    "durban": "ZAF", "lagos": "NGA", "santos": "BRA", "callao": "PER", "cartagena": "COL", "buenaventura": "COL",
    "ciudad juarez": "MEX", "arizona": "USA", "california": "USA", "texas": "USA", "florida": "USA", "puerto rico": "PRI",
    "tangier": "MAR", "istanbul": "TUR", "mersin": "TUR", "bandar abbas": "IRN", "yangon": "MMR", "chiang rai": "THA",
}
DEMONYMS = {
    "colombian": "COL", "mexican": "MEX", "ecuadorian": "ECU", "ecuadorean": "ECU", "peruvian": "PER",
    "bolivian": "BOL", "brazilian": "BRA", "venezuelan": "VEN", "panamanian": "PAN", "paraguayan": "PRY",
    "afghan": "AFG", "iranian": "IRN", "pakistani": "PAK", "turkish": "TUR", "thai": "THA", "burmese": "MMR",
    "laotian": "LAO", "lao": "LAO", "chinese": "CHN", "indian": "IND", "spanish": "ESP", "dutch": "NLD",
    "belgian": "BEL", "british": "GBR", "uk": "GBR", "u.k.": "GBR", "us": "USA", "u.s.": "USA", "american": "USA",
    "canadian": "CAN", "australian": "AUS", "moroccan": "MAR", "albanian": "ALB", "italian": "ITA", "french": "FRA",
    "german": "DEU", "nigerian": "NGA", "filipino": "PHL", "philippine": "PHL", "malaysian": "MYS",
    "vietnamese": "VNM", "indonesian": "IDN", "japanese": "JPN", "portuguese": "PRT", "greek": "GRC",
    "bulgarian": "BGR", "serbian": "SRB", "guatemalan": "GTM", "honduran": "HND", "costa rican": "CRI",
    "dominican": "DOM", "jamaican": "JAM", "chilean": "CHL", "argentine": "ARG", "south african": "ZAF",
    "kenyan": "KEN", "tanzanian": "TZA", "emirati": "ARE", "saudi": "SAU", "syrian": "SYR", "lebanese": "LBN",
    "bangladeshi": "BGD", "sri lankan": "LKA", "cambodian": "KHM", "korean": "KOR", "new zealand": "NZL",
    "russian": "RUS", "ukrainian": "UKR", "tajik": "TJK", "kazakh": "KAZ", "irish": "IRL", "polish": "POL",
    "czech": "CZE", "swedish": "SWE", "norwegian": "NOR", "danish": "DNK", "swiss": "CHE", "austrian": "AUT",
}
EXTRA_NAMES = {"united states": "USA", "america": "USA", "britain": "GBR", "england": "GBR", "holland": "NLD",
               "the netherlands": "NLD", "netherlands": "NLD", "turkiye": "TUR", "türkiye": "TUR", "turkey": "TUR",
               "laos": "LAO", "vietnam": "VNM", "south korea": "KOR", "russia": "RUS", "iran": "IRN", "syria": "SYR",
               "venezuela": "VEN", "bolivia": "BOL", "czech republic": "CZE", "ivory coast": "CIV", "egypt": "EGY",
               "gambia": "GMB", "congo": "COD", "hong kong": "HKG", "macau": "MAC", "uae": "ARE"}
DEST = r"(?:bound for|destined for|headed (?:to|for)|en route to|heading to|to be shipped to|for export to|into|to)"
ORIG = r"(?:from|out of|departing|originating in|shipped from|arriving from|sent from)"
TRANS = r"(?:via|through|transiting)"


@lru_cache(maxsize=1)
def lexicon() -> list[tuple[str, str]]:
    """(lowercase name, ISO3), longest first. World Bank names from the exported country list if available."""
    names: dict[str, str] = {**PLACE_HINTS, **DEMONYMS, **EXTRA_NAMES}
    try:
        from ..config import API_DIR
        for c in json.loads((Path(API_DIR) / "countries.json").read_text(encoding="utf-8")):
            short = re.sub(r",.*$|\(.*?\)", "", c["name"]).strip().lower()
            names.setdefault(short, c["iso3"])
    except (FileNotFoundError, OSError, ValueError):
        pass
    return sorted(names.items(), key=lambda kv: -len(kv[0]))


def _find(text: str) -> list[tuple[int, str]]:
    """All (position, ISO3) country mentions, non-overlapping, in order."""
    t = text.lower()
    taken = [False] * len(t)
    hits = []
    for name, iso3 in lexicon():
        for m in re.finditer(rf"(?<![a-z]){re.escape(name)}(?![a-z])", t):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            hits.append((m.start(), iso3))
    return sorted(hits)


def _after(text: str, cue: str) -> str | None:
    m = re.search(rf"\b{cue}\s+(?:the\s+)?(.{{0,40}})", text, re.I)
    if not m:
        return None
    found = _find(m.group(1))
    return found[0][1] if found else None


class MockJevClassifier(JevClassifier):
    name = "mock"

    def classify(self, title: str, text: str = "") -> Classification:
        s = f"{title}. {text}".strip()
        low = s.lower()
        drug, dconf = "unclear", 0.35
        for d, pat in DRUG_KW:
            if re.search(pat, low):
                drug, dconf = d, 0.9
                break
        if drug == "unclear" and re.search(r"\bdrug|narcotic|trafficker|cartel", low):
            drug, dconf = "other", 0.5
        etype, tconf = "other", 0.45
        for t, pat in TYPE_KW:
            if re.search(pat, low):
                etype, tconf = t, 0.85
                break
        dest = _after(s, DEST)
        orig = _after(s, ORIG)
        trans = _after(s, TRANS)
        mentions = _find(s)
        location = mentions[0][1] if mentions else None
        if dest and not orig and location and location != dest:
            orig = location                      # "Ecuador seizes cocaine bound for Belgium"
        if orig and not dest and location and location != orig:
            dest = location                      # "Spain seizes cocaine from Colombia"
        if orig == dest:
            dest = None
        if re.search(r"\brecord\b|largest|biggest|unprecedented", low):
            size = "record"
        elif re.search(r"\btonnes?\b|\btons?\b|million (?:pills|tablets)|\d{4,}\s?(?:kg|kilo)", low):
            size = "major"
        elif re.search(r"\d{2,3}\s?(?:kg|kilo)|hundreds of|thousands of|\d+,\d{3}", low):
            size = "notable"
        else:
            size = "small"
        size_score = {"small": 0.1, "notable": 0.4, "major": 0.7, "record": 0.95}[size]
        is_event = 0.92 if (etype != "other" and drug not in ("unclear",)) else 0.62 if drug != "unclear" else 0.2
        route = 0.9 if (orig and dest) else 0.55 if (orig or dest) else 0.15
        conf = round((is_event + dconf + tconf) / 3, 3)
        return Classification(is_event=is_event, event_type=etype, event_type_conf=tconf, drug=drug, drug_conf=dconf,
                              origin=orig, transit=trans, destination=dest, location=location or dest or orig,
                              size=size, size_score=size_score, route_mentioned=route, confidence=conf)
