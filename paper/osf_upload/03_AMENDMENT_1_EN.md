# Preregistration Amendment A1: Zone 2 Upgrade, Primary Endpoint Relocation

> **Amendment number**: A1
> **Amendment date**: 2026-09-05
> **Triggering round**: fourth round of adversarial review (Zone 2 attainability determination)
> **Amendment type**: preregistration revision (Preregistration Revision, per Nosek et al. 2019)
> **Pre-amendment protocol hash**: see OSF archive (EXPERIMENT_PROTOCOL.md v2.0 pre-amendment snapshot)
> **Post-amendment protocol hash**: see OSF archive (post-merge snapshot of this amendment)
> **Status**: **preregistration revision draft, pending OSF timestamp archiving**

---

## Amendment A1.1: Preregistration Revision 1, Primary Endpoint Relocation

### A1.1.1 As-registered

- **Primary endpoint**: decay = ΔECE_OOD − ΔECE_ID
- **Primary test**: H₀: ΔECE_ID − ΔECE_OOD = 0 (two-sided, patient-level cluster paired bootstrap B=10,000 BCa)
- **ΔECE definition** (§6:96): ΔECE = ECE_raw − ECE_cal
- **G definition** (§6:94): G = ECE_S1(target) − ECE_oracle(target), a secondary endpoint for "recoverable loss"
- **Family size**: 156 tests (6 transfer pairs × 2 primary architectures × 13 shift levels)

### A1.1.2 As-revised

- **Primary endpoint**: ΔECE_OOD (calibration gain from temperature scaling on OOD)
- **Primary test**: H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0 (one-sided; under convex loss, temperature scaling can only improve or leave calibration unchanged, so the direction has a theoretical prior)
- **Boundary-condition endpoint**: ΔECE_ID (calibration gain from temperature scaling on ID; expected H₀: ΔECE_ID = 0 not rejected)
- **decay downgrade**: decay = ΔECE_OOD − ΔECE_ID is demoted from primary endpoint to a secondary descriptive quantity, reporting only point estimate and 95% CI, excluded from the BH-FDR primary family and excluded from primary-conclusion determination
- **G remains secondary endpoint**: G = ECE_S1(target) − ECE_oracle(target) remains the "recoverable loss" secondary endpoint, definition unchanged
- **Family size unchanged**: 156 tests (6 transfer pairs × 2 primary architectures × 13 shift levels), consistent with §6:91; the primary test replaces decay=0 with ΔECE_OOD=0, but family size and the multiple-testing correction structure are unchanged

### A1.1.3 Rationale

1. **Empirical trigger**: the exploratory pilot phase (an independent pre-experiment whose results do not enter the primary analysis report, consistent with the power-estimation clause §7:122) found that the ID-domain temperature-scaling calibration gain ΔECE_ID had point estimates near 0 or negative across most transfer pairs. As the comparison term of the primary endpoint decay, it lost discriminative power. decay ≈ ΔECE_OOD − 0 ≈ ΔECE_OOD, and the original primary endpoint collapsed into an approximation of the new primary endpoint. The "ID vs OOD decay" contrast structure of the primary test collapsed.
2. **Theoretical prior**: temperature scaling (TS) is an order-preserving monotonic transformation under convex loss, and the source of calibration gain is the distribution mismatch between target and source domains. The ID domain has no distribution mismatch, so the theoretical upper bound of TS gain is 0. The R1 null result is consistent with the theoretical prior, not accidental.
3. **novelty alignment**: §0 relocation already declared the primary contribution as "quantifying OOD calibration gain" (step 1 of the three-step chain). The original primary endpoint decay framed "ID to OOD decay" as the narrative core, creating a narrative mismatch with the §0 novelty relocation. After relocation, the primary endpoint directly quantifies OOD gain, aligning with the §0 primary-contribution statement.
4. **Statistical efficiency**: the one-sided H₁: ΔECE_OOD > 0 requires a smaller sample size than the two-sided H₀: decay = 0 at equal power, and the direction has a theoretical prior (TS direction is determined under convex loss), consistent with the preset spirit of the §7 power clause.

