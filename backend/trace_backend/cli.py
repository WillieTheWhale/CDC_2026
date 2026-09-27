# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""`trace` command line: run the whole pipeline or one stage.

    uv run trace pipeline          # everything, in order (one command)
    uv run trace prepare           # derive model inputs from the SQLite archive only
    uv run trace serve             # FastAPI on :8000
"""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
import time

# stage name -> (module, function, description); run in this order by `pipeline`
STAGES: dict[str, tuple[str, str, str]] = {
    "prepare": ("trace_backend.ingest.prepare", "run",
                "Derive model inputs from the canonical SQLite archive (data_collection/work/trace.sqlite)"),
    "edges": ("trace_backend.model.edges", "run", "Edge table + confidence scores"),
    "models": ("trace_backend.model.train", "run", "Gravity PPML, LightGBM hurdle, SHAP, backtest, Afghan ban test"),
    "risk": ("trace_backend.model.spillover", "run", "Spillover risk scores + hypothesis test"),
    "export": ("trace_backend.export.build", "run", "Precompute API JSON"),
}


def _call(stage: str, **kw):
    mod, fn, _ = STAGES[stage]
    t0 = time.time()
    logging.info("== %s: %s", stage, STAGES[stage][2])
    out = getattr(importlib.import_module(mod), fn)(**kw)
    logging.info("== %s done in %.1fs", stage, time.time() - t0)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trace", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("pipeline", help="run every stage in order")
    pp.add_argument("--refresh", action="store_true", help="(unused; the archive is refreshed by data_collection/)")
    pp.add_argument("--skip", nargs="*", default=[], choices=list(STAGES), help="stages to skip")
    for name, (_, _, desc) in STAGES.items():
        sp = sub.add_parser(name, help=desc)
        sp.add_argument("--refresh", action="store_true")
        if name == "export":
            sp.add_argument("--fixtures", action="store_true", help="also rewrite contracts/fixtures from real output")
            sp.add_argument("--route-snapshots", action="store_true",
                            help="also write every year's full routes and risk to frontend/public/data/")
    sv = sub.add_parser("serve", help="run the API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    rd = sub.add_parser("reflex-data", help="build Reflex train/val/test/zeroshot data")
    rd.add_argument("--scale", type=float, default=1.0)
    rt = sub.add_parser("reflex-train", help="train + calibrate Reflex (resumable)")
    rt.add_argument("--epochs", type=int, default=1)
    rt.add_argument("--limit", type=int, default=None, help="train on N shuffled examples")
    rt.add_argument("--init-from", default=None, help="continue from saved Reflex weights (v0.2)")
    rt.add_argument("--train-splits", nargs="+", default=["train"])
    rt.add_argument("--val-splits", nargs="+", default=["val"])
    rt.add_argument("--replay", default=None, help="split:n, e.g. train:800")
    rt.add_argument("--q-per-headline", type=int, default=None)
    rt.add_argument("--model-id", default="reflex-0.1.0")
    rt.add_argument("--out-dir", default=None)
    rt.add_argument("--lr", type=float, default=3e-5)
    sub.add_parser("reflex-download", help="download the published Reflex weights (verified) into data/reflex/model")
    re_ = sub.add_parser("reflex-eval", help="evaluate Reflex against the Reflex Parity Scale")
    re_.add_argument("--quick", action="store_true", help="small subsets")
    re_.add_argument("--model-dir", default=None)
    re_.add_argument("--out", default="eval.json")
    lw = sub.add_parser("livewire", help="poll GDELT once and classify (prints events)")
    lw.add_argument("--offline", action="store_true", help="use the bundled sample articles instead of GDELT")

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if a.cmd == "pipeline":
        t0 = time.time()
        for name in STAGES:
            if name in a.skip:
                continue
            _call(name, refresh=a.refresh) if name != "export" else _call(name)
        logging.info("pipeline complete in %.1fs", time.time() - t0)
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("trace_backend.api.app:app", host=a.host, port=a.port, reload=a.reload)
        return 0
    if a.cmd.startswith("reflex"):
        import os
        os.environ.setdefault("HF_HOME", str(__import__("trace_backend.config", fromlist=["x"]).DATA / "reflex" / "hf"))
        if a.cmd == "reflex-download":
            from trace_backend.reflex.release import download
            logging.info("reflex weights: %s", download())
            return 0
        if a.cmd == "reflex-data":
            from trace_backend.reflex.data import build
            logging.info("reflex data: %s", build(a.scale))
        elif a.cmd == "reflex-train":
            from trace_backend.reflex.train import run as train_run
            rp = {a.replay.split(":")[0]: int(a.replay.split(":")[1])} if a.replay else None
            logging.info("reflex train: %s", train_run(
                epochs=a.epochs, limit=a.limit, init_from=a.init_from, train_splits=tuple(a.train_splits),
                val_splits=tuple(a.val_splits), replay=rp, q_per_headline=a.q_per_headline, model_id=a.model_id,
                out_dir=a.out_dir, lr=a.lr))
        else:
            from trace_backend.reflex.evaluate import run as eval_run
            logging.info("reflex eval written: %s", eval_run(quick=a.quick, model_dir=a.model_dir, out_name=a.out))
        return 0
    if a.cmd == "livewire":
        from trace_backend.api.livewire import poll_once
        for e in poll_once(offline=a.offline):
            print(f"{e['published_at']}  {e['event_type']:<22} {e['drug']:<9} {e['origin']}->{e['destination']}  "
                  f"conf={e['confidence']:.2f}{'  ANOMALY' if e['is_anomaly'] else ''}  {e['title'][:70]}")
        return 0
    kw = {}
    if a.cmd == "export":
        kw["fixtures"] = a.fixtures
        kw["route_snapshots"] = a.route_snapshots
    else:
        kw["refresh"] = a.refresh
    _call(a.cmd, **kw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
