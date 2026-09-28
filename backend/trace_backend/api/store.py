# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""In-memory store of the precomputed API JSON (data/processed/api/). No model runs on the request path
except /api/simulate."""
from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

from .. import config
from ..wb.indicators import ROLE_LABELS

ROLE_ORDER = ["governance", "logistics", "gravity", "vulnerability", "outcome"]


class Store:
    def __init__(self, root: Path | None = None):
        import os
        self.root = root or (Path(os.environ["TRACE_API_DIR"]) if os.environ.get("TRACE_API_DIR") else config.API_DIR)
        if not (self.root / "meta.json").exists():
            raise FileNotFoundError(f"No exported API data in {self.root}. Run `uv run trace pipeline` first.")

    def _load(self, name: str):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    @cached_property
    def meta(self) -> dict:
        return self._load("meta.json")

    @cached_property
    def countries(self) -> list[dict]:
        return self._load("countries.json")

    @cached_property
    def country_index(self) -> dict[str, dict]:
        return {c["iso3"]: c for c in self.countries}

    @cached_property
    def observed(self) -> dict[int, list[dict]]:
        return {int(k): v for k, v in self._load("routes_observed.json").items()}

    @cached_property
    def predicted(self) -> dict[int, list[dict]]:
        return {int(k): v for k, v in self._load("routes_predicted.json").items()}

    @cached_property
    def risk(self) -> dict[int, list[dict]]:
        return {int(k): v for k, v in self._load("risk.json").items()}

    @cached_property
    def risk_details(self) -> dict[str, dict]:
        return self._load("risk_details.json")

    @cached_property
    def prices(self) -> list[dict]:
        return self._load("prices.json")

    @cached_property
    def indicators(self) -> dict[str, dict]:
        return self._load("indicators.json")

    @cached_property
    def indicator_meta(self) -> dict:
        return self._load("indicator_meta.json")

    @cached_property
    def oc_index(self) -> dict[str, list]:
        return self._load("oc_index.json")

    @cached_property
    def harm_reduction(self) -> dict[str, list]:
        return self._load("harm_reduction.json")

    @cached_property
    def cultivation(self) -> dict[str, list]:
        return self._load("cultivation.json")

    @cached_property
    def briefings(self) -> dict[str, str]:
        return self._load("briefings.json")

    @cached_property
    def afghan_ban(self) -> dict:
        return self._load("afghan_ban.json")

    @cached_property
    def metrics(self) -> dict:
        return self._load("metrics.json")

    # ------------------------------------------------------------------ helpers
    def routes(self, mode: str, year: int) -> list[dict] | None:
        return (self.observed if mode == "observed" else self.predicted).get(year)

    def edges_for_year(self, year: int) -> list[dict]:
        return self.observed.get(year) or self.predicted.get(year) or []

    def indicator_groups(self, iso3: str, year: int) -> list[dict]:
        codes = self.indicator_meta["codes"]
        series = self.indicators.get(iso3, {})
        groups = []
        for role in ROLE_ORDER:
            items = []
            for code, m in codes.items():
                if m["role"] != role:
                    continue
                pts = [p for p in series.get(code, []) if p[0] <= year]
                y, v = (pts[-1] if pts else (None, None))
                items.append({"code": code, "source_id": m["source_id"], "year": y, "value": v, "name": m["name"],
                              "unit": m["unit"], "imputed": bool(m["forward_fill"] and y is not None and y < year)})
            groups.append({"role": role, "label": ROLE_LABELS[role], "indicators": items})
        return groups

    def hr_for(self, iso3: str, year: int) -> dict | None:
        """HRI edition in force for the year (latest edition <= year; none before the first edition)."""
        eds = [e for e in self.harm_reduction.get(iso3, []) if e["year"] <= year]
        return eds[-1] if eds else None

    def oc_for(self, iso3: str, year: int) -> dict | None:
        eds = self.oc_index.get(iso3)
        if not eds:
            return None
        prior = [e for e in eds if e["edition"] <= year]
        return prior[-1] if prior else eds[0]