### A1.1.4 Transparency Statement (Not HARKing)

This amendment does NOT constitute HARKing (Hypothesizing After Results are Known), on the following grounds:

- **Lakens (2019)**, "The practical alternative to p-hacking": preregistration revision allows relocating the primary endpoint when triggered by exploratory evidence, provided the revision direction is driven by a theoretical prior rather than by the result direction. In this amendment, the revision direction ("OOD is the source of calibration gain") is determined a priori by the theoretical properties of temperature scaling (order-preserving under convex loss, no mismatch in the ID domain). The R1 null result serves only as triggering evidence and did not participate in selecting the revision direction.
- **Nosek et al. (2019)**, "Preregistration revision": the revision must register the pre- and post-amendment protocol hashes, the rationale, and the date before data collection completes or during the exploratory phase. This amendment A1 is registered before the main-grid data collection completes; OSF timestamp archives the pre- and post-amendment protocol snapshots.
- **Exploratory results of the pre-amendment primary test do not enter the primary report**: the exploratory pilot estimate of decay is used only to trigger the revision and re-estimate power, and is not evidence for the primary conclusion, consistent with §7:122 ("pilot results do not enter the primary analysis report").
- **Direction prior archived**: temperature scaling under convex loss can only improve or leave calibration unchanged (Guo et al. 2017, Kull et al. 2019), so the direction prior of one-sided H₁: ΔECE_OOD > 0 was established in the literature before the amendment, not chosen from pilot data.

### A1.1.5 As-registered vs As-revised Comparison Table

| Item | As-registered | As-revised |
|---|---|---|
| Primary endpoint | decay = ΔECE_OOD − ΔECE_ID | ΔECE_OOD |
| Primary test H₀ | ΔECE_ID − ΔECE_OOD = 0 (two-sided) | ΔECE_OOD = 0 (one-sided H₁: ΔECE_OOD > 0) |
| Boundary-condition endpoint | none (decay implicitly carries the ID comparison) | ΔECE_ID (expected H₀ not rejected) |
| decay role | primary endpoint | secondary descriptive quantity (report point estimate + 95% CI only) |
| G role | secondary endpoint (recoverable loss) | secondary endpoint (unchanged) |
| BH-FDR family size | 156 | 156 (unchanged) |
| Primary contribution statement | "ID to OOD decay" | "OOD calibration gain quantification" (aligned with §0) |

---

## Amendment A1.2: §6 Symbol Typo Correction

### A1.2.1 Original text

§6:90 original: "Primary formalization: single-label 5-class softmax; primary ECE = 5-class confidence SmoothECE (no binning bias), classwise macro-average as secondary perspective."

The §6 primary-endpoint narrative implicitly stated "decay positive = decay" (i.e., decay > 0 means OOD gain exceeds ID gain, and the calibration-repair gain decays from ID to OOD).

### A1.2.2 Typo

The symbol convention "decay positive = decay" holds under the original primary endpoint decay = ΔECE_OOD − ΔECE_ID, but is opposite in sign to the primary test H₀: ΔECE_ID − ΔECE_OOD = 0 in §6:101. The H₀ in §6:101 uses ΔECE_ID − ΔECE_OOD (i.e., −decay), while the narrative uses decay positive = decay, so the sign directions of "reject H₀" and "decay positive" are inconsistent. This is a symbol typo from the preregistration draft stage.

### A1.2.3 Correction

**Corrected to**: "decay positive = OOD gain − ID gain" (i.e., decay = ΔECE_OOD − ΔECE_ID, decay > 0 means OOD gain exceeds ID gain).

### A1.2.4 Downgrade Note

After amendment A1.1 demoted decay to a secondary descriptive quantity, this symbol typo is likewise demoted to a secondary-descriptive-quantity typo. It does not affect the primary test (now replaced by ΔECE_OOD = 0, whose sign direction is unambiguous). The correction serves only symbol consistency in the secondary descriptive quantity report.

