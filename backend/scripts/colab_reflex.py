# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Train and evaluate Reflex v0.1 and v0.2 on a Colab GPU (run remotely with the Colab CLI).

Local side (WSL):
    colab new -s reflex --gpu T4
    colab upload -s reflex reflex_bundle.tar.gz /content/reflex_bundle.tar.gz
    colab exec -s reflex -f backend/scripts/colab_reflex.py
    colab download -s reflex /content/reflex_out.tar.gz reflex_out.tar.gz
    colab stop -s reflex

The bundle holds the backend package, contracts/, and the prepared jsonl splits (no raw data, no secrets).
Stages can be skipped by setting REFLEX_STAGES (default "v1,v2,eval").
"""
import os
import subprocess
import sys
import tarfile
import time

ROOT = "/content/CDC_2026"
t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:7.1f}s] {msg}", flush=True)


if not os.path.exists(ROOT):
    log("unpacking bundle")
    with tarfile.open("/content/reflex_bundle.tar.gz") as tf:
        tf.extractall("/content")
log("installing packages")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "python-dotenv", "sentencepiece", "protobuf",
                "fastapi", "jsonschema", "pyyaml", "transformers>=4.45", "apscheduler<4"], check=True)
sys.path.insert(0, f"{ROOT}/backend")
os.environ["HF_HOME"] = "/content/hf"
os.environ["TRACE_CLASSIFIER"] = "mock"
os.environ["TRACE_LIVEWIRE_POLL"] = "0"

import logging  # noqa: E402

import torch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", force=True)
log(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")

from trace_backend.reflex import evaluate, train  # noqa: E402
from trace_backend.reflex.data import OUT  # noqa: E402

stages = os.environ.get("REFLEX_STAGES", "v1,v2,eval").split(",")
v1, v2 = str(OUT / "model_v0.1"), str(OUT / "model_v0.2")
if "v1" in stages:
    log("training Reflex v0.1 (open datasets + UNODC-record headlines, from the NLI backbone)")
    log(train.run(max_pairs=64, lr=5e-5, model_id="reflex-0.1.0", out_dir=v1))
if "v2" in stages:
    log("training Reflex v0.2 (continue from v0.1 on Claude-written headlines + replay of v0.1 data)")
    log(train.run(init_from=v1, train_splits=("llm_train",), val_splits=("val", "llm_val"),
                  replay={"train": 4000}, max_pairs=64, lr=3e-5, model_id="reflex-0.2.0", out_dir=v2))
if "eval" in stages:
    for tag, path in (("v0.1", v1), ("v0.2", v2)):
        log(f"evaluating {tag} (full Reflex Parity Scale)")
        log(evaluate.run(model_dir=path, out_name=f"eval_{tag}.json"))
log("packing results")
with tarfile.open("/content/reflex_out.tar.gz", "w:gz") as tf:
    for name in ("eval_v0.1.json", "eval_v0.2.json", "train_log.jsonl"):
        if (OUT / name).exists():
            tf.add(OUT / name, arcname=name)
    for d in ("model_v0.1", "model_v0.2"):
        if (OUT / d).exists():
            tf.add(OUT / d, arcname=d)
log("done")
