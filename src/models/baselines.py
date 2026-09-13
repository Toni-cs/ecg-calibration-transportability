"""Two CNN backbones for the Section 4 baselines: 1D-ResNet and InceptionTime.

Design constraints (for fair comparison with the BiMamba backbone):
- Input (batch, n_leads=12, seq_len) -> output (batch, seq_len_out, d_model).
- Same contract as ECGMambaBackbone: feature extraction only, no final
  classification. Pooling and the classification head are unified in
  ECGClassifier (AttentionPooling + LayerNorm/GELU/Linear).
- AttentionPooling operates over any seq_len_out (softmax over time), so each
  backbone may downsample freely without breaking the downstream interface.
  Calibration comparison varies only the feature extractor; the head is fixed.

Architectures (standard, reproducible public implementations, documented layer
by layer):
1. ResNet1D: VGG/ResNet 1D adaptation (He et al. 2016; standard ResNet-1D for
   ECG classification). conv stem -> 4 residual stages (first block of each
   stage uses stride=2 downsampling, channel doubling) -> global/temporal
   features -> 1x1 projection to d_model -> (batch, seq_len_out, d_model).
2. InceptionTime: inception module from Ismail Fawaz et al. 2020 (bottleneck
   1x1 + multi-scale conv 5/11/23 + pooling branch), no temporal downsampling,
   final 1x1 projection to d_model. The original InceptionTime uses global
   average pooling for classification; to unify the interface we keep the
   temporal features and delegate to AttentionPooling, aligning only on the
   feature-extraction method.

BatchNorm discipline: BN updates running stats during training; the main
protocol temperature is fit at calibration time and metrics are reported only
at test time (compatible with the BN-freezing logic in
ECGClassifier.predict_with_uncertainty).
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


# ===========================================================================
# 1D-ResNet
# ===========================================================================
class _ResBlock1D(nn.Module):
    """Standard basic residual block (1D).

    Basic block (base_width style):
      bn+relu -> conv3x3 -> bn+relu -> conv3x3 -> + shortcut (optional projection).
    Supports stride>1 downsampling and channel expansion (first block of each stage).
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
    """1D ResNet backbone (12-lead ECG -> temporal features (batch, seq_out, d_model)).

    Layer config (number of blocks per stage; ResNet-34 style [3,4,6,3]):
      conv stem (7x7/stride2 + maxpool) -> 4 stages with channels [64,128,256,512]
      -> 1x1 projection to d_model (optional adaptive pooling to normalize length).

    Each stage halves seq_len via stride=2 (4 times, ~5000->313). This downsampling
    is intrinsic to ResNet and matches the Section 4 premise that differing
    architectures are a source of calibration transfer heterogeneity.
    """

    def __init__(
        self,
        in_channels: int = 12,
        d_model: int = 64,
        block_layers: tuple = (2, 2, 2, 2),  # small ECG ResNet-1D (limited capacity for fair comparison)
        base_width: int | None = None,        # None -> scales with d_model
        dropout: float = 0.0,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.d_model = d_model
        # Scale base_width with d_model so capacity matches BiMamba/InceptionTime.
        # Final stage channels = base_width * 2**(len-1); base_width ~ d_model/4 puts
        # the deepest layer at ~d_model, avoiding the unfair ~7M params of a default 64.
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
    """InceptionTime inception module (Ismail Fawaz et al., Data Min. Knowl. Disc., 2020).

    - 1x1 bottleneck (reduces channels, lowers convolution cost).
    - Parallel branches: 1D conv with kernel 5/11/23 + maxpool branch.
    - batch-norm after concatenation.
    The original uses global average pooling; here we keep the temporal output
    for AttentionPooling.
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
        branches.append(self.pool(self.maxpool(z)))  # pooling branch keeps channels via 1x1
        out = torch.cat(branches, dim=1)
        if self.use_bn:
            out = self.bn(out)
        return self.activation(out)


class ECGInceptionTime(nn.Module):
    """InceptionTime backbone (12-lead ECG -> temporal features (batch, seq_out, d_model)).

    No temporal downsampling (seq_out == seq_len); multi-scale convolutions capture
    cross-sample local structure, aligning with the full-resolution property of
    BiMamba for calibration transfer comparison.
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
        # channels after each block = n_filters*4; halve between blocks to avoid blowup (common InceptionTime scaling)
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
# Backbone registry (used by ECGClassifier / train.py to fetch by name)
# ===========================================================================
def build_backbone(name: str, in_channels: int, d_model: int,
                   n_layers: int, dropout: float) -> nn.Module:
    """Build a backbone by Section 4 architecture name (returns a (batch, ..., d_model)
    temporal-feature backbone).

    name:
      - "mamba"/"bimamba": main-protocol BiMamba (default, s4_backbone.ECGMambaBackbone).
      - "resnet1d": ECGResNet1D (Section 4 baseline 1).
      - "inceptiontime": ECGInceptionTime (Section 4 baseline 2).
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
    if name in ("inceptiontime_lite", "inception_lite", "inception-lite"):
        # E5 experiment: 3-block lightweight InceptionTime (~310K params, distinct architecture family)
        from .inceptiontime_lite import build_inceptiontime_lite
        return build_inceptiontime_lite(in_channels=in_channels,
                                        d_model=d_model,
                                        dropout=dropout)
    raise ValueError(f"Unknown backbone name: {name!r}")


__all__ = [
    "ECGResNet1D",
    "ECGInceptionTime",
    "build_backbone",
    "ECGInceptionTimeLite",
]

# E5 experiment: expose InceptionTime-Lite in the baselines namespace (used by ECGClassifier by name)
from .inceptiontime_lite import ECGInceptionTimeLite  # noqa: E402,F401

# E5 experiment: expose InceptionTime-Lite in the baselines namespace (used by ECGClassifier by name)
from .inceptiontime_lite import ECGInceptionTimeLite  # noqa: E402,F401
