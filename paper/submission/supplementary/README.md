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
> 1↔3 swap. Two result tables ship in encoding-paired pairs: the unmarked
> member is the current, manuscript-cited regeneration (post-retrain
> caches, corrected label encoding), and the `.OLD_ENCODING.csv` member
> is the label-restored 2026-09-16 artifact from the pre-retrain
> checkpoints, retained so that the release lineage is auditable:
>
> | file | status |
> |---|---|
> | `ablation_ts_components.csv` | **authoritative, manuscript-cited** — the paper's raw-ECE range (`0.062`–`0.357`, mean `0.205`) is its `stage=raw` rows over the 60 main-grid cells |
> | `ablation_ts_components.OLD_ENCODING.csv` | pre-retrain-era artifact — retained for release-lineage comparison only; **not** manuscript-cited. Its all-62 `stage=raw` subset (60 grid cells + 2 BiMamba extras) is the source of the superseded `0.036`–`0.357`, mean `0.211` figure quoted in earlier manuscript drafts |
> | `discrimination_metrics_60exp.csv` | **authoritative, manuscript-cited** — carries `variant=raw` **and** `variant=ts` rows on the post-retrain caches; source of the paper's mean/max ΔAUROC_TS−raw (`+0.0002` / `0.0014`) and per-cell OOD AUROC (`0.695`–`0.886`, mean `0.802`) |
> | `discrimination_metrics_60exp.OLD_ENCODING.csv` | pre-retrain-era artifact — retained for release-lineage comparison only |
>
> Where the two files of a pair disagree, the unmarked file is the one
> the manuscript cites. The two `discrimination_metrics_60exp` files
> differ under both encodings: over the 124 `variant=raw` rows shared by
> the two schemas (62 grid cells × 2 splits), 44 rows differ in all six
> metrics — exactly the 22 cells retrained on 2026-09-17 (checkpoint
> independence) and 2026-10-07 (validation-leak repair); the same holds
> for the `variant=ts` rows (124 compared, 44 differ, same 22 cells).
> The `.OLD_ENCODING` version is retained for release-lineage comparison
> only; it is not the metric source for any manuscript-cited number.

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
| **Total** | matches `SHA256SUMS.txt` | **178** (+ this README; the manifest additionally lists this README, 179 entries in total) |

### S1_protocol
`EXPERIMENT_PROTOCOL.md` (protocol v2.1-A1), the A1 endpoint re-location
amendment, the A2 family-reduction amendment, the A3 corpus-identity
amendment, `OSF_MANIFEST_POST_CORRECTIONS_2026-09-16.md`, and
`osf_archive_manifest.json` -- the file-level SHA-256 manifest taken on
2026-09-16. See `docs/` in the public repository for the same documents.
Amendment A4 (mapping-sensitivity gate operationalization, 2026-10-11)
is deposited with the OSF project (project 53h64, Files, 2026-10-11,
per-file SHA-256 verified) and is intentionally NOT mirrored in this
folder.

### S2_result_tables
Aggregate result tables underlying every number in the main text.
`samplelevel_ts_60cells.csv` is the per-cell deliverable for the
sample-level (adaptive-TS, Robey et al. 2021) baseline cited in the
manuscript; added 2026-10-14, hash-matched to the public repository copy.

### S3_per_experiment
`transfer_result.json` for each cell of the 60-experiment transfer grid
plus two extra exploratory BiMamba cells under
`ptbxl_chapman/mamba/seed<42-43>/` (62 files in total), kept in the
`transfer/<pair>/<architecture>/seed<NN>/` layout of the public
repository; the 22 retrained cells (2026-09-17 / 2026-10-07) were
repopulated from the repository of record on 2026-10-15.

### S4_reliability_diagrams
The 60 per-seed reliability diagrams catalogued in the Supplementary
Materials section of the manuscript, named
`fig_reliability_supp_{pair}_{arch}_seed{s}.pdf`.

## Verification

`SHA256SUMS.txt` lists the SHA-256 of every file in this package. Verify
with `sha256sum -c SHA256SUMS.txt`.
