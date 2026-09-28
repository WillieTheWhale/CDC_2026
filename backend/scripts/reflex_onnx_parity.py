# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Parity of the ONNX Reflex backends with the torch backend, plus CPU speed and memory.

    .venv/Scripts/python scripts/reflex_onnx_parity.py [--variants int8,fp32,int8-matmul] [--limit N]

Compares per-option probabilities (max / mean absolute difference), top-choice agreement per primitive on the
synthetic val / test / llm_val / llm_test splits (reflex/data.py), and end-to-end Live Wire field agreement
(ReflexClassifier) on the 100 labelled eval headlines plus 50 other Claude-written headlines from llm_test.
Writes trace_backend/reflex/results/onnx_parity.json.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from trace_backend.reflex.data import load_split  # noqa: E402
from trace_backend.reflex.model import ONNX_DIR, Reflex, ReflexOnnx, find_onnx  # noqa: E402

SPLITS = ["val", "test", "llm_val", "llm_test"]
FILES = {"fp32": "model.onnx", "emb8": "model.emb8.onnx", "int8-ffn": "model.int8-ffn.onnx", "int8": "model.int8.onnx"}
OUT = BACKEND / "trace_backend" / "reflex" / "results" / "onnx_parity.json"


def headlines() -> list[str]:
    ev = json.loads((BACKEND / "trace_backend" / "jev" / "data" / "labeled_eval.json").read_text(encoding="utf-8"))
    titles = [r[0] for r in ev["rows"]]
    seen, extra = set(titles), []
    for e in load_split("llm_test"):
        if isinstance(e.state, str) and e.state not in seen and len(extra) < 50:
            seen.add(e.state)
            extra.append(e.state)
    return titles + extra


def classify_all(rx, heads: list[str]) -> tuple[list[dict], list[float]]:
    from trace_backend.jev.reflex_client import ReflexClassifier
    clf = ReflexClassifier(None, model=rx)
    clf.classify("warm-up: Police seize cocaine in Spain")
    out, ms = [], []
    for h in heads:
        t = time.perf_counter()
        c = clf.classify(h)
        ms.append(1000 * (time.perf_counter() - t))
        out.append({"is_event": c.is_event >= 0.5, "event_type": c.event_type, "drug": c.drug, "origin": c.origin,
                    "destination": c.destination, "size": c.size, "route_mentioned": c.route_mentioned >= 0.5,
                    "on_wire": c.confidence >= 0.6 and c.is_event >= 0.5})
    return out, ms


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="emb8,int8-ffn,int8,fp32")
    ap.add_argument("--limit", type=int, default=0, help="examples per split (0 = all)")
    a = ap.parse_args(argv)
    examples = {s: load_split(s)[: a.limit or None] for s in SPLITS}
    heads = headlines()
    report = {"evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "splits": {s: len(v) for s, v in examples.items()},
              "n_headlines": len(heads), "cpu_threads": os.cpu_count(), "variants": {}}

    t0 = time.perf_counter()
    rt = Reflex.load(backend="torch")
    report["torch"] = {"load_s": round(time.perf_counter() - t0, 2)}
    ref = {s: [rt.probs_for(e.state, e.question()) for e in ex] for s, ex in examples.items()}
    ref_fields, ref_ms = classify_all(rt, heads)
    report["torch"]["ms_per_headline_median"] = round(statistics.median(ref_ms), 1)
    del rt

    for v in a.variants.split(","):
        path = ONNX_DIR / FILES[v]
        if not path.exists():
            print(f"skip {v}: {path} missing")
            continue
        _, meta = find_onnx(ONNX_DIR)
        rx = ReflexOnnx(path, meta)
        t = time.perf_counter()
        rx.warm()
        load_s = time.perf_counter() - t
        diffs, agree = [], {}
        for s, ex in examples.items():
            for e, pr in zip(ex, ref[s], strict=True):
                po = rx.probs_for(e.state, e.question())
                diffs.extend(abs(x - y) for x, y in zip(po, pr, strict=True))
                ag = agree.setdefault(e.prim, [0, 0])
                ag[0] += int(max(range(len(po)), key=po.__getitem__) == max(range(len(pr)), key=pr.__getitem__))
                ag[1] += 1
        fields, ms = classify_all(rx, heads)
        per_field = {k: round(sum(f[k] == g[k] for f, g in zip(fields, ref_fields, strict=True)) / len(heads), 4)
                     for k in ref_fields[0]}
        all_top = sum(x[0] for x in agree.values()) / sum(x[1] for x in agree.values())
        report["variants"][v] = {
            "file": path.name, "mb": round(path.stat().st_size / 1e6, 1), "load_s": round(load_s, 2),
            "prob_abs_diff": {"max": round(max(diffs), 5), "mean": round(statistics.mean(diffs), 6), "n": len(diffs)},
            "top_choice_agreement": {**{p: round(x[0] / x[1], 4) for p, x in agree.items()}, "all": round(all_top, 4)},
            "livewire_field_agreement": per_field,
            "livewire_all_fields_identical": round(sum(f == g for f, g in zip(fields, ref_fields, strict=True))
                                                   / len(heads), 4),
            "ms_per_headline": {"median": round(statistics.median(ms), 1), "p90": round(sorted(ms)[int(.9 * len(ms))], 1),
                                "max": round(max(ms), 1)},
        }
        print(v, json.dumps(report["variants"][v], indent=1))
        del rx
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
