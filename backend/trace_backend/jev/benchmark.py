# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Real-news benchmark for Live Wire classifiers: accuracy, false events, hallucination and calibration.

    python -m trace_backend.jev.benchmark            # mock + Reflex (if weights exist), raw and grounded
    python -m trace_backend.jev.benchmark --tune     # pick thresholds on the SYNTHETIC validation headlines

The benchmark (`jev/data/real_headlines_v1.jsonl`) holds real, published headlines (plus the first sentence where
available) hand-labelled from the text alone, including what the text supports (`support.countries`,
`support.drugs`). A prediction is a hallucination when it names an origin/destination country or a drug that is not
in the hand-labelled support set. That set is written by a person, independently of `grounding.py`, so the metric
does not grade the guardrail with its own gazetteer.

Thresholds are never tuned here on the real benchmark: `--tune` uses the synthetic validation split
(`data/reflex/llm_val.jsonl` headlines with gold rows from `reflex/llm_data`), and the real set stays held out.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from .base import Classification, JevClassifier
from .grounding import EVENT_THRESHOLD, MIN_CONFIDENCE, ground

HERE = Path(__file__).resolve().parent
BENCH = HERE / "data" / "real_headlines_v1.jsonl"
RESULTS = HERE.parent / "reflex" / "results" / "real_news_v1.json"
FIELDS = ["is_event", "event_type", "drug", "origin", "destination", "size"]
NEG_GROUPS = ("near_miss", "unrelated")


def load_benchmark(path: Path = BENCH) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if "_ai_assistance" not in r:
                rows.append(r)
    return rows


def text_of(r: dict) -> tuple[str, str]:
    return r["headline"], (r.get("lede") or "")


# ------------------------------------------------------------------ metrics
def ece(conf: list[float], correct: list[int], bins: int = 10) -> float:
    n = len(conf)
    if not n:
        return float("nan")
    tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(conf) if lo < c <= hi or (b == 0 and c == 0)]
        if idx:
            tot += len(idx) / n * abs(sum(correct[i] for i in idx) / len(idx) - sum(conf[i] for i in idx) / len(idx))
    return round(tot, 4)


def pred_size(c: Classification) -> str | None:
    return c.size if c.size_stated else None


def score(rows: list[dict], preds: list[Classification], min_conf: float = MIN_CONFIDENCE) -> dict:
    """All metrics for one classifier on labelled rows (same order)."""
    hit = {f: 0 for f in FIELDS}
    n_size = 0
    halluc_rows, ents, halluc = [], 0, []
    shown, shown_neg, neg = 0, 0, 0
    conf_all, corr_all, conf_shown, corr_shown = [], [], [], []
    extracted = {"origin": 0, "destination": 0, "drug": 0}
    extracted_possible = {"origin": 0, "destination": 0, "drug": 0}
    for r, c in zip(rows, preds, strict=True):
        g, sup = r["labels"], r["support"]
        hit["is_event"] += int((c.is_event >= 0.5) == bool(g["is_event"]))
        hit["event_type"] += int(c.event_type == g["event_type"])
        hit["drug"] += int(c.drug == g["drug"])
        hit["origin"] += int(c.origin == g["origin"])
        hit["destination"] += int(c.destination == g["destination"])
        if g["event_type"] == "seizure":
            n_size += 1
            hit["size"] += int(pred_size(c) == g["size"])
        for f in ("origin", "destination"):
            if g[f]:
                extracted_possible[f] += 1
                extracted[f] += int(getattr(c, f) == g[f])
        if g["drug"] not in ("unclear",):
            extracted_possible["drug"] += 1
            extracted["drug"] += int(c.drug == g["drug"])
        # hallucination: an entity the text does not support
        bad = []
        for f in ("origin", "destination"):
            v = getattr(c, f)
            if v:
                ents += 1
                if v not in sup["countries"]:
                    bad.append(f"{f}:{v}")
        if c.drug != "unclear":
            ents += 1
            if c.drug not in sup["drugs"]:
                bad.append(f"drug:{c.drug}")
        if bad:
            halluc_rows.append({"id": r["id"], "headline": r["headline"], "hallucinated": bad})
            halluc += bad
        is_shown = c.confidence >= min_conf and c.is_event >= 0.5
        correct = int(bool(g["is_event"]) and c.event_type == g["event_type"] and c.drug == g["drug"])
        conf_all.append(c.confidence)
        corr_all.append(int((c.is_event >= 0.5) == bool(g["is_event"]) and c.event_type == g["event_type"]
                            and c.drug == g["drug"]))
        if is_shown:
            shown += 1
            conf_shown.append(c.confidence)
            corr_shown.append(correct)
        if r["group"] in NEG_GROUPS:
            neg += 1
            shown_neg += int(is_shown)
    n = len(rows)
    acc = {f: round(hit[f] / (n_size if f == "size" else n), 3) for f in FIELDS}
    non_events = [(r, c) for r, c in zip(rows, preds, strict=True) if not r["labels"]["is_event"]]
    return {
        "n": n, "field_accuracy": acc, "n_size_rows": n_size,
        "correct_extractions": {f: f"{extracted[f]}/{extracted_possible[f]}" for f in extracted},
        "false_event_rate_negatives": round(shown_neg / max(1, neg), 3),
        "false_event_rate_all_non_events": round(
            sum(c.confidence >= min_conf and c.is_event >= 0.5 for _, c in non_events) / max(1, len(non_events)), 3),
        "n_negatives": neg, "shown_on_wire": shown,
        "hallucination": {"entities_predicted": ents, "hallucinated": len(halluc),
                          "rate": round(len(halluc) / max(1, ents), 3), "rows": halluc_rows},
        "calibration": {"ece_all": ece(conf_all, corr_all), "mean_conf_all": round(statistics.mean(conf_all), 3),
                        "accuracy_all": round(statistics.mean(corr_all), 3),
                        "mean_conf_shown": round(statistics.mean(conf_shown), 3) if conf_shown else None,
                        "precision_shown": round(statistics.mean(corr_shown), 3) if corr_shown else None,
                        "ece_shown": ece(conf_shown, corr_shown)},
    }


