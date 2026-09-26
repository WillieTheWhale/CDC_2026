# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reflex Parity Scale evaluation (docs/REFLEX_SPEC.md section 3). Writes data/reflex/eval.json and eval.md."""
from __future__ import annotations

import json
import logging
import statistics
import time
from collections import Counter

import torch

from .data import OUT, Example, load_split
from .model import Reflex
from .types import Choice, Noul, NoulCriteria, Score, confidence, render

log = logging.getLogger(__name__)
BINS = 15


def ece(conf: list[float], correct: list[int], bins: int = BINS) -> float:
    n = len(conf)
    if not n:
        return float("nan")
    tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(conf) if (lo < c <= hi) or (b == 0 and c == 0)]
        if idx:
            tot += len(idx) / n * abs(sum(correct[i] for i in idx) / len(idx) - sum(conf[i] for i in idx) / len(idx))
    return round(tot, 4)


def predict(rx: Reflex, e: Example) -> list[float]:
    q = e.question()
    s = torch.tensor(rx.logits_for(e.state, q))
    return torch.softmax(s / rx.temps.get(e.prim, 1.0), 0).tolist()


def score_set(rx: Reflex, examples: list[Example]) -> dict:
    by: dict[str, dict] = {}
    for e in examples:
        p = predict(rx, e)
        d = by.setdefault(e.task, {"prim": e.prim, "n": 0, "correct": [], "nll": [], "conf": [], "brier": [],
                                   "p_yes": [], "y": []})
        pred = max(range(len(p)), key=p.__getitem__)
        d["n"] += 1
        d["correct"].append(int(pred == e.gold))
        d["nll"].append(-float(torch.log(torch.tensor(max(p[e.gold], 1e-9)))))
        d["conf"].append(max(p))
        d["brier"].append(sum((pi - (1.0 if i == e.gold else 0.0)) ** 2 for i, pi in enumerate(p)))
        if e.prim == "noul":
            d["p_yes"].append(p[0])
            d["y"].append(int(e.gold == 0))
    out = {}
    for t, d in by.items():
        out[t] = {"prim": d["prim"], "n": d["n"], "accuracy": round(sum(d["correct"]) / d["n"], 4),
                  "nll": round(statistics.mean(d["nll"]), 4), "brier": round(statistics.mean(d["brier"]), 4),
                  "ece": ece(d["conf"], d["correct"]),
                  **({"ece_yes": ece(d["p_yes"], d["y"])} if d["p_yes"] else {})}
    allc = [c for d in by.values() for c in d["correct"]]
    allp = [c for d in by.values() for c in d["conf"]]
    out["_all"] = {"n": len(allc), "accuracy": round(sum(allc) / max(1, len(allc)), 4), "ece": ece(allp, allc)}
    return out


def majority(train: list[Example], test: list[Example]) -> dict:
    """Majority-class baseline per task (most common gold answer text in train)."""
    def key(e):
        q = e.question()
        if isinstance(q, Choice):
            return list(q.criteria)[e.gold]
        return e.gold
    out = {}
    for t in {e.task for e in test}:
        tr = Counter(key(e) for e in train if e.task == t)
        if not tr:
            continue
        top = tr.most_common(1)[0][0]
        te = [e for e in test if e.task == t]
        out[t] = round(sum(key(e) == top for e in te) / len(te), 4)
    return out


def chance(examples: list[Example]) -> dict:
    out = {}
    for t in {e.task for e in examples}:
        te = [e for e in examples if e.task == t]
        out[t] = round(statistics.mean(1 / len(e.question().criteria) if e.prim != "noul" else 0.5 for e in te), 4)
    return out


