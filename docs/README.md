# docs/

Preregistration and governance documents for the study. Reading order:

| File | Role |
|---|---|
| [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md) | Preregistered study protocol, v2.0: hypotheses, main/secondary endpoints, data splits, statistical analysis plan, and the registered revision log |
| [`PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md`](PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md) | Registered amendment A1: relocation of the preregistration archive (hash manifest) |
| [`PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md`](PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md) | Registered amendment A2: endpoint family reduction, with a deviation log |
| [`osf_archive_manifest.json`](osf_archive_manifest.json) | SHA-256 hash manifest of the preregistration bundle, as registered for archival |

Notes:

- Amendments are numbered in registration order; both are part of the preregistered record and predate the final analysis.
- These documents were authored in Chinese and are provided here in English translation. The Chinese originals are the preregistered record of authority; their integrity is anchored by the SHA-256 hashes in [`osf_archive_manifest.json`](osf_archive_manifest.json).
- The code in `scripts/` and `src/` implements the protocol's registered analysis plan; the split export tool (`scripts/export_splits.py`) documents the exact as-used data partitions cross-validated against the dataset builders.
