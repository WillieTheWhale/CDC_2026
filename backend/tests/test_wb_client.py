# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""World Bank client: pagination, nulls, error bodies, caching (no network)."""
import json
import re

import pandas as pd
import pytest

from trace_backend.wb.client import WorldBankClient, WorldBankError
from trace_backend.wb.indicators import BY_CODE, INDICATORS
from trace_backend.wb.ingest import build_panel


class FakeResp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status
        self.headers = {"content-type": "application/json;charset=utf-8"}
        self.text = json.dumps(body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls, self.headers = pages, [], {}

    def get(self, url, timeout):
        self.calls.append(url)
        m = re.search(r"[?&]page=(\d+)", url)
        page = int(m.group(1)) if m else 1
        return FakeResp(self.pages[page - 1])


def rec(iso3, year, value):
    return {"countryiso3code": iso3, "date": str(year), "value": value, "obs_status": "",
            "indicator": {"id": "X"}, "country": {"id": iso3[:2]}}


def test_paginates_all_pages_and_keeps_nulls():
    pages = [
        [{"page": 1, "pages": 2, "per_page": 2, "total": 3, "lastupdated": "2026-07-13", "sourceid": "2"},
         [rec("COL", 2020, 1.5), rec("COL", 2021, None)]],
        [{"page": 2, "pages": 2, "per_page": 2, "total": 3}, [rec("ECU", 2020, 2.0)]],
    ]
    s = FakeSession(pages)
    c = WorldBankClient(session=s, per_page=2)
    res = c.indicator("NY.GDP.MKTP.CD", 2, "2020:2021")
    assert len(res.records) == 3 and len(s.calls) == 2
    assert all("source=2" in u and "format=json" in u for u in s.calls)
    assert res.records[1]["value"] is None
    assert res.lastupdated == "2026-07-13"


def test_error_body_with_http_200_raises():
    s = FakeSession([[{"message": [{"id": "120", "key": "Invalid value", "value": "The provided parameter value is not valid"}]}]])
    with pytest.raises(WorldBankError, match="API error"):
        WorldBankClient(session=s, retries=1).indicator("BAD.CODE", 2, "2020")


def test_cache_roundtrip(tmp_path):
    pages = [[{"page": 1, "pages": 1, "per_page": 50, "total": 1}, [rec("COL", 2020, 3.0)]]]
    s = FakeSession(pages)
    WorldBankClient(session=s, cache_dir=tmp_path).indicator("SP.POP.TOTL", 2, "2020")
    s2 = FakeSession([])
    res = WorldBankClient(session=s2, cache_dir=tmp_path).indicator("SP.POP.TOTL", 2, "2020")
    assert res.from_cache and not s2.calls and res.records[0]["value"] == 3.0


def test_registry_uses_verified_codes():
    assert BY_CODE["GOV_WGI_RL.EST"].source_id == 3
    assert "SM.POP.RHCR.EA" in BY_CODE and "SM.POP.REFG" not in BY_CODE
    assert not any(i.code in {"CC.EST", "RL.EST", "GE.EST", "PV.EST", "SP.POP.1524.TO.UN"} for i in INDICATORS)
    assert BY_CODE["LP.LPI.CUST.XQ"].public is False  # design boundary: model-only


def test_panel_forward_fill_flags_imputed():
    countries = pd.DataFrame({"iso3": ["COL"]})
    long = pd.DataFrame([
        {"iso3": "COL", "year": 2018, "code": "LP.LPI.OVRL.XQ", "value": 2.9},
        {"iso3": "COL", "year": 2022, "code": "LP.LPI.OVRL.XQ", "value": 3.1},
        {"iso3": "COL", "year": 2024, "code": "SP.POP.TOTL", "value": 5e7},
    ])
    p = build_panel(long, countries).set_index("year")
    assert p.loc[2020, "lpi_overall"] == 2.9 and bool(p.loc[2020, "lpi_overall_imputed"])
    assert p.loc[2022, "lpi_overall"] == 3.1 and not bool(p.loc[2022, "lpi_overall_imputed"])
    assert pd.isna(p.loc[2005, "lpi_overall"])
