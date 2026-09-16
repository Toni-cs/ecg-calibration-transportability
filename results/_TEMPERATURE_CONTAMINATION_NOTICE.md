# ⚠️ Contamination notice — temperature columns in `results/`

> **Date**: 2026-09-16
> **Affected files**: `temperature_distribution_analysis.csv`,
> `binned_temperature_exploratory.csv`, `temperature_shift_sensitivity.csv`
> **Affected columns**: the fitted-temperature columns listed below
> **Status**: values are **not usable**; the correct values are given at the end
> **Related**: `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` (in the paper's
> supplementary material), `tests/test_mapping_encoding.py`

## What is wrong

The `SUBSPACE_CPSC` tuple was changed on 2026-09-09 from
`("NORM","CD","STTC","MI")` to `("NORM","MI","STTC","CD")` **without retraining
the models**. Because the tuple order *is* the integer label encoding
(`label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}`), every CPSC
label array regenerated after that date was out of step with the checkpoints,
swapping the MI and CD classes.

Temperature scaling is fitted by minimising NLL against the labels, so a
temperature fitted on swapped labels is not a temperature fitted on the true
labels. For the 40 CPSC-containing experiments it is substantially inflated.

The tuple was restored on 2026-09-16 and is now pinned by
`tests/test_mapping_encoding.py`. **The CSVs in this directory were not
regenerated**, so they still hold the inflated values.

## Affected columns

| File | Columns affected |
|---|---|
| `temperature_distribution_analysis.csv` | `T_global` |
| `binned_temperature_exploratory.csv` | `T_global`; `T_bin` (assumed, same pipeline) |
| `temperature_shift_sensitivity.csv` | `T_shift` (verified at `shift_name == "baseline"`); shifted rows assumed likewise |

All other columns in those files — the `*_rel_*` reliability/ECE columns —
are derived from the same calibration step and should be treated as suspect for
the 40 CPSC-containing experiments. The 20 non-CPSC experiments
(`chapman` ↔ `ptbxl`) are unaffected, since both encodings coincide there.

## Evidence

Recomputed from the per-experiment probability caches under both encodings
(`scripts/audit_temperature_csv_caliber.py` in the paper's working repository;
the caches themselves are not redistributed here).

| Check (40 CPSC experiments) | Result |
|---|---|
| `T_global` bit-matches the OLD encoding | **0 / 40** |
| `T_global` bit-matches the NEW encoding | 19 / 40 (rest within 9e-5, CSV rounding) |
| `max |T_global − T_old|` | 2.967 |
| `max |T_global − T_new|` | 9.0e-5 |
| Non-CPSC control (22 experiments) | consistent, as expected |

Headline statistics, 60 main experiments:

| Caliber | median T | fraction with T ≥ 2 |
|---|---|---|
| **As shipped in these CSVs (contaminated)** | **1.836** | **50.0 %** |
| **Correct (original encoding)** | **1.076** | **0.0 %** |

The corrected range is [0.932, 1.498]; the shipped range is [0.984, 4.440].

## Correct values

Temperature scaling is close to the identity across the whole grid: the median
fitted temperature is **1.076** and **no** experiment reaches T = 2. Any claim
of the form "TS fits large temperatures / half the cells exceed T = 2" is an
artefact of the encoding mismatch and must not be made.

To regenerate: restore the caches against the original encoding and re-run the
temperature analysis. The encoding to use is pinned by
`tests/test_mapping_encoding.py`; the pipeline fix is recorded in the
supplementary amendment A3.
