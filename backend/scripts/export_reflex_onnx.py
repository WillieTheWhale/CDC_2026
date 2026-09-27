# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Export Reflex (the fine-tuned nli-deberta-v3-xsmall cross-encoder) to ONNX for torch-free CPU inference.

    .venv/Scripts/python scripts/export_reflex_onnx.py                 # emb8 (default, the shipped variant)
    .venv/Scripts/python scripts/export_reflex_onnx.py --variant all   # every variant, for scripts/reflex_onnx_parity.py

Needs the reflex extra (torch, transformers) plus `uv pip install onnx onnxruntime`. Reads data/reflex/model and
writes data/reflex/onnx/{model.<variant>.onnx, tokenizer.json, reflex.json}.

Variants (parity with torch: trace_backend/reflex/results/onnx_parity.json):
- fp32      model.onnx           284 MB  exact.
- emb8      model.emb8.onnx      137 MB  DEFAULT. fp32 network; the 128k x 384 word-embedding table (70% of all weights)
                                         stored as int8 with one scale per row and dequantised right after the Gather.
- int8-ffn  model.int8-ffn.onnx   95 MB  emb8 + dynamic int8 (per-channel) feed-forward MatMul weights.
- int8      model.int8.onnx       87 MB  onnxruntime quantize_dynamic on everything (per-tensor). Misses the 99%
                                         top-choice agreement target; kept for comparison.

The graph takes (input_ids, attention_mask) and returns one scalar per pair: logit[entailment] - logit[contradiction],
exactly ReflexNet.forward. Tokenisation, temperature scaling and the confidence formula stay in Python
(trace_backend/reflex/model.py, ReflexOnnx), so both backends share them. reflex.json gains an `onnx` block naming the
default file; `ReflexOnnx` and scripts/build_vercel.py read it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from trace_backend.reflex.model import ONNX_DIR, WEIGHTS_DIR  # noqa: E402

OPSET = 17
FILES = {"fp32": "model.onnx", "emb8": "model.emb8.onnx", "int8-ffn": "model.int8-ffn.onnx", "int8": "model.int8.onnx"}
DEFAULT = "emb8"
QUANT_NOTES = {"fp32": None,
               "emb8": "word embeddings int8 with per-row scales (dequantised after the Gather); network fp32",
               "int8-ffn": "word embeddings int8 per-row; feed-forward MatMul weights dynamic int8 per-channel",
               "int8": "onnxruntime quantize_dynamic, QInt8 per-tensor, all MatMul and Gather weights"}


def export_fp32(src: Path, out: Path) -> Path:
    import torch

    from trace_backend.reflex.model import ReflexNet

    net = ReflexNet(str(src)).eval()
    net.enc.config.return_dict = True

    class Scalar(torch.nn.Module):  # (input_ids, attention_mask) -> entail - contradict, as ReflexNet.forward
        def __init__(self, n):
            super().__init__()
            self.n = n

        def forward(self, input_ids, attention_mask):
            return self.n(input_ids=input_ids, attention_mask=attention_mask)

    ids = torch.tensor([[1, 5365, 447, 2, 7581, 294, 1204, 2], [1, 5365, 2, 7581, 294, 2, 0, 0]], dtype=torch.long)
    mask = (ids != 0).long()
    target = out / FILES["fp32"]
    with torch.no_grad():
        torch.onnx.export(Scalar(net), (ids, mask), str(target), input_names=["input_ids", "attention_mask"],
                          output_names=["score"], opset_version=OPSET, do_constant_folding=True, dynamo=False,
                          dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                        "score": {0: "batch"}})
    return target


def embed_rows_int8(src: Path, target: Path) -> Path:
    """Store the word-embedding table as int8 with one fp32 scale per row: Gather(int8) -> Cast -> Mul(Gather(scale)).
    Every looked-up vector comes back within half a quantisation step (1/254 of its largest component), and the file
    shrinks by about 147 MB."""
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    m = onnx.load(str(src))
    name = next(i.name for i in m.graph.initializer if i.name.endswith("word_embeddings.weight"))
    for init in m.graph.initializer:
        if init.name == name:
            w = numpy_helper.to_array(init)
            scale = np.abs(w).max(axis=1, keepdims=True) / 127.0
            scale[scale == 0] = 1.0
            init.CopyFrom(numpy_helper.from_array(np.clip(np.round(w / scale), -127, 127).astype(np.int8), name))
            m.graph.initializer.append(numpy_helper.from_array(scale.astype(np.float32), name + "_scale"))
            break
    for k, n in enumerate(m.graph.node):
        if n.op_type == "Gather" and n.input[0] == name:
            out, ids = n.output[0], n.input[1]
            n.output[0] = out + "_q"
            for j, node in enumerate([
                    helper.make_node("Cast", [out + "_q"], [out + "_f"], to=TensorProto.FLOAT, name="emb_dq_cast"),
                    helper.make_node("Gather", [name + "_scale", ids], [out + "_s"], axis=0, name="emb_dq_scale"),
                    helper.make_node("Mul", [out + "_f", out + "_s"], [out], name="emb_dq_mul")]):
                m.graph.node.insert(k + 1 + j, node)
            break
    else:
        raise ValueError("word-embedding Gather not found")
    onnx.save(m, str(target))
    return target


