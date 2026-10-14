# Supplementary material

Manuscript: *When Does Temperature Scaling Pay Off in Cross-Corpus ECG
Transfer? A Multi-Seed Calibration Boundary Study*

Target journal: Computer Methods and Programs in Biomedicine (Elsevier).

> **Note on `S1_protocol/`.** The protocol documents are byte-identical copies
> of the versions archived at OSF (DOI `10.17605/OSF.IO/53H64`, sha256
> `0e8afa92…`). They are reproduced verbatim so that the pre-registered text
> can be checked against what was actually run, and they are therefore *not*
> updated when the manuscript's wording changes. In particular they describe
> the third corpus as "CPSC2018+2019" and name a different target journal;
> both are superseded by amendment A3 and by this submission respectively.
> The corrections are recorded in `S1_protocol/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md`.

> **Note on the encoding-paired tables in `S2_result_tables/`.** Between
> 2026-09-09 and 2026-09-16 the CPSC sub-space label encoding changed from
> `(NORM, CD, STTC, MI)` to `(NORM, MI, STTC, CD)`, which is exactly a
> 1↔3 swap. Two result tables were regenerated afterwards and are shipped
> **alongside** their original, wrong-encoding versions so that the
> difference is auditable rather than hidden:
>
> | file | status |
> |---|---|
> | `ablation_ts_components.csv` | **original (wrong encoding)** — retained for audit |
> | `ablation_ts_components.OLD_ENCODING.csv` | **authoritative** — label-restored ablation table; its `raw` stage supplies the paper's raw-ECE range (`0.036`–`0.357`, mean `0.211`) |
> | `discrimination_metrics_60exp.csv` | **original (wrong encoding)** — retained for audit |
> | `discrimination_metrics_60exp.OLD_ENCODING.csv` | **authoritative** — carries `variant=raw` **and** `variant=ts` rows; source of the paper's mean/max ΔAUROC_TS−raw |
>
> Where the two disagree, the `.OLD_ENCODING.csv` file is the one the
> manuscript cites. `raw` rows of the discrimination pair are bit-identical
> between the two releases' schemas only in the `.OLD_ENCODING` version.

## Contents

> **Scope updates (2026-10-11/12 regeneration + review closing).** New entries
> in `S2_result_tables/`:
> `robustness_val_8method_perbranch_recheck.csv` (per-branch correctness
> recheck of the delivered 8-method table — read
> `results/_EIGHT_METHOD_SEMANTICS_NOTICE.md` in the repository before
> quoting non-`ts` rows),
> `deployment_780grid_recompute.csv` (the manuscript's deployment
> sensitivity/specificity and lookup-table rows recomputed on the delivered
> 780-cell grid), plus the refreshed `real_prior_recovery_summary.json`
> (generator reconstructed in the repository; pair-cluster CI fields are
> intentionally `null` from the table alone).
>
> `S2_result_tables/archive_pre_retrain/` holds the three pre-retrain
> decomposition legacy tables **kept for provenance only** — do not quote
> them as current readouts (see its README and the repository's
> `results/archive/README.md`). `S0_manuscript/` carries the compiled PDFs.

| Folder | Contents | Files |
|---|---|---|
| `S0_manuscript/` | the compiled manuscript PDF, supplementary PDF, cover-letter PDF (latest regeneration wave) | 3 |
| `S1_protocol/` | see below | 6 |
| `S2_result_tables/` | see below | 47 |
| `S3_per_experiment/chapman_cpsc/inceptiontime/seed42/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/inceptiontime/seed43/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/inceptiontime/seed44/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/inceptiontime/seed45/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/inceptiontime/seed46/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/resnet1d/seed42/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/resnet1d/seed43/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/resnet1d/seed44/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/resnet1d/seed45/` | see below | 1 |
| `S3_per_experiment/chapman_cpsc/resnet1d/seed46/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/inceptiontime/seed42/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/inceptiontime/seed43/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/inceptiontime/seed44/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/inceptiontime/seed45/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/inceptiontime/seed46/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/resnet1d/seed42/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/resnet1d/seed43/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/resnet1d/seed44/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/resnet1d/seed45/` | see below | 1 |
| `S3_per_experiment/chapman_ptbxl/resnet1d/seed46/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/inceptiontime/seed42/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/inceptiontime/seed43/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/inceptiontime/seed44/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/inceptiontime/seed45/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/inceptiontime/seed46/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/resnet1d/seed42/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/resnet1d/seed43/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/resnet1d/seed44/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/resnet1d/seed45/` | see below | 1 |
| `S3_per_experiment/cpsc_chapman/resnet1d/seed46/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/inceptiontime/seed42/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/inceptiontime/seed43/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/inceptiontime/seed44/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/inceptiontime/seed45/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/inceptiontime/seed46/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/resnet1d/seed42/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/resnet1d/seed43/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/resnet1d/seed44/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/resnet1d/seed45/` | see below | 1 |
| `S3_per_experiment/cpsc_ptbxl/resnet1d/seed46/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/inceptiontime/seed42/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/inceptiontime/seed43/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/inceptiontime/seed44/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/inceptiontime/seed45/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/inceptiontime/seed46/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/mamba/seed42/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/mamba/seed43/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/resnet1d/seed42/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/resnet1d/seed43/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/resnet1d/seed44/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/resnet1d/seed45/` | see below | 1 |
| `S3_per_experiment/ptbxl_chapman/resnet1d/seed46/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/inceptiontime/seed42/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/inceptiontime/seed43/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/inceptiontime/seed44/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/inceptiontime/seed45/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/inceptiontime/seed46/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/resnet1d/seed42/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/resnet1d/seed43/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/resnet1d/seed44/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/resnet1d/seed45/` | see below | 1 |
| `S3_per_experiment/ptbxl_cpsc/resnet1d/seed46/` | see below | 1 |
| `S4_reliability_diagrams/` | see below | 60 |
| **Total** | matches `SHA256SUMS.txt` | **177** (+ this README) |

### S1_protocol
`EXPERIMENT_PROTOCOL.md` (protocol v2.1-A1), the A1 endpoint re-location
amendment, the A2 family-reduction amendment, the A3 corpus-identity
amendment, `OSF_MANIFEST_POST_CORRECTIONS_2026-09-16.md`, and
`osf_archive_manifest.json` -- the file-level SHA-256 manifest taken on
2026-09-16. See `docs/` in the public repository for the same documents.

### S2_result_tables
Aggregate result tables underlying every number in the main text.
`samplelevel_ts_60cells.csv` is the per-cell deliverable for the
sample-level (adaptive-TS, Robey et al. 2021) baseline cited in the
manuscript; added 2026-10-14, hash-matched to the public repository copy.

### S3_per_experiment
`transfer_result.json` for each cell of the 60-experiment transfer grid,
kept in the `transfer/<pair>/<architecture>/seed<42-46>/` layout of the
public repository.

### S4_reliability_diagrams
The 60 per-seed reliability diagrams catalogued in the Supplementary
Materials section of the manuscript, named
`fig_reliability_supp_{pair}_{arch}_seed{s}.pdf`.

## Verification

`SHA256SUMS.txt` lists the SHA-256 of every file in this package. Verify
with `sha256sum -c SHA256SUMS.txt`.
