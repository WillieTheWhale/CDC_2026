# data/

Everything here except this README is gitignored and reproducible: `uv run trace pipeline`.

- `raw/` downloads (World Bank cache, UNODC, OC Index, HRI, CEPII)
- `processed/` manifests, metrics.json, exported API JSON (`processed/api/`)
- `trace.duckdb` the single local database
