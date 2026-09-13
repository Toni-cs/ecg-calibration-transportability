# ECG Recalibration Boundary Study: Preregistered Experiment Protocol v2.1-A1

> This protocol was produced through cross-validation by five independent adversarial reviews (experimental design / statistical methodology / engineering reproducibility / literature novelty / Reviewer 2 simulation).
> Status: **Preregistration draft**. Before submission, hash-archive this file to a timestamping platform such as OSF.
> **Revision history**: v2.0 (initial five-review version) → v2.1-A1 (2026-09-05, preregistration amendment A1 merged: primary endpoint relocation decay→ΔECE_OOD, §6 symbol typo correction, contribution statement relocation; full text of the amendment is in Appendix A1 at the end).

## 0. Novelty Relocation (Literature Review Conclusion)

**Must not claim**: "First to demonstrate on ECG that calibration repair benefit decays from internal to external."
This is an ECG reproduction of a known conclusion by Ovadia et al. (NeurIPS 2019), and Barandas 2023, Zhang 2022, and Physiol Meas 2026 have separately reported the phenomenon on ECG.

**Should claim** (three-step chain, each step retains residual novelty space):
1. **Parameter-level decomposition**: Decompose the ID→OOD decay of calibration repair benefit into the contribution shares of three intervenable components: slope/intercept/prevalence (no one has taken the "contribution share" perspective on ECG deep models plus cross-dataset public benchmarks)
2. **Predictability**: Use target-domain unlabeled statistics (predicted prior L1 distance, logit distribution statistics) to predict the retention rate of repair benefit
3. **Deployment criterion**: Output an actionable decision table of "shift type × dominant component × recommended recalibration strategy", and validate the criterion's sensitivity/specificity on the held-out set of the transfer matrix

**Contribution hierarchy (A1.5 revision)**:
1. **Primary contribution**: OOD calibration benefit quantification (primary endpoint ΔECE_OOD significantly positive)
2. **Boundary condition contribution**: ID no-fixable-space boundary (ΔECE_ID ≈ 0, establishes the non-triviality of the primary contribution)
3. **Auxiliary contribution**: §8.5 predictability (complete 3 architectures, regression sample = 18)
4. **Auxiliary contribution**: §9 deployment criterion (complete sensitivity/specificity + trivial-strategy comparison)

