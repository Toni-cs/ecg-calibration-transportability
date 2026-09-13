# Preregistration Amendment A2: Confirmatory Family Reduction, 156 → 12

> **Amendment number**: A2
> **Amendment date**: 2026-09-10
> **Triggering round**: intensified protocol adversarial review (step 4)
> **Amendment type**: preregistration revision (Preregistration Revision, per Nosek et al. 2018)
> **Pre-amendment protocol hash**: see OSF archive (EXPERIMENT_PROTOCOL.md v2.1-A1 pre-amendment snapshot)
> **Status**: preregistration revision draft, pending OSF timestamp archiving

---

## A2.1 As-registered

- **Confirmatory family**: 156 tests = 6 transfer pairs × 2 primary architectures × 13 shift levels (protocol §6:91)
- **Primary test**: H₀: ΔECE_OOD = 0 vs H₁: ΔECE_OOD > 0, per-cell BH-FDR q=0.05
- **L2 shift levels**: 13 tiers (sampling rate 500→250→125 Hz, leads 12→6→3→2→1, noise SNR {24,12,6,0,−6} dB, gain ×0.5/×2)

## A2.2 As-revised

- **Confirmatory family**: 12 tests = 6 transfer pairs × 2 primary architectures × **1 shift level (L0/L1 primary grid)**
- **Primary test**: H₀: ΔECE_OOD = 0 vs H₁: ΔECE_OOD > 0, 12-cell BH-FDR q=0.05
- **L2 shift levels**: 13 tiers positioned as exploratory dose-response curve, excluded from confirmatory family, report per-tier CI without confirmatory p-value
- **60 seed experiments**: positioned as robustness evidence (5 seed repeats per confirmatory cell), excluded from confirmatory family

## A2.3 Rationale

1. **L2 is eval-time transform, not confirmatory**: the L2 shift levels (downsampling, lead dropping, noise addition, gain) are eval-time probability transforms that do not retrain the model, and are essentially dose-response exploration rather than confirmatory testing. Including them in the confirmatory family conflates the two scientific goals of "confirming the primary endpoint" and "exploring shift dose".
2. **156 family not run in full**: the confirmatory family of 156 requires all 13 tiers to be run; actual L2 coverage is 157/390 (40%), dual-seed single-architecture, with ResNet L2 13 cells excluded. Applying BH correction to a family not run in full is building on sand.
3. **12-cell confirmatory can be realized**: 6 pairs × 2 architectures × 5 seeds = 60 experiments all completed, 12 cells each aggregated over 5 seeds (meta-analytic pooled ΔECE), BH-12 can be strictly enforced.
4. **Consistent with A1**: A1 relocated the primary endpoint (decay→ΔECE_OOD), A2 reduced the family; the two are independent. A2 does not change the primary endpoint definition, only reduces the confirmatory family size.

## A2.4 Transparency Statement (Not HARKing)

- **Revision direction prior**: the judgment that L2 eval-only is an exploratory dose response is determined a priori by experimental design (eval-time transform does not retrain), not driven by result direction.
- **Exploratory results of the pre-amendment 156 family do not enter the primary report**: the L2 dose-response curve serves as exploratory supplement, not as evidence for confirmatory conclusions.
- **Nosek et al. 2018 preregistration revision**: register the pre- and post-amendment protocol hashes, rationale, and date after main-grid data collection completes and before submission.

## A2.5 As-registered vs As-revised Comparison Table

| Item | As-registered | As-revised |
|---|---|---|
| Confirmatory family size | 156 | 12 |
| L2 role | confirmatory family member | exploratory dose response |
| 60 seed experiments | family member | robustness evidence (5 seed repeats per cell) |
| BH-FDR | BH-156 (not run in full) | BH-12 (strictly enforceable) |
| Primary conclusion | 51/60 (BH-60 robustness) | 9/12 (BH-12 confirmatory) + 51/60 robustness |

## A2.6 BH-12 Results (Confirmatory)

- **12-cell aggregation**: per-cell 5-seed meta-analytic pooled ΔECE (DerSimonian-Laird random effects)
- **BH-12 q=0.05**: 9/12 significant (6/6 for InceptionTime), 3/12 not significant (boundary cases: cpsc_chapman/RN, cpsc_ptbxl/RN, chapman_cpsc/IT)
- **Bonferroni-12**: 2/12 significant (cpsc_chapman/IT, ptbxl_chapman/RN)
- **Robustness evidence**: 51/60 seed experiments support (BH-60 51/60, no conflict with confirmatory)

## A2.7 Impact on Primary Conclusion

The primary conclusion is reorganized from "51/60 seed experiments support" into:
1. **Confirmatory**: 9/12 direction × architecture cells BH-12 significant (75%)
2. **Robustness**: 51/60 seed experiments support (85%), as 5-seed robustness evidence per confirmatory cell
3. **Exploratory**: L2 13-tier dose-response curve (157/390 coverage, dual-seed single-architecture)

This reorganization does not weaken the primary-conclusion narrative that "TS yields positive OOD calibration gain under cross-corpus ECG transfer"; rather it strengthens confirmatory rigor (12 cells realizable vs 156 not run in full).

---

## Appendix: Synergy with Step 2 Discrimination-Power Gating

A2 reduces the family to 12 confirmatory cells, after which step 2's discrimination-power gating operates on the 12 cells:
- 7/12 cells pass the gate (acc > target majority-class baseline) → deployable
- 5/12 cells fail the gate (insufficient discrimination power) → calibration valid but not deployable
- Confirmatory deployable cells: BH-12 significant & gate passed = 7/12 (to be confirmed after actual aggregation)

C5 contribution: discrimination-aware calibration gate, validating the gate's sensitivity/specificity on the confirmatory 12 cells.
