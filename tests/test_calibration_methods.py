"""校准方法库测试"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.calibration import smooth_ece, ece
from src.utils.calibration_methods import (
    fit_isotonic, apply_isotonic,
    fit_vector_scaling, apply_vector_scaling,
    fit_matrix_scaling, apply_matrix_scaling,
    fit_dirichlet, apply_dirichlet,
    fit_saerens_em, apply_prior_correction,
    fit_oracle, apply_oracle,
    fit_temperature_multiclass, apply_temperature_multiclass,
    fit_platt_multiclass, apply_platt_multiclass,
    CALIBRATION_METHODS,
)


def _make_miscalibrated(n=2000, K=5, seed=0):
    """构造miscalibrated数据：基线校准 → 施加 p^2 + shift 畸变"""
    rng = np.random.default_rng(seed)
    p = rng.dirichlet(np.ones(K), size=n)  # 基线：随机但合法概率
    z = np.log(np.clip(p, 1e-12, 1))
    z_mis = 2.0 * z + 0.5   # 过自信畸变
    z_mis = z_mis - z_mis.max(axis=1, keepdims=True)
    e = np.exp(z_mis)
    probs_mis = e / e.sum(axis=1, keepdims=True)
    labels = rng.choice(K, size=n, p=np.ones(K) / K)
    return probs_mis, labels


def _argmax(a):
    return a.argmax(axis=1)


class TestCalibrationRecovery:
    """测试1：miscalibrated数据fit后ECE应下降"""

    @pytest.mark.parametrize("name", ["ts", "platt", "vector", "matrix", "dirichlet", "oracle"])
    def test_ece_decreases(self, name):
        probs, labels = _make_miscalibrated()
        fit_fn, apply_fn, _ = CALIBRATION_METHODS[name]
        params = fit_fn(probs, labels)
        cal = apply_fn(probs, params)
        raw_e = smooth_ece(probs.max(1), (_argmax(probs) == labels).astype(float))
        cal_e = smooth_ece(cal.max(1), (_argmax(cal) == labels).astype(float))
        assert cal_e < raw_e, f"{name}: cal_ece={cal_e} >= raw_ece={raw_e}"

    def test_isotonic_ece_decreases(self):
        probs, labels = _make_miscalibrated(n=2000)
        params = fit_isotonic(probs, labels)
        assert params is not None
        cal = apply_isotonic(probs, params)
        raw_e = smooth_ece(probs.max(1), (_argmax(probs) == labels).astype(float))
        cal_e = smooth_ece(cal.max(1), (_argmax(cal) == labels).astype(float))
        assert cal_e < raw_e


class TestNoDegradation:
    """测试2：已校准数据apply后ECE不应恶化超过+0.02"""

    @pytest.mark.parametrize("name", ["ts", "vector", "matrix", "dirichlet"])
    def test_no_degradation(self, name):
        rng = np.random.default_rng(1)
        n, K = 2000, 5
        p = rng.dirichlet(np.ones(K) * 2, size=n)
        labels = np.array([rng.choice(K, p=p[i]) for i in range(n)])  # 按p采样=校准
        fit_fn, apply_fn, _ = CALIBRATION_METHODS[name]
        params = fit_fn(p, labels)
        cal = apply_fn(p, params)
        y = lambda pr, la: smooth_ece(pr.max(1), (_argmax(pr) == la).astype(float))
        # argmax不变时label一致性相同；TS/vector/matrix不改argmax
        assert y(cal, labels) <= y(p, labels) + 0.02, \
            f"{name}: {y(p, labels):.4f} -> {y(cal, labels):.4f}"


class TestArgmaxPreserved:
    """测试3：只有全局TS保证top-1 argmax不变（协议Sanity条目）
    vector/matrix/dirichlet按类操作，本就可以改变argmax——不约束。
    """

    def test_argmax_preserved_ts(self):
        probs, labels = _make_miscalibrated()
        params = fit_temperature_multiclass(probs, labels)
        cal = apply_temperature_multiclass(probs, params)
        assert np.array_equal(_argmax(probs), _argmax(cal))


class TestSmallSampleGuards:
    """测试4：小样本防护"""

    def test_isotonic_returns_none(self):
        probs, labels = _make_miscalibrated(n=30)
        assert fit_isotonic(probs, labels) is None

    def test_matrix_small_sample_returns_none(self):
        """修复后语义：n=30 < 2×(25+5) → 返回None（不再静默返回垃圾参数）"""
        probs, labels = _make_miscalibrated(n=30)
        params = fit_matrix_scaling(probs, labels)
        assert params is None
        with pytest.raises(ValueError):
            apply_matrix_scaling(probs, None)


class TestSaerensEM:
    """测试5：Saerens EM先验估计"""

    def test_prior_recovery(self):
        rng = np.random.default_rng(2)
        n = 5000
        pi_train = np.array([0.6, 0.4])
        pi_target_true = np.array([0.3, 0.7])
        # 用"校准模型"生成target预测：标签~π_target，预测=该类的soft one-hot
        labels_t = rng.choice(2, size=n, p=pi_target_true)
        # 模型有区分力但不完美
        probs = np.zeros((n, 2))
        for i in range(n):
            true = labels_t[i]
            if rng.uniform() < 0.8:
                probs[i, true] = 0.9
            else:
                probs[i, 1 - true] = 0.9
            probs[i, 1 - true] = max(probs[i, 1 - true], 0.1)
            probs[i, true] = max(probs[i, true], 0.1)
            s = probs[i].sum()
            probs[i] /= s
        pi_hat = fit_saerens_em(probs, pi_train)
        l1 = np.abs(pi_hat - pi_target_true).sum()
        assert l1 < 0.05, f"Saerens估计偏差过大: pi_hat={pi_hat}, L1={l1}"

    def test_prior_correction(self):
        probs, _ = _make_miscalibrated(n=100)
        pi_train = np.ones(5) / 5
        cal = apply_prior_correction(probs, pi_train, pi_train)
        assert np.allclose(cal, probs, atol=1e-9)  # 相同先验=恒等


class TestEdgeCases:
    """测试6：边界情况"""

    @pytest.mark.parametrize("name", ["ts", "vector", "dirichlet"])
    def test_all_ones_prob(self, name):
        probs = np.ones((10, 5)) / 5
        labels = np.arange(10) % 5
        fit_fn, apply_fn, _ = CALIBRATION_METHODS[name]
        params = fit_fn(probs, labels)
        cal = apply_fn(probs, params)
        assert np.isfinite(cal).all()

    def test_all_ones_prob_matrix_none(self):
        """matrix在n=10时按守卫返回None（正确行为），apply应raise而非静默"""
        probs = np.ones((10, 5)) / 5
        labels = np.arange(10) % 5
        params = fit_matrix_scaling(probs, labels)
        assert params is None

    def test_binary_K2(self):
        probs, labels = _make_miscalibrated(n=500, K=2)
        params = fit_vector_scaling(probs, labels)
        cal = apply_vector_scaling(probs, params)
        assert cal.shape == (500, 2)

    def test_K10(self):
        probs, labels = _make_miscalibrated(n=1000, K=10)
        params = fit_vector_scaling(probs, labels)
        cal = apply_vector_scaling(probs, params)
        assert np.allclose(cal.sum(axis=1), 1.0, atol=1e-6)


class TestRegistry:
    """测试7：注册表与n_params"""

    def test_registry_complete(self):
        expected = {'none', 'ts', 'platt', 'isotonic', 'vector', 'matrix',
                    'dirichlet', 'saerens', 'oracle'}
        assert set(CALIBRATION_METHODS.keys()) == expected
        # 修复HIGH-1后：saerens在注册表且needs_labels=False
        assert CALIBRATION_METHODS['saerens'][2] is False

    def test_platt_fit_apply_consistency(self):
        """修复FATAL-1的回归测试：apply(fit(同数据))的NLL必须≤raw NLL"""
        from src.utils.calibration_methods import _to_logits, _nll
        probs, labels = _make_miscalibrated()
        onehot = np.eye(5)[labels]
        params = fit_platt_multiclass(probs, labels)
        cal = apply_platt_multiclass(probs, params)
        assert _nll(_to_logits(cal), onehot) <= _nll(_to_logits(probs), onehot) + 1e-6

    def test_n_params(self):
        probs, labels = _make_miscalibrated(n=500)
        assert fit_temperature_multiclass(probs, labels)['n_params'] == 1
        assert fit_vector_scaling(probs, labels)['n_params'] == 10  # 2*5
        assert fit_matrix_scaling(probs, labels)['n_params'] == 30  # 25+5
        assert fit_platt_multiclass(probs, labels)['n_params'] == 10
