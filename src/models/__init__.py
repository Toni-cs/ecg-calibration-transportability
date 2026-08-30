"""ECG校准修复研究 - 模型模块"""

from .s4_backbone import ECGMambaBackbone, BiMambaBlock
from .ecg_classifier import ECGClassifier, AttentionPooling

# 兼容旧导入
S4Backbone = ECGMambaBackbone
