"""Bidirectional Mamba Backbone for ECG Signal Processing (2026 SOTA)

架构（全量重写，无遗留旧代码）：
- mambapy Mamba 块（纯PyTorch平行扫描 Blelloch prefix-sum，O(L log L)，Windows可用）
- 双向扫描：前向 Mamba + 翻转后向 Mamba → 融合（ECG-Mamba2 / S2M2ECG 模式）
- 点卷积 Stem（不降采样，保留全时序分辨率）
- 残差连接 + LayerNorm

输出 (batch, seq_len, d_model)——不内部池化，由分类器的 AttentionPooling 负责。

参考：
- Mamba: Linear-Time Sequence Modeling with Selective State Spaces (Gu & Dao, 2023)
- ECG-Mamba2: Bidirectional State Space Model (2024-2026)
- S2M2ECG: Spatio-temporal bi-directional SSM (2025)
"""

import math
from typing import Optional

import torch
import torch.nn as nn

from mambapy.mamba import Mamba, MambaConfig


class BiMambaBlock(nn.Module):
    """双向Mamba块（flip-and-fuse 模式）

    forward:  mamba_f(x)
    backward: mamba_b(x.flip([1])).flip([1])
    fusion:   concat -> Linear(2d -> d) + 残差
    """

    def __init__(self, d_model: int, d_state: int = 16, d_conv: int = 4, expand: int = 2):
        super().__init__()
        self.norm = nn.LayerNorm(d_model)
        self.mamba_f = Mamba(MambaConfig(
            d_model=d_model, n_layers=1,
            d_state=d_state, d_conv=d_conv, expand_factor=expand,
        ))
        self.mamba_b = Mamba(MambaConfig(
            d_model=d_model, n_layers=1,
            d_state=d_state, d_conv=d_conv, expand_factor=expand,
        ))
        self.fusion = nn.Linear(d_model * 2, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, d_model) -> (batch, seq_len, d_model)"""
        residual = x
        h = self.norm(x)
        f_out = self.mamba_f(h)
        b_out = self.mamba_b(h.flip([1])).flip([1])
        fused = self.fusion(torch.cat([f_out, b_out], dim=-1))
        return fused + residual


class ECGMambaBackbone(nn.Module):
    """ECG 双向Mamba主干网络（2026 SOTA）

    流程：
    1. Pointwise Stem: Conv1d(k=1) + BN + GELU —— 12导联 -> d_model，不降采样
    2. n_layers 个 BiMambaBlock（双向扫描 + 残差融合）
    3. 输出全时序特征 (batch, seq_len, d_model)，池化交给下游 AttentionPooling
    """

    def __init__(
        self,
        in_channels: int = 12,
        d_model: int = 64,
        n_layers: int = 4,
        d_state: int = 16,
        d_conv: int = 4,
        expand: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.d_model = d_model

        self.stem = nn.Sequential(
            nn.Conv1d(in_channels, d_model, kernel_size=1, bias=False),
            nn.BatchNorm1d(d_model),
            nn.GELU(),
        )

        self.layers = nn.ModuleList([
            BiMambaBlock(d_model, d_state, d_conv, expand)
            for _ in range(n_layers)
        ])

        self.norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, n_leads, seq_len) 12导联ECG
        Returns:
            features: (batch, seq_len, d_model) 全时序特征（未池化）
        """
        x = self.stem(x)            # (batch, d_model, seq_len)
        x = x.transpose(1, 2)       # (batch, seq_len, d_model)
        for layer in self.layers:
            x = layer(x)
        x = self.norm(x)
        return self.dropout(x)


# 兼容旧命名
S4Backbone = ECGMambaBackbone


def create_ecg_mamba(
    in_channels: int = 12,
    d_model: int = 64,
    n_layers: int = 4,
    **kwargs,
) -> ECGMambaBackbone:
    """工厂函数"""
    return ECGMambaBackbone(
        in_channels=in_channels,
        d_model=d_model,
        n_layers=n_layers,
        **kwargs,
    )
