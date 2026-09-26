<!-- AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md. -->
# v2 SQLite release validation

The [GitHub Actions package run](https://github.com/WillieTheWhale/CDC_2026/actions/runs/36271624698) completed successfully on the standard Ubuntu runner on 2026-09-26. It downloaded and checksum-verified the immutable v1 database, downloaded the four SHA-pinned v2 source shards, extended v1 without changing its original tables, checked SQLite integrity and foreign keys, audited the cross-table evidence constraints, generated `coverage.md`, and wrote the v2 gzip and manifest. The runner then uploaded them to a draft release.

An independent authenticated **remote stream** download of the draft asset verified both the compressed and decompressed SHA-256 values without allocating a second local database:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `trace.sqlite.gz` | 171,353,116 | `de48417321d404a35764052b8bee7b254298a580de8f7edff617e06c421a5003` |
| decompressed `trace.sqlite` | 1,214,050,304 | `49b5f2df268688dbb58bafff3a6e08a8de51386020723a79df2a0c9199bbe06a` |

The database contains 61 tables and records seven contributing shards in `collection_shards`. The automated audit checked 3,070 research values against 13,300 linked input rows with **zero support-count/publication-year mismatches**, 449 exact-product retail/wholesale ratios, 476 purity-adjusted prices and their valid source observation IDs, 2,316 officially modeled versus 174 country-reported treatment-coverage values, all suppressed CDC rows as NULL, eight cited context claims, and the single prespecified fixed-effects model result. Coarse product-mismatched candidate price ratios are absent from `research_values`.

Local Python tests for the merger, extension, snapshot restore/tamper handling, streaming hashes and evidence-row formulas passed on small fixtures. The GitHub runner also ran the merger tests before packaging. The full v2 file was integrity-checked on the runner and the remote asset was independently hash-checked locally; a second physical 1.2 GB restore was not performed on the workstation because of disk pressure. After release publication, anyone with enough disk can run `python3 data_collection/manage.py download` to obtain a fully checked local copy.

See [the manifest](../snapshot.json), [coverage report](coverage.md), [source reports](../README.md), and [backend drilldown queries](../schema_v2.md). The regression is retrospective and noncausal; UNODC seizure countries are not measured origin/transit/destination routes. Health source age bands, modeled values, CDC provisional rolling periods and suppressed NULLs must retain their labels.