---

## Amendment A1.3: Formal Definition of the New Primary Endpoint ΔECE_OOD

### A1.3.1 Definition

$$
\Delta\mathrm{ECE}_{\mathrm{OOD}} := \mathrm{ECE}_{\mathrm{raw}}^{\mathrm{OOD}} - \mathrm{ECE}_{\mathrm{TS}}^{\mathrm{OOD}}
$$

where:

- **ECE_raw_OOD**: 5-class confidence SmoothECE computed on target-domain raw probabilities by the classifier trained on the source domain (no binning bias, consistent with the primary ECE definition in §6:90)
- **ECE_TS_OOD**: 5-class confidence SmoothECE computed on target-domain post-TS probabilities, where the source-domain cal split fits temperature T (temperature scaling, TS)
- **TS fitting paradigm**: source cal fit (consistent with §5:84 S1 zero-shot transfer scenario, R14 revision clause); T is fit on the source cal split, and the target domain contributes no labels to fitting
- **SmoothECE bandwidth**: 0.45·(n/2000)^(−0.2) (consistent with §11.5 F3 revision; anchor n=2000 → 0.45)

### A1.3.2 Primary test

$$
H_0: \Delta\mathrm{ECE}_{\mathrm{OOD}} = 0 \quad \text{vs} \quad H_1: \Delta\mathrm{ECE}_{\mathrm{OOD}} > 0
$$

- **Direction prior**: one-sided H₁: ΔECE_OOD > 0. Temperature scaling is order-preserving under convex loss (NLL); ECE is non-increasing under order-preserving transformations (Guo et al. 2017, Kull et al. 2019), so ΔECE_OOD ≥ 0 holds theoretically. H₁: > 0 corresponds to "the target domain has distribution mismatch and TS can recover part of the calibration loss."
- **Test statistic**: patient-level cluster paired bootstrap (paired, raw vs TS on the same samples), B = 10,000 BCa (bias-corrected and accelerated, consistent with §7:116 + §11.5 F2 revision)
- **Stratified pooling**: strata = transfer pair × architecture (6 pairs × 2 primary architectures = 12 strata); pairs within strata, pooled across strata into the BH-FDR family
- **BH-FDR family**: family size = 156 tests (6 transfer pairs × 2 primary architectures × 13 shift levels, consistent with §6:91), q = 0.05
- **Point-estimate report**: full-sample statistic (never report bootstrap mean, consistent with §7:119), format "ΔECE_OOD = X [95% CI L, U], baseline ECE_raw_OOD = Y → post-repair ECE_TS_OOD = Z" (consistent with §1:24 refusing ratios as primary report quantities)
- **Cell handling for ΔECE_OOD ≤ 0**: report the count and grid proportion of "repair harmful or ineffective", excluded from the primary conclusion's "positive gain" statement, consistent with the spirit of the ΔECE ≤ 0 handling clause in §6:102

### A1.3.3 Relation to the Original Primary Test

The original primary test H₀: ΔECE_ID − ΔECE_OOD = 0 collapses under the R1 null result (ΔECE_ID ≈ 0) to H₀: −ΔECE_OOD = 0, i.e., H₀: ΔECE_OOD = 0. The new primary test is the theoretical simplified form of the original primary test under the R1 boundary condition. The substance of the test ("whether recoverable calibration loss exists on OOD") is unchanged; only the sign direction and the one- vs two-sided choice are adjusted.

---

## Amendment A1.4: Formal Definition of the Boundary-Condition Endpoint ΔECE_ID

### A1.4.1 Definition

$$
\Delta\mathrm{ECE}_{\mathrm{ID}} := \mathrm{ECE}_{\mathrm{raw}}^{\mathrm{ID}} - \mathrm{ECE}_{\mathrm{TS}}^{\mathrm{ID}}
$$