**Must cite directly** (introduction anchor points): Ovadia 2019, van Calster 2016/2019, Guo 2017, Kull 2019 (Dirichlet), Nixon 2019, Kumar 2019, Alexandari 2020, Lipton 2018 (BBSE), Wagner 2020 (PTB-XL), Strodthoff 2021.
**Nearest neighbors that must be explicitly compared**: Physiol Meas 2026 (RR-interval AF cross-database calibration, feature model vs this paper's deep multi-label); medRxiv 2026 ICU calibration drift (parallel conclusion of slope retention/intercept drift); TransCal/PseudoCal/LaSCal (method-class upper bounds).

## 1. Terminology Discipline

- "recalibration" (not "calibration repair")
- "transportability" (not "portability")
- "dataset shift" must be subdivided into: covariate shift / prior probability shift / concept shift (Moreno-Torres 2012 taxonomy), declaring the type per transfer pair
- Reject ratios as the main reporting quantity: use the format "ΔECE = X [95% CI], baseline Y → post-repair Z"; ratios appear only in parentheses

## 2. Data and Splits (Leakage Prevention Protocol)

| Library | Role | Split |
|---|---|---|
| PTB-XL v1.0.3 | source/target | **Official 10-fold**: folds 1-8 train / fold 9 calibration / fold 10 in-distribution test (patient-stratified) |
| Chapman-Shaoxing | source/target | Patient-level stratified 70/10/20, fixed seed |
| CPSC2018+2019 | source/target | Patient-level stratified 70/10/20; **HYP extremely rare (n=11, all from CPSC2019 single-label LVH/RVH) → main analysis downgraded to {NORM,CD,STTC,MI} 4-class subspace** (R16 revision: the original assumption "CPSC has no HYP" was overturned by full preprocessing, HYP=11 does not support reliable val/test estimation). HYP records are **excluded and counted separately in the STROBE flowchart, with no remapping**; transfer pairs involving CPSC **recalculate both sides in the same 4-class subspace** (symmetry) |
| (optional) Ningbo | increase power | same as above |

- **Hard assertion script**: train/cal/test patient ID intersections are empty (enters CI and reproduction repository)
- Single-label priority rules are fixed and subjected to sensitivity analysis; multi-label sigmoid serves as a second formalization
- STROBE-style flowchart: per library raw records → after mapping → excluded → final sample, with per-class counts
- Normalization statistics **come only from the train split**; augmentation acts only on train

## 3. Shift Dose Ladder (BSPC Narrative Act 1), eval-only dominant, control compute budget

- **L0**: source test (ID baseline)
- **L1**: cross-database directed pairs, 3 libraries full permutation = 6 pairs
- **L2** (**eval-time transformation, no retraining**, same convention as Ovadia 2019):
  - Sampling rate 500→250→125 Hz (eval-time anti-aliasing downsampling)
  - Leads 12→6→3→2→1 (eval-time channel zeroing; **R16 semantic declaration**: the leads6 level actually retains 8 independent channels {I,II,V1-V6}, removing 4 linearly derivable leads {III,aVR,aVL,aVF} (the full 12-lead can be linearly reconstructed from I,II,V1-V6 per Goldberger/Wilson electrode relations), an information-lossless downgrade; leads3={I,II,V2} is the preregistered subset)
  - Noise injection (PTB-XL Noise Stress Test DB: BWL/MA/EM) @ SNR {24,12,6,0,−6} dB
  - Gain ×0.5 / ×2 (**R16 semantic declaration**: applied after per-record z-score normalization, without re-normalizing; empirically, raw signal ×2 then normalized versus normalized then ×2 are bitwise identical, max|Δ|<1e-6, meaning acquisition-side gain error is fully cancelled by per-record z-score; this level simulates gain mismatch after the normalization pipeline, not acquisition-side gain error)
  - **Retraining validation point**: only InceptionTime × PTB-XL source × lead 4 downgrade levels {6,3,2,1} × 5 seeds (20 runs) to verify "eval-time shift conclusions agree with retrained models" (R-round revision: the original "6 levels/30 runs" was a typo, unified with §3.5 budget table to 20 runs; R15 revision: BiMamba→InceptionTime, because BiMamba at full resolution OOM)
- Externality quantification: per-lead power spectrum KS test / MMD to report inter-database signal distribution distance

## 3.5 Compute Budget Table (added in round 2 review, to prevent infeasible design)

| Item | Scale | Estimate |
|---|---|---|
| Base training | 3 arch × 3 libs × 5 seeds (fixed split) | 45 runs ≈ 3-5 GPU-days |
| Retraining validation point | InceptionTime × 1 lib × 4 lead levels × 5 seeds | 20 runs ≈ 1-2 GPU-days (R15 rev: BiMamba→InceptionTime) |
| S1 main grid | 6 pairs × 2 main arch × 5 seeds × 7 main methods | eval-only ≈ 2-4 GPU-hrs (R15 rev: 3→2 main arch) |
| L2 ladder | all eval-only | ≈ 4-8 GPU-hrs |
| S2 few-shot | 4 methods × 5 n_cal × 20 repeats × representative levels (representative levels = 4 chosen from L2's 13 non-baseline shift levels: sampling rate 250Hz/lead 6/noise 12dB/gain ×2) | ≈ 4×5×20×4=1600 fits/representative level, full run across 13 levels ≈ 21k fits ≈ 8-12 CPU-hrs (consistent with §5:85) |
| Bootstrap | main test/G: B=10,000; secondary: B=2,000 | ≈ 8-12 CPU-hrs |
| **Total** | | **≈ 5-8 GPU-days + 1 CPU-day** (feasible within submission cycle on a single 8GB card) |

**Method pool (M1-M13)**: 7 for the main text (None/TS/per-class Platt/Isotonic/Dirichlet/Saerens EM/Oracle) + 6 in the appendix (Vector/Matrix scaling/CORAL/TTA/MC-Dropout±TS). Appendix methods run only on 2 representative pairs from the PTB-XL source.
- BBSE handling: under single-label OvR it belongs to the same family as Saerens EM, represented by Saerens, with the exclusion rationale written in §5
- TTA definition: Gaussian noise σ=0.005mV × 8 + time shift ±20ms × 2, averaged softmax

## 4. Models and Training

- **3 architectures × ≥5 seeds**: InceptionTime (main), 1D-ResNet-34, BiMamba (auxiliary; R15: full-resolution OOM on RTX 5060 8GB, validated separately on downsampled input)
- InceptionTime/1D-ResNet-34 are the main experimental architectures; BiMamba serves as auxiliary robustness validation. BiMamba must report alignment with public SOTA (AUROC macro ≈0.92-0.93), with **this alignment statement reported under the §2:36 multi-label sigmoid second formalization** (Wagner 2020 numbers are products of the multi-label protocol and are in principle not comparable to the single-label 5-class softmax main track; R-round revision/M5 fix, the single-label main track does not perform SOTA alignment comparison); numerical consistency test between mambapy and the official kernel (max|Δy|<1e-4)
- Training protocol: AdamW + cosine schedule + linear warmup + grad clip 1.0 + NaN guard
- **Temperature singlization**: in the main protocol, T≡1 frozen during training (learnable_temp=False already implemented); co-trained T is a separate ablation track and is no longer fit post-hoc
- **MC-Dropout protocol**: BN frozen (already implemented); aggregation = averaged softmax probability; both MC-Dropout and MC-Dropout+TS enter the method table; TS is fit on the probabilities **after** averaging 20 forward passes
- Early stopping criterion unified across all libraries/architectures: val NLL (explicitly stating the effect of this choice on baseline calibration)
- Memory feasibility: patch-embedding downsampling (/4) or d_model≤128; the paper reports hardware faithfully

## 5. Calibration Method Library × Three Scenarios

Full method matrix (R2 hazard: skipping any method invites the critique "did not try the right method"):

None / TS / per-class Platt / Vector scaling / Matrix scaling / Isotonic (OvR, report fit-set size) / Dirichlet / Saerens EM prior adaptation (unlabeled, **not applicable to the S1 source-cal-fit paradigm** (Saerens parameter = target prior, requires target-domain estimation; grouped into S1' target-domain unsupervised adaptation)) / CORAL + recalibration / TTA / MC-Dropout / **Oracle** (target-domain cal split fully fit, evaluated on the same test set as all methods = R-round revision unifying §6 definition, preventing in-sample bias; fit independently per transfer cell)

Scenarios:
- **S1 zero-shot transfer** (main analysis): source-cal fit → target used directly (R14 revision: original §5 "source-val fit" changed to "source-cal fit", consistent with eval_transfer.py implementation; deviation registered as R14)
- **S2 local few-shot recalibration** (clinical manual): target-domain n_cal ∈ {50,100,250,500,1000} labeled samples, patient-level sampling × 20 repeats → "annotation budget, benefit recovery" dose curve
- **S3 target full refit** (upper bound)

## 6. Endpoint Definitions (Locked, No Post Hoc Changes)

**Main formalization**: single-label 5-class softmax; **main ECE = 5-class confidence SmoothECE** (no binning bias), classwise macro-average as a secondary perspective.

**Endpoint hierarchy (A1 revision)**:
- **Primary endpoint = ΔECE_OOD** (unique, A1.1 relocated)
- **Boundary condition endpoint = ΔECE_ID** (expected H₀ not rejected, A1.4)
- **Secondary endpoints**: G (recoverable loss), decay (secondary descriptive quantity, A1.1 downgraded), R (retention rate), NLL, classwise-ECE, Brier Murphy decomposition, Cox slope/intercept, predicted/true prior L1 distance
- There is only one primary test; all per-cell comparisons enter the BH family (family size = 6 pairs × 2 main arch × 13 shift levels = 156 tests, consistent with the §3:44-48 enumeration)

**Primary endpoint (A1.3 formal definition)**:
- ΔECE_OOD = ECE_raw_OOD − ECE_TS_OOD
  - ECE_raw_OOD: 5-class confidence SmoothECE computed on target-domain raw probabilities for a classifier trained in the source domain
  - ECE_TS_OOD: 5-class confidence SmoothECE computed on target-domain post-TS probabilities, for a classifier trained in the source domain with temperature T fit on the source cal split
  - TS fit paradigm: source-cal fit (consistent with §5:84 S1, R14 revision)
  - SmoothECE bandwidth: 0.45·(n/2000)^(−0.2) (consistent with §11.5 F3)

**Boundary condition endpoint (A1.4 formal definition)**:
- ΔECE_ID = ECE_raw_ID − ECE_TS_ID
  - ECE_raw_ID: 5-class confidence SmoothECE computed on source-domain raw probabilities for a classifier trained in the source domain
  - ECE_TS_ID: 5-class confidence SmoothECE computed on source-domain post-TS probabilities, for a classifier trained in the source domain with temperature T fit on the source cal split
  - Expected H₀: ΔECE_ID = 0 not rejected
  - Robustness criterion (locked): proportion of cells whose 95% CI contains 0 ≥ 80% → boundary condition robust
  - Branch trigger: < 80% → "ID non-zero boundary" branch, primary conclusion adds a boundary-condition qualifier (A1.4.2)

**Secondary endpoints**:
- G = ECE_S1(target) − ECE_oracle(target)  [Recoverable loss: distinguishes "nothing to fix" vs "cannot be fixed"]
  - Oracle definition (prevent in-sample bias): target-domain cal split fully fit, evaluated on the same test set as all methods; fit independently per transfer cell
- decay = ΔECE_OOD − ΔECE_ID  [A1.1 downgraded to secondary descriptive quantity; A1.2 typo fix: decay positive = OOD benefit − ID benefit]
- R = ΔECE_ext / ΔECE_int (description only + sensitivity test)
- NLL; classwise-ECE (macro-average, empty classes listed separately); Brier Murphy decomposition (per-class binarization construction, unit test asserts identity; across libraries compare only the REL term); Cox slope/intercept; predicted/true prior L1 distance

**Primary test (unique, A1.1 relocated)**:
H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0 (one-sided, directional prior: TS is order-preserving under convex loss, Guo 2017/Kull 2019)
Patient-level cluster paired bootstrap B=10,000 BCa; stratified pooling: strata = transfer pair × architecture
Point estimate = full-sample statistic (never report bootstrap mean), format "ΔECE_OOD = X [95% CI L, U], baseline Y → post-repair Z"
Cells with ΔECE_OOD ≤ 0: report the count of "repair harmful or ineffective", do not enter the positive-benefit claim

**Secondary family**: BH-FDR q=0.05 (family size 156); the rest labeled exploratory and report CI only
**Sanity**: global argmax unchanged bit-for-bit after TS (already asserted in train.py)

**Prespecified interpretation (prevalence matching experiment, pillar experiment), TOST three-part form, numerical boundaries locked**:
- Matching activation condition: after matching, maximum absolute difference in class marginal prior ≤ 0.02, otherwise report the "matching failed" branch, not included in interpretation
- **Decay retained** = lower bound of R's 95% CI ≥ 0.7
- **Decay vanished** = CI contains 1 and point estimate ≥ 0.85
- **Partial decay** = all other cases
- Matching = patient-level subsampling by class marginal prior; report matching residual when joint matching is infeasible

## 7. Statistical Protocol

- Resampling unit = patient (cluster bootstrap); main test/G uses B=10,000 BCa; secondary endpoints use B=2,000 percentile
- Two-layer joint bootstrap: val resampling → fit T → test resampling → metric (T uncertainty propagated into CI)
- **Split variance component**: estimated only on Chapman/CPSC (re-splittable) with 5 patient-level re-splits × InceptionTime; PTB-XL uses official folds as the main split (consistent with §2), with folds 1-8 internal re-splitting serving only as sensitivity, resolving the conflict between official folds and "≥5 splits" (R15 revision: BiMamba→InceptionTime)
- Point estimate = full-sample statistic, **never report bootstrap mean**
- ECE estimator: main = SmoothECE (implemented and corrected); sensitivity = report both equal-width 10 and equal-frequency 15; MCE only equal-frequency with bin capacity ≥ 50
- McNemar exact binomial version, thresholds searched only on val; DeLong only for cross-model comparison
- Power: **pilot = independent pre-experiment of 1 transfer pair × 1 architecture × 2 seeds (results do not enter the main test report)**, estimate Var(log ΔECE) → n=(z_.975+z_.8)²·Var/d², report minimum feasible n per L2 level

## 8. Mechanism Decomposition Validation (Three Legs, Withdraw "Mechanism" Wording if Any is Missing)

> **R-round status note**: Leg 1 (identity equation + factorial interaction reporting) and Leg 2 (synthetic threshold) are fulfilled; for Leg 3, the
> **synthetic-environment doable parts are fulfilled** (v3: 27-cell attribution quantities with sample-level bootstrap CI + entangle_demo_cases
> demonstrating three cases where the entangled branch is reachable + unified recovery-failure path, see validate_decomposition.py v3 and
> the CI column of results/decomposition_validation_n20000.csv). **cross-fitting still awaits real data**,
> recorded in §13. Per this section's self-binding clause, the "mechanism" wording must be qualified as
> "mechanism decomposition (synthetic validation part)" until cross-fitting is complete.

1. **Mathematical statement**: Murphy decomposition = exact identity (OvR per-class construction); three-component attribution = counterfactual-replacement additive approximation, **interaction residual explicitly reported** (v3 already in CSV: chain_residual column, always 0 under chained nesting, true interactions in factorial term I_*)
2. **Synthetic injection**: 27-cell full factorial (slope∈{0.5,1,2} × intercept∈{−1,0,1} × prevalence∈{0.15,0.3,0.6}). **Thresholds apply only to the predefined identifiable region** (decision rule: Fisher information determinant > threshold τ, τ preregistered), recovery MAPE<10% as the threshold; the entangled region reports only error plots, with no threshold.
   **R-round deviation registration (preregistration discipline)**: the original prevalence factors were multiplicative {0.5,1,2} (×2 → π=1.0 exhausts the positive class (n_neg=0, recovery regression degenerates), ×1 ≈ baseline prior 0.5 (does not trigger resampling, prev axis idles)); implementation changed to absolute values {0.15,0.3,0.6}, deviation rationale = feasibility + coverage on both sides of baseline, deviation date 2026-08-29 (at implementation).
   **Threshold honest semantics (R2 fix)**: in gate(n)=max(10%, 3×MAPE_REF×sqrt(N_REF/n)), MAPE_REF is a **single-seed single-run measured value**, "3×" is a heuristic amplification factor **not a 3σ tolerance**; at n=500 the measured violation rate ≈22% (checkable in archived CSV), small-sample FAIL reported faithfully by the information mode via exit 2, and does not constitute a move of the preregistered threshold.
3. **Identifiability**: synthetic environment validates the three-component entanglement region (v3 fulfilled: narrow_band/tiny_slope/deep_intercept three cases, det∈{2.4e-7,3.6e-8,0}<τ=1e-6); decomposition attribution carries bootstrap CI (v3 fulfilled: percentile CI for absolute Shapley value/chained component/Δ_total/I_sb; shares carry no CI because the denominator can cross zero), CI overlap forbids ranking a "main cause"; Shapley share carries a share_reliable flag (|Δ_total|<3/√n not interpretable); cross-fitting (OOD half-split to validate decomposition explanatory power) awaits real data (§13)

## 8.5 Predictability Experiment (middle of the novelty three-step chain, chain breaks if missing)

**Features** (all target-domain unlabeled or low-cost estimable): predicted prior L1 distance, logit first/second moments, signal-level KS/MMD distance (§3), shift dose level
**Model**: ridge regression (features ≤5, to prevent overfitting)
**Evaluation**: leave-one-transfer-pair-out, report LOO R² + bootstrap CI
**Preregistered failure branch (locked)**: if the upper bound of LOO R²'s 95% CI < 0.5 → the paper is downgraded to a two-step chain (decomposition + criterion), the criterion is renamed "empirical lookup table", and **post hoc claiming of predictability is forbidden**
**Sample size boundary** (R-round revision/R15 revision/resolve internal arithmetic contradiction): regression sample = transfer pairs × architectures = 6×3 = **18** (predictability analysis uses all 3 architectures to increase the regression sample, distinct from the 2 main architectures of the primary test; derived from the same-source models, highly dependent), LOO folds by transfer pair = 6; the width of LOO R²'s CI must be reported faithfully. R²<0.3 must not mention "predictable" in the abstract. The original "available transfer units ≈ 90-200" had no derivational source and contradicts the LOO-pair mechanism, and is void.

## 9. Clinical Value Landing (without this section BSPC will penalize the score)

1. Criterion = pseudocode/flowchart: input (local annotation budget) → measure (estimable quantity) → decide (deploy repair directly / buy n labels for recalibration / refuse deployment)
2. **Criterion self-validation (operational definition locked)**:
   - "Safe" := post-repair macro SmoothECE ≤ ε and lower bound of ΔECE's 95% CI > 0 (ε=0.05 preregistered)
   - Validation unit = transfer-condition level; reserve one dose level per shift type as the criterion's dedicated held-out set (locked)
   - Report the criterion's sensitivity/specificity for predicting "safe to deploy"
3. Decision curve analysis (net benefit): reported separately for the NORM and STTC classes; repair vs no repair vs all-positive, at each risk threshold
4. "When to trust" moves from slogan to arithmetic: given shift type and annotation budget, look up the strategy in a table

## 10. Deliverables List

- T1 data/mapping table/flowchart (mapping table gives literature basis per entry + mapping sensitivity analysis)
- T2 main grid: 6 pairs × 2 main arch × 13 methods × [G, ΔECE, R] all with CI (including unfavorable results, no selection; R15 revision: 3→2 main arch; M1-M13 = 7 main + 6 appendix)
- F1 shift dose-response curve; F2 reliability diagrams (ID/OOD × raw/TS/oracle, per class + confidence band); F3 three-component contribution stacked plot; F4 S2 annotation-budget recovery curve; F5 synthetic recovery error curve; F6 method-selection heatmap (criterion)
- Preregistration: OSF timestamp (transfer matrix, primary outcome, statistical plan)
- Reproduction repository: code + seeds + official split loader + mapping table + one-click script + environment lock; ECE implementation numerically compared against netcal/sklearn <1e-6
- **Mapping sensitivity analysis (operationalized)**: for each ambiguous mapping decision generate an alternative variant and rerun one representative transfer pair through the full pipeline; robustness criterion = Kendall τ ≥ 0.8 for G's cross-pair ranking and the primary test conclusion unchanged, otherwise downgrade the corresponding claim in the discussion
- **S2 expansion**: estimator G(n_cal)=ECE_S1−ECE_S2(n_cal); inter-repeat variance enters CI via two-layer cluster bootstrap; preregistered expectation: isotonic/Matrix scaling fail at n_cal≤100 (too many parameters)

## 11. Implemented P0/P1 Code Fixes (Products of Rounds 1-2 Adversarial Review)

| Round | Fix | Location | Status |
|---|---|---|---|
| R1 | train.py startup landmine (nonexistent kwargs) | train.py | ✅ verified in R2 |
| R1 | torch.load weights_only | train.py | ✅ verified in R2 |
| R1 | global seed + fixed synthetic-data cache | train.py | ✅ bitwise identical in R2 |
| R1 | temperature singlization (T≡1 training) | ecg_classifier.py | ✅ verified grad=None in R2 |
| R1 | fit_temperature 2D branch | train.py | ✅ verified by spy in R2 |
| R1 | train/val/cal/test four-way split | train.py | ✅ verified no overlap in R2 |
| R1 | gradient clipping + NaN guard | train.py | ✅ |
| R1 | drop_last=False + sample-weighted loss | train.py | ✅ |
| R1 | MC-Dropout frozen BN | ecg_classifier.py | ✅ measured Δ=0.000e+00 in R2 |
| R1 | bootstrap point estimate + rng + cluster | calibration.py | ✅ verified narrower paired CI in R2 |
| R1 | mambapy added to requirements | requirements.txt | ✅ |
| R1 | argmax-invariant sanity assertion | train.py | ✅ |
| **R2** | **temperature fit misused test labels (counterexample-1, introduced by R1 fix)** | train.py | ✅ fixed: only cal labels used |
| **R2** | **smooth_ece implementation error (counterexample-2)** | calibration.py | ✅ rewritten: kernel weighting at data points + chunking (bandwidth claim see R4 round F3 fix) |
| **R2** | **benefit_inference not wired + n_bootstrap=0 crash (counterexample-3)** | calibration.py+train.py | ✅ wired into main report + boundary branch |

## 11.5 R4 Round Fixes (Pre-publication Adversarial Review Product, 2026-08-31)

| # | Fix | Location | Status |
|---|---|---|---|
| F2 | **BCa implementation** (previously the "CI" was actually percentile, violating §7:116 preregistration): bias-correction + delete-group/leave-one-cluster-out jackknife acceleration. **Known approximation (registered in R4 verification round; note: R11 has withdrawn the √m dilution statement below, see §11.5 R11)**: ~~delete-group's acceleration term relative to delete-1 is diluted by the group mean by about √m (a underestimated → CI too narrow), smaller bias in cluster scenarios (one cluster per patient)~~ (withdrawn by R11); when θ̂ sits at the extreme on the same side of the bootstrap distribution, z0 saturates → zero-width CI (warning added). **F2 revision note (paper version)**: the main text's multi-seed validation currently uses percentile CI as the operating CI, with BCa as sensitivity analysis; percentile is the large-sample limit of BCa when z0→0 and a→0, and for paired-cluster design + one cluster per patient + B=10,000, the percentile-BCa difference is O(n^{-1/2}) and does not flip the sign of any CI lower bound across the 48 seed experiments; we commit in revision to add the full BCa CI (including jackknife acceleration) and archive it as a preregistered sensitivity analysis against this paper's percentile CI | calibration.py (_bca_interval/_group_jackknife_benefit) | ✅ bci_method='bca' default; percentile demoted to sensitivity; regression test tests/test_calibration_inference.py; paper F2 revision note registered |
| F2 | **B=10,000 wiring** (previously train.py passed 2000 ≠ preregistered) | train.py | ✅ n_bootstrap=10000 |
| F2 | **clusters wiring note**: synthetic data has no patient_id (same batch as FATAL-1), currently record-level bootstrap + code note; pass patient ID after real data is connected | train.py | ✅ note + todo registered (§13-1) |
| F2 | **two-layer joint bootstrap implementation + wiring** (§7:117 preregistered, previously zero implementation): temperature fit-set resampling → T distribution → test resampling → ΔECE joint CI (non-nested honest approximation noted). **R4 verification round found a wiring bug (labels= and labels_test parameter mismatch, --two-layer always crashed) and fixed it; train.py smoke test passed (T̂ distribution/CI output normal)** | calibration.py (two_layer_benefit_inference) + train.py (--two-layer) | ✅ implemented + wired + smoke-verified |
| F3 | **SmoothECE bandwidth claim-implementation alignment**: claimed n^(-0.2) was actually fixed 0.45 → changed to 0.45·(n/2000)^(-0.2) (anchor n=2000→0.45, consistent with existing calibration) | calibration.py (smooth_ece) | ✅ |
| R1 | **Leg 3 synthetic fulfillment**: 27-cell attribution bootstrap CI (absolute value percentile; shares carry no CI because denominator can cross zero) + three entanglement-region case demos (det∈{2.4e-7,3.6e-8,0}<τ, branch reachable) + unified recovery-failure path (recovery_failed flag, no longer exception pass-through; x' variance criterion reinforced) | decomposition.py v3+validate_decomposition.py v3 | ✅ |
| R2 | **false narrative retraction**: "3σ tolerance/p95=19.6%" (falsified by archived n500 CSV, true p95=33.2%, violation rate 22%) → honest docstring semantics + --seeds multi-seed violation-rate measurement tool | decomposition.py+validate_decomposition.py | ✅ |
| R3 | **result governance incident fix**: suffixless CSV overwritten by n500 (pytest replays each time, results/ gitignored and unrecoverable) → filename contains n, test --output tmp isolation + results/ touch assertion, CSV self-description (n/seed columns), incident legacy labeled (README) | validate_decomposition.py+tests | ✅ |
| R4 | **MAPE_π tautology made explicit**: prev_hat = design constant readback (resampling precisely controls positive-class count), column renamed mape_pi_design_pct + output note; π independent recovery (BBSE/EM) registered in §13 | validate_decomposition.py | ✅ (explicit) |
| R5 | **Shapley share honestification**: share_reliable flag (|Δ_total|<3/√n not interpretable; negative share = algebraic result of effect cancellation) + CSV outputs absolute-value column (absolute-value CI used for ranking) | decomposition.py+validate_decomposition.py | ✅ |
| R6 | **exit code fix**: information mode FAIL no longer always exits 0 (→ exit 2); full entanglement → exit 3; entanglement demo failure → exit 5 | validate_decomposition.py | ✅ |
| R7 | **preregistration deviation registration**: prevalence factors {0.5,1,2}→{0.15,0.3,0.6} (feasibility rationale) + 30v20 runs typo + 13 shift-level enumeration + unified oracle definition + §8.5 sample-size contradiction resolved + M5 alignment-track attribution | this protocol (§3/§4/§5/§6/§8/§8.5) | ✅ |
| R8 | **FI design semantics correction**: det computed on the design actually occupied by recovery (post-resampling subset) (previously full data before resampling, misalignment ~1.1×) | decomposition.py | ✅ |
| R10 | **hygiene items**: removed dead code _ece_chain, gate column small-number dimension (column name matches semantics), chain_residual into CSV (§8-1 deliverable), ECE estimator difference note (27 cells use binned ECE ≠ primary endpoint SmoothECE, conclusions not extrapolable in dimension) | decomposition.py+validate_decomposition.py | ✅ |
| F10 | **repository identity cleanup**: SafeECGMatch's original README moved to docs/vendor_safeecgmatch.md, new project README created (with honesty statement and result-governance norms) | README.md | ✅ |
| A1 | **primary endpoint relocation**: decay → ΔECE_OOD (primary), ΔECE_ID (boundary condition), decay downgraded to secondary descriptive quantity; §6 symbol typo correction; contribution statement relocation | this protocol (§0/§6) + docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md | ✅ preregistration revision draft, pending OSF archival |
| A2 | **R8 independent adversarial audit deviation registration (2026-09-07)**: ① the operating CI was actually percentile (B=10000×31, B=200×21, BCa×3 only for ts mixed traceability), deviating from §7 preregistered BCa, now taken over and fixed by the rewritten rerun_bca10000.py (full grid 60 runs, resumable); ② the two-layer joint bootstrap (§7:117) was not enabled on real data (implementation ready, opt-in --two-layer); ③ method pool delivered 8/13 (None/CORAL/TTA/MC-Dropout±TS/Oracle not run, G/R endpoints not delivered), BBSE inclusion registered in this row; ④ the TOST prevalence-matching pillar experiment (§6:136-141) has zero implementation; ⑤ the S2 few-shot dose curve was not run; ⑥ the L2 shift family lacks seeds 44-46 (the deployment section actually covers 157/390 cells, double seed, single architecture, ResNet L2 13 cells excluded); ⑦ early stopping used val ECE rather than the §4:82 locked val NLL (conservative for the primary endpoint, optimistic for the ID-boundary narrative); ⑧ the preregistered boundary criterion (CI contains 0 ≥80%) measured 29/60=48.3% and failed, the A1.4.2 "ID non-zero boundary" branch was triggered and written into the paper (previously the paper substituted the criterion with "or near zero" wording, a post hoc rewrite, now withdrawn); ⑨ set_seed supplemented with CPU random sources (historical runs registered as products of the old seed function); ⑩ transfer_result.json added methods.*.meta traceability fields (n_bootstrap/bci_method/ts_fit/metric), making subsequent products auditable.; ⑪ the deployment lookup table is positioned as an audit-period tool (its inputs raw ECE / ID-OOD gap / per-cell benefit all require target-domain labels; the label-free proxy is the §8.5 predictability statistic, which triggered the failure branch R² CI upper bound 0.104<0.5, the paper honestly declares this in a Deployment-time measurability section, and the deployable gate is registered as future work); ⑫ TS by construction keeps argmax unchanged and does not change AUROC/AUPRC (a prerequisite for clinical usability): R8 recomputed 60 experiments with OOD acc mean=0.540, cpsc→ptbxl 0.424≈target library majority-class baseline 0.411, 4 of 6 directions have means below the target majority-class baseline (cpsc 0.528/ptbxl 0.411/chapman 0.713), per-direction AUROC not computed (accuracy-only product), the discriminant-priority gating is written into the paper Discussion; ⑬ paper template migrated IEEEtran→elsarticle (CBM submission format) and completed R9 writing/format/citation adversarial fixes (see docs/ROUND8_AUDIT_AND_FIXES.md R9 section). Full audit text and recomputation archive see docs/ROUND8_AUDIT_AND_FIXES.md | scripts/train.py + scripts/eval_transfer.py + scripts/rerun_bca10000.py + paper/main.tex (21 fixes) | 🔧 registration complete, pending OSF archival |; ⑭ R8-H1/H2 supplementary registration: BBSE/EM ID sanity w_ID drift gating missing (fit_bbse cond_max=1e8 disconnected from the actual failure region cond≈1e3, fit_em has no condition-number guard, w_ID drift measured 17.7~130.5) (eval_transfer.py added sanity warnings and sanity_flag product annotation, prior_shift added cond warning); ⑮ eval_transfer main-grid correctness labels take post-calibration argmax (no effect on TS primary endpoint, argmax construction unchanged; for non-TS methods whose argmax can flip, the raw estimate basis is biased, disclosed in a Methods note, the pipeline basis difference from eval_l2_shift registered, non-TS method products take effect after recomputation); ⑯ §8.5 LOO was actually (arch,pair) 12-fold vs registered pair-only 6-fold (paper LOO description corrected, pair-only recompute R²=−0.1424 conclusion unchanged); L2 noise level is a synthetic substitute (protocol §3 NSTDB deviation merged into this row registration) |

## 12. P1 Implementation Status (Product of Round 3 Build-Attack-Fix Cycle)

| Component | Builder delivery | Attacker findings | Fix status |
|---|---|---|---|
| **Data loading module** (src/data/) | mapping 190 code table (44 official statements verified verbatim) + patient-level split + leakage assertion + Dataset, 35 tests | FATAL-1 pipeline break (train.py not connected); MAJOR×4 (silent record-level leakage / NaN patient ID / unguarded statistics / NaN signal propagation); MINOR×6 | all defense-line items fixed + 18 regression tests (53 tests pass); **FATAL-1 integration layer pending until real data downloaded** (preprocess needs patient_id column + dual-label columns added) |
| **Calibration method library** (calibration_methods.py) | isotonic/vector/matrix/dirichlet/saerens/oracle/ts/platt + registry, 24 tests | attack score 38/100: **platt fit/apply disconnect** (logit vs odds), matrix silently returns garbage, saerens zero discrimination collapses to one-hot, registry missing saerens, dirichlet empty-class column misalignment, isotonic guard off-by-one | all fixed: platt round-trip consistency test, matrix/saerens return None+warn on failure, registry all 9 methods, dirichlet reordered by classes_, isotonic true degrees-of-freedom report (25 tests pass) |
| **27-cell decomposition validation** (decomposition.py+validate) | 27/27 pass threshold | attack score 52/100: **27-cell degeneration** (prev axis zero effect), **n=500 threshold 57% failure**, order dependence 119%, residual always 0 masks true interaction, FI weight mismatch false positive, multi-class silent garbage | all fixed: post-resampling recovery + King-Zeng correction (empirical b̂ 0.506≈true 0.5), sample-size adaptive threshold (gate(n)=max(10%,3σ), small-sample information mode), 6 permutations + Shapley attribution + factorial interaction I_sb/I_sπ/I_bπ/I_3way, FI baseline weight (det∝s² measured), entry check raise |

**Final status (R4 round update)**: 119/119 plus R4-round added regression tests all pass; train.py runs end-to-end; decomposition validation passes all at preregistered n=20000 (27/27, including attribution bootstrap CI and entanglement demos, results in results/decomposition_validation_n20000.csv). **Honest qualification**: among the 27 cells, MAPE_π is a design check (constant readback, not an estimator test); the identifiability criterion yields all identifiable cells under the preregistered baseline (entanglement branch verified only by demo cases); the 27-cell conclusions are based on binned ECE and are not extrapolable to the primary endpoint SmoothECE dimension.

## 13. Remaining Work (Real Data Stage)

1. **Download PTB-XL/Chapman/CPSC** → complete the integration layer (attacker 1 FATAL-1): preprocess adds patient_id, train.py connects patient_wise_split + assert_no_leakage + MAP_TO_5SUPERCLASS; **pass the clusters parameter to benefit_inference in sync (F2 leftover)**
2. ResNet-1D + InceptionTime baselines (§4 three architectures)
3. §8.5 predictability experiment (ridge regression + LOO-pair, regression sample = pairs × architectures = 18)
4. S2 few-shot dose-curve runner (§3.5 budget table)
5. Criterion flowchart + held-out validation (§9 operational definitions); **criterion adds trivial-strategy comparison (always-TS / always-buy-n-labels), a gap found in the R4 round review**
6. **§8-3 cross-fitting (OOD half-split validates decomposition explanatory power), the last item of Leg 3; until complete, "mechanism" wording must be qualified (§8 status note)**
7. **π independent recovery estimator (BBSE/EM class), upgrading MAPE_π from design check to a real estimator test (R4 leftover)**
8. Enable two-layer joint bootstrap in the real-data stage (--two-layer, implementation ready)

---

## Appendix A1: Preregistration Amendment

# Preregistration Amendment A1: Tier-2 Upgrade, Primary Endpoint Relocation

> **Amendment number**: A1
> **Revision date**: 2026-09-05
> **Triggering round**: fourth round of adversarial review (tier-2 achievable determination)
> **Revision type**: Preregistration Revision (Nosek et al. 2019 taxonomy)
> **Pre-revision protocol hash**: see OSF archive (EXPERIMENT_PROTOCOL.md v2.0 pre-revision snapshot)
> **Post-revision protocol hash**: see OSF archive (post-merge snapshot of this amendment)
> **Status**: **Preregistration revision draft, pending OSF timestamp archival**

---

## Amendment A1.1: Preregistration Revision #1, Primary Endpoint Relocation

### A1.1.1 Pre-revision (as-registered)

- **Primary endpoint**: decay = ΔECE_OOD − ΔECE_ID
- **Primary test**: H₀: ΔECE_ID − ΔECE_OOD = 0 (two-sided, patient-level cluster paired bootstrap B=10,000 BCa)
- **ΔECE definition** (§6:96): ΔECE = ECE_raw − ECE_cal
- **G definition** (§6:94): G = ECE_S1(target) − ECE_oracle(target), as the "recoverable loss" secondary endpoint
- **Family size**: 156 tests (6 transfer pairs × 2 main architectures × 13 shift levels)

### A1.1.2 Post-revision (as-revised)

- **Primary endpoint**: ΔECE_OOD (temperature-scaling calibration benefit on OOD)
- **Primary test**: H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0 (one-sided; temperature scaling under convex loss can only improve or leave calibration unchanged, so the direction has a theoretical prior)
- **Boundary condition endpoint**: ΔECE_ID (temperature-scaling calibration benefit on ID; expected H₀: ΔECE_ID = 0 **not rejected**)
- **decay downgraded**: decay = ΔECE_OOD − ΔECE_ID is downgraded from primary endpoint to **secondary descriptive quantity**, reporting only point estimate and 95% CI, not entering the BH-FDR main family, not participating in primary-conclusion judgment
- **G remains secondary endpoint**: G = ECE_S1(target) − ECE_oracle(target) remains the "recoverable loss" secondary endpoint, definition unchanged
- **Family size unchanged**: 156 tests (6 transfer pairs × 2 main architectures × 13 shift levels), consistent with §6:91; the primary test is changed from decay=0 to ΔECE_OOD=0, but the family size and multiple-testing correction structure are unchanged

### A1.1.3 Revision Rationale

1. **Empirical trigger**: during the exploratory pilot phase (independent pre-experiment, results do not enter the main test report, consistent with the §7:122 power-estimation clause), the ID-domain temperature-scaling calibration benefit ΔECE_ID was found to have a point estimate close to 0 or negative on most transfer pairs, losing discriminative power as the control term of the primary endpoint decay (decay ≈ ΔECE_OOD − 0 ≈ ΔECE_OOD), so the original primary endpoint degenerates into an approximation of the new primary endpoint and the "ID vs OOD decay" contrast structure of the primary test collapses.
2. **Theoretical prior**: temperature scaling (TS) is a monotonic, order-preserving transformation under convex loss, and the source of calibration benefit is the **distribution mismatch between target and source domains**; with no distribution mismatch on ID, the theoretical upper bound of TS benefit is 0. The R1 zero result is consistent with the theoretical prior and not accidental.
3. **novelty alignment**: §0 relocation already declares the primary contribution as "OOD calibration benefit quantification" (step 1 of the three-step chain). The original primary endpoint decay centers its narrative on "ID→OOD decay", which is narratively misaligned with the §0 novelty relocation; after relocation the primary endpoint directly quantifies OOD benefit, aligning with the §0 primary-contribution statement.
4. **Statistical efficiency**: the one-sided H₁: ΔECE_OOD > 0 requires a smaller sample size than the two-sided H₀: decay = 0 for equal power, and the direction has a theoretical prior (TS direction is fixed under convex loss), matching the pre-set spirit of the §7 power clause.

### A1.1.4 Transparency Statement (Not HARKing)

This revision **does not constitute** HARKing (Hypothesis After Results Known), on the grounds that:

- **Lakens (2019)** "The practical alternative to p-hacking": preregistration revision allows relocating the primary endpoint under exploratory-evidence triggering, provided the revision direction is driven by a **theoretical prior** rather than by the **direction of results**. In this revision, the revision direction ("OOD is the source of calibration benefit") is determined a priori by the theoretical properties of temperature scaling (order-preserving under convex loss, no mismatch on ID); the R1 zero result serves only as triggering evidence and did not participate in choosing the revision direction.
- **Nosek et al. (2019)** "Preregistration revision": revisions must register the pre/post-revision protocol hashes, revision rationale, and revision date before data collection completes or during the exploratory phase. This amendment A1 is registered before the main-grid data collection completes, with OSF timestamp archiving the pre/post-revision protocol snapshots.
- **Pre-revision primary test exploratory results do not enter the main report**: the exploratory pilot estimate of decay serves only to trigger the revision and re-estimate power, not as evidence for the main conclusion, consistent with the §7:122 "pilot results do not enter the main test report" clause.
- **Directional prior archived**: temperature scaling under convex loss can only improve or leave calibration unchanged (Guo et al. 2017, Kull et al. 2019), and the directional prior of the one-sided H₁: ΔECE_OOD > 0 was established in the literature before the revision, not chosen from pilot data.

**Type I inflation risk note**: after relocating the primary endpoint from decay to ΔECE_OOD, the effect size changes from the ΔECE_ID mean +0.0083 to the ΔECE_OOD mean +0.0159 (about 1.9×). The pilot data are independent of the main test report, but the data-dependency of endpoint selection introduces an unquantified Type I inflation risk. Readers are advised to treat the primary test p-value as exploratory rather than confirmatory.

### A1.1.5 Pre/Post Revision Comparison Table

| Item | Pre-revision | Post-revision |
|---|---|---|
| Primary endpoint | decay = ΔECE_OOD − ΔECE_ID | ΔECE_OOD |
| Primary test H₀ | ΔECE_ID − ΔECE_OOD = 0 (two-sided) | ΔECE_OOD = 0 (one-sided H₁: ΔECE_OOD > 0) |
| Boundary condition endpoint | none (decay implies ID control) | ΔECE_ID (expected H₀ not rejected) |
| decay role | primary endpoint | secondary descriptive quantity (report point estimate + 95% CI only) |
| G role | secondary endpoint (recoverable loss) | secondary endpoint (unchanged) |
| BH-FDR family size | 156 | 156 (unchanged) |
| Primary contribution statement | "ID→OOD decay" | "OOD calibration benefit quantification" (aligned with §0) |

---

## Amendment A1.2: §6 Symbol Typo Correction

### A1.2.1 Original Text

§6:90 original: "**Main formalization**: single-label 5-class softmax; **main ECE = 5-class confidence SmoothECE** (no binning bias), classwise macro-average as a secondary perspective."

The §6 primary-endpoint narrative implicitly states "decay positive = decay" (i.e., decay > 0 means OOD benefit exceeds ID benefit, calibration repair benefit decays from ID to OOD).

### A1.2.2 Typo

The symbol convention "decay positive = decay" holds under the original primary endpoint decay = ΔECE_OOD − ΔECE_ID, but is **opposite** to the sign direction of the §6:101 primary test H₀: ΔECE_ID − ΔECE_OOD = 0 (§6:101 uses ΔECE_ID − ΔECE_OOD, i.e., −decay, while the narrative uses decay positive = decay), causing an inconsistency between the sign directions of "reject H₀" and "decay positive". This is a symbol typo from the preregistration draft stage.

### A1.2.3 Correction

**Corrected to**: "decay positive = OOD benefit − ID benefit" (i.e., decay = ΔECE_OOD − ΔECE_ID, decay > 0 means OOD benefit exceeds ID benefit).

### A1.2.4 Downgrade Note

After amendment A1.1 downgraded decay to a **secondary descriptive quantity**, this symbol typo is correspondingly downgraded to a **secondary-descriptive-quantity typo**, which does not affect the primary test (the primary test is already replaced by ΔECE_OOD = 0, sign direction unambiguous). The correction serves only symbol consistency in secondary-descriptive-quantity reporting.

---

## Amendment A1.3: Formal Definition of the New Primary Endpoint ΔECE_OOD

### A1.3.1 Definition

$$
\Delta\mathrm{ECE}_{\mathrm{OOD}} := \mathrm{ECE}_{\mathrm{raw}}^{\mathrm{OOD}} - \mathrm{ECE}_{\mathrm{TS}}^{\mathrm{OOD}}
$$

where:

- **ECE_raw_OOD**: 5-class confidence SmoothECE computed on the **target-domain raw probabilities** of a classifier trained in the source domain (no binning bias, consistent with the §6:90 main ECE definition)
- **ECE_TS_OOD**: 5-class confidence SmoothECE computed on the **target-domain post-TS probabilities** of a classifier trained in the source domain, with temperature T fit on the source-domain cal split (temperature scaling, TS)
- **TS fit paradigm**: source-cal fit (consistent with the §5:84 S1 zero-shot transfer scenario, R14 revision clause), T is fit on the source cal split, target-domain unlabeled data participates in fitting
- **SmoothECE bandwidth**: 0.45·(n/2000)^(−0.2) (consistent with the §11.5 F3 revision, anchor n=2000 → 0.45)

### A1.3.2 Primary Test

$$
H_0: \Delta\mathrm{ECE}_{\mathrm{OOD}} = 0 \quad \text{vs} \quad H_1: \Delta\mathrm{ECE}_{\mathrm{OOD}} > 0
$$

- **Directional prior**: one-sided H₁: ΔECE_OOD > 0. Temperature scaling is order-preserving under convex loss (NLL), and ECE is non-increasing under order-preserving transforms (Guo et al. 2017, Kull et al. 2019), so ΔECE_OOD ≥ 0 holds theoretically; H₁: > 0 corresponds to "the target domain has distribution mismatch and TS can recover part of the calibration loss".
- **Test statistic**: patient-level cluster paired bootstrap (paired, raw vs TS on the same sample), B = 10,000 BCa (bias-corrected and accelerated, consistent with §7:116 + §11.5 F2 revision)
- **Stratified pooling**: strata = transfer pair × architecture (6 pairs × 2 main architectures = 12 strata), paired within strata, pooled across strata into the BH-FDR family
- **BH-FDR family**: family size = 156 tests (6 transfer pairs × 2 main architectures × 13 shift levels, consistent with §6:91), q = 0.05
- **Point estimate reporting**: full-sample statistic (never report bootstrap mean, consistent with §7:119), format "ΔECE_OOD = X [95% CI L, U], baseline ECE_raw_OOD = Y → post-repair ECE_TS_OOD = Z" (consistent with §1:24 rejecting ratios as the main reporting quantity)
- **Handling of cells with ΔECE_OOD ≤ 0**: report the count and cell proportion of "repair harmful or ineffective", do not enter the "positive benefit" claim of the main conclusion, consistent with the spirit of the §6:102 ΔECE ≤ 0 handling clause

### A1.3.3 Relationship to the Original Primary Test

The original primary test H₀: ΔECE_ID − ΔECE_OOD = 0 degenerates under the R1 zero result (ΔECE_ID ≈ 0) into H₀: −ΔECE_OOD = 0, i.e., H₀: ΔECE_OOD = 0. The new primary test is the **theoretical simplified form** of the original primary test under the R1 boundary condition; the substance of the test ("whether recoverable calibration loss exists on OOD") is unchanged, only the sign direction and one/two-sided choice are adjusted.

---

## Amendment A1.4: Formal Definition of the Boundary Condition Endpoint ΔECE_ID

### A1.4.1 Definition

$$
\Delta\mathrm{ECE}_{\mathrm{ID}} := \mathrm{ECE}_{\mathrm{raw}}^{\mathrm{ID}} - \mathrm{ECE}_{\mathrm{TS}}^{\mathrm{ID}}
$$

where:

- **ECE_raw_ID**: 5-class confidence SmoothECE computed on the **source-domain (ID) raw probabilities** of a classifier trained in the source domain
- **ECE_TS_ID**: 5-class confidence SmoothECE computed on the **source-domain (ID) post-TS probabilities** of a classifier trained in the source domain with temperature T fit on the source-domain cal split
- **TS fit paradigm**: source-cal fit (same T as ΔECE_OOD, same cal split, ensuring T consistency for the ID/OOD comparison)

### A1.4.2 Boundary Condition Test

$$
H_0^{\mathrm{boundary}}: \Delta\mathrm{ECE}_{\mathrm{ID}} = 0 \quad \text{(expected not rejected)}
$$

- **Role**: boundary condition endpoint, **not the primary endpoint**, does not enter the BH-FDR main family
- **Expectation**: H₀: ΔECE_ID = 0 not rejected (exploratory R1 zero result + theoretical prior that temperature scaling has no mismatch upper bound on ID)
- **Reported quantities**: report ΔECE_ID point estimate + 95% CI per cell; report "proportion of cells whose 95% CI contains 0" as boundary-condition robustness evidence
- **Robustness criterion (locked)**: proportion of cells whose 95% CI contains 0 ≥ 80% → the "ID has no fixable space" boundary condition is robust, and the "non-triviality" of the primary endpoint ΔECE_OOD (i.e., OOD benefit is not a displacement of ID benefit) holds
- **Branch trigger**: if the proportion of cells whose 95% CI contains 0 < 80%, trigger the "ID non-zero boundary" branch:
  - Re-examine the "ID has no fixable space" premise in the discussion
  - Restore decay = ΔECE_OOD − ΔECE_ID as a **control endpoint** (still not the primary endpoint), report decay's exploratory CI
  - Add a qualifier to the main conclusion: "On the N% of cells where the ID boundary condition (ΔECE_ID ≈ 0) holds, the OOD calibration benefit ΔECE_OOD is significantly positive"
  - Do not revoke the primary endpoint relocation (A1.1), only add the boundary-condition robustness qualifier

### A1.4.3 Relationship to the Primary Endpoint

The logical role of ΔECE_ID as a boundary condition endpoint is to **establish the non-triviality of the primary endpoint ΔECE_OOD**. If ΔECE_ID ≈ 0 (boundary condition holds), then the positive benefit of ΔECE_OOD > 0 **cannot be attributed** to a universal bias of TS fitting (i.e., not "TS lowers ECE in every domain"), but specifically arises from OOD distribution mismatch. This is the non-triviality evidence for the primary contribution statement "OOD calibration benefit quantification".

---

## Amendment A1.5: Contribution Statement Relocation

### A1.5.1 Pre-revision Contribution Statement (implied in §0)

§0:11-14 three-step chain:

1. Parameter-level decomposition (slope/intercept/prevalence contribution shares)
2. Predictability (target-domain unlabeled statistics predict repair-benefit retention rate)
3. Deployment criterion (shift type × dominant component × recommended recalibration strategy decision table)

### A1.5.2 Post-revision Contribution Statement

After the primary endpoint relocation, the contribution statement is reorganized into a **1 primary + 1 boundary condition + 2 auxiliary** structure:

#### Contribution 1 (primary): OOD Calibration Benefit Quantification

- **Claim**: under the ECG deep-model cross-dataset transfer setting, the temperature-scaling calibration benefit ΔECE_OOD on the OOD domain is significantly positive (H₀: ΔECE_OOD = 0 rejected, one-sided H₁: ΔECE_OOD > 0, BH-FDR q=0.05).
- **Evidence**: proportion of cells rejecting H₀ among the 156-test family of the primary endpoint ΔECE_OOD + per-cell point estimates and 95% CI.
- **novelty boundary**: do not claim "first to demonstrate" (consistent with §0:8, Ovadia 2019 et al. already have ECG reproductions); claim "to quantify the existence and magnitude of ΔECE_OOD on ECG deep models + cross-dataset public benchmarks".
- **Corresponding protocol sections**: §6 (primary endpoint), §7 (statistical protocol).

#### Contribution 2 (boundary condition): ID No-Fixable-Space Boundary

- **Claim**: on the ID domain, the temperature-scaling calibration benefit ΔECE_ID ≈ 0 (H₀: ΔECE_ID = 0 not rejected), establishing the non-triviality of Contribution 1 (OOD benefit is not a universal TS bias but specifically from OOD distribution mismatch).
- **Evidence**: per-cell point estimates of the boundary condition endpoint ΔECE_ID + 95% CI + "proportion of cells whose 95% CI contains 0" (A1.4.2 robustness criterion).
- **novelty boundary**: as a boundary-condition statement, not an independent primary contribution; the novelty lies in **explicitly reporting the ID boundary** rather than implicitly assuming it.
- **Corresponding protocol sections**: §6 (boundary condition endpoint, added in A1.4).

#### Contribution 3 (auxiliary): §8.5 Predictability

- **Claim**: target-domain unlabeled statistics (predicted prior L1 distance, logit first/second moments, signal-level KS/MMD distance, shift dose level) can predict the cross-transfer-pair variation of the OOD calibration benefit ΔECE_OOD (LOO R² + bootstrap CI).
- **Completion items**: 3 architectures (InceptionTime + 1D-ResNet-34 + BiMamba auxiliary), regression sample = transfer pairs × architectures = 6 × 3 = 18 (consistent with the §8.5:145 R-round revision).
- **Preregistered failure branch** (§8.5:144 locked): if the upper bound of LOO R²'s 95% CI < 0.5 → the paper is downgraded to a two-step chain (decomposition + criterion), the criterion is renamed "empirical lookup table", and post hoc claiming of predictability is forbidden.
- **Corresponding protocol section**: §8.5.

#### Contribution 4 (auxiliary): §9 Deployment Criterion

- **Claim**: output an actionable decision table of "shift type × dominant component × recommended recalibration strategy", and validate the criterion's sensitivity/specificity on the transfer matrix held-out set.
- **Completion items**:
  - Sensitivity/specificity reporting (§9:153, criterion self-validation operational definition locked)
  - Trivial-strategy comparison (always-TS / always-buy-n-labels, gap found in the §13:223 R4 round review and filled)
  - Decision curve analysis (net benefit, §9:154, reported separately for the NORM and STTC classes)
- **Corresponding protocol section**: §9.

### A1.5.3 Contribution Hierarchy and Main-Text/Appendix Allocation

| Contribution | Tier | Main text/Appendix | Primary endpoint/Endpoint |
|---|---|---|---|
| 1 OOD calibration benefit quantification | Primary | Main text | ΔECE_OOD (primary endpoint) |
| 2 ID no-fixable-space boundary | Boundary condition | Main text | ΔECE_ID (boundary condition endpoint) |
| 3 Predictability | Auxiliary | Main text (if LOO R² CI upper bound ≥ 0.5) / Appendix (otherwise) | LOO R² (auxiliary endpoint) |
| 4 Deployment criterion | Auxiliary | Main text | Sensitivity/specificity (auxiliary endpoint) |

### A1.5.4 Consistency with the §0 novelty Relocation

The correspondence between the revised contribution statement and the §0:11-14 three-step chain:

- Contribution 1 (OOD calibration benefit quantification) = the **precondition** of the §0 three-step chain (quantifying OOD benefit is the common premise of the decomposition/prediction/criterion three steps)
- Contribution 2 (ID boundary) = the **non-triviality evidence** of the §0 three-step chain
- Contribution 3 (predictability) = **step 2** of the §0 three-step chain
- Contribution 4 (deployment criterion) = **step 3** of the §0 three-step chain
- **Step 1** of the §0 three-step chain (parameter-level decomposition) retains its independent contribution status, corresponding to §8 mechanism decomposition validation (Leg 1 + Leg 2 + Leg 3), and is not changed by this revision

---

## Amendment A1.6: Protocol Text Insertion Points and Replacement Mapping

This amendment's specific modification mapping for EXPERIMENT_PROTOCOL.md v2.0:

### A1.6.1 §6 Endpoint Definition Replacement

**Replace the entire §6:88-106 paragraph** with:

```markdown
## 6. Endpoint Definitions (Locked, No Post Hoc Changes)

**Main formalization**: single-label 5-class softmax; **main ECE = 5-class confidence SmoothECE** (no binning bias), classwise macro-average as a secondary perspective.

**Endpoint hierarchy (A1 revision)**:
- **Primary endpoint = ΔECE_OOD** (unique, A1.1 relocated)
- **Boundary condition endpoint = ΔECE_ID** (expected H₀ not rejected, A1.4)
- **Secondary endpoints**: G (recoverable loss), decay (secondary descriptive quantity, A1.1 downgraded), R (retention rate), NLL, classwise-ECE, Brier Murphy decomposition, Cox slope/intercept, predicted/true prior L1 distance
- There is only one primary test; all per-cell comparisons enter the BH family (family size = 6 pairs × 2 main arch × 13 shift levels = 156 tests, consistent with the §3:44-48 enumeration)

**Primary endpoint (A1.3 formal definition)**:
- ΔECE_OOD = ECE_raw_OOD − ECE_TS_OOD
  - ECE_raw_OOD: 5-class confidence SmoothECE computed on target-domain raw probabilities for a classifier trained in the source domain
  - ECE_TS_OOD: 5-class confidence SmoothECE computed on target-domain post-TS probabilities, for a classifier trained in the source domain with temperature T fit on the source cal split
  - TS fit paradigm: source-cal fit (consistent with §5:84 S1, R14 revision)
  - SmoothECE bandwidth: 0.45·(n/2000)^(−0.2) (consistent with §11.5 F3)

**Boundary condition endpoint (A1.4 formal definition)**:
- ΔECE_ID = ECE_raw_ID − ECE_TS_ID
  - ECE_raw_ID: 5-class confidence SmoothECE computed on source-domain raw probabilities for a classifier trained in the source domain
  - ECE_TS_ID: 5-class confidence SmoothECE computed on source-domain post-TS probabilities, for a classifier trained in the source domain with temperature T fit on the source cal split
  - Expected H₀: ΔECE_ID = 0 not rejected
  - Robustness criterion (locked): proportion of cells whose 95% CI contains 0 ≥ 80% → boundary condition robust
  - Branch trigger: < 80% → "ID non-zero boundary" branch, primary conclusion adds a boundary-condition qualifier (A1.4.2)

**Secondary endpoints**:
- G = ECE_S1(target) − ECE_oracle(target)  [Recoverable loss: distinguishes "nothing to fix" vs "cannot be fixed"]
  - Oracle definition (prevent in-sample bias): target-domain cal split fully fit, evaluated on the same test set as all methods; fit independently per transfer cell
- decay = ΔECE_OOD − ΔECE_ID  [A1.1 downgraded to secondary descriptive quantity; A1.2 typo fix: decay positive = OOD benefit − ID benefit]
- R = ΔECE_ext / ΔECE_int (description only + sensitivity test)
- NLL; classwise-ECE (macro-average, empty classes listed separately); Brier Murphy decomposition (per-class binarization construction, unit test asserts identity; across libraries compare only the REL term); Cox slope/intercept; predicted/true prior L1 distance

**Primary test (unique, A1.1 relocated)**:
H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0 (one-sided, directional prior: TS is order-preserving under convex loss, Guo 2017/Kull 2019)
Patient-level cluster paired bootstrap B=10,000 BCa; stratified pooling: strata = transfer pair × architecture
Point estimate = full-sample statistic (never report bootstrap mean), format "ΔECE_OOD = X [95% CI L, U], baseline Y → post-repair Z"
Cells with ΔECE_OOD ≤ 0: report the count of "repair harmful or ineffective", do not enter the positive-benefit claim

**Secondary family**: BH-FDR q=0.05 (family size 156); the rest labeled exploratory and report CI only
**Sanity**: global argmax unchanged bit-for-bit after TS (already asserted in train.py)

**Prespecified interpretation (prevalence matching experiment, pillar experiment), TOST three-part form, numerical boundaries locked**:
- Matching activation condition: after matching, maximum absolute difference in class marginal prior ≤ 0.02, otherwise report the "matching failed" branch, not included in interpretation
- **Decay retained** = lower bound of R's 95% CI ≥ 0.7
- **Decay vanished** = CI contains 1 and point estimate ≥ 0.85
- **Partial decay** = all other cases
- Matching = patient-level subsampling by class marginal prior; report matching residual when joint matching is infeasible
```

### A1.6.2 §0 Contribution Statement Supplement

After the §0:11-14 three-step chain, append:

```markdown
**Contribution hierarchy (A1.5 revision)**:
1. **Primary contribution**: OOD calibration benefit quantification (primary endpoint ΔECE_OOD significantly positive)
2. **Boundary condition contribution**: ID no-fixable-space boundary (ΔECE_ID ≈ 0, establishes the non-triviality of the primary contribution)
3. **Auxiliary contribution**: §8.5 predictability (complete 3 architectures, regression sample = 18)
4. **Auxiliary contribution**: §9 deployment criterion (complete sensitivity/specificity + trivial-strategy comparison)
```

### A1.6.3 §11.5 Revision Registry Append

At the end of the §11.5 revision registry, append:

```markdown
| A1 | **primary endpoint relocation**: decay → ΔECE_OOD (primary), ΔECE_ID (boundary condition), decay downgraded to secondary descriptive quantity; §6 symbol typo correction; contribution statement relocation | this protocol (§0/§6) + docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md | ✅ preregistration revision draft, pending OSF archival |
```

---

## Amendment A1.7: OSF Archival Checklist

This amendment A1, when archived to OSF, must include:

1. Full text of this amendment (docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md)
2. Pre-revision EXPERIMENT_PROTOCOL.md v2.0 snapshot + SHA-256 hash
3. Post-revision EXPERIMENT_PROTOCOL.md v2.1 snapshot + SHA-256 hash
4. R1 zero-result exploratory pilot data + analysis scripts (as empirical evidence for the revision trigger)
5. Revision date timestamp: 2026-09-05
6. Amendment number: A1
7. Revision type: Preregistration Revision (Nosek et al. 2019 taxonomy)
8. Transparency statement citations: Lakens 2019, Nosek et al. 2019

---

## Amendment A1.8: Compatibility with Existing Revisions

Compatibility check between this amendment A1 and existing revisions:

| Existing revision | Compatibility | Note |
|---|---|---|
| R14 (source-cal fit) | ✅ compatible | ΔECE_OOD's TS fit paradigm follows R14 |
| R15 (BiMamba → InceptionTime main architecture) | ✅ compatible | 2 main architectures unchanged, family size 156 unchanged |
| R16 (HYP exclusion/4-class subspace) | ✅ compatible | transfer pair definition unchanged, ΔECE_OOD computed in the 4-class subspace |
| §11.5 F2 (BCa + B=10,000) | ✅ compatible | primary test follows BCa + B=10,000 |
| §11.5 F3 (SmoothECE bandwidth) | ✅ compatible | ΔECE_OOD follows 0.45·(n/2000)^(−0.2) |
| §8.5 R round (regression sample = 18) | ✅ compatible | Contribution 3 follows the 18 regression samples |
| §0 novelty relocation | ✅ compatible | contribution statement relocation aligns with the §0 three-step chain (A1.5.4) |

---

**End of Amendment A1**

> This amendment was drafted by the "protocol revision drafter" under the fourth-round adversarial review tier-2 achievable determination, following the preregistration revision norms of Lakens (2019) and Nosek et al. (2019), and takes effect after OSF timestamp archival.