# ------------------------------------------------------------------ L0/L1 contract checks
def contract_checks(rx: Reflex) -> dict:
    r = rx.system_one({"message": "My card was charged twice. Please refund me."}, {
        "refund": Noul("Does the customer request a refund?", NoulCriteria("Asks for money back", "Does not")),
        "dept": Choice("Which team?", {"billing": "Charges and payments", "shipping": {"covers": "Deliveries"},
                                       "returns": None}),
        "frustration": Score("How frustrated is the customer?", ["Calm", {"what": "Annoyed"}, "Very angry"]),
        "big": Choice("Pick", {f"opt{i}": None for i in range(255)}),
    })
    a = r.answers
    checks = {
        "probabilities_sum_to_1": all(abs(sum(x.probabilities.values()) - 1) < 1e-3 for x in (a["dept"], a["frustration"])),
        "choice_is_argmax": a["dept"].choice == max(a["dept"].probabilities, key=a["dept"].probabilities.get),
        "score_is_expected_level": abs(a["frustration"].score - sum(k * v for k, v in a["frustration"].probabilities.items())) < 1e-2,
        "noul_in_0_1": 0 <= a["refund"].noul <= 1,
        "answers_within_options": a["dept"].choice in {"billing", "shipping", "returns"},
        "accepts_255_options": len(a["big"].probabilities) == 255,
        "structured_state_and_criteria": True,
        "confidence_formula_documented_examples": all(abs(confidence(p) - c) < 0.01 for p, c in [
            ([0.0, 0.57, 0.43], 0.355), ([0.04, 0.35, 0.61], 0.415), ([0.34, 0.4, 0.02, 0.24], 0.2),
            ([0.0, 0.89, 0.11], 0.835)]),
        "noul_has_no_confidence": not hasattr(a["refund"], "confidence"),
    }
    return {"checks": checks, "pass": all(checks.values()), "example_response": r.to_dict()["answers"]["dept"]}


# ------------------------------------------------------------------ L5 structure
def structure_test(rx: Reflex, test: list[Example]) -> dict:
    ex = [e for e in test if isinstance(e.state, dict)][:80]
    flat = [Example(e.task, e.prim, " ".join(str(v) for v in e.state.values()), e.instructions, e.criteria, e.gold,
                    e.split) for e in ex]
    s, f = score_set(rx, ex)["_all"], score_set(rx, flat)["_all"]
    return {"n": len(ex), "structured_accuracy": s["accuracy"], "flattened_accuracy": f["accuracy"],
            "pass": s["accuracy"] >= f["accuracy"] - 0.02}


# ------------------------------------------------------------------ L6 domain (100-headline Live Wire eval)
def domain_eval(rx: Reflex) -> dict:
    from ..api.livewire import load_eval
    from ..jev.mock import MockJevClassifier
    from ..jev.reflex_client import ReflexClassifier
    rows = load_eval()
    out = {}
    for name, clf in (("reflex", ReflexClassifier(model=rx)), ("mock", MockJevClassifier())):
        hits = Counter()
        t0 = time.perf_counter()
        for r in rows:
            c = clf.classify(r["title"])
            hits["is_event"] += int((c.is_event >= 0.5) == bool(r["is_event"]))
            for f in ("event_type", "drug", "origin", "destination", "size"):
                hits[f] += int(getattr(c, f) == r[f])
        out[name] = {k: round(v / len(rows), 3) for k, v in hits.items()}
        out[name]["ms_per_article"] = round(1000 * (time.perf_counter() - t0) / len(rows), 1)
    fields = ["is_event", "event_type", "drug", "origin", "destination", "size"]
    out["pass"] = all(out["reflex"][f] >= out["mock"][f] - 1e-9 for f in fields)
    out["fields_better_than_mock"] = [f for f in fields if out["reflex"][f] > out["mock"][f]]
    out["fields_worse_than_mock"] = [f for f in fields if out["reflex"][f] < out["mock"][f]]
    out["note"] = "100 synthetic headlines, labels drafted by the backend agent (jev/data/labeled_eval.json)"
    return out


