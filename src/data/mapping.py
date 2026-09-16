"""5-superclass mapping module: SCP codes / Chapman / CPSC -> {NORM, MI, STTC, CD, HYP}.

Protocol basis (docs/EXPERIMENT_PROTOCOL.md §2, §10-T1):
- Single-label priority rules are fixed and subjected to sensitivity analysis; multi-label
  sigmoid is a secondary formulation.
- Each mapping entry is justified with literature; every ambiguous mapping decision
  generates an alternative variant (mapping sensitivity analysis).
- CPSC2018 (CPSC Database + CPSC-Extra) HYP is extremely rare (n=11) -> the primary
  analysis downgrades to the {NORM, CD, STTC, MI} 4-class subspace. The corpus does
  NOT contain CPSC2019 (that challenge was QRS/heart-rate detection, with no
  diagnostic labels). See docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md.

Code-table sources (all publicly verifiable official code tables; the actual PTB-XL
data was not downloaded):
1. PTB-XL v1.0.3 official ``scp_statements.csv`` (PhysioNet, verified verbatim):
   44 statements with diagnostic=1 and a diagnostic_class (letter-abbreviation keys).
   Reference: Wagner et al., "PTB-XL, a large publicly available
   electrocardiography dataset", Scientific Data 7:148 (2020).
2. PhysioNet / Computing in Cardiology Challenge 2021 official
   ``dx_mapping_scored.csv`` / ``dx_mapping_unscored.csv``
   (github.com/physionetchallenges/evaluation-2021): SNOMED CT numeric code table,
   covering the encodings actually used in the CINC2021 header ``#Dx:`` fields.
3. Chapman-Shaoxing: Zheng et al., Scientific Data 7:274 (2020):
   11 rhythms (SB/SR/AFIB/ST/AF/SI/SVT/AT/AVNRT/AVRT/SAAWR) and
   4 merged groups (SB/AFIB/GSVT/SR).

Known cross-database conflicting codes (part of the study design; each is an object of
per-entry sensitivity analysis; under single-labeling the "adopted semantics" below are used):
- 426177001: CINC2021=sinus bradycardia / SNOMED literal=AF -> both STTC (class unchanged)
- 59118001:  CINC2021=RBBB / SNOMED literal=LBBB -> both CD (class unchanged)
- 429622005: CINC2021=ST depression (->STTC) / SNOMED related code=RBBB (->CD)
  -> adopt CINC2021 semantics (this loader's data ingestion path); included in sensitivity
- 284470004: CINC2021=PAC / some PTB-XL contexts=left axis deviation -> both STTC (class unchanged)
- 164934002: CINC2021=T wave abnormal (->STTC) / PTB-XL=LAH (->HYP)
  -> adopt CINC2021 semantics; included in sensitivity
- 426434006: PTB-XL=myocardial infarction (->MI) / CINC2021=anterior ischemia (->STTC)
  -> adopt the Wagner 2020 system=MI (baseline table uses PTB-XL as reference); included in sensitivity
- 251199005: PTB-XL=LAFB (->CD) / CINC2021=counter-clockwise rotation (descriptive)
  -> adopt PTB-XL semantics=CD; included in sensitivity
- 10370003:  SNOMED literal=bundle branch block (->CD) / CINC2021=pacing rhythm
  -> baseline=CD (per this module); variant ``bbb_10370003_to_sttc`` changes it to STTC
- 111975006: PTB-XL=myocardial ischemia / CINC2021=prolonged QT -> both STTC (class unchanged)

Conflict inventory reference: Reyna et al., "Issues in the automated classification of
multilead ECGs using heterogeneous labels and populations", Physiol Meas (2022).
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping as MappingType, Optional

__all__ = [
    "SUPERCLASSES",
    "DEFAULT_PRIORITY",
    "SUBSPACE_CPSC",
    "SCP_TO_SUPERCLASS",
    "MAP_TO_5SUPERCLASS",
    "generate_mapping_variants",
    "CHAPMAN_TO_SUPERCLASS",
    "CPSC_TO_SUPERCLASS",
    "filter_subspace",
]

# 5 superclasses (Wagner 2020 diagnostic_class system)
SUPERCLASSES = ("NORM", "MI", "STTC", "CD", "HYP")

# ---------------------------------------------------------------------------
# Single-label priority rules (fixed per preregistered protocol §2; this rule is a
# preregistered design decision and an object of sensitivity analysis)
#
# MI > STTC > CD > HYP > NORM
#
# Rationale:
# (a) Pathology takes precedence over normal: "NORM" is the "normal ECG" statement
#     in PTB-XL; when it co-occurs with any pathology statement (e.g. {'NORM':100,
#     'IMI':100}) the pathology wins.
# (b) Ischemia takes precedence over conduction/hypertrophy: ischemic judgments have
#     the highest clinical urgency, and in PTB-XL MI and STTC (ischemic ST-T) statements
#     frequently co-occur (e.g. IMI+ISCIN), so ties must be broken deterministically.
# (c) The Wagner 2020 / Strodthoff 2021 diagnostic_class systems do not themselves
#     define a priority; single-label priority is a design decision of this study,
#     with multi-label sigmoid as a secondary formulation.
# (d) Sensitivity analysis: generate_mapping_variants() provides priority-reversal /
#     STTC-first / ambiguity-reclassification variants (preregistered protocol §10-T1
#     mapping sensitivity analysis).
# ---------------------------------------------------------------------------
DEFAULT_PRIORITY = ("MI", "STTC", "CD", "HYP", "NORM")

# CPSC downgraded subspace (preregistered protocol §2: no HYP class; the primary
# analysis downgrades both sides symmetrically).
#
# ⚠️ **ORDER IS THE ENCODING.** The pipeline builds
#     label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}
# so the *position* of each class in this tuple defines its integer label.
# Changing the order re-labels the data while leaving model output indices
# untouched -> silent semantic mismatch between checkpoints and data.
#
# The order below, ("NORM", "CD", "STTC", "MI"), is the order actually used when
# all 60 main-analysis cells were trained (2026-09-04..06). It is preserved here
# for bit-level reproducibility of the published endpoint. Both sides of every
# 4-class transfer are built from this same constant (eval_transfer.py builds the
# source dataset with `subspace=SUBSPACE_CPSC` whenever num_classes == 4), so
# source and target are inherently co-encoded regardless of the order chosen.
#
# History (do not repeat): on 2026-09-09 this line was changed to
# ("NORM", "MI", "STTC", "CD") (== SUPERCLASSES[:4]) with a comment claiming a
# "fix", but the models were NEVER retrained. The npz label arrays regenerated
# afterwards therefore carried the new order while the checkpoints still spoke
# the old one, swapping the MI and CD classes for every CPSC-containing cell.
# Reverted on 2026-09-16. See reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md.
SUBSPACE_CPSC = ("NORM", "CD", "STTC", "MI")

# ---------------------------------------------------------------------------
# Layer 1: PTB-XL official diagnostic statements (scp_statements.csv, v1.0.3,
# verified verbatim). Keys = SCP-ECG letter abbreviations (scp_codes key style in
# ptbxl_database.csv), values = diagnostic_class.
# ---------------------------------------------------------------------------
_PTBXL_OFFICIAL = {
    # NORM ("normal ECG", Statement Category=Normal/abnormal)
    "NORM": "NORM",
    # MI: myocardial infarction of various walls / subendocardial injury
    "IMI": "MI", "ASMI": "MI", "ILMI": "MI", "AMI": "MI", "ALMI": "MI",
    "LMI": "MI", "IPLMI": "MI", "IPMI": "MI", "PMI": "MI",
    "INJAS": "MI", "INJAL": "MI", "INJIN": "MI", "INJLA": "MI", "INJIL": "MI",
    # STTC: ST/T changes, ischemic ST-T, non-diagnostic T wave, electrolyte/drug, aneurysm
    "NDT": "STTC", "NST_": "STTC", "DIG": "STTC", "LNGQT": "STTC",
    "ISC_": "STTC", "ISCAL": "STTC", "ISCAN": "STTC", "ISCIN": "STTC",
    "ISCIL": "STTC", "ISCAS": "STTC", "ISCLA": "STTC",
    "ANEUR": "STTC", "EL": "STTC",
    # CD: bundle/branch block, AV block, intraventricular conduction disorder, pre-excitation
    "1AVB": "CD", "2AVB": "CD", "3AVB": "CD",
    "LAFB": "CD", "LPFB": "CD", "IRBBB": "CD", "CRBBB": "CD",
    "CLBBB": "CD", "ILBBB": "CD", "IVCD": "CD", "WPW": "CD",
    # HYP: ventricular hypertrophy / atrial load
    "LVH": "HYP", "RVH": "HYP", "SEHYP": "HYP",
    "LAO/LAE": "HYP", "RAO/RAE": "HYP",
}

# ---------------------------------------------------------------------------
# Layer 2: rhythm-statement extension (official tables assign no diagnostic_class to
# rhythm statements; cross-database single-labeling needs a superclass for purely
# rhythmic records). Following the public convention: rhythm/ectopic/pacing-excluded
# rhythm abnormalities -> STTC, sinus rhythm -> NORM. Listed as a sensitivity object.
#
# Sinus-family correction: in the official PTB-XL scp_statements.csv, SBRAD/STACH/SARRH
# are rate/morphology description statements with rhythm=1.0 and diagnostic_class=NaN
# (the PTB-XL system explicitly does NOT classify them as ST-T changes). Mapping them
# to STTC was incorrect because: (a) sinus bradycardia/sinus arrhythmia are not
# repolarization (ST-T) abnormalities clinically, so STTC lacks justification; (b)
# since STTC ranks above CD/HYP in the priority, sinus-rate descriptions would mask
# true conduction/hypertrophy diagnoses (on PTB-XL, 251 STTC->CD and 58 STTC->HYP
# flips are exactly 1AVB/LVH being suppressed by SBRAD); (c) it is inconsistent with
# the Chapman-side override (426177001/427084000 -> NORM, treating brady/tachy as
# normal sinus-rate variants), breaking comparability of cross-database calibration
# transfer measurements.
# Fix: map the sinus family (SR/SBRAD/STACH/SARRH) -> NORM, aligned with the Chapman
# override. Registered as a mapping sensitivity-analysis variant.
# ---------------------------------------------------------------------------
_RHYTHM_EXTENSION = {
    "SR": "NORM",        # sinus rhythm -> NORM
    "SBRAD": "NORM",     # sinus bradycardia: a rate description, not ST-T
    "STACH": "NORM",     # sinus tachycardia: same as above
    "SARRH": "NORM",     # sinus arrhythmia: rate/morphology description, not ST-T
    "AFIB": "STTC", "AFLT": "STTC",
    "SVARR": "STTC", "SVTAC": "STTC", "PSVT": "STTC",
    "PAC": "STTC", "PVC": "STTC", "PRC(S)": "STTC",
    "BIGU": "STTC", "TRIGU": "STTC",
    "LPR": "CD",         # prolonged PR interval -> conduction (sensitivity object; official lists as rhythm)
    "PACE": None,        # paced morphology: officially no class, explicitly unmappable
}

# ---------------------------------------------------------------------------
# Layer 3: SNOMED CT numeric codes (CINC2021 / CPSC2018-2019 header #Dx actual
# encodings; source = evaluation-2021 dx_mapping_scored.csv / dx_mapping_unscored.csv,
# verified verbatim; value=None means "officially no class / unmappable", explicitly
# entered so it can be counted in the report).
# ---------------------------------------------------------------------------
_SNOMED_DIAGNOSTIC = {
    # --- NORM ---
    "426783006": "NORM",   # sinus rhythm (hard task requirement; same code as PTB-XL NORM)
    "426285000": "NORM",   # ECG: normal sinus rhythm (SNOMED literal)
    # --- MI ---
    "426434006": "MI",     # PTB-XL=MI / CINC2021=anterior ischemia (conflict, PTB-XL adopted)
    "164865005": "MI",     # myocardial infarction
    "164867002": "MI",     # old myocardial infarction
    "57054005": "MI",      # acute myocardial infarction
    "54329005": "MI",      # anterior myocardial infarction
    # --- STTC: ischemia/ST-T/rhythm extension ---
    "164861001": "STTC",   # myocardial ischemia
    "413444003": "STTC",   # acute myocardial ischemia
    "413844008": "STTC",   # chronic myocardial ischemia
    "425419005": "STTC",   # inferior ischaemia
    "425623009": "STTC",   # lateral ischaemia
    "55930002": "STTC",    # ST changes
    "428750005": "STTC",   # nonspecific ST-T abnormality
    "164930006": "STTC",   # ST interval abnormal
    "429622005": "STTC",   # CINC2021=ST depression (conflict, CINC2021 adopted)
    "704997005": "STTC",   # inferior ST segment depression
    "164931005": "STTC",   # ST elevation (CPSC STE)
    "164934002": "STTC",   # CINC2021=T wave abnormal (conflict, CINC2021 adopted)
    "59931005": "STTC",    # T wave inversion
    "164917005": "STTC",   # Q wave abnormal (official QWAVE has no class; extended to STTC)
    "164921003": "STTC",   # R wave abnormal
    "365413008": "STTC",   # poor R wave progression
    "164912004": "STTC",   # P wave change
    "164937009": "STTC",   # U wave abnormal
    "251205003": "STTC",   # prolonged P wave
    "251223006": "STTC",   # tall P wave
    "251259000": "STTC",   # high T-voltage
    "428417006": "STTC",   # early repolarization
    "111975006": "STTC",   # PTB-XL=ischemia / CINC2021=long QT (class-unchanged conflict)
    "77867006": "STTC",    # shortened QT
    "418818005": "STTC",   # Brugada morphology (sensitivity object)
    "74615001": "STTC",    # brady-tachy syndrome
    "698247007": "STTC",   # cardiac dysrhythmia (broad; sensitivity object)
    # rhythm-family extension (atrial/ventricular ectopic, SVT, AF spectrum, junctional)
    "164889003": "STTC",   # atrial fibrillation
    "164890007": "STTC",   # atrial flutter
    "426177001": "STTC",   # CINC2021=SB / SNOMED literal=AF (class-unchanged conflict)
    "426627000": "STTC",   # bradycardia
    "427084000": "STTC",   # sinus tachycardia
    "427393009": "STTC",   # sinus arrhythmia
    "284470004": "STTC",   # CINC2021=PAC / some contexts=LAD (class-unchanged conflict)
    "63593006": "STTC",    # supraventricular premature beats
    "427172004": "STTC",   # premature ventricular contractions
    "17338001": "STTC",    # ventricular premature beats
    "164884008": "STTC",   # ventricular ectopics (CPSC PVC)
    "11157007": "STTC",    # ventricular bigeminy
    "251180001": "STTC",   # ventricular trigeminy
    "251182009": "STTC",   # paired VPC
    "75532003": "STTC",    # ventricular escape beat
    "81898007": "STTC",    # ventricular escape rhythm
    "164896001": "STTC",   # ventricular fibrillation
    "111288001": "STTC",   # ventricular flutter
    "164895002": "STTC",   # ventricular tachycardia
    "425856008": "STTC",   # paroxysmal VT
    "13640000": "STTC",    # fusion beats
    "251173003": "STTC",   # atrial bigeminy
    "251170000": "STTC",   # blocked PAC
    "195101003": "STTC",   # wandering atrial pacemaker
    "17366009": "STTC",    # SAAWR
    "5609005": "STTC",     # sinus arrest
    "282825002": "STTC",   # paroxysmal AF
    "426749004": "STTC",   # chronic AF
    "314208002": "STTC",   # rapid AF
    "195080001": "STTC",   # AF and flutter
    "426761007": "STTC",   # supraventricular tachycardia
    "67198005": "STTC",    # paroxysmal SVT
    "251166008": "STTC",   # AVNRT
    "233897008": "STTC",   # AVRT
    "713422000": "STTC",   # atrial tachycardia
    "233892002": "STTC",   # accelerated atrial escape rhythm
    "106068003": "STTC",   # atrial rhythm
    "251187003": "STTC",   # atrial escape beat
    "61277005": "STTC",    # accelerated idioventricular rhythm
    "49260003": "STTC",   # idioventricular rhythm
    "29320008": "STTC",   # AV junctional rhythm
    "426664006": "STTC",   # accelerated junctional rhythm
    "426648003": "STTC",   # junctional tachycardia
    "426995002": "STTC",   # junctional escape
    "251164006": "STTC",   # junctional premature complex
    "251168009": "STTC",   # supraventricular bigeminy
    "50799005": "STTC",   # AV dissociation (rhythm grouping; sensitivity object)
    "39732003": "STTC",   # left axis deviation (axis deviation -> STTC; sensitivity object)
    "47665007": "STTC",   # right axis deviation (same)
    # --- CD: conduction disorders ---
    "270492004": "CD",     # 1st degree AV block
    "164947007": "CD",     # prolonged PR (official lists as rhythm; extended to conduction)
    "49578007": "CD",     # shortened PR (same)
    "195042002": "CD",     # 2nd degree AV block
    "426183003": "CD",     # Mobitz II
    "54016002": "CD",      # Mobitz I / Wenckebach
    "27885002": "CD",      # complete heart block (3AVB)
    "233917008": "CD",     # AV block (nonspecific)
    "204384007": "CD",     # congenital incomplete AV block
    "6374002": "CD",       # bundle branch block (nonspecific)
    "733534002": "CD",     # complete LBBB
    "713427006": "CD",     # complete RBBB
    "713426002": "CD",     # incomplete RBBB
    "164909002": "CD",     # LBBB
    "59118001": "CD",      # CINC2021=RBBB / SNOMED literal=LBBB (class-unchanged conflict)
    "251120003": "CD",     # incomplete LBBB
    "445118002": "CD",     # left anterior fascicular block
    "445211001": "CD",     # left posterior fascicular block
    "698252002": "CD",     # nonspecific intraventricular conduction disorder
    "82226007": "CD",      # diffuse intraventricular block
    "74390002": "CD",      # Wolff-Parkinson-White pattern
    "195060002": "CD",     # ventricular pre-excitation
    "65778007": "CD",      # sinoatrial block (sensitivity object)
    "60423000": "CD",      # sinus node dysfunction (PTB-XL _AVB subclass includes SND)
    "251199005": "CD",     # PTB-XL=LAFB / CINC2021=rotation (conflict, PTB-XL adopted)
    "10370003": "CD",      # SNOMED literal=BBB / CINC2021=pacing rhythm (ambiguous;
    #                    baseline=CD; variant bbb_10370003_to_sttc reclassifies to STTC)
    # --- HYP: hypertrophy/enlargement/load ---
    "164873001": "HYP",    # left ventricular hypertrophy
    "55827005": "HYP",     # left ventricular high voltage
    "89792004": "HYP",     # right ventricular hypertrophy
    "266249003": "HYP",    # ventricular hypertrophy (nonspecific)
    "195126007": "HYP",    # atrial hypertrophy
    "446813000": "HYP",    # left atrial hypertrophy
    "446358003": "HYP",    # right atrial hypertrophy
    "67741000119109": "HYP",  # left atrial enlargement
    "67751000119106": "HYP",  # right atrial high voltage
    "253352002": "HYP",    # left atrial abnormality
    "253339007": "HYP",    # right atrial abnormality
    "370365005": "HYP",    # left ventricular strain (LVH secondary repolarization; sensitivity object)
    # --- explicitly unmappable (officially no class / technical artifact / non-ECG
    #     finding; MAP_TO_5SUPERCLASS skips these and they are counted in the report,
    #     corresponding to the "excluded" branch of the protocol STROBE flowchart) ---
    "251146004": None,     # low QRS voltages (official LVOLT has no class)
    "164951009": None,     # abnormal QRS (official ABQRS has no class)
    "164942001": None,     # fragmented QRS (descriptive)
    "251139008": None,     # arm leads reversed (technical artifact)
    "251198002": None,     # clockwise rotation (descriptive transposition)
    "61721007": None,      # vectorcardiographic loop rotation (descriptive)
    "266257000": None,     # transient ischemic attack (clinical diagnosis, not an ECG finding)
    "251268003": None,     # atrial pacing pattern (pacing morphology, officially no class)
    "251266004": None,     # ventricular pacing pattern (same)
    # --- Chapman-Shaoxing (ecg-arrhythmia 1.0.0) supplementary codes (2026-09-02,
    #     gaps found during ConditionNames_SNOMED-CT.csv coverage pre-check; classified
    #     by the same-family precedent, already registered in the corresponding family) ---
    "28189009": "CD",      # 2AVB2 second-degree type II AV block (AVB family; same as
    #                        195042002 (2AVB)->CD, 27885002 (3AVB)->CD)
    "233896004": "STTC",   # AVNRT (SVT family; same as 233897008 (AVRT)->STTC,
    #                        426761007 (SVT)->STTC)
    "251148003": None,     # low voltage QRS chest lead (official LVOLT 251146004
    #                        has no class; lead-specific variant is also unmappable)
    "251147008": None,     # low voltage QRS limb lead (same)
}

# Combined mapping table (letter-abbreviation + SNOMED numeric keys as a superset;
# covers both PTB-XL and CINC/CPSC key styles).
SCP_TO_SUPERCLASS: dict[str, Optional[str]] = {}
SCP_TO_SUPERCLASS.update(_PTBXL_OFFICIAL)
SCP_TO_SUPERCLASS.update(_RHYTHM_EXTENSION)
for _k, _v in _SNOMED_DIAGNOSTIC.items():
    if _k in SCP_TO_SUPERCLASS and SCP_TO_SUPERCLASS[_k] != _v:
        raise RuntimeError(f"Internal mapping-table conflict: {_k}: {SCP_TO_SUPERCLASS[_k]} vs {_v}")
    SCP_TO_SUPERCLASS[_k] = _v

# ---------------------------------------------------------------------------
# Chapman-Shaoxing mapping (Zheng et al., Sci Data 2020: 11 rhythms + GE MUSE
# condition abbreviations). value=None means unmappable (counted then excluded,
# corresponding to the protocol STROBE flow).
# ---------------------------------------------------------------------------
CHAPMAN_TO_SUPERCLASS: dict[str, Optional[str]] = {
    # rhythms (11 + merged groups; G SVT = SVT merged group)
    "NSR": "NORM", "SR": "NORM", "SI": "STTC",
    "AFIB": "STTC", "AFLT": "STTC", "AF": "STTC",
    "SB": "STTC", "ST": "STTC", "STach": "STTC",
    "GSVT": "STTC", "SVT": "STTC", "AT": "STTC",
    "AVNRT": "STTC", "AVRT": "STTC", "SAAWR": "STTC",
    # common "other conditions" abbreviations (GE MUSE convention)
    "1AVB": "CD", "RBBB": "CD", "CRBBB": "CD", "IRBBB": "CD",
    "LBBB": "CD", "CLBBB": "CD", "ILBBB": "CD",
    "LAFB": "CD",
    "LAD": "CD",   # Chapman dictionary convention=left anterior fascicular block->CD;
    #               if interpreted as "left axis deviation" it would be STTC (sensitivity object)
    "LPR": "CD", "LQT": "STTC", "LMI": "MI", "IMI": "MI", "ASMI": "MI",
    "ISCAL": "STTC", "ISCAN": "STTC", "ISCIN": "STTC",
    "ISCIL": "STTC", "ISCLA": "STTC", "ISCAS": "STTC",
    "PAC": "STTC", "APB": "STTC", "PVC": "STTC", "SVPB": "STTC",
    "LVH": "HYP", "RVH": "HYP", "LAE": "HYP", "RAH": "HYP", "LAH": "HYP",
    "LQRSV": None,  # officially no class
}

# ---------------------------------------------------------------------------
# CPSC class-name mapping -- **REFERENCE ONLY, DEAD CODE.**
#
# This table is NOT used by the data pipeline. It is retained solely for
# readability of the official class names. The real path is
# `preprocess_cpsc.py`, which maps **SCP_TO_SUPERCLASS keyed by SNOMED numeric
# codes** (the `_SNOMED_DIAGNOSTIC` table above), because the local CPSC raw
# `.hea` files carry `#Dx: 164867002,427084000` style SNOMED codes rather than
# the official 9 class names.
# A repo-wide grep confirms this table is referenced only by
# `src/data/__init__.py` (re-export) and `tests/test_data.py` (assertions);
# no pipeline code calls it.
#
# Corpus identity: the local CPSC data is **CPSC2018**, i.e. the union of
#   - CPSC Database      (PhysioNet/CinC 2020, 6,877 records; 9 SNOMED codes)
#   - CPSC-Extra Database(PhysioNet/CinC 2020, 3,453 records; 72 SNOMED codes)
# There is no CPSC2019 in this corpus (CPSC2019 was a QRS/heart-rate detection
# task with no diagnostic labels). Older comments in this file calling the
# extra records a "CPSC2019 extension" were factually wrong.
#
# ⚠️ A consequence that must be disclosed to reviewers: the MI class inside the
# paper's 4-class subspace (14.7% of the CPSC test set) comes **entirely from
# CPSC-Extra's SNOMED labels** (164867002 old MI x1168, 164865005 MI x376,
# 54329005 anterior MI x62, ...), whereas the **official CPSC2018 nine classes
# contain no MI at all**. Under a strict official-class-name caliber the
# 4-class subspace would degrade to {NORM, CD, STTC} (3 classes). This caliber
# choice must be declared explicitly in the paper's data section.
#
# CPSC HYP is extremely rare (n=11, all from CPSC-Extra single-label LVH/RVH);
# per preregistered protocol §2 the primary analysis downgrades to
# SUBSPACE_CPSC={NORM, CD, STTC, MI} (4 classes); HYP is counted then dropped
# (insufficient for a reliable estimate).
# ---------------------------------------------------------------------------
CPSC_TO_SUPERCLASS: dict[str, Optional[str]] = {
    "Normal": "NORM",
    "AF": "STTC",          # atrial fibrillation -> rhythm abnormality (same convention as PTB-XL AF->STTC)
    "AFLT": "STTC",        # atrial flutter (CPSC-Extra)
    "I-AVB": "CD",         # first-degree AV block
    "LBBB": "CD",
    "RBBB": "CD",
    "PAC": "STTC",         # premature atrial contraction -> ectopic rhythm (sensitivity object:
    #                      PTB-XL official ectopic statements have no class)
    "PVC": "STTC",         # premature ventricular contraction (same; mapped to STTC so all
    #                      CPSC records fall into the downgraded subspace)
    "STD": "STTC",         # ST depression
    "STE": "STTC",         # ST elevation
    "LAnFB": "CD",         # left anterior fascicular block (CPSC-Extra)
    "CLBBB": "CD",         # complete left bundle branch block (CPSC-Extra)
    "Brady": "STTC",       # bradycardia (CPSC-Extra)
    "OldMI": "MI",         # old myocardial infarction (CPSC-Extra; the only MI source in THIS table)
    #                        note: the real pipeline uses SNOMED keys, where MI also comes from
    #                        164867002/164865005/54329005/57054005/426434006 in _SNOMED_DIAGNOSTIC
}


def MAP_TO_5SUPERCLASS(
    scp_codes: dict,
    priority_rules: tuple = DEFAULT_PRIORITY,
    *,
    mapping: Optional[MappingType] = None,
    code_overrides: Optional[MappingType] = None,
    use_weights: bool = False,
) -> Optional[str]:
    """{scp_code: weight} -> single-label 5-superclass (returns None if unmappable).

    Parameters
    ----------
    scp_codes : dict
        {scp_code: weight}, keys are letter abbreviations or SNOMED numeric codes
        (auto-stringified).
    priority_rules : tuple
        Priority order (default DEFAULT_PRIORITY = MI>STTC>CD>HYP>NORM, fixed per
        preregistered protocol §2; see module docstring for the rationale). Must be a
        permutation of the 5 superclasses.
    mapping : dict, optional
        Code table (default SCP_TO_SUPERCLASS).
    code_overrides : dict, optional
        Variant code-table overrides (e.g. {"10370003": "STTC"}), taking precedence
        over mapping.
    use_weights : bool
        True ignores statements with weight<=0 (or NaN); False uses the official
        aggregation behavior (weights are ignored entirely). Default False.

    Returns
    -------
    str | None: the highest-priority superclass that is hit; None if no mappable
    statement is present.
    """
    if tuple(priority_rules) != tuple(SUPERCLASSES) and set(priority_rules) != set(SUPERCLASSES):
        raise ValueError(f"priority_rules must be a permutation of the 5 superclasses, got: {priority_rules}")
    table = dict(SCP_TO_SUPERCLASS if mapping is None else mapping)
    if code_overrides:
        table.update(code_overrides)

    candidates: list[str] = []
    for code, weight in scp_codes.items():
        if use_weights:
            try:
                if weight is None or not (float(weight) > 0):
                    continue
            except (TypeError, ValueError):
                continue
        cls = table.get(str(code).strip())
        if cls is not None and cls not in candidates:
            candidates.append(cls)
    if not candidates:
        return None
    for pri in priority_rules:
        if pri in candidates:
            return pri
    return None  # theoretically unreachable (priority_rules validated as full permutation)


def generate_mapping_variants():
    """Generate >=3 alternative mapping variants (preregistered protocol §10-T1
    mapping sensitivity analysis; generator that yields one variant at a time).

    Each variant is a dict:
        name            variant name
        priority        priority permutation for MAP_TO_5SUPERCLASS
        code_overrides  code-table overrides (may be empty dict)
        rationale       variant motivation
        probe_codes     example record for validation {scp_code: weight}
        expected_label  expected label for probe_codes under this variant (for discriminability tests)
    """
    # Variant 1: fully reversed priority (NORM first); tests the "pathology-first"
    # convention direction.
    yield {
        "name": "priority_norm_first",
        "priority": ("NORM", "HYP", "CD", "STTC", "MI"),
        "code_overrides": {},
        "rationale": "fully reversed priority: normal over pathology, testing robustness of the single-labeling direction",
        "probe_codes": {"NORM": 100.0, "IMI": 100.0},
        "expected_label": "NORM",
    }
    # Variant 2: STTC and MI swapped (STTC first); tests the "ischemia over
    # conduction/ST-T" ordering assumption.
    yield {
        "name": "priority_sttc_over_mi",
        "priority": ("STTC", "MI", "CD", "HYP", "NORM"),
        "code_overrides": {},
        "rationale": "ST/T change prioritized over MI: records co-occurring MI and STTC (e.g. IMI+ISCIN) reclassified as STTC",
        "probe_codes": {"IMI": 100.0, "ISCIN": 100.0},
        "expected_label": "STTC",
    }
    # Variant 3: ambiguous code 10370003 reclassified (baseline CD = bundle branch
    # block literal; CINC2021 uses it as pacing rhythm).
    yield {
        "name": "bbb_10370003_to_sttc",
        "priority": DEFAULT_PRIORITY,
        "code_overrides": {"10370003": "STTC"},
        "rationale": "10370003 is a known cross-database ambiguous code (SNOMED literal = bundle branch block -> CD; CINC2021 = pacing rhythm); reclassified to STTC to test robustness of the ambiguity decision",
        "probe_codes": {"10370003": 100.0},
        "expected_label": "STTC",
    }
    # Variant 4: sinus rate/morphology statements reclassified to STTC (the convention
    # before the sinus-family correction), tests whether sinus-family -> NORM changes
    # the cross-database calibration-transfer primary conclusion (contrast arm vs the
    # Chapman override).
    yield {
        "name": "sinus_rhythm_abnormality_to_sttc",
        "priority": DEFAULT_PRIORITY,
        "code_overrides": {"SBRAD": "STTC", "STACH": "STTC", "SARRH": "STTC"},
        "rationale": "sensitivity object for the sinus-family decision: SBRAD/STACH/SARRH under the old 'rhythm abnormality -> STTC' convention, testing whether sinus-family -> NORM changes the cross-database calibration-transfer primary conclusion (contrast arm vs the Chapman override)",
        "probe_codes": {"SBRAD": 100.0, "1AVB": 100.0},
        "expected_label": "STTC",
    }


def filter_subspace(
    labels: Iterable[Optional[str]],
    allowed: Iterable[str] = SUBSPACE_CPSC,
) -> dict:
    """Downgraded-subspace filtering + count report (preregistered protocol §2: CPSC
    primary analysis symmetrically recomputes within the subspace on both sides).

    Parameters
    ----------
    labels : sequence
        Superclass label of each record (None = unmappable, counted as dropped and
        listed separately as "None").
    allowed : container
        Set of superclasses to keep (default CPSC subspace {NORM, CD, STTC, MI}).

    Returns
    -------
    dict: kept/dropped indices, per-class counts (kept_counts/dropped_counts), usable
    directly by a STROBE-style per-class counting flow. The allowed field is always
    emitted in sorted order (set iteration order drifts with PYTHONHASHSEED and must
    not be used for deterministic reporting).
    """
    allowed_set = set(allowed)
    kept_indices: list[int] = []
    dropped_indices: list[int] = []
    kept_counts: Counter = Counter()
    dropped_counts: Counter = Counter()
    for i, lbl in enumerate(labels):
        key = lbl if lbl is not None else "None"
        if lbl is not None and lbl in allowed_set:
            kept_indices.append(i)
            kept_counts[key] += 1
        else:
            dropped_indices.append(i)
            dropped_counts[key] += 1
    return {
        "allowed": tuple(sorted(allowed_set)),
        "n_total": len(kept_indices) + len(dropped_indices),
        "n_kept": len(kept_indices),
        "n_dropped": len(dropped_indices),
        "kept_indices": kept_indices,
        "dropped_indices": dropped_indices,
        "kept_counts": dict(kept_counts),
        "dropped_counts": dict(dropped_counts),
    }


if __name__ == "__main__":
    # self-check: hard task requirements + priority + variant discriminability
    assert SCP_TO_SUPERCLASS["426783006"] == "NORM", "sinus rhythm must map to NORM"
    assert MAP_TO_5SUPERCLASS({"NORM": 100, "IMI": 100}) == "MI"
    assert MAP_TO_5SUPERCLASS({"1AVB": 100, "ISC_": 100}) == "STTC"
    assert MAP_TO_5SUPERCLASS({"NORM": 100, "LVH": 100}) == "HYP"
    assert MAP_TO_5SUPERCLASS({"SR": 100, "NORM": 100}) == "NORM"
    # sinus rate/morphology statements -> NORM, so they do not mask true conduction/hypertrophy diagnoses
    assert MAP_TO_5SUPERCLASS({"SBRAD": 100}) == "NORM", "sinus bradycardia must map to NORM"
    assert MAP_TO_5SUPERCLASS({"STACH": 100}) == "NORM", "sinus tachycardia must map to NORM"
    assert MAP_TO_5SUPERCLASS({"SARRH": 100}) == "NORM", "sinus arrhythmia must map to NORM"
    assert MAP_TO_5SUPERCLASS({"SBRAD": 100, "1AVB": 100}) == "CD", "sinus bradycardia must not mask 1AVB (conduction)"
    assert MAP_TO_5SUPERCLASS({"STACH": 100, "LVH": 100}) == "HYP", "sinus tachycardia must not mask LVH"
    assert MAP_TO_5SUPERCLASS({"AFIB": 100}) == "STTC"
    assert MAP_TO_5SUPERCLASS({"unknown_code_xyz": 100}) is None
    # Known cross-encoding inconsistency: the same diagnosis maps via the letter
    # abbreviation to NORM but via the SNOMED code to STTC (the global table is
    # CINC2021-customized). The Chapman side aligns to NORM via the code_overrides
    # override in preprocess_chapman.py; the PTB-XL side does not trigger this
    # because it uses letter-abbreviation keys.
    # TODO: verify label semantics in the CINC2021 context before unifying the global table.
    # Registered as a preregistered protocol §10-T1 sensitivity-analysis object.
    _cross_code_conflicts = {
        "sinus bradycardia": ("SBRAD", "426177001"),   # SBRAD->NORM vs 426177001->STTC
        "sinus tachycardia": ("STACH", "427084000"),   # STACH->NORM vs 427084000->STTC
        "sinus arrhythmia": ("SARRH", "427393009"),    # SARRH->NORM vs 427393009->STTC
    }
    for dx, (abbr, snomed) in _cross_code_conflicts.items():
        v_abbr = SCP_TO_SUPERCLASS[abbr]
        v_snomed = SCP_TO_SUPERCLASS[snomed]
        if v_abbr != v_snomed:
            print(f"[known conflict] {dx}: {abbr}->{v_abbr} vs {snomed}->{v_snomed} "
                  f"(aligned via Chapman override; registered as §10-T1 sensitivity object)")
    assert MAP_TO_5SUPERCLASS({}) is None
    variants = list(generate_mapping_variants())
    assert len(variants) >= 3
    for v in variants:
        got = MAP_TO_5SUPERCLASS(v["probe_codes"], v["priority"],
                                 code_overrides=v["code_overrides"])
        assert got == v["expected_label"], f"variant {v['name']} probe mismatch: {got}"
    labels = ["NORM", "CD", "STTC", "HYP", "MI", None]
    rep = filter_subspace(labels)
    assert rep["n_kept"] == 4 and rep["kept_counts"] == {"NORM": 1, "CD": 1, "STTC": 1, "MI": 1}
    assert len(SCP_TO_SUPERCLASS) >= 60, f"code table too small: {len(SCP_TO_SUPERCLASS)}"
    print(f"[self-check] mapping module passed: {len(SCP_TO_SUPERCLASS)} codes total "
          f"({sum(1 for v in SCP_TO_SUPERCLASS.values() if v is None)} explicitly unmappable)")
