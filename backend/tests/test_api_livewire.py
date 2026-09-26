# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""T8 Live Wire: classifier, REST and WebSocket against the contract."""
import pytest

from trace_backend import contract
from trace_backend.api.livewire import load_eval
from trace_backend.jev.mock import MockJevClassifier

from .conftest import check


def test_livewire_rest(client):
    d = check(client.get("/api/livewire", params={"limit": 10}), "/api/livewire")["data"]
    assert all(e["confidence"] >= 0.6 for e in d["events"])


def test_livewire_websocket(client):
    frames = []
    with client.websocket_connect("/ws/livewire") as ws:
        frames.append(ws.receive_json())
        ws.send_json({"type": "ping"})
        frames.append(ws.receive_json())
    assert frames[0]["type"] == "hello" and frames[1]["type"] == "pong"
    contract.validate_ws_frames(frames)


def test_eval_set_has_100_rows():
    assert len(load_eval()) == 100


@pytest.mark.parametrize("title,drug,etype,o,d", [
    ("Ecuador navy seizes 4.2 tonnes of cocaine bound for Belgium", "cocaine", "seizure", "ECU", "BEL"),
    ("Spanish police intercept cocaine shipment from Colombia at Algeciras port", "cocaine", "seizure", "COL", "ESP"),
    ("Thai police intercept 12 million meth pills near Myanmar border", "meth", "seizure", None, None),
    ("Germany's cannabis legalization law takes effect", "cannabis", "law_or_policy_change", None, None),
])
def test_mock_classifier(title, drug, etype, o, d):
    c = MockJevClassifier().classify(title)
    assert c.drug == drug and c.event_type == etype
    if o or d:
        assert (c.origin, c.destination) == (o, d)


def test_non_event_is_low_confidence():
    c = MockJevClassifier().classify("Stock markets rally as inflation cools")
    assert c.confidence < 0.6


def test_metrics_include_livewire_accuracy(client):
    d = check(client.get("/api/metrics"), "/api/metrics")["data"]["livewire"]
    assert d["n_labeled"] == 100 and 0 <= d["field_accuracy"]["drug"] <= 1


def test_anomaly_flag_on_unmodelled_edge(client):
    from trace_backend.api.livewire import state
    ev = state().build_event("Cocaine shipment from Bolivia found in Japan port bound for Japan", "https://x.test/1",
                             __import__("datetime").datetime.now(__import__("datetime").timezone.utc), "x.test")
    assert ev and ev["is_anomaly"] and ev["edge_probability"] is not None and ev["edge_probability"] < 0.1
    contract.validate("LiveEvent", ev)
