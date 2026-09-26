<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# data/

Everything here except this README is gitignored and reproducible: `uv run trace pipeline` (reads the SQLite archive in `data_collection/work/`, writes `derived.sqlite`).

- `raw/` downloads (World Bank cache, UNODC, OC Index, HRI, CEPII)
- `processed/` manifests, metrics.json, exported API JSON (`processed/api/`)
- `derived.sqlite` derived model tables (edges, predictions, risk); the canonical data is the archive
