# ⚠️ Contamination notice — `results/ablation_ts_components.csv`

> **Date**: 2026-09-17
> **Affected file**: `results/ablation_ts_components.csv`
> (byte-identical across both repositories, sha256 `6b9a49fa…68ead550`)
> **Affected columns**: every metric column (`smooth_ece`, `ece`, `brier_*`,
> `T_global`, `T_binned_*`, `delta_rel_vs_raw`) for **all four stages** of the
> **40 CPSC-containing** experiments
> **Not affected**: the 22 `chapman` ↔ `ptbxl` experiments, where the two
> encodings coincide
> **Status**: the CPSC values are **not usable**; the corrected table is
> `results/ablation_ts_components.OLD_ENCODING.csv`
> **Related**: `results/_TEMPERATURE_CONTAMINATION_NOTICE.md`,
> `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md`,
> `tests/test_mapping_encoding.py`

## Root cause — a probs/labels encoding mismatch, *not* a noise floor

`checkpoints/e2_probs_cache/*.npz` stores `probs` and `labels` together, but
they originate from **different encodings**:

| array | origin | encoding | meaning |
|---|---|---|---|
| `*_probs` | checkpoint trained 2026-09-08, when `SUBSPACE_CPSC = ("NORM","CD","STTC","MI")` | **OLD** | column 1 = CD, column 3 = MI |
| `*_labels` | written **after** the 2026-09-09 encoding change | **NEW** | 1 = MI, 3 = CD |

`scripts/run_e2_ablation_discrimination.py::load_probs_for_checkpoint` reads
that cache verbatim under `--use-cache` (L384–390); otherwise it rebuilds the
dataset labels with the **current** `SUBSPACE_CPSC` (L394/L423) before running
inference. The CSV was produced on 2026-09-10 — i.e. after the encoding change —
so it consumed the mismatched cache. The model places its CD mass in column 1
while the ground truth in column 1 is MI, so **CD and MI (38.3% of the samples)
are systematically marked wrong**, inflating the raw ECE.

## Evidence

1. **First-party archive.** Each
   `checkpoints/transfer/**/transfer_result.json` stores its own `label_map`.
   All 40 CPSC-containing cells record
   `{"CD":1,"MI":3,"NORM":0,"STTC":2}` (= OLD).
2. **Label frequencies.** The CPSC test labels in the npz are
   `[NORM=183, ?1=303, STTC=1086, ?3=485]` (n = 2057) → 8.90% / 14.73% /
   52.80% / 23.58%. The full-corpus distribution in
   `data/cpsc_processed/preprocess_summary.json` is NORM 8.88% / MI 14.71% /
   STTC 52.75% / CD 23.55% / HYP 0.11%. The match is exact, so index 1 = MI and
   index 3 = CD — the **labels are NEW**. (Read as OLD, the counts would make
   MI 23.6% > CD 14.7%, which inverts the epidemiology.)
3. **Confusion-matrix fingerprint.** For `ptbxl_cpsc_resnet1d_seed42`,
   patients whose NEW label is 1 (= MI) are classified as argmax **3** in
   **250/303 = 82.5%** of cases, and patients whose NEW label is 3 (= CD) as
   argmax **1** in 42.5%. A consistent encoding would put the diagonal on top,
   so the **probs must be OLD**.
4. **The manuscript's own anchors.** The case studies in `paper/main_bspc.tex`
   quote raw ECEs of `0.3160` (L1440), `0.3144` (L1448) and `0.0649` (L1467).
   These match the OLD recomputation to four decimals; the contaminated CSV
   gives `0.3747` / `0.3685` / `0.0832`. The paper's raw-ECE caliber was
   therefore OLD all along, and the values flagged here were the outliers.

## Corrected values

### `smooth_ece` at `stage=raw`

| subset | n | contaminated CSV | **corrected (OLD)** |
|---|---|---|---|
| all 62 raw cells | 62 | mean 0.2728, [0.0357, 0.4689] | **mean 0.2114, [0.0357, 0.3566]** |
| CPSC-containing | 40 | mean 0.3219, [0.0746, 0.4689] | **mean 0.2268, [0.0620, 0.3566]** |
| non-CPSC | 22 | mean 0.1833, [0.0357, 0.2714] | unchanged |

