# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Shared fixtures: a TestClient over the real export, or the committed sample export on a fresh clone."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("TRACE_LIVEWIRE_POLL", "0")  # no background GDELT polling in tests

from trace_backend import config, contract  # noqa: E402

SAMPLE = Path(__file__).parent / "data" / "api_sample"


@pytest.fixture(scope="module")
def client():
    if not (config.API_DIR / "meta.json").exists():
        if not (SAMPLE / "meta.json").exists():
            pytest.skip("no exported API data")
        os.environ["TRACE_API_DIR"] = str(SAMPLE)
    from fastapi.testclient import TestClient

    from trace_backend.api import app as app_mod
    app_mod.store.cache_clear()
    with TestClient(app_mod.app) as c:
        yield c


def check(resp, path: str, method: str = "get", status: int = 200):
    """Assert status and validate the JSON body against the contract schema for that path/status."""
    assert resp.status_code == status, resp.text[:500]
    schema = contract.response_schema_name(path, method, str(status))
    contract.validate(schema, resp.json())
    return resp.json()
