"""新架构单元测试：Bidirectional Mamba + AttentionPooling + 校准"""

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.s4_backbone import ECGMambaBackbone, BiMambaBlock
from src.models.ecg_classifier import ECGClassifier, AttentionPooling
from src.models.baselines import ECGResNet1D, ECGInceptionTime, build_backbone
from src.utils.calibration import ece, mce, bootstrap_ece, compute_all_metrics, fit_temperature, apply_temperature
from src.utils.calibration import brier_parts, brier_raw

# R7-ATK-3 修复：brier_parts 与 ece/mce/bootstrap_ece 共用同一份非法 n_bins 列表，
# 避免两处测试覆盖不一致（R6 遗漏 None/True/2.0/10**18 四个 case）。
BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]


class TestBackbone:
    """BiMamba Backbone测试"""

    def test_forward_shape(self):
        model = ECGMambaBackbone(in_channels=12, d_model=64, n_layers=2)
        x = torch.randn(2, 12, 500)
        out = model(x)
        # 输出全时序特征，不内部池化
        assert out.shape == (2, 500, 64)

    def test_backward_no_nan(self):
        model = ECGMambaBackbone(in_channels=12, d_model=64, n_layers=1)
        x = torch.randn(2, 12, 200)
        out = model(x)
        out.sum().backward()
        for name, p in model.named_parameters():
            if p.grad is not None:
                assert not torch.isnan(p.grad).any(), f"NaN grad in {name}"

    def test_bimamba_block(self):
        block = BiMambaBlock(d_model=64)
        x = torch.randn(2, 100, 64)
        out = block(x)
        assert out.shape == x.shape

    def test_param_count_reasonable(self):
        model = ECGMambaBackbone(in_channels=12, d_model=64, n_layers=2)
        n = sum(p.numel() for p in model.parameters())
        assert 10_000 < n < 5_000_000


class TestAttentionPooling:
    def test_pooling_shape(self):
        pool = AttentionPooling(d_model=64)
        x = torch.randn(2, 100, 64)
        out = pool(x)
        assert out.shape == (2, 64)

    def test_weights_sum_to_one(self):
        pool = AttentionPooling(d_model=64)
        x = torch.randn(2, 50, 64)
        attn = torch.softmax(pool.attention(x), dim=1)
        assert torch.allclose(attn.sum(dim=1), torch.ones(2, 1), atol=1e-5)


class TestECGClassifier:
    def test_forward(self):
        clf = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5)
        x = torch.randn(2, 12, 500)
        logits, probs = clf(x)
        assert logits.shape == (2, 5)
        assert probs.shape == (2, 5)
        assert torch.allclose(probs.sum(dim=-1), torch.ones(2), atol=1e-5)

    def test_temperature(self):
        clf = ECGClassifier(learnable_temp=True)
        t0 = clf.temperature.item()
        clf.log_temperature.data.fill_(0.0)
        assert clf.temperature.item() == pytest.approx(1.0)
        clf.log_temperature.data.fill_(np.log(2.0))
        assert clf.temperature.item() == pytest.approx(2.0)

    def test_get_features(self):
        clf = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5)
        x = torch.randn(2, 12, 300)
        feats = clf.get_features(x)
        assert feats.shape == (2, 64)

    def test_training_step(self):
        clf = ECGClassifier(in_channels=12, d_model=64, n_layers=1, num_classes=5)
        opt = torch.optim.AdamW(clf.parameters(), lr=1e-3)
        x = torch.randn(4, 12, 300)
        y = torch.randint(0, 5, (4,))
        logits, _ = clf(x)
        loss = torch.nn.functional.cross_entropy(logits, y)
        opt.zero_grad()
        loss.backward()
        for name, p in clf.named_parameters():
            if p.grad is not None:
                assert not torch.isnan(p.grad).any(), f"NaN grad in {name}"
        opt.step()

    def test_mc_dropout(self):
        clf = ECGClassifier(in_channels=12, d_model=64, n_layers=1, num_classes=5)
        x = torch.randn(2, 12, 300)
        mean_p, unc, std = clf.predict_with_uncertainty(x, n_forward=3)
        assert mean_p.shape == (2, 5)
        assert unc.shape == (2,)
        assert std.shape == (2, 5)
        assert (unc >= 0).all()


