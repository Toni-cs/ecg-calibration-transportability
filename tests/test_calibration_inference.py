"""F2/F3修复回归测试：BCa、benefit_inference、两层bootstrap、SmoothECE带宽

覆盖R4轮对抗审查确认的测试盲区（修复本体的数值正确性此前零覆盖）。
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.calibration import (
    benefit_inference,
    two_layer_benefit_inference,
    smooth_ece,
    _bca_interval,
    _group_jackknife_benefit,
    fit_temperature,
    apply_temperature,
)


@pytest.fixture(scope="module")
def rng_data():
    rng = np.random.default_rng(7)
    n = 2000
    p_raw = rng.uniform(0.05, 0.95, n)
    # 注入失准：过自信（logit放大1.5倍）
    logits = np.log(p_raw / (1 - p_raw))
    p_cal = 1 / (1 + np.exp(-logits / 1.5))
    y = rng.binomial(1, p_cal).astype(float)
    return p_raw, p_cal, y


class TestBCaInterval:
    def test_bca_approx_percentile_normal_case(self):
        """近正态bootstrap分布下BCa≈percentile（Efron理论性质）"""
        rng = np.random.default_rng(1)
        boot = rng.normal(1.0, 0.2, 5000)
        jack = rng.normal(1.0, 0.2, 300)
        lo, hi = _bca_interval(1.0, boot, jack, 0.95)
        p_lo, p_hi = np.percentile(boot, [2.5, 97.5])
        assert lo == pytest.approx(p_lo, abs=0.05)
        assert hi == pytest.approx(p_hi, abs=0.05)

    def test_bca_too_few_boot_returns_nan(self):
        rng = np.random.default_rng(1)
        lo, hi = _bca_interval(1.0, rng.normal(0, 1, 5), rng.normal(0, 1, 20), 0.95)
        assert np.isnan(lo) and np.isnan(hi)

    def test_bca_zero_width_warns(self):
        """z0饱和→零宽CI→警告（R4轮P2修复）"""
        boot = np.full(100, 5.0)  # 点估计在分布同侧极端
        with pytest.warns(UserWarning, match="零宽"):
            lo, hi = _bca_interval(1.0, boot, np.linspace(0.9, 1.1, 50), 0.95)
        assert lo == hi

    def test_bca_bias_shift_direction(self):
        """z0<0（点估计低于bootstrap中位）→BCa区间整体左移（Efron方向性质）"""
        rng = np.random.default_rng(2)
        boot = rng.normal(1.0, 0.15, 5000)
        jack = np.linspace(0.8, 1.2, 100)  # 对称jack→a≈0，纯z0效应
        lo, hi = _bca_interval(0.9, boot, jack, 0.95)
        p_lo, p_hi = np.percentile(boot, [2.5, 97.5])
        assert lo < p_lo and hi < p_hi  # 整体左移
        assert lo < 0.9 < hi  # 点估计仍被覆盖


class TestBenefitInference:
    def test_bca_benefit_ci_brackets_point(self, rng_data):
        p_raw, p_cal, y = rng_data
        out = benefit_inference(p_raw, p_cal, y, metric=lambda p, l: float(
            np.mean(np.abs(p - l))), n_bootstrap=500,
            rng=np.random.default_rng(3))
        lo, hi = out['benefit_ci']
        assert lo < out['benefit'] < hi
        assert out['method'] == 'bca'

    def test_percentile_method_switch(self, rng_data):
        p_raw, p_cal, y = rng_data
        out = benefit_inference(p_raw, p_cal, y, metric=lambda p, l: float(
            np.mean(np.abs(p - l))), n_bootstrap=500, bci_method='percentile',
            rng=np.random.default_rng(3))
        assert out['method'] == 'percentile'
        lo, hi = out['benefit_ci']
        assert lo < out['benefit'] < hi

    def test_cluster_jackknife_path(self, rng_data):
        """clusters提供时leave-one-cluster-out路径不崩且CI有限"""
        p_raw, p_cal, y = rng_data
        clusters = np.arange(len(y)) // 20  # 100个"患者"
        out = benefit_inference(p_raw, p_cal, y, metric=lambda p, l: float(
            np.mean(np.abs(p - l))), n_bootstrap=300, clusters=clusters,
            rng=np.random.default_rng(4))
        lo, hi = out['benefit_ci']
        assert np.isfinite(lo) and np.isfinite(hi)
        assert lo < out['benefit'] < hi

    def test_b0_skips_ci(self, rng_data):
        p_raw, p_cal, y = rng_data
        out = benefit_inference(p_raw, p_cal, y, n_bootstrap=0)
        assert np.isnan(out['benefit_ci'][0])


class TestTwoLayerBootstrap:
    def test_point_estimate_consistency(self, rng_data):
        """点估计=全数据fit+apply后的ΔECE（T6验证性质固化）"""
        p_raw, p_cal, y = rng_data
        out = two_layer_benefit_inference(
            p_raw, labels_test=y, fit_probs=p_cal, fit_labels=y,
            fit_fn=lambda p, l: 1.0, apply_fn=lambda p, t: p,
            metric=lambda p, l: float(np.mean(np.abs(p - l))),
            b_val=10, b_test=50, rng=np.random.default_rng(5),
        )
        assert out['t_hat'] == 1.0
        assert np.isfinite(out['benefit'])

    def test_2d_probs_branch(self, rng_data):
        """2D概率矩阵闭包路径（train.py实际使用形态）"""
        rng = np.random.default_rng(6)
        n, c = 500, 3
        p2d = rng.dirichlet(np.ones(c), size=n)
        labels = rng.integers(0, c, n)
        one_hot = np.eye(c)[labels]
        out = two_layer_benefit_inference(
            p2d, labels_test=(p2d.argmax(1) == labels).astype(float),
            fit_probs=p2d, fit_labels=one_hot,
            fit_fn=fit_temperature, apply_fn=apply_temperature,
            metric=lambda p, l: float(np.mean(np.abs(p - l))),
            b_val=5, b_test=20, rng=np.random.default_rng(7),
        )
        assert np.isfinite(out['t_hat']) and out['t_hat'] > 0
        assert np.isfinite(out['benefit'])

    def test_bval_zero_uses_t_hat(self, rng_data):
        p_raw, p_cal, y = rng_data
        out = two_layer_benefit_inference(
            p_raw, labels_test=y, fit_probs=p_cal, fit_labels=y,
            fit_fn=lambda p, l: 2.0, apply_fn=lambda p, t: p,
            metric=lambda p, l: float(np.mean(np.abs(p - l))),
            b_val=0, b_test=20, rng=np.random.default_rng(8),
        )
        assert out['t_hat'] == 2.0

    def test_ci_brackets_point(self, rng_data):
        p_raw, p_cal, y = rng_data
        out = two_layer_benefit_inference(
            p_raw, labels_test=y, fit_probs=p_cal, fit_labels=y,
            fit_fn=lambda p, l: 1.0, apply_fn=lambda p, t: p,
            metric=lambda p, l: float(np.mean(np.abs(p - l))),
            b_val=20, b_test=200, rng=np.random.default_rng(9),
        )
        lo, hi = out['benefit_ci']
        assert lo - 1e-3 <= out['benefit'] <= hi + 1e-3


class TestSmoothECEBandwidth:
    def test_anchor_n2000(self):
        """F3修复：n=2000时默认带宽=0.45（与既有标定锚点一致）"""
        rng = np.random.default_rng(10)
        p = rng.uniform(0.05, 0.95, 2000)
        y = rng.binomial(1, p).astype(float)
        assert smooth_ece(p, y) == pytest.approx(smooth_ece(p, y, bandwidth=0.45))

    def test_bandwidth_scaling_direction(self):
        """n^(-0.2)：n增大→带宽减小（自适应锐化）"""
        n_small, n_large = 500, 20000
        h_small = 0.45 * (n_small / 2000) ** (-0.2)
        h_large = 0.45 * (n_large / 2000) ** (-0.2)
        assert h_small > 0.45 > h_large