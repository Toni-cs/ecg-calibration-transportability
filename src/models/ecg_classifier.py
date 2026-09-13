"""ECG Classification Model (architecture-agnostic; BiMamba default).

Full pipeline (no dead code):
12-lead ECG -> backbone (BiMamba / ResNet1D / InceptionTime optional) ->
AttentionPooling -> LayerNorm+GELU MLP -> temperature scaling -> Softmax

- backbone contract: input (batch, n_leads, seq_len), output (batch, seq_len_out,
  d_model) temporal features; AttentionPooling works over any seq_len_out.
- Temperature scaling: the main protocol freezes T=1 during training; temperature
  scaling is applied only post hoc.
- Section 4 three-architecture comparison: only the backbone is swapped
  (build_backbone by name); the classification head is fixed, ensuring a fair
  calibration comparison under identical pooling/classification/temperature.
"""

import math
from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from .baselines import build_backbone


class AttentionPooling(nn.Module):
    """Attention pooling: aggregate (batch, seq_len, d_model) into (batch, d_model)."""

    def __init__(self, d_model: int):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.Tanh(),
            nn.Linear(d_model // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, d_model) -> (batch, d_model)"""
        attn = F.softmax(self.attention(x), dim=1)   # (batch, seq_len, 1)
        return (x * attn).sum(dim=1)                 # (batch, d_model)


class ECGClassifier(nn.Module):
    """ECG classifier (backbone: BiMamba/ResNet1D/InceptionTime + AttentionPooling + calibration-ready)."""

    def __init__(
        self,
        in_channels: int = 12,
        d_model: int = 64,
        n_layers: int = 4,
        num_classes: int = 5,
        dropout: float = 0.1,
        temperature: float = 1.0,
        learnable_temp: bool = False,  # main protocol: T=1 frozen during training; temperature applied only post hoc
        backbone_type: str = "mamba",  # mamba | resnet1d | inceptiontime (Section 4)
    ):
        super().__init__()
        self.in_channels = in_channels
        self.d_model = d_model
        self.num_classes = num_classes
        self.backbone_type = backbone_type

        self.backbone = build_backbone(
            backbone_type,
            in_channels=in_channels,
            d_model=d_model,
            n_layers=n_layers,
            dropout=dropout,
        )

        self.pool = AttentionPooling(d_model)

        self.classifier = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, num_classes),
        )

        if learnable_temp:
            self.log_temperature = nn.Parameter(torch.tensor(math.log(temperature)))
        else:
            self.register_buffer('log_temperature', torch.tensor(math.log(temperature)))

    @property
    def temperature(self) -> torch.Tensor:
        return torch.exp(self.log_temperature)

    def forward(
        self,
        x: torch.Tensor,
        return_probs: bool = True,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, n_leads, seq_len)
        Returns:
            logits: (batch, num_classes)
            probs:  (batch, num_classes) if return_probs
        """
        feats = self.backbone(x)          # (batch, seq_len, d_model)
        pooled = self.pool(feats)         # (batch, d_model)
        logits = self.classifier(pooled)  # (batch, num_classes)
        logits = logits / self.temperature
        probs = F.softmax(logits, dim=-1) if return_probs else None
        return logits, probs

    def predict_with_uncertainty(
        self,
        x: torch.Tensor,
        n_forward: int = 10,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """MC-Dropout uncertainty quantification.

        Engineering note:
        - Freeze BatchNorm during MC sampling (keep eval running stats); otherwise, even
          under no_grad, running_mean/var would update and permanently alter the deployed model.
        - Restore the original training state afterward.

        Returns:
            mean_probs: (batch, num_classes)
            uncertainty: (batch,) predictive entropy
            std: (batch, num_classes) probability standard deviation
        """
        was_training = self.training
        # enable dropout only; freeze BN
        self.train()
        for m in self.modules():
            if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d, nn.LayerNorm)):
                m.eval()

        probs_list = []
        with torch.no_grad():
            for _ in range(n_forward):
                _, probs = self.forward(x)
                probs_list.append(probs)

        self.train(was_training)  # restore original state

        probs_stack = torch.stack(probs_list, dim=0)   # (n, batch, C)
        mean_probs = probs_stack.mean(dim=0)
        uncertainty = -(mean_probs * torch.log(mean_probs + 1e-10)).sum(dim=-1)
        std = probs_stack.std(dim=0)
        return mean_probs, uncertainty, std

    def get_features(self, x: torch.Tensor) -> torch.Tensor:
        """Get pooled features (batch, d_model)."""
        return self.pool(self.backbone(x))


def create_ecg_classifier(
    in_channels: int = 12,
    d_model: int = 64,
    n_layers: int = 4,
    num_classes: int = 5,
    dropout: float = 0.1,
    backbone_type: str = "mamba",
    **kwargs,
) -> ECGClassifier:
    """Factory function (backbone_type: mamba/resnet1d/inceptiontime)."""
    return ECGClassifier(
        in_channels=in_channels,
        d_model=d_model,
        n_layers=n_layers,
        num_classes=num_classes,
        dropout=dropout,
        backbone_type=backbone_type,
        **kwargs,
    )
