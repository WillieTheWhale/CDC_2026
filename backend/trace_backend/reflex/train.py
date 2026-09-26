# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Train Reflex (docs/REFLEX_SPEC.md): log-loss over each question's options, then per-primitive temperature scaling.

    uv run trace reflex-data            # build train/val/test/zeroshot jsonl
    uv run trace reflex-train           # train (resumable from checkpoints), calibrate, save
    uv run trace reflex-eval            # Reflex Parity Scale report

Log-loss (cross-entropy) is a strictly proper scoring rule: its expected value is minimised only by the true
probabilities, which is the calibration objective TypeSafe describes (RLCD itself is unpublished). A temperature per
primitive is then fitted on the validation split to remove residual over- or under-confidence.
"""
from __future__ import annotations

import json
import logging
import math
import random
import time

import torch
from transformers import AutoTokenizer

from .data import OUT, Example, load_split
from .model import BASE, MAX_LEN, Reflex, ReflexNet
from .types import option_hypotheses, render_state

log = logging.getLogger(__name__)
CKPT = OUT / "ckpt.pt"
LOG = OUT / "train_log.jsonl"
TRAIN_MAX_LEN = 128           # CPU budget: headlines and truncated passages fit; inference uses MAX_LEN
TRAIN_CHOICE_K = 4            # sample negatives: gold + 3 others per Choice during training (standard practice)


def pairs_of(e: Example, rng: random.Random | None = None, k_max: int | None = None):
    q = e.question()
    keys, hyps = option_hypotheses(q)
    idx = list(range(len(hyps)))
    if k_max and e.prim == "choice" and len(idx) > k_max and rng is not None:
        others = [i for i in idx if i != e.gold]
        idx = sorted([e.gold] + rng.sample(others, k_max - 1))
    st = render_state(e.state)
    return [(st, hyps[i]) for i in idx], idx.index(e.gold)


def batches(examples, rng, max_pairs=24):
    cur, n = [], 0
    for e in examples:
        p, g = pairs_of(e, rng, TRAIN_CHOICE_K)
        if cur and n + len(p) > max_pairs:
            yield cur
            cur, n = [], 0
        cur.append((e, p, g))
        n += len(p)
    if cur:
        yield cur


def step_loss(net, tok, batch, max_len=TRAIN_MAX_LEN):
    flat = [pp for _, p, _ in batch for pp in p]
    enc = tok([a for a, _ in flat], [b for _, b in flat], truncation="only_first", max_length=max_len,
              padding=True, return_tensors="pt")
    s = net(**enc)
    loss, i = 0.0, 0
    for _, p, g in batch:
        seg = s[i:i + len(p)]
        loss = loss + torch.nn.functional.cross_entropy(seg.unsqueeze(0), torch.tensor([g]))
        i += len(p)
    return loss / len(batch), len(flat)


def fit_temperatures(rx: Reflex, val: list[Example]) -> dict[str, float]:
    """One temperature per primitive, minimising validation NLL (grid + refinement over log T)."""
    by = {}
    for e in val:
        q = e.question()
        by.setdefault(e.prim, []).append((torch.tensor(rx.logits_for(e.state, q)), e.gold))
    temps = {}
    for prim, rows in by.items():
        def nll(t, rows=rows):
            return sum(-torch.log_softmax(s / t, 0)[g].item() for s, g in rows) / len(rows)
        grid = [math.exp(x / 10) for x in range(-12, 25)]
        best = min(grid, key=nll)
        for _ in range(2):
            grid = [best * math.exp(x / 50) for x in range(-5, 6)]
            best = min(grid, key=nll)
        temps[prim] = round(best, 4)
        log.info("temperature %-6s T=%.3f  val NLL %.4f -> %.4f", prim, best, nll(1.0), nll(best))
    return temps


def run(epochs: int = 1, lr: float = 3e-5, max_pairs: int = 24, seed: int = 7, limit: int | None = None,
        init_from: str | None = None, train_splits: tuple[str, ...] = ("train",), val_splits: tuple[str, ...] = ("val",),
        replay: dict[str, int] | None = None, q_per_headline: int | None = None,
        model_id: str = "reflex-0.1.0", out_dir: str | None = None) -> dict:
    """Train from the NLI backbone (v0.1) or continue from saved Reflex weights (`init_from`, v0.2).

    `replay` = {split: n} mixes n random examples of an earlier split back in (limits forgetting).
    `q_per_headline` keeps a random subset of the questions per headline for llm_* splits (CPU budget).
    """
    torch.manual_seed(seed)
    torch.set_num_threads(10)
    rng = random.Random(seed)
    train = [e for sp in train_splits for e in load_split(sp)]
    if q_per_headline:
        by = {}
        for e in train:
            key = json.dumps(e.state, sort_keys=True) if e.task.startswith("llm_") else id(e)
            by.setdefault(key, []).append(e)
        train = [e for g in by.values() for e in (rng.sample(g, min(q_per_headline, len(g)))
                                                    if g[0].task.startswith("llm_") else g)]
    for sp, n in (replay or {}).items():
        pool = load_split(sp)
        train += rng.sample(pool, min(n, len(pool)))
    if limit:
        train = train[:limit]
    val = [e for sp in val_splits for e in load_split(sp)]
    if limit:
        val = val[:limit]
    src = init_from or BASE
    tok = AutoTokenizer.from_pretrained(src)
    net = ReflexNet(src)
    for p in net.enc.deberta.embeddings.parameters():  # 49M-param embedding table frozen (CPU budget)
        p.requires_grad = False
    params = [p for p in net.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=0.01)
    order = []
    for ep in range(epochs):
        ex = list(train)
        random.Random(seed + ep).shuffle(ex)
        order.append(list(batches(ex, random.Random(seed + 100 + ep), max_pairs)))
    total = sum(len(o) for o in order)
    warm = max(1, int(0.05 * total))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min((s + 1) / warm, max(0.0, (total - s) / max(1, total - warm))))
    start = 0
    if CKPT.exists():
        ck = torch.load(CKPT, weights_only=False)
        if ck.get("total") == total:
            net.load_state_dict(ck["net"])
            opt.load_state_dict(ck["opt"])
            sched.load_state_dict(ck["sched"])
            start = ck["step"]
            log.info("resumed from step %d/%d", start, total)
    net.train()
    t0, pairs_done, step = time.time(), 0, 0
    for batch in (b for o in order for b in o):
        if step < start:
            step += 1
            continue
        loss, n = step_loss(net, tok, batch)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        sched.step()
        step += 1
        pairs_done += n
        if step % 20 == 0 or step == total:
            el = time.time() - t0
            rate = pairs_done / el
            rec = {"step": step, "total": total, "loss": round(loss.item(), 4), "pairs_per_s": round(rate, 2),
                   "eta_min": round((total - step) * (el / max(1, step - start)) / 60, 1), "lr": sched.get_last_lr()[0]}
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            log.info("step %d/%d loss %.4f %.2f pairs/s eta %.0f min", step, total, rec["loss"], rate, rec["eta_min"])
        if step % 300 == 0:
            torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "step": step,
                        "total": total}, CKPT)
    net.eval()
    rx = Reflex(net, tok, model_id=model_id)
    temps = fit_temperatures(rx, val)
    rx.temps = temps
    meta = {"trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "train_examples": len(train), "steps": total,
            "init_from": "cross-encoder/nli-deberta-v3-xsmall" if not init_from else str(init_from),
            "train_splits": list(train_splits), "replay": replay or {}, "q_per_headline": q_per_headline,
            "epochs": epochs, "lr": lr, "train_max_len": TRAIN_MAX_LEN, "train_choice_k": TRAIN_CHOICE_K,
            "frozen": "embeddings", "objective": "per-question softmax cross-entropy (log-loss) + temperature scaling"}
    path = rx.save(out_dir, extra={"training": meta})
    CKPT.unlink(missing_ok=True)
    log.info("saved Reflex to %s (temperatures %s)", path, temps)
    return {"path": str(path), "temperatures": temps, **meta}


__all__ = ["run", "fit_temperatures", "pairs_of", "MAX_LEN"]