def quantize(fp32: Path, target: Path, variant: str) -> Path:
    if variant == "emb8":
        return embed_rows_int8(fp32, target)
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.shape_inference import quant_pre_process

    pre = fp32.with_suffix(".pre.onnx")
    quant_pre_process(str(fp32), str(pre), skip_symbolic_shape=True)
    if variant == "int8":
        quantize_dynamic(str(pre), str(target), weight_type=QuantType.QInt8, per_channel=False)
    else:  # int8-ffn: only the feed-forward weight MatMuls (intermediate.dense, output.dense), per channel
        g = onnx.load(str(pre)).graph
        inits = {i.name for i in g.initializer}
        ffn = [n.name for n in g.node if n.op_type == "MatMul" and n.input[1] in inits
               and ("intermediate/dense" in n.name or ("/output/dense" in n.name and "attention" not in n.name))]
        tmp = fp32.with_suffix(".ffn.onnx")
        quantize_dynamic(str(pre), str(tmp), weight_type=QuantType.QInt8, per_channel=True, nodes_to_quantize=ffn)
        embed_rows_int8(tmp, target)
        tmp.unlink(missing_ok=True)
    pre.unlink(missing_ok=True)
    return target


def externalize(model: Path, stem: str, threshold: int = 1 << 20) -> tuple[Path, list[str]]:
    """Re-save `model` with every tensor over `threshold` bytes as its own ONNX external-data file
    (`<stem>.NNN.bin`, same folder). Weights and outputs are byte-identical; each file stays far below the
    100 MB per-file upload limit of Vercel deploys (the 137 MB emb8 model becomes a 31 MB graph + 25 files <= 49 MB)."""
    import onnx
    from onnx.external_data_helper import convert_model_to_external_data
    for old in model.parent.glob(f"{stem}*"):
        old.unlink()
    m = onnx.load(str(model))
    convert_model_to_external_data(m, all_tensors_to_one_file=False, size_threshold=threshold)
    files: list[str] = []
    for t in m.graph.initializer:
        for e in t.external_data:
            if e.key == "location":
                e.value = f"{stem}.{len(files):03d}.bin"
                files.append(e.value)
    out = model.parent / f"{stem}.onnx"
    onnx.save_model(m, str(out))
    return out, files


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variant", choices=[*FILES, "all"], default=DEFAULT, help=f"{DEFAULT} is the shipped default")
    ap.add_argument("--src", type=Path, default=WEIGHTS_DIR)
    ap.add_argument("--out", type=Path, default=ONNX_DIR)
    a = ap.parse_args(argv)
    if not (a.src / "reflex.json").exists():
        sys.exit(f"no trained Reflex at {a.src}; run `uv run trace reflex-download`")
    a.out.mkdir(parents=True, exist_ok=True)
    variants = list(FILES) if a.variant == "all" else [a.variant]

    t0 = time.perf_counter()
    fp32 = export_fp32(a.src, a.out)
    print(f"exported {fp32.name} ({fp32.stat().st_size / 1e6:.1f} MB, opset {OPSET}) in {time.perf_counter() - t0:.1f}s")
    for v in variants:
        if v != "fp32":
            t = quantize(fp32, a.out / FILES[v], v)
            print(f"wrote {t.name} ({t.stat().st_size / 1e6:.1f} MB)")
    if "fp32" not in variants:
        fp32.unlink()

    shutil.copy(a.src / "tokenizer.json", a.out / "tokenizer.json")
    meta = json.loads((a.src / "reflex.json").read_text(encoding="utf-8"))
    default = DEFAULT if DEFAULT in variants else variants[0]
    meta["onnx"] = {"file": FILES[default], "variant": default, "variants": {v: FILES[v] for v in variants},
                    "opset": OPSET, "inputs": ["input_ids", "attention_mask"],
                    "output": "score = logit[entailment] - logit[contradiction]", "quantization": QUANT_NOTES[default],
                    "exported_from": str(a.src.relative_to(BACKEND)) if a.src.is_relative_to(BACKEND) else str(a.src),
                    "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if default == "emb8":  # ship it as external data so every deployed file is < 100 MB (Vercel upload limit)
        ext, parts = externalize(a.out / FILES["emb8"], "model.emb8x")
        meta["onnx"].update(file=ext.name, external_data=parts,
                            external_data_note="emb8 weights as ONNX external data (each file < 100 MB); identical "
                                               "to model.emb8.onnx")
    (a.out / "reflex.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {a.out} (default {meta['onnx']['file']})")


if __name__ == "__main__":
    main()
