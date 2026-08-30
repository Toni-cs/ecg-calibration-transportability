"""三成分分解 v2 单元测试（含攻击者反例回归测试）"""

import sys
import subprocess
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.decomposition import (
    inject_transform,
    resample_prevalence,
    recover_slope_intercept,
    decompose_benefit,
    fisher_information_det,
    identifiability_gate,
    IDENTIFIABILITY_TAU,
    ece_metric_safe,
)


@pytest.fixture(scope="module")
def baseline():
    rng = np.random.default_rng(42)
    n = 20000
    p = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(0, 1, n) < p).astype(float)
    return p, y


class TestInjection:
    def test_identity(self, baseline):
        p, _ = baseline
        out = inject_transform(p, 1.0, 0.0)
        assert np.allclose(out, p, atol=1e-5)

    def test_slope_effect(self, baseline):
        p, _ = baseline
        out = inject_transform(p, 2.0, 0.0)
        # s=2使概率向两端极端化：高p段上移，低p段下移
        hi = p > 0.5
        assert (out[hi] > p[hi]).mean() > 0.95
        assert (out[~hi] < p[~hi]).mean() > 0.95

    def test_validation_rejects_multiclass(self, baseline):
        p, _ = baseline
        with pytest.raises(ValueError, match="1维"):
            inject_transform(p.reshape(-1, 1), 2.0, 0.0)

    def test_validation_rejects_multiclass_labels(self, baseline):
        p, _ = baseline
        # 合法1D二分类输入：不raise（sanity）
        inject_transform(p, 2.0, 0.0)
        # decompose_benefit带类索引标签 → raise（反例6回归）
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError, match="0,1"):
            decompose_benefit(p, rng.integers(0, 5, len(p)),
                              2.0, 0.0, None, rng)