class TestBaselineArchitectures:
    """协议§4三架构基线的 CNN 主干（ResNet1D/InceptionTime）"""

    def _model(self, name, dm=64, layers=2):
        return ECGClassifier(in_channels=12, d_model=dm, n_layers=layers,
                             num_classes=5, dropout=0.1, backbone_type=name)

    def test_forward_all_archs(self):
        x = torch.randn(2, 12, 300)
        for name in ("mamba", "resnet1d", "inceptiontime"):
            clf = self._model(name)
            logits, probs = clf(x)
            assert logits.shape == (2, 5), f"{name} logits"
            assert probs.shape == (2, 5), f"{name} probs"
            assert torch.isfinite(logits).all()
            assert torch.allclose(probs.sum(-1), torch.ones(2), atol=1e-5)

    def test_shared_head_constant(self):
        """三架构分类头必须恒等（AttentionPooling + 同构MLP），保证校准公平对比"""
        head1 = ECGClassifier(in_channels=12, d_model=64, num_classes=5,
                              backbone_type="resnet1d").classifier
        head2 = ECGClassifier(in_channels=12, d_model=64, num_classes=5,
                              backbone_type="inceptiontime").classifier
        for p1, p2 in zip(head1.parameters(), head2.parameters()):
            assert p1.shape == p2.shape, "共享头参数形状不一致"

    def test_backbone_output_resolution(self):
        """ResNet1D可降采样(seq_out<seq)；Mamba/Inception保留全分辨率；
        AttentionPooling对任意seq_out生效。"""
        x = torch.randn(2, 12, 500)
        dm = 32
        for name, expect_full in (("resnet1d", False), ("inceptiontime", True)):
            clf = ECGClassifier(in_channels=12, d_model=dm, num_classes=5,
                                backbone_type=name)
            feat = clf.backbone(x)
            assert feat.shape[-1] == dm
            assert feat.ndim == 3
            if expect_full:
                assert feat.shape[1] == 500, f"{name} 应保留时序"
            logits, _ = clf(x)
            assert logits.shape == (2, 5)

    def test_comparable_capacity(self):
        """同d_model下三架构参数量同量级（公平对比，防过度容量失衡）"""
        x = torch.randn(1, 12, 200)
        params = {}
        for name in ("mamba", "resnet1d", "inceptiontime"):
            params[name] = sum(p.numel() for p in
                               self._model(name, dm=64).parameters())
        mx, mn = max(params.values()), min(params.values())
        assert mx / mn < 10, f"架构容量失衡: {params}"

    def test_backward_no_nan(self):
        x = torch.randn(2, 12, 300)
        y = torch.randint(0, 5, (2,))
        for name in ("resnet1d", "inceptiontime"):
            clf = self._model(name)
            logits, _ = clf(x)
            loss = torch.nn.functional.cross_entropy(logits, y)
            loss.backward()
            for n, p in clf.named_parameters():
                if p.grad is not None:
                    assert not torch.isnan(p.grad).any(), f"NaN grad {name}.{n}"


