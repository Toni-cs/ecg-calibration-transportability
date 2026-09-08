"""§4 三架构基线的两个 CNN 主干：1D-ResNet 与 InceptionTime（协议§13-1）

设计约束（与 BiMamba 主干可公平对比）：
- 输入 (batch, n_leads=12, seq_len) → 输出 **(batch, seq_len_out, d_model)**
- 与 ECGMambaBackbone 同契约：只做特征提取，不做最终分类；池化与分类头
  由 ECGClassifier（AttentionPooling + LayerNorm/GELU/Linear）统一承担。
- AttentionPooling 对任意 seq_len_out 生效（softmax over 时间维），故各主干
  可自由降采样而不破坏下游接口——校准对比只在特征提取器不同，分类头恒等。

架构（均为公开、可复现的标准实现，逐层注明）：
1. ResNet1D：VGG/ResNet 一维化（He et al. 2016；ECG 分类社区通用 ResNet-1D）。
   conv stem → 4 stage 残差（每 stage 首块 stride=2 降采样、通道加倍）→
   全局/时序特征 → 1x1 投影到 d_model → (batch, seq_len_out, d_model)。
2. InceptionTime：Ismail Fawaz et al. 2020 的 inception 模块（bottleneck 1x1 +
   多尺度卷积 5/11/23 + 池化旁路），时间维不降采样，最终 1x1 投影到 d_model。
   注：原始 InceptionTime 是全局平均池化分类；为统一接口，此处保留时序特征
   并交由 AttentionPooling——仅在特征提取方式上与 BiMamba 公平对齐。

BN 纪律：训练时 BN 更新 running stats；主协议温度在 cal 拟合、指标只在
test 报告（与 ECGClassifier.predict_with_uncertainty 的 BN 冻结逻辑兼容）。
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


# ===========================================================================
# 1D-ResNet
# ===========================================================================
class _ResBlock1D(nn.Module):
    """标准瓶颈/基本残差块（一维）

    基本块（base_width 风格）：
      bn+relu → conv3x3 → bn+relu → conv3x3 → +shortcut(投影可选)
    支持 stride>1 降采样与通道扩展（first block of each stage）。
    """

    def __init__(self, in_ch, out_ch, stride=1, downsample=None):
        super().__init__()
        self.conv1 = nn.Conv1d(in_ch, out_ch, kernel_size=3, stride=stride,
                               padding=1, bias=False)
        self.bn1 = nn.BatchNorm1d(out_ch)
        self.conv2 = nn.Conv1d(out_ch, out_ch, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm1d(out_ch)
        self.downsample = downsample
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        identity = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        if self.downsample is not None:
            identity = self.downsample(identity)
        out += identity
        return self.relu(out)


class ECGResNet1D(nn.Module):
    """1D ResNet 主干（12导联ECG → 时序特征 (batch, seq_out, d_model)）

    层配置（每 stage 的 block 数，默认 ResNet-34 风格 [3,4,6,3]）：
      conv stem(7x7/stride2 + maxpool) → 4 stages 通道 [64,128,256,512]
    → 1x1 投影到 d_model（可选对末 stage 输出做 adaptive 池化归一化长度）。

    stages 逐级 stride=2 会把 seq_len 折半 4 次（~5000→313），此降采样
    属 ResNet 设计，符合"架构不同即校准迁移异质性来源之一"的§4命题。
    """

    def __init__(
        self,
        in_channels: int = 12,
        d_model: int = 64,
        block_layers: tuple = (2, 2, 2, 2),  # ECG小型ResNet-1D（避免过度容量，公平对比）
        base_width: int | None = None,        # None → 随 d_model 缩放
        dropout: float = 0.0,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.d_model = d_model
        # base_width 随 d_model 缩放，使主干容量与 BiMamba/InceptionTime 同量级
        # （最终stage通道 = base_width*2^(len-1)；取 base_width≈d_model/4 使
        #   最深层≈d_model，避免4-stage默认64导致7M参数的不公平对比）
        if base_width is None:
            base_width = max(8, int(d_model // 4))
        self.base_width = base_width
        self.in_planes = base_width

        self.stem = nn.Sequential(
            nn.Conv1d(in_channels, base_width, kernel_size=7, stride=2,
                      padding=3, bias=False),
            nn.BatchNorm1d(base_width),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(kernel_size=3, stride=2, padding=1),
        )

        self.stages = nn.ModuleList()
        for i, n_blocks in enumerate(block_layers):
            out_ch = base_width * (2 ** i)
            self.stages.append(self._make_stage(out_ch, n_blocks,
                                                stride=1 if i == 0 else 2))

        self.proj = nn.Conv1d(base_width * (2 ** (len(block_layers) - 1)),
                              d_model, kernel_size=1, bias=True)
        self.norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def _make_stage(self, out_ch, n_blocks, stride):
        downsample = None
        if stride != 1 or self.in_planes != out_ch:
            downsample = nn.Sequential(
                nn.Conv1d(self.in_planes, out_ch, kernel_size=1, stride=stride,
                          bias=False),
                nn.BatchNorm1d(out_ch),
            )
        blocks = [_ResBlock1D(self.in_planes, out_ch, stride, downsample)]
        self.in_planes = out_ch
        blocks += [_ResBlock1D(out_ch, out_ch) for _ in range(n_blocks - 1)]
        return nn.Sequential(*blocks)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, n_leads, seq_len) -> (batch, seq_out, d_model)"""
        x = self.stem(x)
        for stage in self.stages:
            x = stage(x)
        x = self.proj(x)          # (batch, d_model, seq_out)
        x = x.transpose(1, 2)     # (batch, seq_out, d_model)
        return self.dropout(self.norm(x))