class TestRecovery:
    def test_pure_slope(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(0)
        p_inj = inject_transform(p, 2.0, 0.0)
        rec = recover_slope_intercept(p_inj, y,
                                      pi_reference=float(y.mean()),
                                      pi_resampled=float(y.mean()))
        assert abs(rec['s_hat'] - 2.0) < 0.05
        assert abs(rec['b_hat']) < 0.05

    def test_pure_intercept(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(0)
        p_inj = inject_transform(p, 1.0, 1.0)
        rec = recover_slope_intercept(p_inj, y,
                                      pi_reference=float(y.mean()),
                                      pi_resampled=float(y.mean()))
        assert abs(rec['s_hat'] - 1.0) < 0.05
        assert abs(rec['b_hat'] - 1.0) < 0.05

    def test_king_zeng_correction_with_resampling(self, baseline):
        """反例1回归：重采样后恢复+KZ校正应恢复真值"""
        p, y = baseline
        rng = np.random.default_rng(1)
        out = decompose_benefit(p, y, 0.7, 0.5, 0.6, rng=rng)
        rec = out['recovery']
        assert abs(rec['s_hat'] - 0.7) < 0.05
        assert abs(rec['b_hat'] - 0.5) < 0.10  # KZ校正后接近真值
        assert abs(rec['prev_hat'] - 0.6) < 0.01


class TestDecompose:
    def test_identity_delta_total_near_zero(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(2)
        out = decompose_benefit(p, y, 1.0, 0.0, None, rng=rng)
        assert abs(out['delta_total']) < 0.02

    def test_chain_residual_zero_by_construction(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(2)
        out = decompose_benefit(p, y, 1.5, 0.8, 0.6, rng=rng)
        c = out['chain']
        assert abs(c['residual']) < 1e-10  # 链式套叠恒等

    def test_factorial_interactions_nonzero(self, baseline):
        """反例4回归：析因交互项存在且非恒0"""
        p, y = baseline
        rng = np.random.default_rng(2)
        out = decompose_benefit(p, y, 1.5, 0.8, 0.6, rng=rng)
        inter = out['interactions']
        assert 'I_sb' in inter and 'I_3way' in inter
        assert any(abs(v) > 1e-6 for v in inter.values())

    def test_shapley_sums_to_total(self, baseline):
        """反例3回归：Shapley值之和=总效应"""
        p, y = baseline
        rng = np.random.default_rng(2)
        out = decompose_benefit(p, y, 1.5, 0.8, 0.6, rng=rng)
        v = out['shapley']['values']
        assert abs(sum(v.values()) - out['delta_total']) < 1e-9
        shares = out['shapley']['shares']
        assert abs(sum(shares.values()) - 1.0) < 1e-9

    def test_six_permutations_reported(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(2)
        out = decompose_benefit(p, y, 1.5, 0.8, 0.6, rng=rng)
        assert len(out['permutations']) == 6

    def test_return_structure_v2(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(2)
        out = decompose_benefit(p, y, 1.5, 0.8, None, rng=rng)
        for key in ['delta_total', 'chain', 'interactions', 'permutations',
                    'shapley', 'recovery', 'fisher_det', 'entangled',
                    'ece_subsets']:
            assert key in out, f"缺少{key}"


class TestFisherInformation:
    def test_baseline_weights_no_false_entanglement(self, baseline):
        """反例5回归：b=-13极端截距不应产生假阳性纠缠（基线权重独立于b）"""
        p, _ = baseline
        p_inj_deep = inject_transform(p, 1.0, -13.0)
        p_inj_mid = inject_transform(p, 1.0, 0.0)
        det_deep = fisher_information_det(p_inj_deep, p)
        det_mid = fisher_information_det(p_inj_mid, p)
        # 基线权重下，det只随s变化（∝1/s⁴），与b无关
        assert det_deep == pytest.approx(det_mid, rel=0.5)

    def test_nonnegative(self, baseline):
        p, _ = baseline
        p_inj = inject_transform(p, 2.0, 1.0)
        assert fisher_information_det(p_inj, p) >= 0.0

    def test_slope_scales_det(self, baseline):
        """x'设计缩放：det(s=2) ≈ 4×det(s=1)（2×2设计矩阵单维缩放k=s → det∝s²）"""
        p, _ = baseline
        d1 = fisher_information_det(inject_transform(p, 1.0, 0.0), p)
        d2 = fisher_information_det(inject_transform(p, 2.0, 0.0), p)
        assert d2 == pytest.approx(4 * d1, rel=0.3)


class TestGate:
    """反例2回归：门槛随样本量缩放"""

    def test_gate_at_reference(self):
        assert identifiability_gate(20000) == pytest.approx(0.10)

    def test_gate_looser_at_small_n(self):
        g500 = identifiability_gate(500)
        assert 0.15 < g500 < 0.30  # 实测p95=19.6%应可达成
        assert g500 > identifiability_gate(2000)

    def test_gate_floor(self):
        assert identifiability_gate(10**7) == 0.10  # 不低于预注册下限


class TestResamplePrevalence:
    def test_pairs_preserved(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(3)
        idx = resample_prevalence(p, y, 0.6, rng)
        assert len(idx) == len(p)
        y_res = y[idx]
        # 配对保持：正类样本的p均值显著高于负类（0.636 vs 0.366，强分离）
        assert p[idx][y_res == 1].mean() > p[idx][y_res == 0].mean() + 0.2

    def test_edge_prevalence_warns(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(3)
        with pytest.warns(UserWarning):
            resample_prevalence(p, y, 1.5, rng)  # 越界clip+warn

    def test_rejects_multiclass(self, baseline):
        p, _ = baseline
        rng = np.random.default_rng(3)
        with pytest.raises(ValueError):
            resample_prevalence(p, np.zeros(len(p), dtype=int), 0.5, rng)


class TestEndToEnd:
    def test_validate_script_exit_zero(self):
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "scripts" / "validate_decomposition.py")],
            capture_output=True, text=True, timeout=600,
        )
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]

    def test_validate_script_small_n(self):
        """n=500真实量级：门槛自适应后应通过（反例2回归）"""
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "scripts" / "validate_decomposition.py"),
             "--n", "500"],
            capture_output=True, text=True, timeout=600,
        )
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