class TestCalibration:
    def test_ece(self):
        probs = np.random.rand(100)
        labels = (probs > 0.5).astype(float)
        val = ece(probs, labels, n_bins=5)
        assert 0.0 <= val <= 1.0

    def test_bootstrap_ece(self):
        probs = np.random.rand(200)
        labels = (probs > 0.5).astype(float)
        mean, lo, hi = bootstrap_ece(probs, labels, n_bins=5, n_bootstrap=30)
        assert lo <= mean <= hi

    def test_brier_parts(self):
        metrics = compute_all_metrics(
            np.random.rand(100), (np.random.rand(100) > 0.5).astype(float), n_bins=5, n_bootstrap=20
        )
        assert 'ece' in metrics and 'brier' in metrics
        # Murphy分解精确恒等式（按构造成立）
        total = (metrics['brier_reliability'] - metrics['brier_resolution']
                 + metrics['brier_uncertainty'])
        assert total == pytest.approx(metrics['brier'], abs=1e-12)
        # raw Brier 与分解总量应接近（分箱残差小）
        assert abs(metrics['brier_raw'] - metrics['brier']) < 0.1

    # S3-r2 fix: 直接测试 brier_parts（此前仅通过 compute_all_metrics 间接测试）
    def test_brier_parts_direct_known_values(self):
        """直接测试 brier_parts 已知输入的输出值（Murphy 分解精确恒等式）"""
        # 完美校准：probs=labels → reliability=0, brier_total=0
        probs = np.array([0.0, 1.0])
        labels = np.array([0.0, 1.0])
        total, rel, res, unc = brier_parts(probs, labels, n_bins=10)
        assert rel == pytest.approx(0.0, abs=1e-12)
        assert total == pytest.approx(0.0, abs=1e-12)
        assert unc == pytest.approx(0.25, abs=1e-12)
        assert res == pytest.approx(0.25, abs=1e-12)

        # 最差校准：probs 与 labels 完全相反 → reliability=1.0
        probs = np.array([1.0, 0.0])
        labels = np.array([0.0, 1.0])
        total, rel, res, unc = brier_parts(probs, labels, n_bins=10)
        assert rel == pytest.approx(1.0, abs=1e-12)
        assert total == pytest.approx(1.0, abs=1e-12)

        # 全相同概率、标签各半 → reliability=0, resolution=0, brier=uncertainty
        probs = np.array([0.5, 0.5, 0.5, 0.5])
        labels = np.array([0.0, 0.0, 1.0, 1.0])
        total, rel, res, unc = brier_parts(probs, labels, n_bins=10)
        assert rel == pytest.approx(0.0, abs=1e-12)
        assert res == pytest.approx(0.0, abs=1e-12)
        assert total == pytest.approx(unc, abs=1e-12)
        assert unc == pytest.approx(0.25, abs=1e-12)

    def test_brier_parts_direct_n_bins_param(self):
        """直接测试 brier_parts 的 n_bins 参数传递与生效"""
        rng = np.random.default_rng(42)
        probs = rng.random(200)
        labels = (probs > 0.5).astype(float)
        # 不同 n_bins 产生不同 reliability（分箱粒度影响）
        _, rel5, _, _ = brier_parts(probs, labels, n_bins=5)
        _, rel10, _, _ = brier_parts(probs, labels, n_bins=10)
        _, rel20, _, _ = brier_parts(probs, labels, n_bins=20)
        # n_bins 越大，reliability 越精细（通常单调递增或至少不全等）
        assert not (rel5 == rel10 == rel20), "不同 n_bins 应产生不同 reliability"
        # numpy 整数类型应与 Python int 等价
        b_np = brier_parts(probs, labels, n_bins=np.int64(10))
        b_py = brier_parts(probs, labels, n_bins=10)
        assert b_np == b_py, "numpy int64 应与 Python int 等价"
        # n_bins=1：所有样本落入同一箱，reliability = |avg_prob - avg_label|^2
        probs_simple = np.array([0.3, 0.7])
        labels_simple = np.array([0.0, 1.0])
        total, rel, res, unc = brier_parts(probs_simple, labels_simple, n_bins=1)
        avg_p, avg_l = 0.5, 0.5
        assert rel == pytest.approx((avg_p - avg_l) ** 2, abs=1e-12)
        assert res == pytest.approx(0.0, abs=1e-12)

    def test_brier_parts_direct_edge_cases(self):
        """直接测试 brier_parts 边界情况（单元素、二元素、Murphy 恒等式）"""
        # 单元素：uncertainty = base_rate*(1-base_rate)
        probs = np.array([0.5])
        labels = np.array([1.0])
        total, rel, res, unc = brier_parts(probs, labels, n_bins=10)
        assert unc == pytest.approx(0.0, abs=1e-12)  # base_rate=1.0 → 1*0=0
        assert rel == pytest.approx(0.25, abs=1e-12)  # (0.5-1.0)^2
        assert res == pytest.approx(0.0, abs=1e-12)
        assert total == pytest.approx(0.25, abs=1e-12)

        # 单元素 label=0
        probs = np.array([0.5])
        labels = np.array([0.0])
        total, rel, res, unc = brier_parts(probs, labels, n_bins=10)
        assert unc == pytest.approx(0.0, abs=1e-12)
        assert rel == pytest.approx(0.25, abs=1e-12)

        # Murphy 恒等式对随机输入始终成立（按构造）
        rng = np.random.default_rng(123)
        for _ in range(10):
            n = rng.integers(1, 200)
            p = rng.random(n)
            y = rng.integers(0, 2, n).astype(float)
            total, rel, res, unc = brier_parts(p, y, n_bins=10)
            assert total == pytest.approx(rel - res + unc, abs=1e-10)

        # 返回值均为 Python float
        total, rel, res, unc = brier_parts(np.array([0.3]), np.array([0.0]), n_bins=5)
        assert all(isinstance(v, float) for v in (total, rel, res, unc))

    def test_brier_parts_direct_vs_raw(self):
        """直接测试 brier_parts 分解总量与 brier_raw 的关系"""
        rng = np.random.default_rng(456)
        probs = rng.random(500)
        labels = (probs > 0.5).astype(float)
        total, rel, res, unc = brier_parts(probs, labels, n_bins=20)
        raw = brier_raw(probs, labels)
        # 分箱越细，分解总量越接近 raw Brier（分箱内概率近似恒定）
        assert abs(total - raw) < 0.05, f"分解总量 {total} 与 raw {raw} 偏差过大"

    def test_brier_parts_n_bins_validation(self):
        """测试 brier_parts 的 n_bins 参数验证和生效"""
        from src.utils.calibration import brier_parts
        probs = np.random.rand(100)
        labels = (np.random.rand(100) > 0.5).astype(float)
        # 直接测试 n_bins 参数生效
        b5 = brier_parts(probs, labels, n_bins=5)
        b10 = brier_parts(probs, labels, n_bins=10)
        assert b5 != b10, "n_bins=5 和 n_bins=10 应产生不同结果"
        # 测试 numpy 整数类型
        b_np = brier_parts(probs, labels, n_bins=np.int64(10))
        assert b_np == b10, "numpy int64 应与 Python int 等价"
        # 测试 ValueError 守卫（R7-ATK-3：与 ece/mce/bootstrap_ece 共用 BAD_N_BINS）
        for bad_n_bins in BAD_N_BINS:
            with pytest.raises(ValueError):
                brier_parts(probs, labels, n_bins=bad_n_bins)
        # Test compute_all_metrics guard (R8-5: BAD_N_BINS 循环，移除 TypeError 死分支)
        for bad_n_bins in BAD_N_BINS:
            with pytest.raises(ValueError):
                compute_all_metrics(probs, labels, n_bins=bad_n_bins)

    def test_ece_mce_bootstrap_ece_n_bins_guards(self):
        """直接测试 ece/mce/bootstrap_ece 的 n_bins 验证守卫（A2 修复）"""
        from src.utils.calibration import ece, mce, bootstrap_ece
        probs = np.random.rand(100)
        labels = (np.random.rand(100) > 0.5).astype(float)
        # 非法 n_bins（0 / -1 / 1.5 / None / True / "10" / 2.0 / 10**18）应 raise ValueError
        # R7-ATK-3：与 brier_parts 测试共用 BAD_N_BINS 常量，避免覆盖不一致
        for bad_n_bins in BAD_N_BINS:
            with pytest.raises(ValueError):
                ece(probs, labels, n_bins=bad_n_bins)
            with pytest.raises(ValueError):
                mce(probs, labels, n_bins=bad_n_bins)
            with pytest.raises(ValueError):
                bootstrap_ece(probs, labels, n_bins=bad_n_bins)
        # 合法最小值 n_bins=1 不应 raise
        ece(probs, labels, n_bins=1)
        mce(probs, labels, n_bins=1)
        bootstrap_ece(probs, labels, n_bins=1, n_bootstrap=5)

    # N2-r2 fix: 验证 ece/mce 的 ValueError 行为有测试覆盖
    def test_ece_mce_value_error_propagation(self):
        """N2-r2: ece/mce 对非法 n_bins 抛 ValueError，调用方不应 try-except。

        ValueError 传播是正确行为——非法 n_bins 是编程错误，应暴露而非静默吞掉。
        此测试固化该行为契约，防止未来回归（如误加 try-except 吞异常）。
        """
        probs = np.array([0.3, 0.7, 0.5])
        labels = np.array([0.0, 1.0, 0.0])
        # ece/mce 对非法 n_bins 抛 ValueError（由 _validate_n_bins 守卫）
        for bad in (0, -1, 1.5, None, True, "10"):
            with pytest.raises(ValueError, match="n_bins must be"):
                ece(probs, labels, n_bins=bad)
            with pytest.raises(ValueError, match="n_bins must be"):
                mce(probs, labels, n_bins=bad)
        # 合法 n_bins 不抛异常（边界值 n_bins=1 和常规值 n_bins=100）
        ece(probs, labels, n_bins=1)
        mce(probs, labels, n_bins=1)
        ece(probs, labels, n_bins=100)
        mce(probs, labels, n_bins=100)

    def test_fit_temperature_multiclass(self):
        probs = np.random.rand(50, 5)
        probs /= probs.sum(axis=1, keepdims=True)
        labels = np.eye(5)[np.random.randint(0, 5, 50)]
        T = fit_temperature(probs, labels)
        assert T > 0

    def test_apply_temperature(self):
        probs = np.random.rand(10, 5)
        probs /= probs.sum(axis=1, keepdims=True)
        out = apply_temperature(probs, 2.0)
        assert out.shape == probs.shape
        assert np.allclose(out.sum(axis=1), 1.0, atol=1e-5)


class TestIntegration:
    def test_end_to_end(self):
        """模型输出 -> 温度拟合 -> 校准指标，全链路"""
        clf = ECGClassifier(in_channels=12, d_model=32, n_layers=1, num_classes=5)
        x = torch.randn(16, 12, 200)
        logits, probs = clf(x)
        labels = torch.randint(0, 5, (16,))

        T = fit_temperature(probs.detach().numpy(), torch.nn.functional.one_hot(labels, 5).numpy())
        calibrated = apply_temperature(
            torch.softmax(logits / T, dim=-1).detach().numpy(), 1.0
        )

        max_probs = calibrated.max(axis=1)
        correct = (calibrated.argmax(axis=1) == labels.numpy()).astype(float)
        metrics = compute_all_metrics(max_probs, correct, n_bins=5, n_bootstrap=20)
        assert 0.0 <= metrics['ece'] <= 1.0
