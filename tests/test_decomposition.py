"""三成分分解 v3 单元测试（含攻击者反例回归测试 + R轮修复回归）"""

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
    bootstrap_decomposition,
    entangle_demo_cases,
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


@pytest.fixture(scope="module")
def baseline_small():
    rng = np.random.default_rng(42)
    n = 2000
    p = rng.uniform(0.05, 0.95, n)
    y = rng.binomial(1, p).astype(float)
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
        # R4：prev_hat是重采样设计常量回读——精确等于目标先验（设计校验语义）
        assert rec['prev_hat'] == pytest.approx(0.6, abs=1e-9)

    def test_recovery_failure_captured(self):
        """R8回归：恢复退化不raise穿透，标记recovery_failed+entangled"""
        n = 1000
        rng = np.random.default_rng(5)
        p = np.full(n, 0.5)  # 常数概率：x'无方差，恢复退化
        y = rng.binomial(1, p).astype(float)
        out = decompose_benefit(p, y, 1.0, -30.0, None, rng=rng)
        assert out['recovery_failed'] is True
        assert out['entangled'] is True
        assert np.isnan(out['recovery']['s_hat'])


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
        """反例3回归：Shapley值之和=总效应（效率公理）"""
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

    def test_return_structure_v3(self, baseline):
        p, y = baseline
        rng = np.random.default_rng(2)
        out = decompose_benefit(p, y, 1.5, 0.8, None, rng=rng)
        for key in ['delta_total', 'chain', 'interactions', 'permutations',
                    'shapley', 'recovery', 'recovery_failed', 'fisher_det',
                    'entangled', 'ece_subsets']:
            assert key in out, f"缺少{key}"
        for key in ['shares_reliable', 'share_floor']:
            assert key in out['shapley'], f"shapley缺少{key}"

    def test_shapley_share_reliability_flag(self, baseline_small):
        """R5回归：|Δ_total|<3/√n时shares标记不可解读"""
        p, y = baseline_small
        rng = np.random.default_rng(2)
        floor = 3.0 / np.sqrt(len(p))
        # 单位注入：Δ_total≈0 → 不可解读
        out0 = decompose_benefit(p, y, 1.0, 0.0, None, rng=rng)
        if abs(out0['delta_total']) < floor:
            assert out0['shapley']['shares_reliable'] is False
        # 强注入：Δ_total大 → 可解读
        out1 = decompose_benefit(p, y, 2.0, 1.0, 0.6, rng=rng)
        assert abs(out1['delta_total']) > floor
        assert out1['shapley']['shares_reliable'] is True


class TestFisherInformation:
    def test_baseline_weights_no_false_entanglement(self, baseline):
        """反例5回归：b=-13极端截距不应产生假阳性纠缠（基线权重独立于b）"""
        p, _ = baseline
        p_inj_deep = inject_transform(p, 1.0, -13.0)
        p_inj_mid = inject_transform(p, 1.0, 0.0)
        det_deep = fisher_information_det(p_inj_deep, p)
        det_mid = fisher_information_det(p_inj_mid, p)
        # 基线权重下，det只随s变化（∝s²），与b无关
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

    def test_entangled_branch_reachable(self):
        """R8回归：τ=1e-6纠缠分支可达（腿3演示格）——窄带基线"""
        n = 2000
        rng = np.random.default_rng(7)
        p = np.clip(0.5 + 0.0005 * rng.standard_normal(n), 1e-3, 1 - 1e-3)
        y = (rng.uniform(0, 1, n) < p).astype(float)
        det = fisher_information_det(inject_transform(p, 1.0, 0.0), p)
        assert det < IDENTIFIABILITY_TAU


