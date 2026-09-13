"""InceptionTime-Lite 主干：3 blocks 轻量 InceptionTime（E5 实验，协议§4 第3架构家族）

设计目标（E5 预注册）：
- 参数量 ~200K-500K（与 ResNet1D ~200K、BiMamba ~400K 同量级，公平对比）
- 3 个 Inception module（原始 InceptionTime 6 个，简化为 3 个）
- 保留 InceptionTime 三个关键归纳偏置：
  (a) 多尺度并行卷积（kernel 5/11/23 同时捕获短/中/长时程特征）
  (b) bottleneck 1x1 降维（降低卷积成本，Inception 系列标志）
  (c) maxpool 旁路（保留高频信息，与卷积分支互补）
- 时间维不降采样（seq_out == seq_len），与 BiMamba 全分辨率特性对齐

架构家族独立性论证（正方立场）：
  架构家族的区分在于归纳偏置，而非深度：
  - ResNet1D：串行残差 + 逐级降采样（VGG/ResNet 范式）
  - BiMamba：选择性状态空间 + 双向扫描（SSM 范式）
  - InceptionTime-Lite：多尺度并行卷积 + bottleneck + maxpool 旁路（Inception 范式）
  三者在特征提取机制上正交，3 blocks vs 6 blocks 是深度选择，不改变家族归属。

参数量推导（n_filters=48, bottleneck=48, 3 blocks, d_model=64, in_ch=12）：
  Block 1: bottleneck(12*48=576) + 3 convs(48*48*(5+11+23)=89856) + pool(48*48=2304) + BN(384) ≈ 93K
  Block 2: bottleneck(192*48=9216) + 3 convs(89856) + pool(2304) + BN(384) ≈ 102K
  Block 3: 同 Block 2 ≈ 102K
  proj(192*64=12288) + LayerNorm(128) ≈ 12K
  Backbone 总计 ≈ 310K（在 200K-500K 目标内）
  加 ECGClassifier head（AttentionPooling + MLP）≈ 10K → 全模型 ~320K

OOM 备选（RTX 5060 8GB 约束，4 级降级链）：
  Level 1: n_filters 64→48→32（本文件默认 48；若 OOM 改 32，参数量降至 ~136K）
  Level 2: gradient_checkpointing（包装 forward，用时间换显存）
  Level 3: ResNet1D 不同超参变体（depth 3/5/7, width 32/64/128）——退化为 ResNet1D 子家族
  Level 4: 诚实报告"2 架构家族 + BiMamba toy"（最坏情况，论文降级声明）

参考文献：
- Ismail Fawaz et al., "InceptionTime: Finding AlexNet for Time Series Classification",
  Data Mining and Knowledge Discovery, 2020.
- Wang et al., "Time Series Classification from Scratch with Deep Neural Networks",
  arXiv:1903.05994, 2019（InceptionTime 前身 Inception 块设计）。
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint


# ===========================================================================
# InceptionTime-Lite 块（多尺度并行卷积 + bottleneck + maxpool 旁路）
# ===========================================================================
class InceptionBlockLite(nn.Module):
    """InceptionTime-Lite 的 inception 模块（3 分支 + pool 旁路，轻量版）

    与 baselines._InceptionBlock1D 的区别：
    - 显式支持 gradient checkpointing（OOM 备选 Level 2）
    - 默认 kernel_sizes=(5, 11, 23)（与原始 InceptionTime 一致）
    - 文档明确标注参数量贡献，便于 E5 参数量审计
    """

    def __init__(
        self,
        in_ch: int,
        n_filters: int = 48,
        kernel_sizes: tuple = (5, 11, 23),
        bottleneck: int | None = 48,
        use_bn: bool = True,
        use_checkpoint: bool = False,
    ):
        super().__init__()
        self.use_checkpoint = use_checkpoint
        k0, k1, k2 = kernel_sizes
        self.bottleneck = (
            nn.Conv1d(in_ch, bottleneck, kernel_size=1, bias=False)
            if bottleneck
            else None
        )
        self.use_bn = use_bn
        in_branch = bottleneck if bottleneck else in_ch
        self.convs = nn.ModuleList([
            nn.Conv1d(in_branch, n_filters, kernel_size=k, padding=k // 2, bias=False)
            for k in (k0, k1, k2)
        ])
        self.pool = nn.Conv1d(in_branch, n_filters, kernel_size=1, bias=False)
        self.maxpool = nn.MaxPool1d(3, stride=1, padding=1)
        out_ch = n_filters * 4
        if use_bn:
            self.bn = nn.BatchNorm1d(out_ch)
        self.activation = nn.ReLU(inplace=True)

    def _forward_impl(self, x: torch.Tensor) -> torch.Tensor:
        z = x
        if self.bottleneck is not None:
            z = self.bottleneck(x)
        branches = [conv(z) for conv in self.convs]
        branches.append(self.pool(self.maxpool(z)))
        out = torch.cat(branches, dim=1)
        if self.use_bn:
            out = self.bn(out)
        return self.activation(out)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.use_checkpoint and self.training:
            # gradient checkpointing：前向不存激活，反向重算（省显存换时间）
            return checkpoint(self._forward_impl, x, use_reentrant=False)
        return self._forward_impl(x)


# ===========================================================================
# InceptionTime-Lite 主干
# ===========================================================================
class ECGInceptionTimeLite(nn.Module):
    """InceptionTime-Lite 主干（12 导联 ECG → 时序特征 (batch, seq_len, d_model)）

    E5 实验专用：3 blocks 轻量 InceptionTime，参数量目标 ~200K-500K。

    与 baselines.ECGInceptionTime 的区别：
    - 默认 n_blocks=3（vs 原始 4，vs InceptionTime 原文 6）
    - 默认 n_filters=48, bottleneck=48（参数量 ~310K，在目标区间）
    - 显式 use_checkpoint 支持 OOM 备选 Level 2
    - 提供 count_parameters() 便于 E5 参数量审计
    """

    def __init__(
        self,
        in_channels: int = 12,
        d_model: int = 64,
        n_blocks: int = 3,
        n_filters: int = 48,
        bottleneck: int | None = 48,
        kernel_sizes: tuple = (5, 11, 23),
        dropout: float = 0.0,
        use_checkpoint: bool = False,
    ):
        super().__init__()
        assert n_blocks == 3, (
            f"InceptionTime-Lite 固定 n_blocks=3（E5 预注册）；got {n_blocks}. "
            "若需其他深度请用 baselines.ECGInceptionTime。"
        )
        self.in_channels = in_channels
        self.d_model = d_model
        self.n_blocks = n_blocks
        self.n_filters = n_filters
        cur_ch = in_channels
        self.blocks = nn.ModuleList()
        for _ in range(n_blocks):
            self.blocks.append(
                InceptionBlockLite(
                    cur_ch,
                    n_filters=n_filters,
                    kernel_sizes=kernel_sizes,
                    bottleneck=bottleneck,
                    use_checkpoint=use_checkpoint,
                )
            )
            cur_ch = n_filters * 4
        self.proj = nn.Conv1d(cur_ch, d_model, kernel_size=1, bias=True)
        self.norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, n_leads, seq_len) -> (batch, seq_len, d_model)"""
        for block in self.blocks:
            x = block(x)
        x = self.proj(x)          # (batch, d_model, seq_len)
        x = x.transpose(1, 2)     # (batch, seq_len, d_model)
        return self.dropout(self.norm(x))

    def count_parameters(self) -> dict:
        """参数量审计（E5 预注册要求：报告 backbone 各 block 参数量）"""
        audit = {"total": 0, "blocks": []}
        for i, block in enumerate(self.blocks):
            n = sum(p.numel() for p in block.parameters())
            audit["blocks"].append({"block": i, "params": n})
            audit["total"] += n
        proj_n = sum(p.numel() for p in self.proj.parameters())
        norm_n = sum(p.numel() for p in self.norm.parameters())
        audit["proj"] = proj_n
        audit["norm"] = norm_n
        audit["total"] += proj_n + norm_n
        return audit


# ===========================================================================
# 构建函数（供 E5 脚本按名取用，与 baselines.build_backbone 接口一致）
# ===========================================================================
def build_inceptiontime_lite(
    in_channels: int = 12,
    d_model: int = 64,
    n_filters: int = 48,
    bottleneck: int = 48,
    dropout: float = 0.0,
    use_checkpoint: bool = False,
) -> ECGInceptionTimeLite:
    """构建 InceptionTime-Lite 主干（E5 专用）

    默认参数量 ~310K（n_filters=48, bottleneck=48, 3 blocks, d_model=64）。
    OOM 备选：n_filters=32, bottleneck=32 → ~136K（Level 1 降级）。
    """
    return ECGInceptionTimeLite(
        in_channels=in_channels,
        d_model=d_model,
        n_blocks=3,
        n_filters=n_filters,
        bottleneck=bottleneck,
        dropout=dropout,
        use_checkpoint=use_checkpoint,
    )


__all__ = [
    "InceptionBlockLite",
    "ECGInceptionTimeLite",
    "build_inceptiontime_lite",
]
