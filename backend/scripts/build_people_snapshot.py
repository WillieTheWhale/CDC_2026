# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Publish the People manifest as a sharded, content-addressed, versioned snapshot (format trace-people-snapshot/1).

    python backend/scripts/build_people_snapshot.py --manifest frontend/data/people/manifest.json --out DIR \
        [--source-commit SHA] [--history PATH]
    python backend/scripts/build_people_snapshot.py --verify DIR --manifest frontend/data/people/manifest.json

Build writes `DIR/shards/<kind>-<sha16>.json.gz` (gzip, mtime 0, of `{"kind": ..., "records": [...]}`), then
`DIR/index.json` (atomically, last), then `DIR/history.json` (the last five index versions and their shard
files), and finally deletes shard files that no remembered version references. A consumer holding any of the last
five indexes can therefore still fetch every shard it names.

The snapshot copies records verbatim; validation and normalisation stay in the API consumer. The only refusals
(exit code 2) are a manifest that does not parse or lacks `people`/`organizations`/`connections` lists.

Deterministic: the same manifest always gives the same `version` and shard file names. If the output directory
already holds an index for the same version and shard list, it is left untouched (so `generated_at` and
`source_commit` do not churn and the publishing workflow commits nothing).

Standard library only; see docs/PEOPLE_SNAPSHOT.md.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "trace-people-snapshot/1"
SOURCE_PATH = "frontend/data/people/manifest.json"
KINDS = ("people", "organizations", "connections")
PEOPLE_SHARDS = 16
MAX_SHARD_UNCOMPRESSED = 2_000_000  # organizations/connections split once a shard would exceed this
MAX_SPLIT = 256
HISTORY_KEEP = 5
SHARD_NAME = re.compile(r"^(people|organizations|connections)-[0-9a-f]{16}\.json\.gz$")

EXIT_OK, EXIT_VERIFY_FAILED, EXIT_REFUSED = 0, 1, 2


class Refusal(Exception):
    """The manifest cannot be published."""


