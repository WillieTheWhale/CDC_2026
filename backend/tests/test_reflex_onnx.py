# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Torch-free Reflex (ONNX backend): no torch import, same answers as the torch backend, Live Wire fallback.

Model-dependent tests skip when data/reflex/onnx (scripts/export_reflex_onnx.py) or data/reflex/model is absent.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from trace_backend.reflex.model import ONNX_DIR, WEIGHTS_DIR, backend_choice

BACKEND = Path(__file__).resolve().parents[1]
HAS_ONNX = (ONNX_DIR / "reflex.json").exists() and importlib.util.find_spec("onnxruntime") is not None
HAS_TORCH_MODEL = (WEIGHTS_DIR / "model.safetensors").exists() and importlib.util.find_spec("torch") is not None
needs_onnx = pytest.mark.skipif(not HAS_ONNX, reason="no ONNX Reflex (scripts/export_reflex_onnx.py) or onnxruntime")


def test_backend_choice_env(monkeypatch):
    monkeypatch.setenv("TRACE_REFLEX_BACKEND", "onnx")
    assert backend_choice() == "onnx"
    monkeypatch.setenv("TRACE_REFLEX_BACKEND", "torch")
    assert backend_choice() == "torch"
    monkeypatch.delenv("TRACE_REFLEX_BACKEND")
    assert backend_choice() == ("torch" if importlib.util.find_spec("torch") else "onnx")


def test_model_module_does_not_import_torch():
    code = ("import sys; import trace_backend.reflex.model as m; import trace_backend.reflex as r; "
            "assert 'torch' not in sys.modules and 'transformers' not in sys.modules, 'torch imported'")
    subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True)


@needs_onnx
def test_onnx_backend_runs_without_torch():
    """Torch made unimportable: Reflex.load() must pick ONNX, answer a Live Wire request, and never touch torch."""
    code = f"""
import json, sys
sys.modules['torch'] = None  # any `import torch` now raises ImportError
from trace_backend.reflex import Reflex, Choice, Noul, Score
rx = Reflex.load({str(ONNX_DIR)!r})
assert rx.backend == 'onnx' and not rx.loaded, 'session must be lazy'
r = rx.system_one('Ecuador navy seizes 4 tonnes of cocaine bound for Belgium',
                  {{'drug': Choice('Which drug?', {{'cocaine': None, 'heroin': None, 'cannabis': None}}),
                    'ev': Noul('Is this a drug seizure?'),
                    'size': Score('How large?', ['small', 'large', 'record'])}})
a = r.answers
assert a['drug'].choice == 'cocaine' and abs(sum(a['drug'].probabilities.values()) - 1) < 1e-3
assert a['ev'].noul > 0.5 and 0 <= a['size'].score <= 2 and r.usage['pairs'] == 8
assert sys.modules.get('torch') is None
print(json.dumps(r.to_dict()))
"""
    subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True)


@needs_onnx
@pytest.mark.skipif(not HAS_TORCH_MODEL, reason="torch Reflex weights or torch absent")
def test_onnx_matches_torch():
    from trace_backend.reflex.data import load_split
    from trace_backend.reflex.model import Reflex

    exs = []
    for split in ("llm_test", "test"):
        try:
            exs += load_split(split)[:40]
        except FileNotFoundError:
            pass
    if not exs:
        pytest.skip("no Reflex eval splits (uv run trace reflex-data)")
    rt, ro = Reflex.load(backend="torch"), Reflex.load(backend="onnx")
    agree, worst = 0, 0.0
    for e in exs:
        pt, po = rt.probs_for(e.state, e.question()), ro.probs_for(e.state, e.question())
        worst = max(worst, max(abs(a - b) for a, b in zip(pt, po, strict=True)))
        agree += int(pt.index(max(pt)) == po.index(max(po)))
    assert agree / len(exs) >= 0.95, (agree, len(exs))
    assert worst < 0.25, worst  # int8 noise; the full parity report is results/onnx_parity.json
    q = {"drug": {"type": "choice", "instructions": "Which drug?", "criteria": {"cocaine": None, "heroin": None}}}
    s = "Police in Rotterdam seize 3 tonnes of cocaine hidden in bananas"
    assert rt.system_one(s, q).answers["drug"].choice == ro.system_one(s, q).answers["drug"].choice


def test_find_onnx_errors_clearly(tmp_path):
    from trace_backend.reflex.model import ReflexOnnx
    with pytest.raises(FileNotFoundError, match="export_reflex_onnx"):
        ReflexOnnx.load(tmp_path)
    (tmp_path / "reflex.json").write_text(json.dumps({"model_id": "reflex-x", "onnx": {"file": "m.onnx"}}), "utf-8")
    (tmp_path / "tokenizer.json").write_text("{}", "utf-8")
    (tmp_path / "m.onnx").write_bytes(b"not a model")
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip("onnxruntime not installed")
    rx = ReflexOnnx.load(tmp_path)  # cheap: reads reflex.json only
    assert rx.model_id == "reflex-x" and not rx.loaded
    with pytest.raises(Exception):  # noqa: B017 - the corrupt file fails on first use, not at load
        rx.warm()


def test_livewire_guard_falls_back_to_mock_and_reports():
    """A classifier that fails (e.g. the ONNX session cannot be created) switches the wire to the mock, visibly."""
    from trace_backend.api.livewire import LiveWire, _Guarded
    from trace_backend.jev.base import JevClassifier

    class Broken(JevClassifier):
        name = "reflex-9.9.9"

        def classify(self, title, text=""):
            raise RuntimeError("onnx session failed")

    wire = SimpleNamespace(classifier=None, classifier_name="reflex-9.9.9", classifier_fallback=None)
    wire._fall_back = lambda why: LiveWire._fall_back(wire, why)
    g = _Guarded(Broken(), wire)
    wire.classifier = g
    c = g.classify("Spain seizes 2 tonnes of cocaine from Colombia")
    assert c.drug == "cocaine"  # answered by the mock
    assert wire.classifier_name == "mock" and "reflex-9.9.9 failed" in wire.classifier_fallback
    assert "keyword mock" in wire.classifier_fallback


@needs_onnx
def test_vercel_style_env_picks_onnx(monkeypatch):
    if os.environ.get("TRACE_CLASSIFIER") not in (None, "", "mock"):
        pytest.skip("custom classifier env")
    code = """
import os, sys
os.environ['TRACE_CLASSIFIER'] = 'reflex'; os.environ['TRACE_REFLEX_BACKEND'] = 'onnx'
from trace_backend.jev.real import get_classifier
c = get_classifier(None)
assert c.name.startswith('reflex'), c.name
assert 'torch' not in sys.modules
"""
    if not (ONNX_DIR.parent / "model" / "reflex.json").exists():
        pytest.skip("get_classifier looks for data/reflex/model/reflex.json")
    subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True)
