<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# People snapshot (`trace-people-snapshot/1`)

Answers the "People snapshot scaling and search parity" request in `docs/CONTRACT_REQUESTS.md` (storage half).
The People manifest (`frontend/data/people/manifest.json`, committed by the frontend team via
`frontend/scripts/aggregate-people.mjs`) is republished as a sharded, content-addressed, versioned snapshot so the
API refreshes only what changed instead of re-downloading about 10 MB of raw JSON.

## Format

Base URL: `https://raw.githubusercontent.com/WillieTheWhale/CDC_2026/people-snapshot/v1/`
(branch `people-snapshot`, directory `v1/`; the branch is machine-written, never edit it by hand).

- **`index.json`** (plain UTF-8 JSON):
  `format` (`"trace-people-snapshot/1"`), `version` (sha256 hex of the canonical manifest bytes,
  `json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`), `generated_at`
  (ISO UTC), `source_commit` (the `main` commit the manifest came from), `source_path`, `counts`
  (`people`, `organizations`, `connections`), and `shards`: a list of
  `{"kind", "file": "shards/<kind>-<sha16>.json.gz", "sha256", "bytes", "records"}`.
- **Shards**: gzip (mtime 0) of `{"kind": ..., "records": [...]}`. People go into exactly 16 shards by
  `int(sha256(id).hexdigest(), 16) % 16`; organizations and connections use one shard each, split with the same
  id-hash scheme only if a shard would exceed about 2 MB uncompressed. Records are copied verbatim and keep manifest
  order within a shard. The file name carries the first 16 hex of the gzip bytes' sha256, so shards are immutable.
- **`history.json`**: the last five index versions, newest first, each with its shard file list. Every shard any
  of them references is kept; older unreferenced shards are deleted, so a consumer mid-refresh never hits a 404.

At 3,099 people the snapshot is 18 shards, about 0.9 MB gzipped (7.8 MB uncompressed); people shards are about
50 to 63 KB each. Editing one person changes one people shard (about 55 KB to download).

## Publisher

- `backend/scripts/build_people_snapshot.py` (standard library only):
  `--manifest PATH --out DIR [--source-commit SHA] [--history PATH]` builds; `--verify DIR --manifest PATH` checks
  every shard's sha256, byte size, record count and name, and that the shards reproduce the manifest exactly.
  Deterministic: the same manifest gives the same version and shard names, and an unchanged manifest leaves
  `index.json` byte-identical. It refuses (exit 2) a manifest that does not parse or lacks the three lists; it
  does not validate records (the consumer does). Tests: `backend/tests/test_people_snapshot_build.py`.
- `.github/workflows/people-snapshot.yml` runs on pushes to `main` that touch the manifest, the script or the
  workflow, and on demand. It tests the script, checks out `people-snapshot` in a worktree (creating it as an
  orphan branch with a README on first run), builds into `v1/`, verifies, and commits
  `people-snapshot <version[:12]> from <sha[:7]>` only if `index.json` changed. It uses only `GITHUB_TOKEN`.
- Manual rebuild: `gh workflow run people-snapshot.yml` (then `gh run watch`).

## Consumer (`backend/trace_backend/api/people.py`)

1. Fetch `index.json` (small; no cache-busting needed beyond raw.githubusercontent's short TTL). If `version`
   equals the one in memory, stop.
2. Fetch only shards whose `file` is not already held (content addressing makes a name match a content match).
3. Check each download's sha256, byte size and record count against the index; check `counts`.
4. Validate and normalise records, build the in-memory store off to the side, then swap it in atomically.
5. On any failure, keep serving the current store; if there is none yet, fall back to the committed/raw manifest
   and then fixtures. Shards from the previous five versions stay published, so a refresh that raced a publish
   can retry against the index it started with.
