"""ECG calibration study - models subpackage."""

from .s4_backbone import ECGMambaBackbone, BiMambaBlock
from .ecg_classifier import ECGClassifier, AttentionPooling

# legacy import alias
S4Backbone = ECGMambaBackbone
