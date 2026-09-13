# OSF Preregistration — field-by-field answers

For the **OSF Preregistration** template. Paste the text in the right-hand
column. Read the note under "Existing data" first: that single field decides
whether this record is honest about its own timeline, and OSF's own taxonomy
gives you an exact option for the truthful answer.

## The one answer that matters

**Existing data** → select **"Registration following analysis of existing
data."**

Do not select "prior to analysis" or "prior to creation". The analysis is
complete; the protocol and amendments were written during the study; the only
public timestamp starts with this deposit. Choosing the honest option costs
nothing and makes every other field consistent. Choosing a stronger option
would be contradicted by `09_REVISION_LOG.md` in the same deposit, by the
amendments' own "draft pending OSF timestamping" status, and by the
manuscript's "Pre-registration archival status" paragraph.

## Study information

| Field | Answer |
|---|---|
| **Title** | Preregistered protocol and amendments: temperature-scaling calibration transfer across ECG corpora (v2.1-A1) |
| **Description** | Paste the block from `OSF_PROJECT_DESCRIPTION.md`, starting at "Protocol and amendments for". |
| **Hypotheses** | The primary endpoint is the OOD calibration benefit `ΔECE_OOD = ECE_raw^OOD − ECE_TS^OOD` of temperature scaling under cross-corpus ECG transfer, tested one-sided against a registered empirical direction prior. H1: TS yields a positive OOD benefit. The pre-registered ID boundary criterion (≥80% of cells with 95% CIs containing zero) was not met (23/60 = 38.3% under the BCa operating CI), triggering the registered "ID nonzero boundary" branch. Amendment A2 reduces the confirmatory family from 156 to 12 hypotheses (6 transfer pairs × 2 architectures × 1 primary shift level); the 13 L2 shift levels are exploratory dose-response. All hypotheses are tagged exploratory + robustness validation, not confirmatory. |

## Design plan

| Field | Answer |
|---|---|
| **Study type** | Secondary data analysis (no new data collected; three public ECG corpora) |
| **Blinding** | No blinding. The study re-analyses public retrospective datasets; there are no human participants and no treatment assignment. Multi-seed train/eval runs (seeds 42–46) provide the robustness evidence. |
| **Study design** | Six directed cross-corpus transfer pairs among PTB-XL, Chapman-Shaoxing, and CPSC2018+2019, each evaluated on two architectures (InceptionTime, 1D-ResNet-34) × 5 seeds = 60 experiments. Eight recalibration methods, with temperature scaling as the primary method. Patient-level cluster paired bootstrap for all uncertainty estimates. |
| **Randomization** | Not applicable. Seeds 42–46 are fixed a priori, not randomly drawn. |

## Sampling plan

| Field | Answer |
|---|---|
| **Existing data** | **Registration following analysis of existing data.** The protocol and both amendments were authored during the study (A1: 2026-09-05; A2: 2026-09-10); the analysis is complete; the public timestamp begins with this deposit. |
| **Data collection procedures** | None. Three public corpora are used: PTB-XL (PhysioNet, v1.0.3), Chapman-Shaoxing (PhysioNet), CPSC2018+2019 (PhysioNet Challenge). Data were not collected by the authors. |
| **Sample size** | 60 seed experiments (6 pairs × 2 architectures × 5 seeds), fully balanced. Patient-level calibration samples range from 1,027 to 2,099 records. |
| **Sample size rationale** | Fixed by design, not by power calculation: five seeds per cell to expose seed-level variability, two architectures to test architecture dependence, six directed pairs because all ordered pairs among three corpora are used. |
| **Stopping rule** | None. The grid is fixed a priori and complete; no interim analysis or early stopping was used. |

## Variables

| Field | Answer |
|---|---|
| **Measured variables** | Expected calibration error (SmoothECE) in-distribution and out-of-distribution; ΔECE_ID and ΔECE_OOD; accuracy, AUROC and AUPRC where computed (AUROC/AUPRC are not available for all cells — see Limitations (xiv)); net clinical value; Shapley decompositions of the benefit into slope, intercept and prevalence components. |
| **Indices** | Per-cell ΔECE with patient-level cluster paired bootstrap CIs; per-direction and per-architecture aggregate support counts; stratum-level decomposition shares. |
| **Manipulated variables** | Recalibration method (8 variants incl. temperature scaling, BBSE, EM prior adaptation, Matrix scaling); architecture; transfer direction; random seed. |

## Analysis plan

| Field | Answer |
|---|---|
| **Statistical models** | The operating interval is a patient-level cluster paired bootstrap with BCa (B = 10,000), re-run on the full 60-experiment grid (60/60). Earlier percentile intervals (B = 10,000 in 31/60; B = 200 in 21/60) are retained as historical provenance; the two methods agree in sign in 60/60. Family-wise control uses Benjamini-Hochberg FDR (BH-12 on the reduced family) with Bonferroni-12 as a sensitivity check. Meta-analytic pooling uses fixed-effect inverse-variance and DerSimonian-Laird random effects. |
| **Transformations** | None beyond the registered L2 eval-time shift operators (resampling, lead dropping, additive noise, gain). Shapley shares are not reported where the identifiability flag `share_reliable=False`. |
| **Inference criteria** | α = 0.05, one-sided for the pre-registered direction. Family-wise control: BH-FDR q = 0.05 over the reduced 12-hypothesis family; Bonferroni-12 as sensitivity. The C5 deployment gate requires accuracy ≥ source-domain baseline in addition to a positive ΔECE_OOD. |
| **Data exclusion** | No post-hoc exclusion. All 60 seed results, including nine counter-examples, are reported. Six supporting cells with degenerate CI widths (< 3×10⁻⁴) are reported alongside the count that excludes them (45/60 rather than 51/60). |
| **Missing data** | Not applicable to the primary endpoint. The L2 analysis covers 157 of 390 planned cells (2 seeds, single architecture); this is reported as a coverage limitation rather than imputed. |
| **Exploratory analysis** | The 13 L2 shift levels are exploratory dose-response under amendment A2. The decay contrast ΔECE_OOD − ΔECE_ID is restored as exploratory after the ID boundary branch was triggered. |

## Other

| Field | Answer |
|---|---|
| **Other** | The archived protocol is v2.1-A1, the earliest complete version still in existence. An internal SHA-256 manifest was taken on 2026-09-05T04:19:46Z, but for 7 of its 14 entries the frozen file content can no longer be recovered from version control, including the protocol document itself; `README_ARCHIVAL_STATUS.md` in this deposit lists them. This record therefore documents the protocol as deposited, not a pre-registration that predates data collection. |

## After the registration is live

- [ ] Copy the registration DOI (it differs from the project DOI).
- [ ] Decide which DOI the manuscript should cite: the **registration** DOI is
      the stronger one, because it cannot be edited after publication.
- [ ] Run `python _apply_osf_doi.py 10.17605/OSF.IO/XXXXX` from
      `D:\A1\ecg-lab-v2` and check the four replacements report `[OK]`.