class TestBootstrapCI:
    """R1回归：腿3合成兑现——归因量bootstrap CI"""

    def test_ci_covers_point_and_ordered(self, baseline_small):
        p, y = baseline_small
        rng = np.random.default_rng(11)
        point = decompose_benefit(p, y, 2.0, 1.0, 0.6, rng=rng)
        ci = bootstrap_decomposition(p, y, 2.0, 1.0, 0.6,
                                     n_bootstrap=100,
                                     rng=np.random.default_rng(12))
        sv = point['shapley']['values']
        for comp, key in [('s', 'shap_s'), ('b', 'shap_b'), ('pi', 'shap_pi')]:
            lo, hi = ci[f'{key}_ci']
            assert lo < hi
            assert lo - 1e-3 <= sv[comp] <= hi + 1e-3, \
                f"{comp}: 点估计{sv[comp]}未落入CI[{lo},{hi}]（B=100粗粒度容差内）"
        lo, hi = ci['delta_total_ci']
        assert lo - 1e-3 <= point['delta_total'] <= hi + 1e-3

    def test_ci_nonnegative_reliability(self, baseline_small):
        """CI重叠纪律的载体存在：shapley绝对值CI可比较（协议§8-3）"""
        p, y = baseline_small
        ci = bootstrap_decomposition(p, y, 2.0, 1.0, 0.6,
                                     n_bootstrap=50,
                                     rng=np.random.default_rng(13))
        for key in ['shap_s', 'shap_b', 'shap_pi', 'I_sb']:
            lo, hi = ci[f'{key}_ci']
            assert np.isfinite(lo) and np.isfinite(hi)


class TestEntangleDemo:
    """R1回归：腿3纠缠演示三案例——纠缠分支可达且不穿透异常"""

    def test_demo_cases_entangled(self):
        for name, (p, y, s, b, tp) in entangle_demo_cases().items():
            rng = np.random.default_rng([7, 1])
            out = decompose_benefit(p, y, s, b, tp, rng=rng)
            assert out['entangled'], f"{name}: 应entangled（det={out['fisher_det']:.3e}）"
            assert out['fisher_det'] < IDENTIFIABILITY_TAU, name

    def test_deep_intercept_recovery_failed_no_raise(self):
        cases = entangle_demo_cases()
        p, y, s, b, tp = cases['deep_intercept']
        rng = np.random.default_rng([7, 2])
        out = decompose_benefit(p, y, s, b, tp, rng=rng)
        assert out['recovery_failed'] is True
        assert np.isnan(out['recovery']['s_hat'])


class TestGate:
    """反例2回归：门槛随样本量缩放（诚实语义：启发式而非3σ）"""

    def test_gate_at_reference(self):
        assert identifiability_gate(20000) == pytest.approx(0.10)

    def test_gate_looser_at_small_n(self):
        g500 = identifiability_gate(500)
        assert 0.15 < g500 < 0.30
        assert g500 > identifiability_gate(2000)
        # R2诚实语义：gate(500)=23.3%位于n500实测mape_s分布~p74（违率~22%），
        # 不是3σ容差——小样本FAIL是预期行为，由信息模式exit 2报告

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
    """R3回归：测试输出写入tmp_path，不再覆盖results/交付物"""

    def test_validate_script_prereg_mode(self, tmp_path):
        results_dir = Path(__file__).parent.parent / "results"
        before = ({f.name: (f.stat().st_mtime_ns, f.stat().st_size)
                   for f in results_dir.glob("*") if f.is_file()}
                  if results_dir.exists() else {})
        r = subprocess.run(
            [sys.executable,
             str(Path(__file__).parent.parent / "scripts" / "validate_decomposition.py"),
             "--boot", "0", "--output", str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600,
        )
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        assert (tmp_path / "decomposition_validation_n20000.csv").exists()
        assert (tmp_path / "decomposition_error_map_n20000.png").exists()
        # 纠缠演示（腿3）默认执行：demo失败会exit 5，退出码0即蕴含通过
        assert "det=" in r.stdout
        # R3回归：results/交付物不被测试触碰
        after = ({f.name: (f.stat().st_mtime_ns, f.stat().st_size)
                  for f in results_dir.glob("*") if f.is_file()}
                 if results_dir.exists() else {})
        assert before == after, "测试不得修改results/交付物"

    def test_validate_script_info_mode_exit_code(self, tmp_path):
        """R6回归：n=500信息模式FAIL→exit 2（不再恒0绿灯）"""
        r = subprocess.run(
            [sys.executable,
             str(Path(__file__).parent.parent / "scripts" / "validate_decomposition.py"),
             "--n", "500", "--boot", "0", "--output", str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600,
        )
        assert r.returncode == 2, (
            f"n=500实测违率~22%应触发exit 2，得到{r.returncode}\n"
            + r.stdout[-2000:] + r.stderr[-2000:]
        )
        assert "EXIT_INFO_MODE_FAIL" in r.stdout
        assert (tmp_path / "decomposition_validation_n500.csv").exists()