where:

- **ECE_raw_ID**: 5-class confidence SmoothECE computed on source-domain (ID) raw probabilities by the classifier trained on the source domain
- **ECE_TS_ID**: 5-class confidence SmoothECE computed on source-domain (ID) post-TS probabilities, where the source-domain cal split fits temperature T
- **TS fitting paradigm**: source cal fit (same T as ΔECE_OOD, same cal split, ensuring T consistency for ID/OOD comparison)

### A1.4.2 Boundary-condition test

$$
H_0^{\mathrm{boundary}}: \Delta\mathrm{ECE}_{\mathrm{ID}} = 0 \quad \text{(expected not rejected)}
$$

- **Role**: boundary-condition endpoint, not primary, excluded from the BH-FDR primary family
- **Expectation**: H₀: ΔECE_ID = 0 is not rejected (exploratory R1 null result + theoretical prior that temperature scaling has zero upper bound on the ID domain with no mismatch)
- **Reported quantity**: report ΔECE_ID point estimate + 95% CI per cell; report "proportion of cells whose 95% CI contains 0" as boundary-condition robustness evidence
- **Robustness criterion (hard-coded)**: proportion of cells whose 95% CI contains 0 ≥ 80% → boundary condition "no repairable space on ID" is robust, and the "non-triviality" of primary endpoint ΔECE_OOD (i.e., OOD gain is not a shift of ID gain) holds
- **Branch trigger**: if the proportion of cells whose 95% CI contains 0 < 80%, trigger the "ID non-zero boundary" branch:
  - Re-examine the "no repairable space on ID" premise in the discussion
  - Restore decay = ΔECE_OOD − ΔECE_ID as a comparison endpoint (still not primary), report the exploratory CI of decay
  - Add a qualifier to the primary conclusion: "On the N% of cells where the ID boundary condition (ΔECE_ID ≈ 0) holds, the OOD calibration gain ΔECE_OOD is significantly positive"
  - Do not revoke the primary-endpoint relocation (A1.1); only add the boundary-condition robustness qualifier

### A1.4.3 Relation to the Primary Endpoint

The logical role of ΔECE_ID as a boundary-condition endpoint is to establish the non-triviality of the primary endpoint ΔECE_OOD. If ΔECE_ID ≈ 0 (boundary condition holds), then a positive gain ΔECE_OOD > 0 cannot be attributed to a general bias of TS fitting (i.e., not "TS lowers ECE on any domain"), but specifically arises from OOD distribution mismatch. This is the non-triviality evidence for the primary contribution statement "OOD calibration gain quantification".

---

## Amendment A1.5: Contribution Statement Relocation

### A1.5.1 Pre-amendment Contribution Statement (implied in §0)

§0:11-14 three-step chain:
1. Parameter-level decomposition (slope/intercept/prevalence contribution shares)
2. Predictability (target-domain unlabeled statistics predict repair-gain retention rate)
3. Deployment criterion (shift type × dominant component × recommended recalibration-strategy decision table)

### A1.5.2 Post-amendment Contribution Statement

After the primary-endpoint relocation, the contribution statement is reorganized into a "1 primary + 1 boundary condition + 2 auxiliary" structure:

#### Contribution 1 (primary): OOD calibration gain quantification

- **Statement**: under the ECG deep-model cross-dataset transfer setting, the temperature-scaling calibration gain ΔECE_OOD on the OOD domain is significantly positive (H₀: ΔECE_OOD = 0 rejected, one-sided H₁: ΔECE_OOD > 0, BH-FDR q=0.05).
- **Evidence**: proportion of cells rejecting H₀ among the 156-test family of primary endpoint ΔECE_OOD + per-cell point estimates and 95% CI.
- **novelty boundary**: does not claim "first proof" (consistent with §0:8; Ovadia 2019 et al. already reproduced ECG); claims "quantifying the existence and magnitude of ΔECE_OOD on ECG deep models + a public cross-dataset benchmark".
- **Corresponding protocol section**: §6 (primary endpoint), §7 (statistical protocol).

