# When Does Recalibration Transfer? Decomposing the ID-to-OOD Decay of Calibration Benefit in Cross-Corpus ECG Classification

Official code and data-split release for the accompanying article (under review).

Given a calibration fix with a benefit in-distribution (ID), this study measures how much of that benefit survives out-of-distribution (OOD) transfer across three public ECG corpora, decomposes the decay into three interpretable components (slope / intercept / prevalence), and derives a deployment-safety criterion for recalibration before transfer.

## Contents

- [Requirements](#requirements)
- [Dataset](#dataset)
- [Reproducing the results](#reproducing-the-results)
- [Data splits](#data-splits)
- [Paper-to-artifact map](#paper-to-artifact-map)
- [Results](#results)
- [License](#license)
- [Citation](#citation)

## Requirements

- Python ≥ 3.10, PyTorch ≥ 2.4 (CUDA optional; CPU suffices for evaluation-only reproduction)
- All Python dependencies: `pip install -r requirements.txt`

## Dataset

Three public databases, unified to five superclasses (`NORM / MI / STTC / CD / HYP`; CPSC uses a four-class subspace `{NORM, CD, STTC, MI}` because HYP has n = 11):

| Database | Records (after preprocessing) | Source |
|---|---|---|
| PTB-XL | 21,522 | [PhysioNet v1.0.3](https://physionet.org/content/ptb-xl/1.0.3/) |
| Chapman–Shaoxing | 20,243 | PhysioNet (Chapman–Shaoxing ECG) |
| CPSC2018+2019 | 10,285 | [CPSC challenge](https://physionet.org/content/challenge-2018/) |

Raw waveforms are **not redistributed** in this repository (database licenses, size). Download the databases from the sources above, then build the unified NPZ + metadata:

```bash
python scripts/preprocess_ptbxl.py   --source-root data/ptbxl   --output-root data/ptbxl_processed
python scripts/preprocess_chapman.py --source-root data/chapman --output-root data/chapman_processed_v2
python scripts/preprocess_cpsc.py    --source-root data/cpsc    --output-root data/cpsc_processed
```

## Reproducing the results

```bash
# 0. Install and preprocess (see above)

# 1. Regenerate the exact as-used split indices (should be byte-identical to splits/*.csv)
python scripts/export_splits.py
python scripts/export_splits.py --validate 42   # cross-check against the dataset builders

# 2. Train + main endpoint for one grid cell (60 cells: 6 corpus pairs x 2 archs x 5 seeds)
python scripts/train.py --dataset ptbxl --seed 42

# 3. Cross-corpus transfer / recalibration evaluation
python scripts/eval_transfer.py \
    --source ptbxl --source-dir data/ptbxl_processed \
    --target chapman --target-dir data/chapman_processed_v2 \
    --arch inceptiontime --methods ts platt --seeds 42

# 4. Standalone synthetic validation of the decomposition estimator (no data needed, ~4 min)
python scripts/validate_decomposition.py --boot 500
```

Trained checkpoints for the full 60-experiment grid (62 `best_model.pt` + SHA-256 manifest) are provided as assets of [release v1.0.0](https://github.com/gt17641001169-design/ecg-calibration-transportability/releases/tag/v1.0.0).

The preregistered protocol and its registered amendments live in [`docs/`](docs/README.md) (written in Chinese; an English translation is available on request).

## Data splits

[`splits/`](splits/) contains the exact patient-level partition indices used by all 60 experiments: 25 CSVs = 5 dataset variants (`ptbxl`, `ptbxl_sub4`, `chapman`, `chapman_sub4`, `cpsc`) × seeds 42–46, with columns `record_id`, `patient_id`, `split` (`train/val/cal/test`), `in_train_loader` (`yes/no`).

Two documented properties:

- **PTB-XL as-used semantics.** The carved-out `val` patients' records remain in the training loader (all of folds 1–8 are trained on; `val` is early-stopping monitoring only). The CSVs report this faithfully via `in_train_loader=yes` on `val` rows. `cal` (fold 9) and `test` (fold 10) patients have zero overlap with folds 1–8 (asserted at build time). For Chapman/CPSC, `val` patients are excluded from training. See the article's Limitations section.
- **Builder cross-validation.** `scripts/export_splits.py` mirrors the split logic of `scripts/train.py` line-by-line and was verified against the real dataset builders: 20/20 split×builder checks MATCH (5 variants × train/val/cal/test, seed 42).

## Paper-to-artifact map

| Paper element | Script | Artifact |
|---|---|---|
| Data splits (all experiments) | `scripts/export_splits.py` | `splits/*.csv` |
| Main endpoint G, ΔECE, BCa CIs | `scripts/train.py` + `scripts/eval_transfer.py` | `results/robustness_validation_5seeds.csv`, `results/bootstrap_diagnostics.csv` |
| Discrimination (AUROC, 60 exp) | `scripts/train.py` | `results/discrimination_metrics_60exp.csv` |
| Multiple-testing control | `scripts/eval_transfer.py` | `results/bh_fdr_correction.csv` |
| Recalibration deployment safety | `scripts/deployment_holdout_recompute.py` | `results/deployment_metrics.csv`, `results/deployment_holdout_recompute.csv` |
| L2 shift sensitivity grid | `scripts/eval_l2_shift.py` | `results/l2_shift_full_390cells.csv` |
| Three-component decomposition | `src/utils/decomposition.py` | `results/decomposition_validation_n20000.csv` |
| TS component ablation | `scripts/run_e2_ablation_discrimination.py` | `results/ablation_ts_components.csv` |
| Preregistered protocol | — | `docs/EXPERIMENT_PROTOCOL.md`, `docs/PROTOCOL_AMENDMENT_*.md`, `docs/osf_archive_manifest.json` |

## Results

Pooled zero-shot transfer gap `G` (random-effects meta-analysis over the 60-experiment grid; patient-level cluster BCa, B = 10,000):

| Stratum | n | Pooled G | 95% CI |
|---|---|---|---|
| InceptionTime | 30 | 0.0151 | [0.0131, 0.0172] |
| ResNet-1D | 30 | 0.0158 | [0.0140, 0.0176] |
| **All (cross-architecture)** | **60** | **0.0148** | **[0.0141, 0.0155]** |

Recalibration retains a positive OOD benefit in most settings but is not universally safe: temperature-scaling deployment safety rate is 0.64% across the holdout grid; 381/390 (97.7%) cells remain safe under L2 input shifts.

## License

Code: MIT (see [LICENSE](LICENSE)). The three databases remain under their respective PhysioNet / challenge licenses.

## Citation

If you use this codebase or the split indices, please cite the accompanying article (see also [CITATION.cff](CITATION.cff)):

```bibtex
@article{ecgcalib2026,
  title   = {When Does Recalibration Transfer? Decomposing the ID-to-OOD Decay
             of Calibration Benefit in Cross-Corpus ECG Classification},
  author  = {Anonymous},
  journal = {Biomedical Signal Processing and Control},
  note    = {under review},
  year    = {2026}
}
```

Please also cite the source databases (PTB-XL: Wagner et al., *Scientific Data* 2020; Chapman–Shaoxing: Zheng et al. 2020; CPSC2018: Liu et al., *CinC* 2018).

## Contact

Questions and issues: please open a [GitHub issue](https://github.com/gt17641001169-design/ecg-calibration-transportability/issues).
