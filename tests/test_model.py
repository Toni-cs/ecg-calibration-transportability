"""新架构单元测试：Bidirectional Mamba + AttentionPooling + 校准"""

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.s4_backbone import ECGMambaBackbone, BiMambaBlock
from src.models.ecg_classifier import ECGClassifier, AttentionPooling
from src.utils.calibration import ece, bootstrap_ece, compute_all_metrics, fit_temperature, apply_temperature


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
