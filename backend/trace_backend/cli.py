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
    sv = sub.add_parser("serve", help="run the API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
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
    if a.cmd == "livewire":
        from trace_backend.api.livewire import poll_once
        for e in poll_once(offline=a.offline):
            print(f"{e['published_at']}  {e['event_type']:<22} {e['drug']:<9} {e['origin']}->{e['destination']}  "
                  f"conf={e['confidence']:.2f}{'  ANOMALY' if e['is_anomaly'] else ''}  {e['title'][:70]}")
        return 0
    kw = {}
    if a.cmd == "export":
        kw["fixtures"] = a.fixtures
    else:
        kw["refresh"] = a.refresh
    _call(a.cmd, **kw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
