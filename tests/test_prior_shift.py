"""BBSE/EM P-independent 目标先验恢复估计器回归测试（协议§13 item 7）

覆盖：
- 干净 label shift 下 BBSE 高精度恢复真先验（无需目标标签）
- EM 合理恢复（方差更大，允许宽松阈值）
- 不可辨识守卫：近奇异 confusion → None + warn；小样本类 → None
- 输入校验：类数不一致/行数不一致/一维 → raise
- 单纯形输出：π̂ 非负、和=1
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.prior_shift import (
    fit_bbse, fit_em, _simplex_project, _cond_rank,
)


def _make_shifted(K=5, n_src=8000, n_tgt=20000, conf_mass=0.7, seed=0):
    """构造 label-shift：源均匀先验 → 目标倾斜先验；soft-probs类内集中。"""
    rng = np.random.default_rng(seed)
    src_labels = rng.integers(0, K, n_src)
    src_probs = rng.dirichlet(np.full(K, 1.0), n_src) * (1 - conf_mass)
    src_probs[np.arange(n_src), src_labels] += conf_mass
    src_probs = src_probs / src_probs.sum(axis=1, keepdims=True)

    pi_true = np.array([0.5, 0.1, 0.1, 0.15, 0.15])[:K]
    pi_true = pi_true / pi_true.sum()
    tgt_labels = rng.choice(K, n_tgt, p=pi_true)
    tgt_probs = rng.dirichlet(np.full(K, 1.0), n_tgt) * (1 - conf_mass)
    tgt_probs[np.arange(n_tgt), tgt_labels] += conf_mass
    tgt_probs = tgt_probs / tgt_probs.sum(axis=1, keepdims=True)
    return src_probs, src_labels, tgt_probs, tgt_labels, pi_true


class TestSimplexProject:
    def test_normalizes_to_one(self):
        p = _simplex_project(np.array([2.0, 1.0, -1.0]))
        assert p.sum() == pytest.approx(1.0)
        assert (p >= 0).all()

    def test_all_zero_returns_nan(self):
        assert np.isnan(_simplex_project(np.zeros(3))).all()


class TestBBSE:
    def test_recovers_shifted_prior(self):
        src_p, src_y, tgt_p, _, pi_true = _make_shifted()
        res = fit_bbse(src_p, src_y, tgt_p)
        assert res is not None
        assert res["method"] == "bbse"
        err = np.abs(res["pi_hat"] - pi_true).mean()
        assert err < 0.02, f"BBSE恢复误差过高: {err:.4f}"

    def test_pihat_is_probability(self):
        src_p, src_y, tgt_p, _, _ = _make_shifted()
        res = fit_bbse(src_p, src_y, tgt_p)
        assert res["pi_hat"].sum() == pytest.approx(1.0)
        assert (res["pi_hat"] >= 0).all()

    def test_singular_confusion_returns_none(self):
        """秩亏confusion（两列相同→列相关）→ 不可辨识 → None"""
        rng = np.random.default_rng(1)
        n = 500
        # 让类1和类2的soft-confusion列完全相同（模型无法区分这两类）
        src_y = rng.integers(0, 3, n)
        src_p = rng.dirichlet(np.full(3, 1.0), n) * 0.4
        col = rng.dirichlet(np.ones(3), 1)[0]
        src_p[src_y == 0] = col          # 类0 → 列
        src_p[src_y == 1] = col          # 类1 → 同一列（秩亏）
        src_p[src_y == 2] = rng.dirichlet(np.ones(3), 1)[0]
        src_p = src_p / src_p.sum(axis=1, keepdims=True)
        tgt_p = rng.dirichlet(np.full(3, 1.0), 500)
        with pytest.warns(UserWarning, match="不可辨识"):
            res = fit_bbse(src_p, src_y, tgt_p)
        assert res is None

    def test_small_class_returns_none(self):
        """某类源样本过少 → confusion列不可靠 → None"""
        src_y = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2])  # 类2仅1个
        rng = np.random.default_rng(2)
        src_p = rng.dirichlet(np.full(3, 1.0), len(src_y))
        tgt_p = rng.dirichlet(np.full(3, 1.0), 100)
        with pytest.warns(UserWarning, match="min_samples"):
            res = fit_bbse(src_p, src_y, tgt_p, min_samples=10)
        assert res is None


class TestEM:
    def test_recovers_shifted_prior_loose(self):
        src_p, src_y, tgt_p, _, pi_true = _make_shifted()
        res = fit_em(src_p, src_y, tgt_p)
        assert res is not None
        err = np.abs(res["pi_hat"] - pi_true).mean()
        assert err < 0.08, f"EM恢复误差过高: {err:.4f}"

    def test_zero_discrimination_returns_none(self):
        """目标概率行方差≈0 → 不可辨识 → None"""
        rng = np.random.default_rng(3)
        src_y = rng.integers(0, 3, 300)
        src_p = rng.dirichlet(np.full(3, 1.0), 300)
        # 目标全为退化预测：每行都是同一个非信息分布（行方差=0）
        tgt_p = np.full((300, 3), 1 / 3)
        with pytest.warns(UserWarning, match="不可辨识"):
            res = fit_em(src_p, src_y, tgt_p)
        assert res is None


class TestValidation:
    def test_class_mismatch_raises(self):
        rng = np.random.default_rng(4)
        src_p = rng.dirichlet(np.full(4, 1.0), 100)
        src_y = rng.integers(0, 4, 100)
        tgt_p = rng.dirichlet(np.full(3, 1.0), 100)  # 3≠4类
        with pytest.raises(ValueError, match="类数不一致"):
            fit_bbse(src_p, src_y, tgt_p)

    def test_row_mismatch_raises(self):
        rng = np.random.default_rng(5)
        src_p = rng.dirichlet(np.full(3, 1.0), 100)
        src_y = rng.integers(0, 3, 50)  # 50≠100
        tgt_p = rng.dirichlet(np.full(3, 1.0), 100)
        with pytest.raises(ValueError, match="行数不一致"):
            fit_em(src_p, src_y, tgt_p)

    def test_1d_probs_raises(self):
        with pytest.raises(ValueError, match="2D"):
            fit_bbse(np.array([0.5, 0.5]), np.array([0]), np.array([[0.5, 0.5]]))
