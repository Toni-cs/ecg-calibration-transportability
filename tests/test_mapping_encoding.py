"""Regression test: pin the CPSC 4-class subspace **encoding order**.

Run with either of:
    pytest tests/ -v
    python tests/test_mapping_encoding.py

Why this test exists
--------------------
``label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}`` means the *order* of
the ``SUBSPACE_CPSC`` tuple **is** the integer label encoding. Changing the order
re-labels the data while leaving model output indices untouched, producing a
silent semantic mismatch between checkpoints and data.

That is not hypothetical: on 2026-09-09 the order was changed from
``("NORM","CD","STTC","MI")`` to ``("NORM","MI","STTC","CD")`` without retraining,
which swapped the MI and CD classes for every CPSC-containing experiment. The
archived per-experiment ``transfer_result.json`` files still record the original
encoding (``label_map: {NORM: 0, CD: 1, STTC: 2, MI: 3}``), which is what this
test pins.

If the order ever genuinely needs to change, every CPSC model must be retrained
and the whole main analysis re-run -- do not relax this test.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.mapping import (  # noqa: E402
    SUBSPACE_CPSC,
    SUPERCLASSES,
    CPSC_TO_SUPERCLASS,
    filter_subspace,
)


def test_subspace_cpsc_order_is_pinned():
    """The tuple order is the label encoding and must not change silently."""
    assert SUBSPACE_CPSC == ("NORM", "CD", "STTC", "MI"), (
        "SUBSPACE_CPSC order changed! This order is the integer label encoding "
        "used by every CPSC-containing experiment. Changing it makes all CPSC "
        "checkpoints semantically inconsistent with the data. If the change is "
        "intended, retrain every model and re-run the main analysis."
    )


def test_derived_label_map_matches_archived_artifacts():
    """Derived label_map must equal the encoding recorded in transfer_result.json."""
    label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}
    assert label_map == {"NORM": 0, "CD": 1, "STTC": 2, "MI": 3}


def test_subspace_order_differs_from_superclasses_prefix():
    """SUBSPACE_CPSC is deliberately NOT SUPERCLASSES[:4].

    SUPERCLASSES[:4] == ("NORM","MI","STTC","CD"). The CPSC subspace uses a
    different order because that is the order the models were trained with.
    This is a recorded historical fact, not a typo -- do not "tidy" it.
    """
    assert SUBSPACE_CPSC != tuple(SUPERCLASSES[:4])


def test_subspace_set_is_unchanged():
    """Only the *order* is pinned; the *set* must stay the 4 designed classes."""
    assert set(SUBSPACE_CPSC) == {"NORM", "CD", "STTC", "MI"}
    assert "HYP" not in CPSC_TO_SUPERCLASS.values()


def test_filter_subspace_is_order_insensitive():
    """filter_subspace must not depend on the tuple order (it uses a set)."""
    labels = ["NORM", "CD", "STTC", "HYP", "MI", None]
    rep = filter_subspace(labels, SUBSPACE_CPSC)
    assert rep["kept_indices"] == [0, 1, 2, 4]
    assert rep["dropped_indices"] == [3, 5]
    assert rep["kept_counts"] == {"NORM": 1, "CD": 1, "STTC": 1, "MI": 1}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")
