# TRACE People snapshot (generated branch)

Machine-written by `.github/workflows/people-snapshot.yml` on `main`; do not edit by hand.
It republishes `frontend/data/people/manifest.json` from `main` as a sharded, versioned snapshot
(format `trace-people-snapshot/1`). Full description: `docs/PEOPLE_SNAPSHOT.md` on `main`.

- `v1/index.json`: `format`, `version` (sha256 of the canonical manifest JSON), `generated_at`,
  `source_commit`, `source_path`, `counts`, and `shards` (`kind`, `file`, `sha256`, `bytes`, `records`).
- `v1/shards/<kind>-<sha16>.json.gz`: gzip of `{"kind": ..., "records": [...]}`. Content-addressed and
  immutable. People use 16 shards by `sha256(id) % 16`; organizations and connections use one shard each
  unless one would exceed about 2 MB uncompressed.
- `v1/history.json`: the last five index versions and their shard files. Shards referenced by any of
  them are kept, so a consumer mid-refresh never hits a 404; older shards are deleted.

Records are copied verbatim; the TRACE API validates and normalises them. AI-assisted: written with
Claude Code (Anthropic).
