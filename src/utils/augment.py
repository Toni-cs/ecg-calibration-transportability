"""ECG-specific data augmentation module.

Design principles:
    1. Apply randomly during training only; validation/test sets stay untouched -- evaluation
       must reflect the real distribution.
    2. Augmentation must not destroy diagnostic features (the key difference from image
       augmentation):
       - No signal flipping: an upside-down ECG is a different pathology clinically.
       - No time reversal: QRS complex morphology is directional.
       - Keep all perturbation amplitudes mild.
    3. Probabilistic triggers: each augmentation fires independently with probability p; a
       single sample may accumulate several effects.
    4. On-the-fly augmentation: the same sample shows a different variant each epoch,
       effectively enlarging the dataset.
"""

import numpy as np
import torch
from torch.utils.data import Dataset


def random_crop_pad(x: np.ndarray, crop: int = 900) -> np.ndarray:
    """Randomly crop a 9-second window then edge-pad: simulates recording-window offset, forcing the model not to rely on a fixed phase."""
    n = x.shape[-1]
    start = np.random.randint(0, n - crop + 1)
    seg = x[..., start:start + crop]
    pad_left = start
    pad_right = n - crop - start
    return np.pad(seg, ((0, 0), (pad_left, pad_right)), mode="edge")


def amplitude_scale(x: np.ndarray, lo: float = 0.8, hi: float = 1.2) -> np.ndarray:
    """Global amplitude scaling: simulates gain differences across acquisition devices."""
    return x * np.random.uniform(lo, hi)


def gaussian_noise(x: np.ndarray, sigma_max: float = 0.05) -> np.ndarray:
    """Gaussian noise: simulates acquisition-circuit noise (signal is standardized to std=1, so sigma<=0.05 is mild)."""
    sigma = np.random.uniform(0.01, sigma_max)
    return x + np.random.normal(0, sigma, x.shape).astype(np.float32)


def baseline_wander(x: np.ndarray, fs: int = 100, amp: float = 0.1) -> np.ndarray:
    """Baseline wander: adds a 0.05-0.5 Hz low-frequency sine to simulate respiration/electrode-motion artifacts (the most common real ECG noise)."""
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
    """Training-set wrapper: applies online random augmentation on fetch (wraps train only; val/test disabled)."""

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