# ------------------------------------------------------------------ classifiers
def classifiers(include_reflex: bool = True) -> list[tuple[str, JevClassifier, bool]]:
    """(label, classifier, grounded) triples. Reflex runs once per mode (its candidate set differs)."""
    from .mock import MockJevClassifier
    out: list[tuple[str, JevClassifier, bool]] = [("mock", MockJevClassifier(), False),
                                                   ("mock+grounding", MockJevClassifier(), True)]
    if include_reflex:
        try:
            from ..reflex.model import WEIGHTS_DIR
            if (WEIGHTS_DIR / "reflex.json").exists():
                from ..reflex import Reflex
                from .reflex_client import ReflexClassifier
                rx = Reflex.load()
                out += [("reflex", ReflexClassifier(model=rx, grounded=False), False),
                        ("reflex+grounding", ReflexClassifier(model=rx, grounded=True), True)]
        except ImportError:
            pass
    return out


def predict(clf: JevClassifier, rows: list[dict], grounded: bool) -> list[Classification]:
    out = []
    for r in rows:
        title, text = text_of(r)
        c = clf.classify(title, text)
        if grounded and not getattr(clf, "grounded", False):
            c = ground(c, title, text)
        out.append(c)
    return out


def run(include_reflex: bool = True, write: bool = True) -> dict:
    rows = load_benchmark()
    comp: dict[str, int] = {}
    for r in rows:
        comp[r["group"]] = comp.get(r["group"], 0) + 1
    rep = {"benchmark": str(BENCH.relative_to(HERE.parents[1])), "composition": comp,
           "thresholds": {"event": EVENT_THRESHOLD, "min_confidence": MIN_CONFIDENCE},
           "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": {}}
    for label, clf, grounded in classifiers(include_reflex):
        t0 = time.perf_counter()
        preds = predict(clf, rows, grounded)
        res = score(rows, preds)
        res["ms_per_article"] = round(1000 * (time.perf_counter() - t0) / len(rows), 1)
        res["classifier"] = getattr(clf, "name", label)
        rep["results"][label] = res
    if write:
        RESULTS.write_text(json.dumps(rep, indent=2, ensure_ascii=False), "utf-8")
    return rep


# ------------------------------------------------------------------ threshold tuning (synthetic only)
def synthetic_val_rows() -> list[dict]:
    """Gold rows for the headlines in the synthetic validation split (never the real benchmark)."""
    from ..reflex.data import LLM_DIR, OUT, _norm
    states = set()
    for line in (OUT / "llm_val.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            s = json.loads(line)["state"]
            states.add(_norm(s["title"] if isinstance(s, dict) else s))
    rows = {}
    for f in sorted(LLM_DIR.glob("batch_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                k = _norm(r["title"])
                if k in states and k not in rows:
                    rows[k] = r
    return list(rows.values())


def tune(include_reflex: bool = True) -> dict:
    """Grid over (event threshold, min confidence): lowest false-event rate keeping >= 95% of true events shown."""
    rows = synthetic_val_rows()
    out = {"n_rows": len(rows), "n_events": sum(r["is_event"] for r in rows), "grid": {}}
    for label, clf, grounded in classifiers(include_reflex):
        if not grounded:
            continue
        raw = []
        for r in rows:
            c = clf.classify(r["title"])
            if not getattr(clf, "grounded", False):
                c = ground(c, r["title"])
            raw.append(c)
        best = None
        grid = []
        for thr in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            for mc in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8):
                shown = [c.is_event >= thr and c.confidence >= mc for c in raw]
                tp = sum(s and r["is_event"] for s, r in zip(shown, rows, strict=True))
                fp = sum(s and not r["is_event"] for s, r in zip(shown, rows, strict=True))
                ev = sum(r["is_event"] for r in rows)
                recall, fpr = tp / max(1, ev), fp / max(1, len(rows) - ev)
                grid.append({"event_threshold": thr, "min_confidence": mc, "recall": round(recall, 3),
                             "false_event_rate": round(fpr, 3)})
                key = (recall >= 0.95, -fpr, recall, -abs(thr - 0.5), -abs(mc - 0.6))
                if best is None or key > best[0]:
                    best = (key, grid[-1])
        out["grid"][label] = {"best": best[1], "all": grid}
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--no-reflex", action="store_true")
    a = ap.parse_args(argv)
    if a.tune:
        t = tune(not a.no_reflex)
        print(json.dumps({k: (v["best"] if isinstance(v, dict) and "best" in v else v)
                          for k, v in {**t, **t["grid"]}.items() if k != "grid"}, indent=2))
        return
    rep = run(not a.no_reflex)
    for label, r in rep["results"].items():
        print(f"{label:18s} acc={r['field_accuracy']} false_event={r['false_event_rate_negatives']} "
              f"halluc={r['hallucination']['hallucinated']}/{r['hallucination']['entities_predicted']} "
              f"ece={r['calibration']['ece_all']} shown={r['shown_on_wire']} prec={r['calibration']['precision_shown']}")


if __name__ == "__main__":
    main()
