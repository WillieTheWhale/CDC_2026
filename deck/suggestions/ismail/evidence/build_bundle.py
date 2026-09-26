# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Bundle routes, roles, events and World Bank series into one JSON for the map prototype."""
import json
import sys
from pathlib import Path

import pandas as pd

API = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/claude/CDC_2026/backend/tests/data/api_sample")
SERIES = ["VC.IHR.PSRC.P5", "GOV_WGI_RL.EST", "NY.GDP.PCAP.PP.KD", "SL.UEM.1524.ZS",
          "SI.POV.DDAY", "IS.SHP.GOOD.TU"]

routes = json.loads((API / "routes_observed.json").read_text())
edges = {}
for yr, lst in routes.items():
    for e in lst:
        k = e["id"]
        edges.setdefault(k, {"id": k, "from": e["from"], "to": e["to"], "drug": e["drug"], "kg": {}, "conf": {}})
        edges[k]["kg"][yr] = round(e["kg"], 1)
        edges[k]["conf"][yr] = e["confidence"]

countries = {c["iso3"]: {k: c[k] for k in ("name", "lat", "lon", "region", "income_group")}
             for c in json.loads((API / "countries.json").read_text())}

roles = pd.read_csv("out/roles.csv")
role_map = {}
for r in roles.itertuples():
    role_map.setdefault(r.iso3, {}).setdefault(r.drug, {})[str(r.year)] = [
        r.role, round(r.in_kg), round(r.out_kg), round(r.prod_kg), round(r.hub_share, 4)]

ind = json.loads((API / "indicators.json").read_text())
meta = json.loads((API / "indicator_meta.json").read_text())["codes"]
wb = {iso: {c: d[c] for c in SERIES if c in d} for iso, d in ind.items()}
wb_meta = {c: {"name": meta[c]["name"], "unit": meta[c]["unit"], "source_id": meta[c]["source_id"]} for c in SERIES}

prof = pd.read_csv("out/role_profiles.csv").drop(columns="countries")
bundle = {
    "edges": list(edges.values()), "countries": countries, "roles": role_map,
    "events": json.loads(Path("events.json").read_text()), "wb": wb, "wb_meta": wb_meta,
    "profiles": prof.where(prof.notna(), None).to_dict(orient="records"),
    "years": sorted(int(y) for y in routes),
}
Path("out/bundle.json").write_text(json.dumps(bundle, separators=(",", ":")))
print(len(bundle["edges"]), "edges;", Path("out/bundle.json").stat().st_size // 1024, "KB")
