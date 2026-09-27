# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Validate JSON payloads against contracts/openapi.yaml (OpenAPI 3.1 = JSON Schema 2020-12)."""
from __future__ import annotations

import json
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
OPENAPI_PATH = CONTRACTS / "openapi.yaml"
FIXTURES = CONTRACTS / "fixtures"

# fixture file -> (schema name) ; request bodies included
FIXTURE_SCHEMAS: dict[str, str] = {
    "meta.json": "MetaResponse",
    "countries.json": "CountriesResponse",
    "routes_observed.json": "RoutesResponse",
    "routes_predicted.json": "RoutesResponse",
    "country_COL.json": "CountryResponse",
    "risk.json": "RiskResponse",
    "prices.json": "PricesResponse",
    "simulate_request.json": "SimulateRequest",
    "simulate.json": "SimulateResponse",
    "afghan_ban.json": "AfghanBanResponse",
    "metrics.json": "MetricsResponse",
    "livewire.json": "LivewireResponse",
    "command_request.json": "CommandRequest",
    "command.json": "CommandResponse",
    "people.json": "PeoplePageResponse",
    "people_countries.json": "PeopleCountriesResponse",
    "people_network.json": "PeopleNetworkResponse",
    "person.json": "PersonResponse",
    "people_unlocated.json": "PeoplePageResponse",
    "route_evidence.json": "RouteEvidencePageResponse",
    "route_evidence_item.json": "RouteEvidenceItemResponse",
    "evidence_values.json": "EvidenceValuesResponse",
    "evidence_value.json": "EvidenceValueResponse",
    "evidence_value_market.json": "EvidenceValueResponse",
    "evidence_health.json": "EvidenceHealthResponse",
    "evidence_overdose.json": "EvidenceOverdoseResponse",
    "evidence_research_model.json": "EvidenceResearchModelResponse",
}


@lru_cache(maxsize=1)
def openapi() -> dict[str, Any]:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


@cache
def validator(schema_name: str) -> Draft202012Validator:
    doc = openapi()
    root = {"$ref": f"#/components/schemas/{schema_name}", "components": doc["components"]}
    return Draft202012Validator(root)


def response_schema_name(path_template: str, method: str = "get", status: str = "200") -> str:
    op = openapi()["paths"][path_template][method.lower()]
    ref = op["responses"][status]["content"]["application/json"]["schema"]["$ref"]
    return ref.rsplit("/", 1)[-1]


def errors(schema_name: str, payload: Any) -> list[str]:
    v = validator(schema_name)
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(v.iter_errors(payload), key=lambda e: list(map(str, e.absolute_path)))]


def validate(schema_name: str, payload: Any) -> None:
    errs = errors(schema_name, payload)
    if errs:
        raise AssertionError(f"{schema_name} contract violations:\n  " + "\n  ".join(errs[:25]))


def validate_ws_frames(frames: list[dict]) -> None:
    """Validate WebSocket frames per contracts/websocket.md."""
    for f in frames:
        t, d = f["type"], f["data"]
        assert t in {"hello", "event", "anomaly", "heartbeat", "pong"}, t
        if t in ("event", "anomaly"):
            validate("LiveEvent", d)
            assert d["is_anomaly"] == (t == "anomaly")
            assert d["confidence"] >= 0.6
        elif t == "hello":
            assert {"classifier", "poll_minutes", "server_time", "backlog"} <= d.keys()
            for e in d["backlog"]:
                validate("LiveEvent", e)
        elif t == "heartbeat":
            assert {"server_time", "next_poll_at", "events_total"} <= d.keys()


def validate_fixtures() -> int:
    n = 0
    for name, schema in FIXTURE_SCHEMAS.items():
        validate(schema, json.loads((FIXTURES / name).read_text(encoding="utf-8")))
        n += 1
    validate_ws_frames(json.loads((FIXTURES / "ws_livewire.json").read_text(encoding="utf-8")))
    return n + 1


if __name__ == "__main__":
    print(f"{validate_fixtures()} fixtures valid")