#### Contribution 2 (boundary condition): ID no-repairable-space boundary

- **Statement**: on the ID domain, the temperature-scaling calibration gain ΔECE_ID ≈ 0 (H₀: ΔECE_ID = 0 not rejected), establishing the non-triviality of Contribution 1, that OOD gain is not a general TS bias but specifically arises from OOD distribution mismatch.
- **Evidence**: per-cell point estimate + 95% CI of boundary-condition endpoint ΔECE_ID + "proportion of cells whose 95% CI contains 0" (robustness criterion, A1.4.2).
- **novelty boundary**: as a boundary-condition statement, not an independent primary contribution; the novelty lies in explicitly reporting the ID boundary rather than assuming it implicitly.
- **Corresponding protocol section**: §6 (boundary-condition endpoint, added in A1.4).

#### Contribution 3 (auxiliary): §8.5 predictability

- **Statement**: target-domain unlabeled statistics (predictive prior L1 distance, logit first/second moments, signal-level KS/MMD distance, shift dose tier) can predict the cross-transfer-pair variation of OOD calibration gain ΔECE_OOD (LOO R² + bootstrap CI).
- **Filling item**: 3 architectures (InceptionTime + 1D-ResNet-34 + BiMamba auxiliary), regression sample = transfer pairs × architectures = 6 × 3 = 18 (consistent with §8.5:145 R-round revision).
- **Preregistration failure branch** (hard-coded, §8.5:144): if the 95% CI upper bound of LOO R² < 0.5 → paper downgraded to a two-step chain (decomposition + criterion), criterion renamed "empirical lookup table", post-hoc ratification of predictability prohibited.
- **Corresponding protocol section**: §8.5.

#### Contribution 4 (auxiliary): §9 deployment criterion

- **Statement**: output an actionable decision table of "shift type × dominant component × recommended recalibration strategy", and validate the criterion's sensitivity/specificity on the transfer-matrix held-out set.
- **Filling items**:
  - sensitivity/specificity report (§9:153, criterion self-validation operational definition hard-coded)
  - trivial-strategy comparison (always-TS / always-buy-n-labels, gap filled per §13:223 R4-round review finding)
  - decision curve analysis (net benefit, §9:154, reported separately for NORM and STTC classes)
- **Corresponding protocol section**: §9.

### A1.5.3 Contribution Tier and Main-text/Appendix Allocation

| Contribution | Tier | Main text/Appendix | Primary endpoint/endpoint |
|---|---|---|---|
| 1 OOD calibration gain quantification | primary | main text | ΔECE_OOD (primary endpoint) |
| 2 ID no-repairable-space boundary | boundary condition | main text | ΔECE_ID (boundary-condition endpoint) |
| 3 predictability | auxiliary | main text (if LOO R² CI upper bound ≥ 0.5) / appendix (otherwise) | LOO R² (auxiliary endpoint) |
| 4 deployment criterion | auxiliary | main text | sensitivity/specificity (auxiliary endpoint) |

### A1.5.4 Consistency with the §0 novelty Relocation

Mapping of the post-amendment contribution statement to the §0:11-14 three-step chain:

- Contribution 1 (OOD calibration gain quantification) = the precondition of the §0 three-step chain (quantifying OOD gain is the common premise of the decomposition/prediction/criterion steps)
- Contribution 2 (ID boundary) = the non-triviality evidence of the §0 three-step chain
- Contribution 3 (predictability) = step 2 of the §0 three-step chain
- Contribution 4 (deployment criterion) = step 3 of the §0 three-step chain
- Step 1 of the §0 three-step chain (parameter-level decomposition) retains its independent contribution status, corresponding to the §8 mechanism-decomposition validation (leg 1 + leg 2 + leg 3), unchanged by this amendment

---

## Amendment A1.6: Protocol Text Insertion Points and Replacement Map