# ----------------------------------------------------------------------------------------------------- helpers
def canonical_bytes(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_key(record) -> str:
    """The id used for bucketing. Records without a string id (the consumer rejects them) hash on their content."""
    if isinstance(record, dict) and isinstance(record.get("id"), str):
        return record["id"]
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def bucket_of(record, n: int) -> int:
    if n == 1:
        return 0
    return int(sha256_hex(record_key(record).encode("utf-8")), 16) % n


def partition(records: list, n: int) -> list[list[tuple[int, object]]]:
    """Buckets of (manifest position, record); manifest order is kept inside each bucket."""
    buckets: list[list] = [[] for _ in range(n)]
    for pos, rec in enumerate(records):
        buckets[bucket_of(rec, n)].append((pos, rec))
    return buckets


def shard_json(kind: str, bucket: list[tuple[int, object]]) -> bytes:
    # Records verbatim (original key order) plus each record's manifest position, so a consumer can rebuild the
    # manifest's exact order (response arrays keep matching the frontend's fixture mode). Compact separators.
    return json.dumps({"kind": kind, "records": [r for _, r in bucket], "positions": [p for p, _ in bucket]},
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def gzip_deterministic(data: bytes) -> bytes:
    # GzipFile with filename "" and mtime 0 writes a fixed header (OS byte 255) on every platform,
    # unlike gzip.compress, which may defer to zlib's platform-specific OS byte.
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, compresslevel=9, mtime=0) as gz:
        gz.write(data)
    return buf.getvalue()


def load_manifest(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Refusal(f"cannot read manifest {path}: {exc}") from exc
    try:
        manifest = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(f"manifest {path} does not parse as UTF-8 JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise Refusal("manifest top level is not a JSON object")
    for kind in KINDS:
        if kind not in manifest:
            raise Refusal(f"manifest is missing '{kind}'")
        if not isinstance(manifest[kind], list):
            raise Refusal(f"manifest '{kind}' is not a list")
    return manifest


def shard_count(kind: str, records: list) -> int:
    if kind == "people":
        return PEOPLE_SHARDS
    n = 1
    while n < MAX_SPLIT:
        if all(len(shard_json(kind, b)) <= MAX_SHARD_UNCOMPRESSED for b in partition(records, n)):
            return n
        n += 1
    return MAX_SPLIT


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def dump_json(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ------------------------------------------------------------------------------------------------------- build
def plan(manifest: dict) -> tuple[str, list[dict], list[tuple[str, bytes]], dict]:
    """Return (version, shard entries, [(file, gz bytes)], stats) without touching disk."""
    version = sha256_hex(canonical_bytes(manifest))
    entries: list[dict] = []
    blobs: list[tuple[str, bytes]] = []
    raw_total = 0
    for kind in KINDS:
        records = manifest[kind]
        for bucket in partition(records, shard_count(kind, records)):
            raw = shard_json(kind, bucket)
            gz = gzip_deterministic(raw)
            digest = sha256_hex(gz)
            name = f"shards/{kind}-{digest[:16]}.json.gz"
            entries.append({"kind": kind, "file": name, "sha256": digest, "bytes": len(gz), "records": len(bucket)})
            blobs.append((name, gz))
            raw_total += len(raw)
    stats = {"uncompressed_bytes": raw_total, "compressed_bytes": sum(e["bytes"] for e in entries)}
    return version, entries, blobs, stats


def build(manifest_path: Path, out: Path, source_commit: str, history_path: Path | None = None,
          now: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    version, entries, blobs, stats = plan(manifest)
    out.mkdir(parents=True, exist_ok=True)
    history_path = history_path or out / "history.json"

    # 1. Shards (content-addressed: an existing file with the right name and hash is already correct).
    for name, gz in blobs:
        target = out / name
        if target.exists() and sha256_hex(target.read_bytes()) == sha256_hex(gz):
            continue
        write_atomic(target, gz)

    # 2. Index, written last among the data files; untouched when nothing changed.
    previous = read_json(out / "index.json")
    unchanged = (isinstance(previous, dict) and previous.get("format") == FORMAT
                 and previous.get("version") == version and previous.get("shards") == entries)
    if unchanged:
        index = previous
    else:
        index = {
            "format": FORMAT,
            "version": version,
            "generated_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_commit": source_commit,
            "source_path": SOURCE_PATH,
            "counts": {kind: len(manifest[kind]) for kind in KINDS},
            "shards": entries,
        }
        write_atomic(out / "index.json", dump_json(index))

    # 3. History: newest first, at most HISTORY_KEEP distinct (version, shard list) entries.
    history = read_json(history_path)
    history = [h for h in history if isinstance(h, dict)] if isinstance(history, list) else []
    files = [e["file"] for e in entries]
    current = {"version": index["version"], "generated_at": index["generated_at"],
               "source_commit": index["source_commit"], "shards": files}
    rest = [h for h in history if not (h.get("version") == version and h.get("shards") == files)]
    history = [current, *rest][:HISTORY_KEEP]
    write_atomic(history_path, dump_json(history))

    # 4. Prune shards no remembered version references.
    keep = {f for h in history for f in h.get("shards", []) if isinstance(f, str)}
    pruned = []
    shard_dir = out / "shards"
    for path in sorted(shard_dir.iterdir()) if shard_dir.is_dir() else []:
        rel = f"shards/{path.name}"
        if SHARD_NAME.match(path.name) and rel not in keep:
            path.unlink()
            pruned.append(rel)
    return {"version": version, "changed": not unchanged, "index": index, "pruned": pruned, **stats}


# ------------------------------------------------------------------------------------------------------ verify
def verify(out: Path, manifest_path: Path) -> list[str]:
    """Return a list of problems (empty means the snapshot at `out` faithfully publishes the manifest)."""
    problems: list[str] = []
    index = read_json(out / "index.json")
    if not isinstance(index, dict):
        return [f"{out / 'index.json'} missing or not a JSON object"]
    manifest = load_manifest(manifest_path)
    if index.get("format") != FORMAT:
        problems.append(f"format is {index.get('format')!r}, expected {FORMAT!r}")
    expected_version = sha256_hex(canonical_bytes(manifest))
    if index.get("version") != expected_version:
        problems.append(f"version {index.get('version')} != manifest sha256 {expected_version}")
    shards = index.get("shards")
    if not isinstance(shards, list) or not shards:
        return problems + ["index has no shards"]

    got: dict[str, list[list]] = {kind: [] for kind in KINDS}
    for entry in shards:
        name = entry.get("file", "")
        kind = entry.get("kind")
        path = out / name
        if kind not in KINDS:
            problems.append(f"{name}: unknown kind {kind!r}")
            continue
        if not path.is_file():
            problems.append(f"{name}: missing")
            continue
        gz = path.read_bytes()
        digest = sha256_hex(gz)
        if digest != entry.get("sha256"):
            problems.append(f"{name}: sha256 {digest} != index {entry.get('sha256')}")
        if name != f"shards/{kind}-{digest[:16]}.json.gz":
            problems.append(f"{name}: file name does not match its content hash")
        if len(gz) != entry.get("bytes"):
            problems.append(f"{name}: {len(gz)} bytes != index {entry.get('bytes')}")
        try:
            body = json.loads(gzip.decompress(gz).decode("utf-8"))
        except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"{name}: unreadable ({exc})")
            continue
        records = body.get("records") if isinstance(body, dict) else None
        if not isinstance(records, list) or body.get("kind") != kind:
            problems.append(f"{name}: body kind/records malformed")
            continue
        if len(records) != entry.get("records"):
            problems.append(f"{name}: {len(records)} records != index {entry.get('records')}")
        positions = body.get("positions")
        if not isinstance(positions, list) or len(positions) != len(records):
            problems.append(f"{name}: positions missing or not one per record")
            continue
        got[kind].append(list(zip(positions, records)))

    counts = index.get("counts") or {}
    for kind in KINDS:
        expected = manifest[kind]
        if counts.get(kind) != len(expected):
            problems.append(f"counts.{kind} {counts.get(kind)} != manifest {len(expected)}")
        # Union check, order-aware: re-bucketing the manifest with this kind's shard count must reproduce
        # each shard exactly (same records, same manifest positions, manifest order within the shard).
        n = len(got[kind])
        if n == 0:
            problems.append(f"no {kind} shards")
            continue
        want = partition(expected, n)
        by_bucket = {}
        for records in got[kind]:
            b = bucket_of(records[0][1], n) if records else None
            if b is not None:
                by_bucket.setdefault(b, []).append(records)
        for b, bucket in enumerate(want):
            have = by_bucket.get(b, [])
            if bucket and (len(have) != 1 or have[0] != bucket):
                problems.append(f"{kind} bucket {b}/{n}: shard records differ from the manifest")
        union = sum(len(r) for r in got[kind])
        if union != len(expected):
            problems.append(f"{kind}: shards hold {union} records, manifest has {len(expected)}")
    return problems


# --------------------------------------------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", type=Path, required=True, help="People manifest JSON")
    ap.add_argument("--out", type=Path, help="snapshot directory to write (the branch's v1/)")
    ap.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", "unknown"),
                    help="main commit the manifest came from")
    ap.add_argument("--history", type=Path, help="history file (default OUT/history.json)")
    ap.add_argument("--verify", type=Path, metavar="DIR", help="verify an existing snapshot against --manifest")
    args = ap.parse_args(argv)

    try:
        if args.verify:
            problems = verify(args.verify, args.manifest)
            if problems:
                for p in problems:
                    print(f"FAIL {p}", file=sys.stderr)
                return EXIT_VERIFY_FAILED
            index = read_json(args.verify / "index.json")
            print(f"OK {index['version'][:12]}: {len(index['shards'])} shards, counts {index['counts']}")
            return EXIT_OK
        if not args.out:
            ap.error("--out is required unless --verify is given")
        result = build(args.manifest, args.out, args.source_commit, args.history)
    except Refusal as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return EXIT_REFUSED

    index = result["index"]
    print(json.dumps({
        "version": result["version"],
        "changed": result["changed"],
        "counts": index["counts"],
        "shards": len(index["shards"]),
        "compressed_bytes": result["compressed_bytes"],
        "uncompressed_bytes": result["uncompressed_bytes"],
        "pruned": result["pruned"],
    }, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
