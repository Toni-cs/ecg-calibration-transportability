# docs/

Preregistration and governance documents for the study. Reading order:

| File | Role |
|---|---|
| [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md) | Study protocol **v2.1-A1** (English translation): hypotheses, main and secondary endpoints, data splits, statistical analysis plan, the revision log, and the full text of amendment A1 in Appendix A1 |
| [`PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md`](PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md) | Amendment A1: primary endpoint relocation (`decay` to `dECE_OOD`), merged into v2.1-A1 |
| [`PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md`](PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md) | Amendment A2: confirmatory family reduction (156 to 12 hypotheses), with a deviation log |
| [`osf_archive_manifest.json`](osf_archive_manifest.json) | SHA-256 manifest of the working tree as of 2026-09-05T04:19:46Z, taken before amendment A2 |

## Status of the preregistration record

Read this before relying on any file in this directory.

- The protocol and both amendments were authored during the study, and both
  amendments record their own status as a **draft pending public timestamping**.
  They are not yet part of a publicly registrable record.
- `osf_archive_manifest.json` is a **local snapshot**, not a verification tool:
  none of its 14 entries currently matches the files in this repository, because
  the documents and code were revised after the snapshot was taken. For 7 of the
  14 entries the frozen content can no longer be recovered from the version
  history of either this repository or the working repository. The manifest
  records intent and timing; it does not prove that any file here is unchanged.
- These documents were authored in Chinese and are provided here in English
  translation. The Chinese originals are the record of authority; they are not
  included in this repository.
- The manuscript discloses this under "Pre-registration archival status". The
  protocol, both amendments, and a per-file archival-status report are being
  deposited under a public OSF timestamp before publication.

The code in `scripts/` and `src/` implements the protocol's analysis plan; the
split export tool (`scripts/export_splits.py`) documents the exact as-used data
partitions cross-validated against the dataset builders.