This amendment's concrete modification map for EXPERIMENT_PROTOCOL.md v2.0:

### A1.6.1 §6 Endpoint Definition Replacement

**Replace the entire §6:88-106 block** with:

```markdown
## 6. Endpoint Definitions (hard-coded, post-hoc modification prohibited)

**Primary formalization**: single-label 5-class softmax; **primary ECE = 5-class confidence SmoothECE** (no binning bias), classwise macro-average as secondary perspective.

**Endpoint tier (A1 revision)**:
- **Primary endpoint = ΔECE_OOD** (unique, relocated in A1.1)
- **Boundary-condition endpoint = ΔECE_ID** (expected H₀ not rejected, A1.4)
- **Secondary endpoints**: G (recoverable loss), decay (secondary descriptive quantity, downgraded in A1.1), R (retention rate), NLL, classwise-ECE, Brier Murphy decomposition, Cox slope/intercept, predicted/true prior L1 distance
- Only one primary test; all per-cell comparisons enter the BH family (family size = 6 pairs × 2 primary architectures × 13 shift levels = 156 tests, consistent with the enumeration in §3:44-48)

**Primary endpoint (formal definition, A1.3)**:
- ΔECE_OOD = ECE_raw_OOD − ECE_TS_OOD
  - ECE_raw_OOD: 5-class confidence SmoothECE computed on target-domain raw probabilities by the source-domain-trained classifier
  - ECE_TS_OOD: 5-class confidence SmoothECE computed on target-domain post-TS probabilities, where the source cal split fits temperature T
  - TS fitting paradigm: source cal fit (consistent with §5:84 S1, R14 revision)
  - SmoothECE bandwidth: 0.45·(n/2000)^(−0.2) (consistent with §11.5 F3)

**Boundary-condition endpoint (formal definition, A1.4)**:
- ΔECE_ID = ECE_raw_ID − ECE_TS_ID
  - ECE_raw_ID: 5-class confidence SmoothECE computed on source-domain (ID) raw probabilities by the source-domain-trained classifier
  - ECE_TS_ID: 5-class confidence SmoothECE computed on source-domain (ID) post-TS probabilities, where the source cal split fits temperature T
  - Expected H₀: ΔECE_ID = 0 not rejected
  - Robustness criterion (hard-coded): proportion of cells whose 95% CI contains 0 ≥ 80% → boundary condition robust
  - Branch trigger: < 80% → "ID non-zero boundary" branch, primary conclusion adds boundary-condition qualifier (A1.4.2)

**Secondary endpoints**:
- G = ECE_S1(target) − ECE_oracle(target)  [recoverable loss: distinguishes "nothing to repair" vs "cannot be repaired"]
  - Oracle definition (guards against in-sample bias): full fit on target-domain cal split, evaluated on the same test set as all methods; independently fit per transfer cell
- decay = ΔECE_OOD − ΔECE_ID  [downgraded to secondary descriptive quantity in A1.1; typo corrected in A1.2: decay positive = OOD gain − ID gain]
- R = ΔECE_ext / ΔECE_int (description and sensitivity analysis only)
- NLL; classwise-ECE (macro-average, empty classes listed separately); Brier Murphy decomposition (per-class binarization construction, unit-test asserts identity; cross-corpus compares REL term only); Cox slope/intercept; predicted/true prior L1 distance

**Primary test (unique, relocated in A1.1)**:
H₀: ΔECE_OOD = 0  vs  H₁: ΔECE_OOD > 0 (one-sided, direction prior: TS is order-preserving under convex loss, Guo 2017/Kull 2019)
Patient-level cluster paired bootstrap B=10,000 BCa; stratified pooling: strata = transfer pair × architecture
Point estimate = full-sample statistic (never report bootstrap mean), format "ΔECE_OOD = X [95% CI L, U], baseline Y → post-repair Z"
Cells with ΔECE_OOD ≤ 0: report "repair harmful or ineffective" count, excluded from positive-gain statement

**Secondary family**: BH-FDR q=0.05 (family size 156); the rest labeled exploratory, report CI only
**Sanity**: global post-TS argmax unchanged bit by bit (asserted in train.py)

**Preset interpretation (prevalence matching experiment, pillar experiment), TOST three-part form, numerical bounds hard-coded**:
- Matching enable condition: max absolute difference of matched class marginal prior ≤ 0.02, otherwise report "matching failed" branch, excluded from interpretation
- **Decay retained** = lower bound of R's 95% CI ≥ 0.7
- **Decay vanished** = CI contains 1 and point estimate ≥ 0.85
- **Partial decay** = all other cases
- Matching = patient-level subsampling by class marginal prior; report matching residual when joint matching is infeasible
```

