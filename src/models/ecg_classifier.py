"""ECG Classification Model with Bidirectional Mamba Backbone (2026 SOTA)

架构流程（全链路，无死代码）：
12-lead ECG → Pointwise Stem → BiMamba Layers → **AttentionPooling** → LayerNorm+GELU MLP → 温度缩放 → Softmax

特性：
- Attention Pooling：学习关注判别性时间步（ECG上优于mean pooling）
- 可学习温度参数：后续校准修复研究的基础
- MC-Dropout：不确定性量化
"""

import math
from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from .s4_backbone import ECGMambaBackbone


class AttentionPooling(nn.Module):
    """注意力池化：对 (batch, seq_len, d_model) 加权聚合为 (batch, d_model)"""

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
    """ECG分类器（Bidirectional Mamba + AttentionPooling + 校准就绪）"""

    def __init__(
        self,
        in_channels: int = 12,
        d_model: int = 64,
        n_layers: int = 4,
        num_classes: int = 5,
        dropout: float = 0.1,
        temperature: float = 1.0,
        learnable_temp: bool = False,  # 主协议：T≡1冻结训练，温度只做后验TS（对抗性审查修复）
    ):
        super().__init__()
        self.in_channels = in_channels
        self.d_model = d_model
        self.num_classes = num_classes

        self.backbone = ECGMambaBackbone(
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
            probs:  (batch, num_classes) 若 return_probs
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
        """MC-Dropout不确定性量化

        工程修复（对抗性审查）：
        - MC采样时冻结BatchNorm（保持eval running stats），
          否则即使no_grad也会更新running_mean/var，永久改变部署模型
        - 结束后恢复原始training状态

        Returns:
            mean_probs: (batch, num_classes)
            uncertainty: (batch,) 预测熵
            std: (batch, num_classes) 概率标准差
        """
        was_training = self.training
        # 只开dropout，冻结BN
        self.train()
        for m in self.modules():
            if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d, nn.LayerNorm)):
                m.eval()

        probs_list = []
        with torch.no_grad():
            for _ in range(n_forward):
                _, probs = self.forward(x)
                probs_list.append(probs)

        self.train(was_training)  # 恢复原状态

        probs_stack = torch.stack(probs_list, dim=0)   # (n, batch, C)
        mean_probs = probs_stack.mean(dim=0)
        uncertainty = -(mean_probs * torch.log(mean_probs + 1e-10)).sum(dim=-1)
        std = probs_stack.std(dim=0)
        return mean_probs, uncertainty, std

    def get_features(self, x: torch.Tensor) -> torch.Tensor:
        """获取池化后特征 (batch, d_model)"""
        return self.pool(self.backbone(x))


def create_ecg_classifier(
    in_channels: int = 12,
    d_model: int = 64,
    n_layers: int = 4,
    num_classes: int = 5,
    dropout: float = 0.1,
    **kwargs,
) -> ECGClassifier:
    """工厂函数"""
    return ECGClassifier(
        in_channels=in_channels,
        d_model=d_model,
        n_layers=n_layers,
        num_classes=num_classes,
        dropout=dropout,
        **kwargs,
    )
