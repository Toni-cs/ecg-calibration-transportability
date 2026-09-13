"""InceptionTime-Lite backbone: 3-block lightweight InceptionTime (E5 experiment, Section 4 architecture family 3).

Design goals (E5 preregistration):
- Parameter count ~200K-500K (comparable to ResNet1D ~200K, BiMamba ~400K, for fair comparison).
- 3 Inception modules (original InceptionTime uses 6, simplified to 3).
- Preserve the three key inductive biases of InceptionTime:
  (a) Multi-scale parallel convolutions (kernels 5/11/23 capture short/medium/long-range features).
  (b) 1x1 bottleneck for dimensionality reduction (lowers convolution cost, signature of the Inception family).
  (c) maxpool branch (retains high-frequency information, complementary to the conv branches).
- No temporal downsampling (seq_out == seq_len), aligning with BiMamba's full-resolution property.

Argument for architectural-family independence (proponent position):
  Architectural families differ by inductive bias, not depth:
  - ResNet1D: serial residuals + staged downsampling (VGG/ResNet paradigm).
  - BiMamba: selective state space + bidirectional scan (SSM paradigm).
  - InceptionTime-Lite: multi-scale parallel conv + bottleneck + maxpool branch (Inception paradigm).
  The three are orthogonal in feature-extraction mechanism; 3 vs 6 blocks is a depth choice, not a family change.

Parameter derivation (n_filters=48, bottleneck=48, 3 blocks, d_model=64, in_ch=12):
  Block 1: bottleneck(12*48=576) + 3 convs(48*48*(5+11+23)=89856) + pool(48*48=2304) + BN(384) ~ 93K
  Block 2: bottleneck(192*48=9216) + 3 convs(89856) + pool(2304) + BN(384) ~ 102K
  Block 3: same as Block 2 ~ 102K
  proj(192*64=12288) + LayerNorm(128) ~ 12K
  Backbone total ~ 310K (within the 200K-500K target)
  Adding the ECGClassifier head (AttentionPooling + MLP) ~ 10K -> full model ~ 320K

OOM fallback (RTX 5060 8GB constraint, 4-level degradation chain):
  Level 1: n_filters 64->48->32 (this file defaults to 48; if OOM, use 32, params drop to ~136K).
  Level 2: gradient_checkpointing (wrap forward, trade time for memory).
  Level 3: ResNet1D with different hyperparameter variants (depth 3/5/7, width 32/64/128); degrades to a ResNet1D subfamily.
  Level 4: honestly report "2 architecture families + BiMamba toy" (worst case, paper downgrade statement).

References:
- Ismail Fawaz et al., "InceptionTime: Finding AlexNet for Time Series Classification",
  Data Mining and Knowledge Discovery, 2020.
- Wang et al., "Time Series Classification from Scratch with Deep Neural Networks",
  arXiv:1903.05994, 2019 (predecessor Inception block design behind InceptionTime).
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint


# ===========================================================================
# InceptionTime-Lite block (multi-scale parallel conv + bottleneck + maxpool branch)
# ===========================================================================
class InceptionBlockLite(nn.Module):
    """InceptionTime-Lite inception module (3 branches + pool branch, lightweight).

    Differences from baselines._InceptionBlock1D:
    - Explicit gradient checkpointing support (OOM fallback Level 2).
    - Default kernel_sizes=(5, 11, 23) (consistent with original InceptionTime).
    - Docs annotate per-module parameter contributions for E5 parameter auditing.
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
            # gradient checkpointing: do not store activations in forward, recompute in backward (trade time for memory)
            return checkpoint(self._forward_impl, x, use_reentrant=False)
        return self._forward_impl(x)


# ===========================================================================
# InceptionTime-Lite backbone
# ===========================================================================
class ECGInceptionTimeLite(nn.Module):
    """InceptionTime-Lite backbone (12-lead ECG -> temporal features (batch, seq_len, d_model)).

    E5 experiment only: 3-block lightweight InceptionTime, target params ~200K-500K.

    Differences from baselines.ECGInceptionTime:
    - Default n_blocks=3 (vs original 4, vs InceptionTime paper 6).
    - Default n_filters=48, bottleneck=48 (~310K params, within target range).
    - Explicit use_checkpoint for OOM fallback Level 2.
    - Provides count_parameters() for E5 parameter auditing.
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
            f"InceptionTime-Lite fixes n_blocks=3 (E5 preregistration); got {n_blocks}. "
            "Use baselines.ECGInceptionTime for other depths."
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
        """Parameter audit (E5 preregistration requires per-block backbone parameter reporting)."""
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
# Build function (used by E5 scripts by name, same interface as baselines.build_backbone)
# ===========================================================================
def build_inceptiontime_lite(
    in_channels: int = 12,
    d_model: int = 64,
    n_filters: int = 48,
    bottleneck: int = 48,
    dropout: float = 0.0,
    use_checkpoint: bool = False,
) -> ECGInceptionTimeLite:
    """Build the InceptionTime-Lite backbone (E5 only).

    Default params ~310K (n_filters=48, bottleneck=48, 3 blocks, d_model=64).
    OOM fallback: n_filters=32, bottleneck=32 -> ~136K (Level 1 degradation).
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
