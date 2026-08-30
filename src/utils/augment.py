"""ECG 专用数据增强模块

设计原则（教学点）:
    1. 只在训练时随机应用，验证/测试集保持原样——评估必须反映真实分布
    2. 增强不能破坏诊断特征（这是与图像增强的本质区别）:
       - 禁止信号翻转: 心电上下颠倒在医学上是另一种病理
       - 禁止时间反转: QRS波群形态有方向性
       - 所有扰动幅度保持温和
    3. 概率触发: 每种增强独立以 p 概率触发，一条样本可能叠加多种效果
    4. 在线增强(on-the-fly): 每个epoch同一样本呈现不同变体，等效扩充数据集
"""

import numpy as np
import torch
from torch.utils.data import Dataset


def random_crop_pad(x: np.ndarray, crop: int = 900) -> np.ndarray:
    """随机截取9秒窗口再边缘补齐: 模拟记录窗口偏移，逼迫模型不依赖固定相位"""
    n = x.shape[-1]
    start = np.random.randint(0, n - crop + 1)
    seg = x[..., start:start + crop]
    pad_left = start
    pad_right = n - crop - start
    return np.pad(seg, ((0, 0), (pad_left, pad_right)), mode="edge")


def amplitude_scale(x: np.ndarray, lo: float = 0.8, hi: float = 1.2) -> np.ndarray:
    """整体幅度缩放: 模拟不同采集设备的增益差异"""
    return x * np.random.uniform(lo, hi)


def gaussian_noise(x: np.ndarray, sigma_max: float = 0.05) -> np.ndarray:
    """高斯噪声: 模拟采集电路噪声（信号已标准化为std=1，sigma<=0.05属温和）"""
    sigma = np.random.uniform(0.01, sigma_max)
    return x + np.random.normal(0, sigma, x.shape).astype(np.float32)


def baseline_wander(x: np.ndarray, fs: int = 100, amp: float = 0.1) -> np.ndarray:
    """基线漂移: 叠加0.05~0.5Hz低频正弦，模拟呼吸/电极移动伪影（真实心电最常见噪声）"""
    t = np.arange(x.shape[-1]) / fs
    freq = np.random.uniform(0.05, 0.5)
    phase = np.random.uniform(0, 2 * np.pi)
    offset = amp * np.random.uniform(-1, 1) * np.sin(2 * np.pi * freq * t + phase)
    return x + offset.astype(np.float32).reshape(1, -1)


AUGMENT_FNS = [
    (random_crop_pad, 0.3),
    (amplitude_scale, 0.5),
    (gaussian_noise, 0.5),
    (baseline_wander, 0.3),
]


def augment(x: np.ndarray) -> np.ndarray:
    out = x
    for fn, p in AUGMENT_FNS:
        if np.random.rand() < p:
            out = fn(out)
    return out.astype(np.float32)


class AugmentedECGDataset(Dataset):
    """训练集包装器: 取样本时在线随机增强（只包装train，val/test禁用）"""

    def __init__(self, base: Dataset, enabled: bool = True):
        self.base = base
        self.enabled = enabled

    def __len__(self):
        return len(self.base)

    def __getitem__(self, idx):
        x, y = self.base[idx]
        if self.enabled:
            x = augment(x.numpy())
        return torch.from_numpy(np.ascontiguousarray(x)), y
