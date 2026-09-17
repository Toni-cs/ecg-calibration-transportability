"""分块 select 扫描（src/models/mamba_chunked.py）的数值等价性回归测试。

背景：``mambapy`` 的 Blelloch pscan 会物化 ``(B, L, ED, N)`` 张量，
B=16/L=5000 时峰值 19.7 GB，超出 8.55 GB 显卡 → 靠 WDDM 换页，18 s/步。
分块版把它降到 5.2 GB。本测试锁住"分块不改变数值"这一性质。

关键性质：
  * ``chunk == L``（单块）应与原版**逐位相同**（前向 logits 完全相等）；
  * ``chunk < L`` 只多出块间状态叠加的舍入，量级 ~1e-6。

另有一条反向测试：确认 cumsum 比值形式在块长较大时**确实会 NaN**，
以防有人"顺手优化"回那条已被否决的路径（见 mamba_chunked.py 模块 docstring）。
"""

import copy

import pytest
import torch

from src.models.ecg_classifier import ECGClassifier
from src.models.mamba_chunked import enable_chunked_scan, selective_scan_chunked


def _tiny_model(device):
    torch.manual_seed(0)
    return ECGClassifier(in_channels=12, d_model=16, n_layers=1,
                         num_classes=5, dropout=0.0,
                         backbone_type="mamba").to(device).eval()


def _grads(model, x, y):
    model.zero_grad(set_to_none=True)
    logits, _ = model(x)
    torch.nn.functional.cross_entropy(logits, y).backward()
    g = torch.cat([p.grad.flatten() for p in model.parameters()
                   if p.grad is not None])
    return logits.detach(), g


def test_single_chunk_is_bit_identical():
    """chunk == L 时，分块版应与原版逐位相同。"""
    dev = torch.device("cpu")
    base = _tiny_model(dev)
    x = torch.randn(2, 12, 128)
    y = torch.randint(0, 5, (2,))

    ref = copy.deepcopy(base)
    lo, _ = _grads(ref, x, y)

    m = copy.deepcopy(base)
    n = enable_chunked_scan(m, chunk=128, use_checkpoint=True)
    assert n > 0, "未替换到任何 MambaBlock"
    l, _ = _grads(m, x, y)

    assert torch.equal(l, lo), "单块分块应与原版逐位相同"


@pytest.mark.parametrize("chunk", [32, 64])
def test_multi_chunk_matches_reference(chunk):
    """chunk < L 时只允许 fp32 舍入级差异。"""
    dev = torch.device("cpu")
    base = _tiny_model(dev)
    x = torch.randn(2, 12, 128)
    y = torch.randint(0, 5, (2,))

    ref = copy.deepcopy(base)
    lo, go = _grads(ref, x, y)

    m = copy.deepcopy(base)
    enable_chunked_scan(m, chunk=chunk, use_checkpoint=True)
    l, g = _grads(m, x, y)

    assert (l - lo).abs().max().item() < 1e-5
    assert (g - go).abs().max().item() < 1e-5


def test_chunked_scan_accepts_odd_length():
    """L 不是块长整数倍时不能出错（最后一块更短）。"""
    dev = torch.device("cpu")
    B, L, ED, N = 2, 100, 16, 4
    x = torch.randn(B, L, ED)
    delta = torch.rand(B, L, ED) * 0.1
    Bm = torch.randn(B, L, N)
    Cm = torch.randn(B, L, N)
    A = -torch.ones(ED, N)
    D = torch.ones(ED)

    y = selective_scan_chunked(x, delta, A, Bm, Cm, D, chunk=32,
                               use_checkpoint=False)
    assert y.shape == (B, L, ED)
    assert torch.isfinite(y).all()


def test_cumsum_ratio_form_overflows_at_large_chunk():
    """反向测试：cumsum 比值形式在块长较大时必然 NaN。

    这是**预期行为**，用来防止有人把 mamba_chunked.py 换回那条路径。
    原因：该形式需要把 exp(±range) 塞进 fp32，而 range = 块内总衰减
    Σ|logΔA| 随块长线性增长，块长 64 时实测最大已 103.9 > ln(3.4e38)=88.7。
    """
    B, C, ED, N = 2, 64, 16, 4
    torch.manual_seed(0)
    x = torch.randn(B, C, ED)
    # 故意取大的 |logΔA|：Δ~0.13、A~-16 → 单步 -2.08
    delta = torch.full((B, C, ED), 0.13)
    Bm = torch.randn(B, C, N)
    Cm = torch.randn(B, C, N)
    A = -torch.full((ED, N), 16.0)
    D = torch.ones(ED)

    log_dA = delta.unsqueeze(-1) * A
    c = torch.cumsum(log_dA, dim=1)
    rng = (c.amax(dim=1) - c.amin(dim=1)).max().item()
    assert rng > 88.7, f"构造的极差 {rng:.1f} 未超过 fp32 上溢阈值，测试失去意义"

    neg_c = -c
    m = neg_c.amax(dim=1, keepdim=True)
    dB = delta.unsqueeze(-1) * Bm.unsqueeze(2)
    BX = dB * x.unsqueeze(-1)
    h_loc = torch.exp(c + m) * torch.cumsum(BX * torch.exp(neg_c - m), dim=1)
    assert not torch.isfinite(h_loc).all(), "预期出现 inf/NaN"
