# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Regenerate contracts/fixtures/ from the live API (real pipeline output, trimmed for size), and write the
small sample export used by tests on a fresh clone (tests/data/api_sample)."""
from __future__ import annotations

import json
import logging
import os
import shutil

from .. import config, contract

log = logging.getLogger(__name__)
SAMPLE_ISO3 = ["COL", "ECU", "PER", "BOL", "BRA", "PAN", "MEX", "USA", "ESP", "NLD", "BEL", "AFG", "IRN", "PAK",
               "TUR", "MMR", "THA", "LAO", "CHN", "IND"]
SAMPLE_DIR = config.BACKEND / "tests" / "data" / "api_sample"


def _dump(name: str, obj) -> None:
    (contract.FIXTURES / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("fixture %s", name)


def regenerate() -> None:
    os.environ.setdefault("TRACE_LIVEWIRE_POLL", "0")
    from fastapi.testclient import TestClient

    from ..api.app import app
    c = TestClient(app)
    ok = lambda r: (r.raise_for_status(), r.json())[1]  # noqa: E731

    _dump("meta.json", ok(c.get("/api/meta")))
    _dump("countries.json", ok(c.get("/api/countries")))
    for mode in ("observed", "predicted"):
        d = ok(c.get("/api/routes", params={"mode": mode}))
        d["data"]["edges"] = d["data"]["edges"][:80]
        _dump(f"routes_{mode}.json", d)
    _dump("country_COL.json", ok(c.get("/api/country/COL")))
    _dump("risk.json", ok(c.get("/api/risk", params={"limit": 40})))
    d = ok(c.get("/api/prices"))
    keep = {"COL", "ESP", "USA", "BEL", "AFG", "TUR", "GBR", "THA", "CAN", "MAR", "DEU", "NLD"}
    d["data"]["series"] = [s for s in d["data"]["series"] if s["iso3"] in keep]
    _dump("prices.json", d)
    req = {"scenario": "Colombia cuts coca 50%", "shocks": [], "year": None}
    req = {k: v for k, v in req.items() if v is not None}
    _dump("simulate_request.json", req)
    d = ok(c.post("/api/simulate", json=req))
    d["data"]["edges_changed"] = d["data"]["edges_changed"][:25]
    d["data"]["risk_deltas"] = d["data"]["risk_deltas"][:20]
    _dump("simulate.json", d)
    _dump("afghan_ban.json", ok(c.get("/api/experiments/afghan-ban")))
    _dump("metrics.json", ok(c.get("/api/metrics")))
    lw = ok(c.get("/api/livewire", params={"limit": 20}))
    _dump("livewire.json", lw)
    frames = []
    with c.websocket_connect("/ws/livewire") as ws:
        frames.append(ws.receive_json())
    frames[0]["data"]["backlog"] = frames[0]["data"]["backlog"][:3]
    for e in lw["data"]["events"][:6]:
        frames.append({"type": "anomaly" if e["is_anomaly"] else "event", "data": e})
    frames.append({"type": "heartbeat", "data": {"server_time": frames[0]["data"]["server_time"],
                                                 "next_poll_at": frames[0]["data"]["server_time"],
                                                 "events_total": len(lw["data"]["events"])}})
    _dump("ws_livewire.json", frames)
    cmd = {"text": "SHOCK AFG CULTIVATION -95%"}
    _dump("command_request.json", cmd)
    _dump("command.json", ok(c.post("/api/command", json=cmd)))
    n = contract.validate_fixtures()
    log.info("regenerated and validated %d fixtures", n)
    write_sample()


def write_sample() -> None:
    """Small subset of the real export (20 countries) so tests run without the pipeline."""
    src = config.API_DIR
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    keep = set(SAMPLE_ISO3)
    load = lambda n: json.loads((src / n).read_text(encoding="utf-8"))  # noqa: E731
    save = lambda n, o: (SAMPLE_DIR / n).write_text(json.dumps(o, separators=(",", ":")), encoding="utf-8")  # noqa: E731
    save("countries.json", [c for c in load("countries.json") if c["iso3"] in keep])
    for n in ("routes_observed.json", "routes_predicted.json"):
        save(n, {y: [e for e in es if e["from"] in keep and e["to"] in keep] for y, es in load(n).items()})
    risk = load("risk.json")
    save("risk.json", {y: [r for r in rows if r["iso3"] in keep] for y, rows in risk.items()})
    for n in ("risk_details.json", "indicators.json", "oc_index.json", "harm_reduction.json", "cultivation.json",
              "briefings.json"):
        save(n, {k: v for k, v in load(n).items() if k in keep})
    save("prices.json", [p for p in load("prices.json") if p["iso3"] in keep])
    for n in ("meta.json", "indicator_meta.json", "afghan_ban.json", "metrics.json"):
        shutil.copy(src / n, SAMPLE_DIR / n)
    log.info("sample export written to %s", SAMPLE_DIR)


ROUTE_SNAPSHOT_DIR = config.BACKEND.parent / "frontend" / "public" / "data" / "routes"
RISK_SNAPSHOT_DIR = config.BACKEND.parent / "frontend" / "public" / "data" / "risk"


def write_route_snapshots() -> int:
    """Every year's full /api/routes and /api/risk response (no trimming) for the frontend's no-API mode.

    One file per mode and year (`routes/observed-2006.json` ... `routes/predicted-2025.json`,
    `risk/2008.json` ... `risk/2025.json`, every country) so the browser fetches only the year on screen.
    Each file is the exact API envelope and is validated against the contract."""
    os.environ.setdefault("TRACE_LIVEWIRE_POLL", "0")
    from fastapi.testclient import TestClient

    from ..api.app import app
    c = TestClient(app)
    meta = c.get("/api/meta").json()["data"]
    ROUTE_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in ROUTE_SNAPSHOT_DIR.glob("*.json"):
        old.unlink()
    index = {}
    for mode, years in (("observed", meta["observed_years"]), ("predicted", meta["predicted_years"])):
        for year in years:
            r = c.get("/api/routes", params={"mode": mode, "year": year})
            r.raise_for_status()
            body = r.json()
            contract.validate("RoutesResponse", body)
            name = f"{mode}-{year}.json"
            (ROUTE_SNAPSHOT_DIR / name).write_text(json.dumps(body, separators=(",", ":"), ensure_ascii=False),
                                                  encoding="utf-8")
            index[name] = len(body["data"]["edges"])
    (ROUTE_SNAPSHOT_DIR / "index.json").write_text(json.dumps(
        {"_ai_assisted": "Claude Code (Anthropic). See docs/AI_USAGE.md.",
         "generated_by": "uv run trace export --route-snapshots", "files": index}, indent=2) + "\n",
        encoding="utf-8")
    log.info("wrote %d route snapshots (%d edges) to %s", len(index), sum(index.values()), ROUTE_SNAPSHOT_DIR)
    RISK_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in RISK_SNAPSHOT_DIR.glob("*.json"):
        old.unlink()
    for year in meta["risk_years"]:
        r = c.get("/api/risk", params={"year": year})
        r.raise_for_status()
        body = r.json()
        contract.validate("RiskResponse", body)
        (RISK_SNAPSHOT_DIR / f"{year}.json").write_text(json.dumps(body, separators=(",", ":"), ensure_ascii=False),
                                                        encoding="utf-8")
    log.info("wrote %d risk snapshots to %s", len(meta["risk_years"]), RISK_SNAPSHOT_DIR)
    return len(index)