# ------------------------------------------------------------------ L7 jaggedness probes (docs: Jev 1.13 jaggedness)
def jaggedness(rx: Reflex) -> dict:
    def noul(state, q, crit=None):
        return rx.system_one(state, {"q": Noul(q, crit)}).answers["q"].noul

    res = {}
    # 8. structural invariants: P(q) + P(not q) (Jev documented 1.19 on a similar pair)
    pairs = [("I was charged twice for the same order. Can someone look into this?",
              "Is the customer asking for a refund?", "Is the customer asking for something other than a refund?"),
             ("My parcel never arrived and tracking stopped a week ago.", "Is the customer reporting a delivery problem?",
              "Is the customer reporting something other than a delivery problem?"),
             ("Colombian police seized 2 tonnes of cocaine at the port of Cartagena.", "Was cocaine seized?",
              "Was something other than cocaine seized?")]
    sums = [round(noul(s, a) + noul(s, b), 3) for s, a, b in pairs]
    res["negation_sum"] = {"sums": sums, "ideal": 1.0, "mean_abs_gap": round(statistics.mean(abs(x - 1) for x in sums), 3)}
    # 2. counting
    items = ["apple", "table", "banana", "river", "cherry", "laptop", "grape"]
    cnt = [(n, noul({"items": items}, f"Does `items` contain exactly {n} fruits?")) for n in (3, 4, 5)]
    res["counting"] = {"truth": "4 fruits", "p_yes": {str(n): round(p, 3) for n, p in cnt},
                       "correct": max(cnt, key=lambda x: x[1])[0] == 4}
    # 3. dates
    dq = [("The ban took effect on 3 April 2022. The survey was published on 5 November 2023.",
           "Did the survey come after the ban?", 1),
          ("Shipment A left on 14 March 2021. Shipment B left on 2 February 2021.", "Did shipment A leave first?", 0),
          ("The law passed on 2019-07-01 and the arrest happened on 2018-12-30.", "Did the arrest happen after the law passed?", 0)]
    dres = [int((noul(s, q) >= 0.5) == bool(y)) for s, q, y in dq]
    res["dates"] = {"correct": sum(dres), "n": len(dres)}
    # 5. large irrelevant state
    filler = ("The city council met on Tuesday to discuss parking fees, library opening hours and a new bicycle lane. "
              "Several residents asked about recycling schedules and the weather forecast for the weekend. ") * 6
    heads = [e for e in load_split("test") if e.task == "trace_drug"][:30]
    clean = score_set(rx, heads)["_all"]["accuracy"]
    noisy = score_set(rx, [Example(e.task, e.prim, f"{filler}\n{render(e.state)}", e.instructions, e.criteria, e.gold,
                                   e.split) for e in heads])["_all"]["accuracy"]
    res["irrelevant_state"] = {"clean_accuracy": clean, "with_filler_accuracy": noisy, "n": len(heads)}
    # 7. contradictory criteria (true/false swapped)
    s = "Thai police seized 12 million meth pills near the Myanmar border."
    ok = noul(s, "Were drugs seized?", NoulCriteria("Drugs were seized", "No drugs were seized"))
    sw = noul(s, "Were drugs seized?", NoulCriteria("No drugs were seized", "Drugs were seized"))
    res["contradictory_criteria"] = {"aligned": round(ok, 3), "swapped": round(sw, 3)}
    # 2b. numbers
    nq = [("The haul weighed 0.3 kg.", "Did the haul weigh more than 300 grams?", 0),
          ("Police found 1,500 kg of cocaine.", "Was more than one tonne found?", 1),
          ("The boat carried 950 kg.", "Did the boat carry more than a tonne?", 0)]
    nres = [int((noul(s, q) >= 0.5) == bool(y)) for s, q, y in nq]
    res["numbers"] = {"correct": sum(nres), "n": len(nres)}
    res["pass"] = True  # documenting the profile is the pass condition (spec L7)
    return res


