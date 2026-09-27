# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""RemoteReflexClassifier: the production path where the API calls the separate Reflex function."""
import io
import json

import pytest

from trace_backend.jev import remote
from trace_backend.jev.remote import RemoteReflexClassifier

PAYLOAD = {"data": {"classifier": "reflex-0.2.0", "on_wire": True, "latency_ms": 5, "classification": {
    "is_event": 0.99, "event_type": "seizure", "event_type_conf": 0.9, "drug": "cocaine", "drug_conf": 0.95,
    "origin": "VEN", "transit": None, "destination": "DOM", "location": "DOM", "size": "notable", "size_score": 0.6,
    "route_mentioned": 0.9, "confidence": 0.97, "size_stated": True, "dropped": [], "unknown_future_field": 1}}}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_remote_classifier_parses_the_service_payload(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["body"] = req.full_url, json.loads(req.data)
        return _Resp(json.dumps(PAYLOAD).encode())

    monkeypatch.setattr(remote.urllib.request, "urlopen", fake_urlopen)
    c = RemoteReflexClassifier("https://reflex.example/").classify("Dominican agency seizes 500 kg from Venezuela")
    assert seen["url"] == "https://reflex.example/api/classify" and seen["body"]["title"].startswith("Dominican")
    assert (c.origin, c.destination, c.size, c.size_stated, c.dropped) == ("VEN", "DOM", "notable", True, ())


def test_remote_is_selected_and_not_reported_as_a_fallback(monkeypatch):
    monkeypatch.setenv("TRACE_CLASSIFIER", "reflex-remote")
    monkeypatch.setenv("TRACE_REFLEX_URL", "https://reflex.example")
    from trace_backend.jev.real import get_classifier
    clf = get_classifier([])
    assert isinstance(clf, RemoteReflexClassifier) and clf.name.startswith("reflex")
    from trace_backend.api.livewire import LiveWire
    lw = LiveWire.__new__(LiveWire)
    lw.classifier_fallback = None
    lw._pick_classifier([])
    assert lw.classifier_fallback is None


def test_classify_endpoint_returns_503_when_the_service_is_down(monkeypatch):
    from fastapi.testclient import TestClient

    from trace_backend.api import livewire
    from trace_backend.api.app import app

    class Down:
        name, url = "reflex-0.2.0", "https://reflex.example"

        def classify(self, title, text=""):
            raise OSError("connection refused")

    monkeypatch.setattr(livewire.state(), "classifier", Down())
    r = TestClient(app).post("/api/livewire/classify", json={"title": "Police seize cocaine in Spain"})
    assert r.status_code == 503
