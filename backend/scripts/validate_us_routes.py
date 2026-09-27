# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Do TRACE's predictions agree with the cited US route data (seed/us_routes.csv)?

Scores, per drug and per contiguous US state, against the states the documents name as destinations:
  EST-2011  route-based estimated local flows built from observed 2011 edges (the proximity heuristic)
  EST-2025  the same arrow layer built from the classifier's predicted 2025 edges (the Scenarios hurdle model)
  POP       baseline: state population (sum of Natural Earth populated-place pop_max)
Also: city-level AUC, where domestic distribution starts (origin states), and, at country level, the
classifier's inbound US edges vs the foreign origins the documents name. Bootstrap CIs resample states.

Reads the live API (default https://trace-api-six.vercel.app) and the Natural Earth files that
`uv run trace us-routes` uses. Usage: uv run python scripts/validate_us_routes.py [--api URL] [--out FILE]
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import random
import urllib.request

from trace_backend.us import routes as us

STATES48 = ("AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
            "PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
DRUGS = ["cannabis", "cocaine", "heroin", "meth"]
BORDER = {"TX", "AZ", "NM", "CA"}


def get(api: str, path: str) -> dict:
    with urllib.request.urlopen(f"{api}{path}", timeout=120) as r:  # noqa: S310 (fixed https API)
        return json.load(r)["data"]


class Places:
    def __init__(self) -> None:
        self.post = {f["properties"]["name"]: f["properties"]["postal"]
                     for f in json.loads(us.STATES.read_text(encoding="utf-8"))["features"]}
        self.ne = [f["properties"] for f in json.loads(us.PLACES.read_text(encoding="utf-8"))["features"]
                   if f["properties"]["adm0_a3"] == "USA"]
        self.pop = collections.Counter()
        for p in self.ne:
            if p["adm1name"] in self.post:
                self.pop[self.post[p["adm1name"]]] += p["pop_max"] or 0
        self.city_pop = {p["name"]: p["pop_max"] for p in self.ne}

    def state(self, lon: float, lat: float) -> str | None:
        best = min(self.ne, key=lambda p: (p["longitude"] - lon) ** 2 + (p["latitude"] - lat) ** 2)
        return self.post.get(best["adm1name"])


def arrows(data: dict, places: Places) -> dict:
    """Per drug: inbound strength by state and by city, first-wave (entry) strength by city, outbound by state."""
    ci = {k: i for i, k in enumerate(data["city_fields"])}
    fi = {k: i for i, k in enumerate(data["flow_fields"])}
    cities = data["cities"]
    st = {i: places.state(c[ci["lon"]], c[ci["lat"]]) for i, c in enumerate(cities) if c[ci["iso3"]] == "USA"}
    out = {k: {d: collections.Counter() for d in DRUGS} for k in ("state", "city", "entry", "origin")}
    for f in data["flows"]:
        d, a, b, s = data["drugs"][f[fi["drug"]]], f[fi["from"]], f[fi["to"]], f[fi["strength"]]
        if b in st:
            out["state"][d][st[b]] += s
            out["city"][d][cities[b][ci["name"]]] += s
        if a in st:
            out["origin"][d][st[a]] += s
            if f[fi["generation"]] == 1:  # first wave leaves the entry city of a modeled edge
                out["entry"][d][cities[a][ci["name"]]] += s
                out["state"][d][st[a]] += s
                out["city"][d][cities[a][ci["name"]]] += s
    out["us_cities"] = {cities[i][ci["name"]] for i in st}
    return out


def auc(score: dict, pos: set, universe: list) -> float:
    P = [score.get(s, 0) for s in universe if s in pos]
    N = [score.get(s, 0) for s in universe if s not in pos]
    if not P or not N:
        return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))


def spearman(x: list, y: list) -> float:
    def rank(v):
        order, r, i = sorted(range(len(v)), key=lambda k: v[k]), [0.0] * len(v), 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True)) / den if den else float("nan")


