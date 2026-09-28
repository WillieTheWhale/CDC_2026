# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Native-library shims, run lazily right before the heavy model stack is imported.

LightGBM needs libgomp.so.1, which Vercel's Python runtime lacks. `preload_libgomp()` is called by the simulator
(api/simulate.py) just before lightgbm is first imported, so the read-only endpoints never pay for it. It used to run
unconditionally in the Vercel entrypoint (scripts/build_vercel.py APP).
"""
from __future__ import annotations

import sys

_done = False


def preload_libgomp() -> None:
    """scikit-learn's wheel vendors libgomp under a hashed soname; copy it to /tmp with the soname rewritten to
    libgomp.so.1 (same length, NUL-padded) and load it globally so lib_lightgbm.so resolves against it.
    No-op off Linux, when a system libgomp.so.1 exists, or after the first call."""
    global _done
    if _done or not sys.platform.startswith("linux"):
        return
    import ctypes
    import glob
    import importlib.util
    from pathlib import Path

    try:
        ctypes.CDLL("libgomp.so.1")
        _done = True
        return
    except OSError:
        pass
    spec = importlib.util.find_spec("sklearn")
    if spec is None or spec.origin is None:
        return  # nothing to borrow; lightgbm's own import error will say what is missing
    libs = Path(spec.origin).parents[1] / "scikit_learn.libs"
    found = sorted(glob.glob(str(libs / "libgomp-*.so*")))
    if not found:
        return
    src = Path(found[0])
    old = src.name.encode()
    data = src.read_bytes().replace(old + b"\0", b"libgomp.so.1".ljust(len(old) + 1, b"\0"))
    dst = Path("/tmp/trace_gomp/libgomp.so.1")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    ctypes.CDLL(str(dst), mode=ctypes.RTLD_GLOBAL)
    _done = True