# ===========================================================================
# InceptionTime
# ===========================================================================
class _InceptionBlock1D(nn.Module):
    """InceptionTime inception 模块（Ismail Fawaz et al., Data Min. Knowl. Disc., 2020）

    - bottleneck 1x1（降通道，降低卷积成本）
    - 并行分支：kernel 5/11/23 一维卷积 + maxpool 旁路
    - concat 后 batch-norm
    原文用全局平均池化；此处保留时序输出交给 AttentionPooling。
    """

    def __init__(self, in_ch, n_filters=32, kernel_sizes=(5, 11, 23),
                 bottleneck: int | None = 32, use_bn=True):
        super().__init__()
        k0, k1, k2 = kernel_sizes
        self.bottleneck = (nn.Conv1d(in_ch, bottleneck, kernel_size=1, bias=False)
                           if bottleneck else None)
        self.use_bn = use_bn
        in_branch = bottleneck or in_ch
        self.convs = nn.ModuleList([
            nn.Conv1d(in_branch, n_filters, kernel_size=k, padding=k // 2,
                      bias=False)
            for k in (k0, k1, k2)
        ])
        self.pool = nn.Conv1d(in_branch, n_filters, kernel_size=1, bias=False)
        self.maxpool = nn.MaxPool1d(3, stride=1, padding=1)
        out_ch = n_filters * 4
        if use_bn:
            self.bn = nn.BatchNorm1d(out_ch)
        self.activation = nn.ReLU(inplace=True)

    def forward(self, x):
        z = x
        if self.bottleneck is not None:
            z = self.bottleneck(x)
        branches = [conv(z) for conv in self.convs]
        branches.append(self.pool(self.maxpool(z)))  # pool 旁路经 1x1 保持通道
        out = torch.cat(branches, dim=1)
        if self.use_bn:
            out = self.bn(out)
        return self.activation(out)


class ECGInceptionTime(nn.Module):
    """InceptionTime 主干（12导联ECG → 时序特征 (batch, seq_out, d_model)）

    时间维不降采样（seq_out == seq_len），多尺度卷积捕获跨样本局部结构；
    适合校准迁移对比中对齐 BiMamba 的全分辨率特性。
    """

    def __init__(
        self,
        in_channels: int = 12,
        d_model: int = 64,
        n_blocks: int = 4,
        n_filters: int = 32,
        bottleneck: int | None = 32,
        dropout: float = 0.0,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.d_model = d_model
        cur_ch = in_channels
        self.blocks = nn.ModuleList()
        # 每个块后通道 = n_filters*4；块间降半通道避免爆炸（InceptionTime 常用缩放）
        for i in range(n_blocks):
            self.blocks.append(
                _InceptionBlock1D(cur_ch, n_filters=n_filters,
                                  bottleneck=bottleneck))
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


# ===========================================================================
# 主干注册表（供 ECGClassifier / train.py 按名取用）
# ===========================================================================
def build_backbone(name: str, in_channels: int, d_model: int,
                   n_layers: int, dropout: float) -> nn.Module:
    """按 §4 架构名构造主干（返回 (batch,...,d_model) 时序特征主干）。

    name:
      - "mamba"/"bimamba": 主协议 BiMamba（默认，s4_backbone.ECGMambaBackbone）
      - "resnet1d": ECGResNet1D（§4 基线1）
      - "inceptiontime": ECGInceptionTime（§4 基线2）
    """
    name = name.lower()
    if name in ("mamba", "bimamba", "s4"):
        from .s4_backbone import ECGMambaBackbone
        return ECGMambaBackbone(in_channels=in_channels, d_model=d_model,
                                n_layers=n_layers, dropout=dropout)
    if name in ("resnet1d", "resnet", "resnet-1d"):
        return ECGResNet1D(in_channels=in_channels, d_model=d_model,
                           dropout=dropout)
    if name in ("inceptiontime", "inception", "inception-time"):
        return ECGInceptionTime(in_channels=in_channels, d_model=d_model,
                                dropout=dropout)
    raise ValueError(f"Unknown backbone name: {name!r}")


__all__ = [
    "ECGResNet1D",
    "ECGInceptionTime",
    "build_backbone",
]