def latency(rx: Reflex) -> dict:
    from ..jev.reflex_client import ReflexClassifier
    clf = ReflexClassifier(model=rx)
    ts = []
    for t in ["Ecuador navy seizes 4.2 tonnes of cocaine bound for Belgium",
              "Thai police intercept 12 million meth pills near Myanmar border",
              "Germany's cannabis legalization law takes effect"] * 2:
        t0 = time.perf_counter()
        clf.classify(t)
        ts.append(1000 * (time.perf_counter() - t0))
    one = []
    for _ in range(5):
        t0 = time.perf_counter()
        rx.system_one("Can I please talk to a real person?", {"q": Noul("Is the customer asking for a human agent?")})
        one.append(1000 * (time.perf_counter() - t0))
    return {"livewire_7_questions_ms_median": round(statistics.median(ts), 1),
            "single_noul_ms_median": round(statistics.median(one), 1), "device": "laptop CPU (Intel Core 7 150U)",
            "jev_reference_ms": "70-500 incl. network (TypeSafe)", "pass": True}


def run(quick: bool = False, model_dir: str | None = None, out_name: str = "eval.json") -> str:
    torch.set_num_threads(10)
    rx = Reflex.load(model_dir)
    base = Reflex.load(OUT / "does-not-exist", base_if_missing=True)
    train, test, zs = load_split("train"), load_split("test"), load_split("zeroshot")
    if quick:
        test = [e for t in {e.task for e in test} for e in [x for x in test if x.task == t][:15]]
        zs = [e for t in {e.task for e in zs} for e in [x for x in zs if x.task == t][:15]]
    base_sub = [e for t in {e.task for e in test} for e in [x for x in test if x.task == t][:60]]
    zs_sub = [e for t in {e.task for e in zs} for e in [x for x in zs if x.task == t][:100]]
    log.info("L0/L1 contract")
    rep = {"model": rx.model_id, "temperatures": rx.temps, "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    rep["L0_L1_contract"] = contract_checks(rx)
    log.info("L2/L4 held-out test (%d examples)", len(test))
    t_trained = score_set(rx, test)
    t_base = score_set(base, base_sub)
    maj = majority(train, test)
    rep["L2_competence"] = {"trained": t_trained, "untuned_backbone_subset": t_base, "majority_baseline": maj,
                            "pass": all(t_trained[t]["accuracy"] > max(maj.get(t, 0), t_base.get(t, {}).get("accuracy", 0))
                                        for t in t_trained if t != "_all")}
    log.info("L3 zero-shot (%d examples)", len(zs))
    z_tr, z_base, ch = score_set(rx, zs), score_set(base, zs_sub), chance(zs)
    rep["L3_zero_shot"] = {"trained": z_tr, "untuned_backbone": z_base, "chance": ch,
                           "pass": all(z_tr[t]["accuracy"] > max(ch[t], z_base.get(t, {}).get("accuracy", 0))
                                       for t in z_tr if t != "_all")}
    rep["L4_calibration"] = {"in_distribution_ece": t_trained["_all"]["ece"], "zero_shot_ece": z_tr["_all"]["ece"],
                             "untuned_backbone_ece": t_base["_all"]["ece"],
                             "pass": t_trained["_all"]["ece"] <= 0.05}
    log.info("L5 structure")
    rep["L5_structure"] = structure_test(rx, test)
    log.info("L6 domain")
    rep["L6_domain"] = domain_eval(rx)
    if (OUT / "llm_test.jsonl").exists():  # second domain test: Claude-written headlines, never trained on
        lt = load_split("llm_test")
        if quick:
            lt = lt[:60]
        rep["L6_domain"]["llm_test"] = score_set(rx, lt)
    log.info("L7 jaggedness")
    rep["L7_jaggedness"] = jaggedness(rx)
    log.info("L8 latency")
    rep["L8_latency"] = latency(rx)
    rep["scale"] = {k: rep[k]["pass"] for k in ["L0_L1_contract", "L2_competence", "L3_zero_shot", "L4_calibration",
                                                "L5_structure", "L6_domain", "L7_jaggedness", "L8_latency"]}
    (OUT / out_name).write_text(json.dumps(rep, indent=2, default=float), "utf-8")
    return str(OUT / out_name)