def p_at_10(score: dict, pos: set) -> float:
    return sum(s in pos for s in sorted(STATES48, key=lambda s: -score.get(s, 0))[:10]) / 10


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://trace-api-six.vercel.app")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    api = a.api.rstrip("/") + "/api"
    places = Places()
    rows = list(csv.DictReader(open(us.SEED, encoding="utf-8")))
    dest = {d: collections.Counter(r["to_state"] for r in rows if r["drug"] == d and r["to_state"]) for d in DRUGS}
    dest_city = {d: {r["to_city"] for r in rows if r["drug"] == d and r["to_city"]} for d in DRUGS}
    doc_origin = {d: collections.Counter(r["from_state"] for r in rows if r["drug"] == d and r["from_state"])
                  for d in DRUGS}
    foreign = {d: {r["from_country"] for r in rows if r["drug"] == d and r["from_country"] and not r["to_country"]}
               for d in DRUGS}
    preds = {"EST-2011": arrows(get(api, "/estimated-flows?year=2011"), places),
             "EST-2025": arrows(get(api, "/estimated-flows?mode=predicted"), places)}
    routes_pred = get(api, "/routes?mode=predicted")["edges"]
    routes_2011 = get(api, "/routes?year=2011")["edges"]
    rng = random.Random(7)
    res: dict = {"state": {}, "city": {}, "origin": {}, "entry": {}, "country": {}, "ci": {}}
    for d in DRUGS:
        pos = set(dest[d]) & set(STATES48)
        counts = [dest[d].get(s, 0) for s in STATES48]
        scores = {"EST-2011": preds["EST-2011"]["state"][d], "EST-2025": preds["EST-2025"]["state"][d],
                  "POP": places.pop}
        res["state"][d] = {k: {"auc": round(auc(v, pos, STATES48), 3),
                               "spearman": round(spearman([v.get(s, 0) for s in STATES48], counts), 3),
                               "p_at_10": p_at_10(v, pos),
                               "states_with_arrows": sum(v.get(s, 0) > 0 for s in STATES48)}
                           for k, v in scores.items()}
        res["state"][d]["positives"] = len(pos)
        diffs = collections.defaultdict(list)
        for _ in range(2000):
            u = [rng.choice(STATES48) for _ in STATES48]
            A = {k: auc(v, pos, u) for k, v in scores.items()}
            if not math.isnan(A["POP"]):
                diffs["EST-2011 minus POP"].append(A["EST-2011"] - A["POP"])
                diffs["EST-2025 minus EST-2011"].append(A["EST-2025"] - A["EST-2011"])
        res["ci"][d] = {k: [round(sorted(v)[int(.025 * len(v))], 3), round(sorted(v)[int(.975 * len(v))], 3)]
                        for k, v in diffs.items()}
        usc = sorted(preds["EST-2011"]["us_cities"])
        cpos = dest_city[d] & set(usc)
        res["city"][d] = {"positives": len(cpos), "cities": len(usc),
                          **{k: round(auc(preds[k]["city"][d], cpos, usc), 3) for k in preds},
                          "POP": round(auc({c: places.city_pop.get(c, 0) for c in usc}, cpos, usc), 3)}
        t = sum(doc_origin[d].values())
        res["origin"][d] = {"documented_border_share": round(sum(doc_origin[d][s] for s in BORDER) / t, 2),
                            "documented_top": [(s, round(n / t, 2)) for s, n in doc_origin[d].most_common(4)]}
        for k in preds:
            o = preds[k]["origin"][d]
            t2 = sum(o.values())
            res["origin"][d][f"{k}_border_share"] = round(sum(o[s] for s in BORDER) / t2, 2)
            res["origin"][d][f"{k}_top"] = [(s, round(n / t2, 2)) for s, n in o.most_common(4)]
            res["entry"].setdefault(d, {})[k] = [(c, round(n, 2)) for c, n in preds[k]["entry"][d].most_common(4)]
        res["country"][d] = {
            "documented_foreign_origins": sorted(foreign[d]),
            "classifier_2025_p_active": {e["from"]: e["probability"] for e in routes_pred
                                         if e["to"] == "USA" and e["drug"] == d},
            "observed_2011_origins": sorted(e["from"] for e in routes_2011 if e["to"] == "USA" and e["drug"] == d)}
    text = json.dumps(res, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
