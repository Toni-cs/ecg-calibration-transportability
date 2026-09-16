"""Patient-level splitting and leakage-assertion module (preregistered protocol §2 leakage
prevention protocol).

Functions:
1. ``patient_wise_split``: patient-level stratified split train/cal/test (Chapman/CPSC 70/10/20,
   fixed seed; stratification key = patient majority label; numpy Generator)
2. ``ptbxl_official_folds``: PTB-XL official 10-fold loading (folds 1-8 train / 9 calibration /
   10 test; per Wagner 2020: strat_fold is obtained by stratified sampling and respects patient
   assignment, folds 9/10 were manually reviewed and have higher label quality)
3. ``assert_no_leakage``: hard assertion that train/cal/test patient-ID intersections are empty
   (protocol §2 "hard assertion script: into CI and the reproduction repo"); supports
   ``patient_of_record`` to normalize record-level input to patient-level before checking
   intersections; NaN/None IDs are rejected (NaN objects are not equal to each other, so a set
   intersection cannot detect cross-split leakage)
4. ``coverage_report``: per-class support counts + union/intersection diagnostics (protocol §2
   class-coverage checklist; empty classes listed separately)

Design notes:
- resampling unit = patient (consistent with protocol §7 cluster bootstrap); splitting never
  shuffles by record
- stratification key = patient majority label (multi-record patients take the mode; ties take the
  lexically-first label, deterministic)
- tiny strata (fewer than 3 patients) are merged entirely into train: record-level randomness
  would only produce spurious independence; patient-level guarantees no same-stratum patient
  crosses splits (no leakage; cost is the split variance of tiny strata, known per protocol §7)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Callable, Hashable, Iterable, Mapping as MappingType, Optional, Sequence

import numpy as np
import pandas as pd

from src.data.mapping import SUPERCLASSES

__all__ = [
    "patient_wise_split",
    "ptbxl_official_folds",
    "assert_no_leakage",
    "coverage_report",
]

DEFAULT_RATIOS = (0.7, 0.1, 0.2)


def _resolve_label_for_patient(
    patient_ids: Sequence,
    label_for_patient,
) -> dict:
    """Resolve label_for_patient (Mapping or callable) into {pid: stratum}."""
    if isinstance(label_for_patient, MappingType):
        mapping = label_for_patient
        missing = [p for p in patient_ids if p not in mapping]
        if missing:
            raise KeyError(f"label_for_patient missing patient stratification keys: {missing[:5]} ...")
        return {p: mapping[p] for p in patient_ids}
    if callable(label_for_patient):
        return {p: label_for_patient(p) for p in patient_ids}
    raise TypeError("label_for_patient must be a Mapping or callable(pid)->stratum")


def patient_wise_split(
    patient_ids: Sequence[Hashable],
    label_for_patient,
    ratios: Sequence[float] = DEFAULT_RATIOS,
    seed: int = 42,
) -> dict[str, list]:
    """Patient-level stratified split: returns {"train": [...], "cal": [...], "test": [...]}.

    - stratify by patient stratification key (patient majority label); shuffle within stratum
      using numpy Generator(seed)
    - within-stratum quotas use the largest-remainder method to keep the total ratio closest to
      ratios
    - strata with fewer than 3 patients are merged entirely into train (see module docstring)
    - ratios must sum to 1 (tolerance 1e-9)

    Note: with very few patients cal/test may end up empty (e.g. total < 10); raise in that
    case rather than silently returning an empty split, since the protocol requires each split
    to be independently usable for fitting/evaluation.
    """
    if len(ratios) != 3:
        raise ValueError(f"ratios must be a (train,cal,test) triple, got: {ratios}")
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError(f"ratios must sum to 1, got: {sum(ratios)}")
    patient_ids = list(patient_ids)
    n_total = len(patient_ids)
    if n_total == 0:
        raise ValueError("patient_ids is empty")
    strata = _resolve_label_for_patient(patient_ids, label_for_patient)

    rng = np.random.default_rng(seed)
    by_stratum: dict = defaultdict(list)
    for p in patient_ids:
        by_stratum[strata[p]].append(p)

    split_names = ("train", "cal", "test")
    splits: dict[str, list] = {name: [] for name in split_names}
    for _, members in sorted(by_stratum.items(), key=lambda kv: str(kv[0])):
        members = np.asarray(members, dtype=object)
        members = members[rng.permutation(len(members))]  # shuffle patients within stratum
        n = len(members)
        if n < 3:
            splits["train"].extend(members.tolist())
            continue
        raw = [r * n for r in ratios]
        quota = [int(np.floor(x)) for x in raw]
        remainder = n - sum(quota)
        # largest-remainder: distribute leftover slots to splits by descending fractional part
        order = sorted(range(3), key=lambda i: raw[i] - quota[i], reverse=True)
        for k in range(remainder):
            quota[order[k % 3]] += 1
        start = 0
        for name, q in zip(split_names, quota):
            splits[name].extend(members[start:start + q].tolist())
            start += q

    for name in split_names:
        if not splits[name]:
            raise ValueError(
                f"split '{name}' is empty after splitting (total patients={n_total}); "
                "please increase the data size or adjust ratios"
            )
    return splits


def ptbxl_official_folds(meta_df: pd.DataFrame) -> dict:
    """PTB-XL official 10-fold split (Wagner 2020 protocol: folds 1-8 train / 9 cal / 10 test).

    Per Wagner et al., Sci Data 2020, v1.0.3: strat_fold is obtained by stratified sampling
    (stratified by patient and age/sex) and respects patient assignment (all records of one
    patient share a fold); folds 9/10 were reviewed at least once and have higher label quality,
    so the official recommendation is folds 1-8 train / fold 9 validation (= this study's cal) /
    fold 10 test.

    Parameters
    ----------
    meta_df : DataFrame
        must contain columns 'patient_id' and 'fold' (fold=strat_fold, values 1..10).
        patient_id must not contain missing values (NaN objects are unequal, so the same patient
        could be split across folds and a set intersection would miss it); fold must be an integer
        1..10, with missing/non-integer/non-numeric values raising with the row number.

    Returns
    -------
    {"train": {"patients": ndarray, "records": ndarray(position indices)},
     "cal":   {...}, "test": {...}}
    """
    for col in ("patient_id", "fold"):
        if col not in meta_df.columns:
            raise KeyError(f"meta_df missing required column '{col}'")
    if meta_df["patient_id"].isna().any():
        bad_rows = np.flatnonzero(
            meta_df["patient_id"].isna().to_numpy()
        ).tolist()
        raise ValueError(
            f"patient_id contains missing values and is excluded from splitting "
            f"(NaN objects are unequal, cross-split leakage cannot be caught by set intersection; "
            f"missing rows: {bad_rows[:10]})"
        )
    out_of_range: set = set()
    folds_parsed: list[int] = []
    for i, f in enumerate(meta_df["fold"].tolist()):
        try:
            missing = pd.isna(f)
        except (TypeError, ValueError):
            missing = False
        if missing:
            raise ValueError(f"fold column row {i} contains a missing value")
        try:
            fval = float(f)
        except (TypeError, ValueError):
            raise ValueError(f"fold column row {i} contains a non-numeric value: {f!r}")
        if not np.isfinite(fval) or fval != int(fval):
            raise ValueError(f"fold column has a non-integer value: {f} (row {i})")
        fi = int(fval)
        if not (1 <= fi <= 10):
            out_of_range.add(fi)
        folds_parsed.append(fi)
    if out_of_range:
        raise ValueError(f"fold column has values outside the official range (1..10): {sorted(out_of_range)}")
    folds = np.array(folds_parsed)

    records_pos = np.arange(len(meta_df))
    spec = {"train": (1, 8), "cal": (9, 9), "test": (10, 10)}
    out: dict[str, dict] = {}
    for name, (lo, hi) in spec.items():
        mask = (folds >= lo) & (folds <= hi)
        idx = records_pos[mask]
        if len(idx) == 0:
            raise ValueError(f"split '{name}' (folds {lo}-{hi}) is empty")
        out[name] = {
            "patients": pd.unique(meta_df["patient_id"].to_numpy()[mask]),
            "records": idx,
        }
    return out


def _as_patient_set(value) -> set:
    """Normalize split value: list/set/tuple/ndarray or {"patients": ...}/{"patient_ids": ...}."""
    if isinstance(value, dict):
        for key in ("patients", "patient_ids"):
            if key in value:
                value = value[key]
                break
        else:
            raise KeyError("split value dict must contain a 'patients' or 'patient_ids' key")
    return set(value)


def _as_record_set(value) -> set:
    """Normalize record-level split value: list/set/tuple/ndarray or {"records": ...}/{"record_ids": ...}."""
    if isinstance(value, dict):
        for key in ("records", "record_ids"):
            if key in value:
                value = value[key]
                break
        else:
            raise KeyError("record-level split value dict must contain a 'records' or 'record_ids' key")
    return set(value)


def _nan_like_ids(ids: set) -> list:
    """Find NaN/None-like IDs in a set (pd.unique returns a different nan object each time, so a
    set intersection would miss the match)."""
    bad = []
    for v in ids:
        try:
            if pd.isna(v):
                bad.append(v)
        except (TypeError, ValueError):
            continue  # exotic objects that cannot be tested for isna are not treated as missing
    return bad


def assert_no_leakage(
    splits_dict: dict,
    patient_ids: Optional[Iterable] = None,
    patient_of_record: Optional[MappingType] = None,
) -> bool:
    """Hard assertion: the patient-ID sets of all splits are pairwise disjoint; raises ValueError
    on violation.

    Parameters
    ----------
    splits_dict : dict
        {"train": patient-ID container, "cal": ..., "test": ...}; values may be
        list/set/tuple/ndarray, or {"patients": ...} form (compatible with ptbxl_official_folds).
    patient_ids : optional
        the full set of valid patient IDs; when provided, additionally asserts each split contains
        only registered patients (guards against dirty IDs).
    patient_of_record : Mapping, optional
        {record ID: patient ID}. When provided, the values of splits_dict are interpreted as
        **record-level** IDs, normalized to patient IDs before the intersection check: treating
        record-level input directly as patient-level would silently miss "same patient across
        splits" leakage; record IDs missing from the mapping raise KeyError. When not provided,
        the input is assumed already patient-level: this function has no record mapping to rely on
        and does not validate that assumption; returning True only means "no intersection under the
        patient-level interpretation".

    Returns
    -------
    True (no leakage).

    Raises
    ------
    ValueError with a message listing the leaked patient IDs and the split pairs; input IDs
    containing NaN/None also raise (NaN objects are unequal, so a set intersection cannot detect
    them).
    """
    if patient_of_record is not None:
        sets: dict = {}
        for name, val in splits_dict.items():
            mapped: set = set()
            for rec in _as_record_set(val):
                if rec not in patient_of_record:
                    raise KeyError(
                        f"patient_of_record missing record ID: {rec!r} (split '{name}')"
                    )
                mapped.add(patient_of_record[rec])
            sets[name] = mapped
    else:
        sets = {name: _as_patient_set(val) for name, val in splits_dict.items()}
    nan_ids = {name: ids for name, ids in
               ((name, _nan_like_ids(s)) for name, s in sets.items()) if ids}
    if nan_ids:
        raise ValueError(
            f"[LEAKAGE] input IDs contain NaN/None and are excluded from splitting "
            f"(NaN objects are unequal, cross-split leakage cannot be caught by set intersection): {nan_ids}"
        )
    if patient_ids is not None:
        known = set(patient_ids)
        unknown = {name: sorted(s - known, key=str) for name, s in sets.items()}
        unknown = {name: ids for name, ids in unknown.items() if ids}
        if unknown:
            raise ValueError(f"split contains unregistered patient IDs: {unknown}")
    leaks: dict = defaultdict(list)
    leaked_ids: set = set()
    for (n1, s1), (n2, s2) in combinations(sets.items(), 2):
        inter = s1 & s2
        if inter:
            leaked_ids |= inter
            leaks[f"{n1}∩{n2}"] = sorted(inter, key=str)
    if leaked_ids:
        raise ValueError(
            f"[LEAKAGE] found {len(leaked_ids)} patient(s) appearing in multiple splits: "
            f"{sorted(leaked_ids, key=str)}; detail: {dict(leaks)}"
        )
    return True


def coverage_report(labels_per_split: MappingType[str, Iterable]) -> dict:
    """Per-class support counts + union/intersection diagnostics (protocol §2 class-coverage
    checklist; empty classes listed separately).

    Parameters
    ----------
    labels_per_split : dict
        {split name: label sequence} (None labels go into a "None" key, counted separately).

    Returns
    -------
    dict:
        classes             list of classes in the statistics (the 5 superclasses are always
                            present, even at count 0; empty classes listed separately)
        per_split          {split: {class: count}} (including zero counts)
        per_split_total    {split: n}
        union               classes appearing in any split
        intersection        classes appearing in all splits
        missing_per_split  {split: [classes in union missing from this split]}
    """
    classes = set(SUPERCLASSES)
    observed: dict[str, Counter] = {}
    for name, labels in labels_per_split.items():
        cnt = Counter(
            lbl if lbl is not None else "None" for lbl in labels
        )
        observed[name] = cnt
        classes |= set(cnt.keys())
    ordered_classes = sorted(classes, key=str)
    per_split = {name: {c: int(cnt.get(c, 0)) for c in ordered_classes}
                 for name, cnt in observed.items()}
    present = {name: {c for c, n in d.items() if n > 0} for name, d in per_split.items()}
    union = set().union(*present.values()) if present else set()
    intersection = set.intersection(*present.values()) if present else set()
    return {
        "classes": ordered_classes,
        "per_split": per_split,
        "per_split_total": {name: sum(d.values()) for name, d in per_split.items()},
        "union": sorted(union, key=str),
        "intersection": sorted(intersection, key=str),
        "missing_per_split": {
            name: sorted(union - present[name], key=str) for name in present
        },
    }


if __name__ == "__main__":
    # self-check: 500-patient stratified split + leakage assertion + coverage report
    rng = np.random.default_rng(0)
    pids = [f"P{i:04d}" for i in range(500)]
    labels = {p: str(rng.integers(0, 5)) for p in pids}
    splits = patient_wise_split(pids, labels, seed=42)
    sizes = {k: len(v) for k, v in splits.items()}
    assert abs(sizes["train"] / 500 - 0.7) < 0.05
    assert abs(sizes["cal"] / 500 - 0.1) < 0.05
    assert abs(sizes["test"] / 500 - 0.2) < 0.05
    assert assert_no_leakage(splits, pids) is True
    try:
        assert_no_leakage({"train": [1, 2, 3], "cal": [3], "test": [4]})
        raise AssertionError("should have detected leakage")
    except ValueError as e:
        assert "3" in str(e)
    rep = coverage_report({"train": ["NORM"] * 7 + ["MI"] * 3,
                           "test": ["NORM"] * 5 + ["STTC"] * 5})
    assert rep["missing_per_split"]["test"] == ["MI"]
    assert "STTC" in rep["missing_per_split"]["train"]
    print("Self-check: split module passed:", sizes)
