# Calibration Recalibration Transportability in Cross-Corpus ECG Classification

Code, data-split indices, and result artifacts for the study:

> **When Does Recalibration Transfer? Decomposing the ID→OOD Decay of Calibration Benefit in Cross-Corpus ECG Classification**

The study asks a deployment-critical question: after a calibration fix delivers a benefit in-distribution (ID), how much of that benefit survives out-of-distribution (OOD) — and which component (slope / intercept / prevalence) of the miscalibration decay dominates for a given shift type?

**Main endpoint**: `G = ECE_S1 − ECE_oracle` (zero-shot transfer gap), with the recalibration benefit `ΔECE = ECE_raw − ECE_cal` and its ID→OOD **decay** as secondary endpoints. Uncertainty is quantified with patient-level cluster bootstrap + BCa (B = 10,000), multiple testing controlled by BH-FDR.

## Repositories & databases

Experiments use three public databases, unified to 5 superclasses (`NORM / MI / STTC / CD / HYP`; CPSC uses a 4-class subspace `{NORM, CD, STTC, MI}` because HYP has n=11):

| Database | Source | Access |
|---|---|---|
| PTB-XL (21,522 records after preprocessing) | [PhysioNet](https://physionet.org/content/ptb-xl/1.0.3/) | open (O Attribution 4.0) |
| Chapman–Shaoxing (20,243 records) | CPSC+Chapman stack on PhysioNet | open |
| CPSC2018+2019 (10,285 records) | [CPSC challenge](https://physionet.org/content/challenge-2018/) | open |

⚠️ **Raw waveforms are NOT redistributed here** (license terms + size). Download from the sources above, then run the preprocessing scripts in `scripts/preprocess_*.py`.

## What is in this repo

```text
src/
  data/
    splits.py               patient-level splits, official PTB-XL folds, leakage assertions
    mapping.py              5-superclass label maps, SUBSPACE_CPSC, filter_subspace
    datasets.py             NPZ dataset loader
  models/                   backbones (BiMamba / InceptionTime-lite / ResNet-1D baselines)
  utils/
    calibration.py          TS/Platt/ECE/SmoothECE, BCa benefit_inference, two-layer bootstrap
    calibration_methods.py  9-method recalibration registry
    decomposition.py        3-component (slope/intercept/prevalence) decomposition estimator
    prior_shift.py          BBSE / EM label-shift prior estimators
scripts/
  preprocess_ptbxl.py       PTB-XL → unified NPZ + metadata
  preprocess_chapman.py     Chapman → unified NPZ + metadata
  preprocess_cpsc.py        CPSC → unified NPZ + metadata
  train.py                  end-to-end training + main endpoint (paired BCa bootstrap, B=10,000)
  eval_transfer.py          cross-corpus transfer / calibration evaluation
  export_splits.py          ★ exports the exact as-used split indices (see below)
  validate_decomposition.py synthetic 27-cell validation of the decomposition estimator
splits/                     ★ 25 CSVs: 5 variants × seeds 42–46 (see below)
results/                    result artifacts (small CSV/JSON only)
docs/
  EXPERIMENT_PROTOCOL.md    preregistered protocol (v2.0)
  PROTOCOL_AMENDMENT_*.md   registered protocol amendments
  osf_archive_manifest.json hash manifest for archival
```

## The `splits/` directory — exact as-used partition indices

Every CSV corresponds to one of the 60 experiments' data partition:

| File pattern | Variant |
|---|---|
| `ptbxl_seed{S}.csv` | PTB-XL, 5 superclasses |
| `ptbxl_sub4_seed{S}.csv` | PTB-XL, 4-class subspace |
| `chapman_seed{S}.csv` | Chapman, 5 superclasses |
| `chapman_sub4_seed{S}.csv` | Chapman, 4-class subspace |
| `cpsc_seed{S}.csv` | CPSC, 4-class subspace (fixed) |

Columns: `record_id` (preprocessing NPZ stem), `patient_id`, `split` (`train/val/cal/test`), `in_train_loader` (`yes/no`).

**PTB-XL as-used semantics (important).** In `train.py`, the carved-out `val` patients' records remain in the training loader (all of folds 1–8 are trained on; `val` serves early-stopping monitoring only). This is how the 60 experiments actually ran; the CSVs reflect this faithfully via the `in_train_loader` column (`val` rows are `yes`). `cal` (fold 9) / `test` (fold 10) patients have **zero overlap** with folds 1–8 (asserted). For Chapman/CPSC, `val` patients are correctly excluded from training (`no`). This quirk is disclosed in the paper's Limitations.

**Verification.** `scripts/export_splits.py` mirrors the split logic in `train.py` line-by-line and was cross-validated against the real dataset builders: **20/20 split×builder checks MATCH** (5 variants × train/val/cal/test, seed 42):

```bash
python scripts/export_splits.py                 # regenerate all 25 CSVs (seeds 42–46)
python scripts/export_splits.py --validate 42   # cross-check against real builders
```

## Reproduction

```bash
pip install -r requirements.txt

# 1. Download the three databases from PhysioNet (links above)
# 2. Preprocess (writes data/<db>_processed/metadata_single_label.csv + NPZ)
python scripts/preprocess_ptbxl.py
python scripts/preprocess_chapman.py
python scripts/preprocess_cpsc.py

# 3. Regenerate the split indices (should be byte-identical to splits/*.csv)
python scripts/export_splits.py

# 4. Train + evaluate one cell (example)
python scripts/train.py --dataset ptbxl --seed 42

# 5. Cross-corpus transfer / calibration evaluation
python scripts/eval_transfer.py
```

The synthetic validation of the decomposition estimator runs standalone (no data download needed, ≈4 min):

```bash
python scripts/validate_decomposition.py --boot 500
```

## Key results (artifacts in `results/`)

| File | Content |
|---|---|
| `discrimination_metrics_60exp.csv` | discrimination (AUROC) for all 60 experiments |
| `robustness_validation_5seeds.csv` | 5-seed robustness validation |
| `ablation_ts_components.csv` | temperature-scaling component ablation |
| `bootstrap_diagnostics.csv` | BCa bootstrap diagnostics |
| `bh_fdr_correction.csv` | BH-FDR multiple-testing correction |
| `deployment_metrics.csv` + `deployment_holdout_recompute.csv` | deployment-safety metrics (TS safety rate 0.64%) |
| `l2_shift_full_*.csv` | L2 shift-sensitivity grid |
| `decomposition_validation_n20000.csv` | decomposition estimator synthetic validation (n=20,000) |

## Data availability statement

Split indices + label maps + preprocessing scripts in this repo allow exact reconstruction of all 60 experiments' data partitions from the public sources, without trusting a prose description of the splitting logic. Full code snapshot and environment lock are archived (Zenodo DOI upon acceptance).

## License

Code: MIT (see `LICENSE`). The three databases remain under their respective PhysioNet / challenge licenses — users must obtain access directly from the sources.

## Citation

Citation block will be added upon publication.
