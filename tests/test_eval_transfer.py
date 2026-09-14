"""eval_transfer.py 单元测试：覆盖纯函数与边界分支（M10修复）"""
import sys
from pathlib import Path

import numpy as np
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from eval_transfer import fit_apply_method, _maxprob, _bin, DATASET_NUM_CLASSES
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES


class TestMaxprob:
    def test_2d_to_1d(self):
        p = np.array([[0.1, 0.7, 0.2], [0.5, 0.3, 0.2]])
        result = _maxprob(p)
        assert result.shape == (2,)
        np.testing.assert_allclose(result, [0.7, 0.5])

    def test_single_row(self):
        p = np.array([[0.3, 0.7]])
        assert _maxprob(p) == pytest.approx(0.7)


class TestBin:
    def test_correct_predictions(self):
        p = np.array([[0.1, 0.9], [0.8, 0.2]])
        labels = np.array([1, 0])
        result = _bin(p, labels)
        np.testing.assert_array_equal(result, [1.0, 1.0])

    def test_incorrect_predictions(self):
        p = np.array([[0.1, 0.9], [0.8, 0.2]])
        labels = np.array([0, 0])
        result = _bin(p, labels)
        np.testing.assert_array_equal(result, [0.0, 1.0])


class TestFitApplyMethod:
    def test_none_returns_original(self):
        probs = np.random.rand(10, 3)
        result, params = fit_apply_method("none", probs, None, probs)
        np.testing.assert_array_equal(result, probs)

    def test_ts_applies_temperature(self):
        fit_probs = np.random.rand(50, 3)
        fit_probs /= fit_probs.sum(axis=1, keepdims=True)
        fit_labels = np.random.randint(0, 3, 50)
        test_probs = np.random.rand(20, 3)
        test_probs /= test_probs.sum(axis=1, keepdims=True)
        result, params = fit_apply_method("ts", fit_probs, fit_labels, test_probs)
        assert result.shape == test_probs.shape
        assert np.allclose(result.sum(axis=1), 1.0, atol=1e-6)
        assert 'T' in params

    def test_unknown_method_raises(self):
        probs = np.random.rand(10, 3)
        with pytest.raises(KeyError):
            fit_apply_method("nonexistent", probs, None, probs)


class TestNumClassesAndLabelMap:
    """验证4类/5类降级的 label_map 一致性（防止跨实验标签语义混淆）"""

    def test_dataset_num_classes_values(self):
        assert DATASET_NUM_CLASSES["ptbxl"] == 5
        assert DATASET_NUM_CLASSES["chapman"] == 5
        assert DATASET_NUM_CLASSES["cpsc"] == 4

    def test_5class_label_map_matches_superclasses(self):
        label_map = {c: i for i, c in enumerate(SUPERCLASSES)}
        assert label_map == {"NORM": 0, "MI": 1, "STTC": 2, "CD": 3, "HYP": 4}

    def test_4class_label_map_matches_subspace_cpsc(self):
        label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}
        assert label_map == {"NORM": 0, "CD": 1, "STTC": 2, "MI": 3}

    def test_4class_and_5class_label_maps_differ(self):
        lm5 = {c: i for i, c in enumerate(SUPERCLASSES)}
        lm4 = {c: i for i, c in enumerate(SUBSPACE_CPSC)}
        assert lm5["MI"] != lm4["MI"], "MI 编号在4类5类间应不同"
        assert lm5["CD"] != lm4["CD"], "CD 编号在4类5类间应不同"

    def test_num_classes_inference_min(self):
        for s, t in [("ptbxl", "chapman"), ("chapman", "ptbxl")]:
            nc = min(DATASET_NUM_CLASSES[s], DATASET_NUM_CLASSES[t])
            assert nc == 5, f"{s}->{t} 应为5类"
        for s, t in [("ptbxl", "cpsc"), ("cpsc", "ptbxl"),
                     ("chapman", "cpsc"), ("cpsc", "chapman"),
                     ("cpsc", "cpsc")]:
            nc = min(DATASET_NUM_CLASSES[s], DATASET_NUM_CLASSES[t])
            assert nc == 4, f"{s}->{t} 应为4类"

    def test_subspace_cpsc_is_4_classes(self):
        assert len(SUBSPACE_CPSC) == 4
        assert set(SUBSPACE_CPSC) == {"NORM", "CD", "STTC", "MI"}
        assert "HYP" not in SUBSPACE_CPSC