Element-wise, `max|CSV − OLD| = 0.193472`; **not one of the 62 cells agrees**.

### The nine main-endpoint counter-examples

(Identical set to `ood_deltaECE < 0` in `robustness_validation_5seeds.csv`.)

| cell | raw (contaminated) | raw (corrected) |
|---|---|---|
| chapman→cpsc/inceptiontime/45 | 0.3747 | 0.3160 |
| chapman→cpsc/resnet1d/43 | 0.3685 | 0.3144 |
| chapman→ptbxl/inceptiontime/42 | 0.2583 | 0.2583 |
| chapman→ptbxl/resnet1d/45 | 0.2452 | 0.2452 |
| cpsc→chapman/resnet1d/42 | 0.0832 | 0.0649 |
| cpsc→chapman/resnet1d/44 | 0.1802 | 0.1435 |
| cpsc→ptbxl/resnet1d/43 | 0.4028 | 0.2893 |
| cpsc→ptbxl/resnet1d/44 | 0.4167 | 0.3213 |
| ptbxl→chapman/inceptiontime/46 | 0.1613 | 0.1613 |

Counter-example raw range: `0.0832–0.4167` contaminated → **`0.0649–0.3213`**.

### `T_global` (60 main cells)

Corrected: **median 1.0757, range 0.9320–1.4982, T ≥ 2 in 0.0%**. This agrees
with the independent correction recorded in
`_TEMPERATURE_CONTAMINATION_NOTICE.md`, which reports the shipped CSVs as
median 1.836 / T ≥ 2 in 50.0%.

## Effect on the manuscript

Two passages in `paper/main_bspc.tex` quoted the contaminated values; both are
corrected.

| Location | was (contaminated) | now (corrected) |
|---|---|---|
| L1213 | `$0.036$ to $0.469$ (mean $0.273$)` | `$0.036$ to $0.357$ (mean $0.211$)` |
| L1214 | `$2$--$28\times$` | `$2$--$21\times$` |
| L1216 | `($0.08$--$0.24$)` | `($0.065$--$0.321$)` |
| L1782 | `$2$--$28\times$` | `$2$--$21\times$` |
| L1783 | `($0.036$--$0.469$, mean $0.273$)` | `($0.036$--$0.357$, mean $0.211$)` |

Note also that L1216 previously read `confirming the negative $\Delta$ECE
reflects genuine TS-induced harm, not metric noise`. That sentence failed
twice over: (a) a *negative* ΔECE means TS *helped*, so "harm" contradicts the
sign; and (b) the noise floor pushes ΔECE in exactly the negative direction
(TS raises ECE under perfect calibration), so a large raw ECE does **not**
license the "not metric noise" conclusion. The clause now states only what is
provable and demotes the counter-example signs to exploratory.

## Reproduce

The recomputation script ships with this release as
`scripts/recompute_ablation_old_encoding.py`:

```bash
python scripts/recompute_ablation_old_encoding.py          # compare only
python scripts/recompute_ablation_old_encoding.py --write  # emit corrected CSV
```

It requires `checkpoints/e2_probs_cache/` and `checkpoints/transfer/`, both of
which are excluded from version control, so it runs only in the development
workspace (elsewhere it reports the missing cache and exits without writing).

The script permutes **labels only** (applying `swap13`, i.e. 1↔3, to
CPSC-containing cells) and leaves `probs` untouched, then re-derives all four
stages through the *same* `fit_temperature_multiclass` /
`fit_binned_temperature` / `optimize_thresholds` / `calibration_reliability`
calls as the original script.

## Open decisions

- Whether to **replace** `ablation_ts_components.csv` rather than ship the
  corrected table alongside it. The current policy is to keep the original,
  ship the corrected file separately, and document both, so the original
  artifact stays auditable.
- Whether to re-run `run_e2_ablation_discrimination.py` end-to-end (clearing
  `checkpoints/e2_probs_cache/` first) to produce an authoritative
  single-run CSV. The correction here is a label restoration and should be
  numerically equivalent, but a re-run would also eliminate the poisoned cache.
