# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Parse plain-English scenarios and command-bar text into structured shocks / intents.

Rules first (deterministic, offline). If rules find no shock and ANTHROPIC_API_KEY is set, Claude
(structured output) parses the scenario. Requests about weak enforcement or avoiding detection are
refused (design boundary).
"""
from __future__ import annotations

import logging
import re

from .. import config
from ..jev.mock import _find

log = logging.getLogger(__name__)

BLOCKED = re.compile(
    r"least (?:watched|monitored|patrolled|guarded|policed|inspected|checked)|weakest (?:customs|enforcement|border|"
    r"police|controls?)|safest (?:route|path|way|port|border)|avoid(?:ing)? (?:detection|customs|police|seizure|"
    r"being caught)|evad(?:e|ing)|undetected|how (?:to|do i|can i) (?:smuggle|traffic|move|ship)|where (?:to|can i) "
    r"(?:smuggle|traffic)|easiest (?:route|border|port)|get (?:drugs )?past (?:customs|police|border)", re.I)
BLOCK_MSG = ("TRACE shows where flows and harms are, to support prevention. It does not answer questions about "
             "weak enforcement, unwatched routes, or avoiding detection.")
DRUG_WORDS = {"cocaine": "cocaine", "coca": "cocaine", "crack": "cocaine", "heroin": "heroin", "opium": "heroin",
              "poppy": "heroin", "opiates": "heroin", "meth": "meth", "methamphetamine": "meth",
              "cannabis": "cannabis", "marijuana": "cannabis", "weed": "cannabis", "hashish": "cannabis"}


def _drug(text: str) -> str | None:
    for w, d in DRUG_WORDS.items():
        if re.search(rf"\b{w}\b", text, re.I):
            return d
    return None


def _countries(text: str) -> list[str]:
    out = [m.group(0).upper() for m in re.finditer(r"\b[A-Z]{3}\b", text)]
    from ..api.app import store
    valid = set(store().country_index)
    out = [c for c in out if c in valid]
    for _, iso3 in _find(text):
        if iso3 not in out:
            out.append(iso3)
    return out


def _pct(text: str) -> float | None:
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) if m else None


def parse_clause(clause: str) -> dict | None:
    c = clause.strip()
    if not c:
        return None
    ctry = _countries(c)
    if not ctry:
        return None
    iso3, low, drug = ctry[0], c.lower(), _drug(c)
    pct = _pct(c)
    if re.search(r"legali[sz]|regulat|decriminali[sz]|\blegal\b", low):
        val = 0.0 if re.search(r"re-?criminali[sz]|repeal|ban", low) else 1.0
        return {"type": "legalization", "iso3": iso3, "drug": drug or "cannabis", "value": val}
    if re.search(r"customs|port|border|crack(?:s|ing)? down|interdiction|inspection", low):
        m = re.search(r"([+-]\s?\d+(?:\.\d+)?)(?!\s*%)", c)
        if m:
            delta = float(m.group(1).replace(" ", ""))
        elif pct is not None:
            delta = pct / 100 * 2
        else:
            delta = -1.0 if re.search(r"weak|cut|reduce|loosen|lower", low) else 1.0
        return {"type": "customs_efficiency", "iso3": iso3, "drug": None, "value": max(-4.0, min(4.0, delta))}
    if re.search(r"cultivat|coca|opium|poppy|crop|production|harvest|ban|eradicat|cut|halve|double|grow", low):
        if pct is not None:
            m = 1 + pct / 100 if re.search(r"[+-]\s*\d", c) else (
                1 - pct / 100 if re.search(r"cut|reduc|fall|drop|eradicat|lower|decreas", low) else 1 + pct / 100)
        elif re.search(r"\bban", low):
            m = 0.05
        elif "halve" in low:
            m = 0.5
        elif "double" in low:
            m = 2.0
        elif "triple" in low:
            m = 3.0
        else:
            m = 0.5
        return {"type": "cultivation", "iso3": iso3, "drug": drug, "value": round(max(0.0, m), 4)}
    return None


def parse_rules(text: str) -> list[dict]:
    text = re.sub(r"^\s*shock\s+", "", text, flags=re.I)
    clauses = re.split(r"\band\b|;|,| then ", text, flags=re.I)
    return [s for s in (parse_clause(c) for c in clauses) if s]


def parse_llm(text: str) -> list[dict]:
    """Claude structured output. Only used when rules fail and ANTHROPIC_API_KEY is set."""
    if not config.ANTHROPIC_API_KEY:
        return []
    try:
        from typing import Literal

        import anthropic
        from pydantic import BaseModel

        class ShockModel(BaseModel):
            type: Literal["cultivation", "legalization", "customs_efficiency"]
            iso3: str
            drug: Literal["cocaine", "heroin", "meth", "cannabis"] | None = None
            value: float

        class Scenario(BaseModel):
            shocks: list[ShockModel]

        client = anthropic.Anthropic()
        resp = client.messages.parse(
            model="claude-opus-5", max_tokens=2000,
            system=("Convert a drug-policy scenario into shocks for a trafficking-route model. cultivation: value is a "
                    "multiplier on illicit crop output (a 95% cut = 0.05). legalization: value 1 legalizes, 0 reverses. "
                    "customs_efficiency: value is a delta on the 1-5 LPI customs scale. iso3 is ISO 3166 alpha-3. "
                    "Return no shocks if the scenario asks about weak enforcement or avoiding detection."),
            messages=[{"role": "user", "content": text}], output_format=Scenario)
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            return []
        return [s.model_dump() for s in resp.parsed_output.shocks]
    except Exception as exc:  # never break the simulator on the LLM path
        log.warning("LLM scenario parsing failed: %s", exc)
        return []


# ------------------------------------------------------------------ command bar
def parse_command(text: str) -> dict:
    t = text.strip()
    up = t.upper()
    base = {"drug": None, "iso3": None, "iso3_b": None, "year": None, "limit": None, "predict": None, "shocks": []}

    def out(intent, conf, msg, **params):
        return {"text": text, "intent": intent, "params": {**base, **params}, "confidence": conf,
                "parser": "rules", "message": msg}

    if BLOCKED.search(t):
        return out("blocked", 0.99, BLOCK_MSG)
    if not t or up in ("HELP", "?"):
        return out("help", 0.95, "Try: HEROIN ROUTES, MEX <GO>, RISK TOP 20, SHOCK AFG CULTIVATION -95%, NEWS COCAINE, "
                                 "COMPARE COL PER, YEAR 2023, PREDICT ON")
    m = re.match(r"^PREDICT\s+(ON|OFF)$", up)
    if m:
        return out("predict", 0.97, f"Predicted routes {m.group(1).lower()}", predict=m.group(1) == "ON")
    m = re.match(r"^YEAR\s+(\d{4})$", up)
    if m:
        return out("year", 0.97, f"Year {m.group(1)}", year=int(m.group(1)))
    m = re.match(r"^RISK(?:\s+TOP\s+(\d+))?", up)
    if m:
        n = int(m.group(1) or 20)
        return out("risk", 0.96, f"Spillover risk board, top {n}", limit=n)
    m = re.match(r"^NEWS(?:\s+(\w+))?$", up)
    if m:
        d = _drug(m.group(1) or "") or (m.group(1).lower() if m.group(1) and m.group(1).lower() == "fentanyl" else None)
        return out("news", 0.95, f"Live Wire{' - ' + d if d else ''}", drug=d)
    m = re.match(r"^COMPARE\s+(\w{3})\s+(\w{3})$", up)
    if m:
        return out("compare", 0.96, f"Compare {m.group(1)} and {m.group(2)}", iso3=m.group(1), iso3_b=m.group(2))
    if up.startswith("SHOCK") or re.search(r"legali[sz]|cuts? (?:coca|opium)|bans? (?:opium|poppy)|crack", t, re.I):
        shocks = parse_rules(t)
        if shocks:
            return out("shock", 0.9, "Shock: " + "; ".join(f"{s['iso3']} {s['type']} {s['value']:g}" for s in shocks),
                       shocks=shocks, iso3=shocks[0]["iso3"], drug=shocks[0].get("drug"))
    if re.search(r"AFGHAN|EXPERIMENT|BAN TEST", up):
        return out("experiment", 0.9, "Afghanistan 2022 opium ban experiment")
    if re.match(r"^(METRICS|BACKTEST|ACCURACY)", up):
        return out("metrics", 0.93, "Model metrics")
    m = re.match(r"^(?:PRICES?|MARKET)(?:\s+(\w+))?", up)
    if m:
        return out("prices", 0.92, "Market board", drug=_drug(m.group(1) or ""))
    m = re.match(r"^(?:(\w+)\s+)?ROUTES?$", up)
    if m:
        d = _drug(m.group(1) or "")
        return out("routes", 0.95, f"{(d or 'all').title()} routes", drug=d)
    m = re.match(r"^(\w{3})(?:\s*<?GO>?)?$", up)
    if m:
        from ..api.app import store
        if m.group(1) in store().country_index:
            return out("country", 0.97, f"Country screen {m.group(1)}", iso3=m.group(1))
    ctry = _countries(t)
    if ctry:
        return out("country", 0.6, f"Country screen {ctry[0]}", iso3=ctry[0])
    return {**out("unknown", 0.2, "Command not recognised. Type HELP for examples."), "parser": "rules"}
