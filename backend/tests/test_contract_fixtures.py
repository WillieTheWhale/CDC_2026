# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Every fixture in contracts/fixtures/ must match contracts/openapi.yaml."""
import json

import pytest

from trace_backend import contract


@pytest.mark.parametrize("name,schema", sorted(contract.FIXTURE_SCHEMAS.items()))
def test_fixture_matches_contract(name, schema):
    payload = json.loads((contract.FIXTURES / name).read_text(encoding="utf-8"))
    contract.validate(schema, payload)


def test_ws_fixture_frames():
    frames = json.loads((contract.FIXTURES / "ws_livewire.json").read_text(encoding="utf-8"))
    contract.validate_ws_frames(frames)


def test_every_path_has_a_fixture():
    paths = set(contract.openapi()["paths"])
    covered = {"/api/meta", "/api/countries", "/api/routes", "/api/country/{iso3}", "/api/risk", "/api/prices",
               "/api/simulate", "/api/experiments/afghan-ban", "/api/metrics", "/api/livewire", "/api/livewire/classify", "/api/command",
               "/api/people", "/api/people/countries", "/api/people/network", "/api/people/{person_id}",
               "/api/route-evidence", "/api/route-evidence/sources", "/api/route-evidence/{evidence_id}",
               "/api/evidence/values", "/api/evidence/value/{value_id}", "/api/evidence/health/{iso3}",
               "/api/evidence/overdose", "/api/evidence/research-model",
               "/api/evidence/market-observations", "/api/evidence/market-observations/countries",
               "/api/estimated-flows", "/api/us-routes"}
    assert paths == covered


def test_validator_rejects_bad_payload():
    bad = json.loads((contract.FIXTURES / "routes_observed.json").read_text(encoding="utf-8"))
    bad["data"]["edges"][0]["volume_norm"] = 5
    assert contract.errors("RoutesResponse", bad)