### A1.6.2 §0 Contribution Statement Supplement

Append after the §0:11-14 three-step chain:

```markdown
**Contribution tier (A1.5 revision)**:
1. **Primary contribution**: OOD calibration gain quantification (primary endpoint ΔECE_OOD significantly positive)
2. **Boundary-condition contribution**: ID no-repairable-space boundary (ΔECE_ID ≈ 0, establishes non-triviality of primary contribution)
3. **Auxiliary contribution**: §8.5 predictability (fills in 3 architectures, regression sample = 18)
4. **Auxiliary contribution**: §9 deployment criterion (fills in sensitivity/specificity + trivial-strategy comparison)
```

### A1.6.3 §11.5 Revision Register Append

Append at the end of the §11.5 revision register:

```markdown
| A1 | **Primary endpoint relocation**: decay → ΔECE_OOD (primary), ΔECE_ID (boundary condition), decay downgraded to secondary descriptive quantity; §6 symbol typo correction; contribution statement relocation | this protocol (§0/§6) + docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md | ✅ preregistration revision draft, pending OSF archiving |
```

---

## Amendment A1.7: OSF Archiving Checklist

This amendment A1, when archived to OSF, must include:

1. Full text of this amendment (docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md)
2. Pre-amendment EXPERIMENT_PROTOCOL.md v2.0 snapshot + SHA-256 hash
3. Post-amendment EXPERIMENT_PROTOCOL.md v2.1 snapshot + SHA-256 hash
4. R1 null-result exploratory pilot data + analysis scripts (as empirical evidence triggering the revision)
5. Revision date timestamp: 2026-09-05
6. Amendment number: A1
7. Amendment type: Preregistration Revision (per Nosek et al. 2019)
8. Transparency statement citations: Lakens 2019, Nosek et al. 2019

---

## Amendment A1.8: Compatibility with Existing Revisions

Compatibility check of this amendment A1 with existing revisions:

| Existing revision | Compatibility | Note |
|---|---|---|
| R14 (source cal fit) | ✅ compatible | ΔECE_OOD's TS fitting paradigm follows R14 |
| R15 (BiMamba → InceptionTime primary architecture) | ✅ compatible | the 2 primary architectures unchanged, family size 156 unchanged |
| R16 (HYP removed / 4-class subspace) | ✅ compatible | transfer pair definition unchanged, ΔECE_OOD computed on 4-class subspace |
| §11.5 F2 (BCa + B=10,000) | ✅ compatible | primary test follows BCa + B=10,000 |
| §11.5 F3 (SmoothECE bandwidth) | ✅ compatible | ΔECE_OOD follows 0.45·(n/2000)^(−0.2) |
| §8.5 R round (regression sample = 18) | ✅ compatible | Contribution 3 follows 18 regression samples |
| §0 novelty relocation | ✅ compatible | contribution statement relocation aligns with §0 three-step chain (A1.5.4) |

---

**End of Amendment A1**

> This amendment was drafted by the "protocol revision drafter" under the fourth-round adversarial review Zone 2 attainability determination, following the preregistration revision norms of Lakens (2019) and Nosek et al. (2019), and takes effect after OSF timestamp archiving.
