import numpy as np
import torch


def _ensure_channel_first(x):
    return x if x.shape[0] == 12 else x.T


def _add_gaussian_noise(x, scale):
    noise = np.random.normal(loc=0.0, scale=scale, size=x.shape)
    return x + noise


def _scale_amplitude(x, sigma):
    factor = np.random.normal(loc=1.0, scale=sigma, size=(x.shape[0], 1))
    return x * factor


def _baseline_wander(x, max_amplitude=0.08):
    time_axis = np.linspace(0.0, 1.0, x.shape[1], endpoint=False)
    freq = np.random.uniform(0.05, 0.5)
    phase = np.random.uniform(0.0, 2.0 * np.pi)
    drift = np.sin(2.0 * np.pi * freq * time_axis + phase)[None, :]
    amplitude = np.random.uniform(0.0, max_amplitude, size=(x.shape[0], 1))
    return x + amplitude * drift


def _time_mask(x, min_len, max_len, repeats=1, fill_value=0.0):
    x = x.copy()
    for _ in range(repeats):
        mask_len = np.random.randint(min_len, max_len + 1)
        if mask_len >= x.shape[1]:
            continue
        start = np.random.randint(0, x.shape[1] - mask_len)
        x[:, start : start + mask_len] = fill_value
    return x


def _time_shift(x, max_shift):
    shift = np.random.randint(-max_shift, max_shift + 1)
    return np.roll(x, shift=shift, axis=1) if shift != 0 else x


def _segment_permutation(x, segments):
    if segments <= 1:
        return x
    seg_len = x.shape[1] // segments
    if seg_len == 0:
        return x
    order = np.random.permutation(segments)
    chunks = [x[:, idx * seg_len : (idx + 1) * seg_len] for idx in order]
    remainder = x[:, seg_len * segments :]
    return np.concatenate(chunks + [remainder], axis=1)


def _lead_dropout(x, max_leads=3):
    x = x.copy()
    n_drop = np.random.randint(1, max_leads + 1)
    drop_idx = np.random.choice(x.shape[0], size=n_drop, replace=False)
    x[drop_idx] = 0.0
    return x


def _lead_gain_jitter(x, max_delta=0.2):
    gains = np.random.uniform(1.0 - max_delta, 1.0 + max_delta, size=(x.shape[0], 1))
    return x * gains


def _frequency_mask(x, min_ratio=0.02, max_ratio=0.15):
    spectrum = np.fft.rfft(x, axis=1)
    freq_bins = spectrum.shape[1]
    width = max(1, int(np.random.uniform(min_ratio, max_ratio) * freq_bins))
    max_start = max(2, freq_bins - width)
    start = np.random.randint(1, max_start)
    attenuation = np.random.uniform(0.0, 0.2)
    spectrum[:, start : start + width] *= attenuation
    return np.fft.irfft(spectrum, n=x.shape[1], axis=1).astype(np.float32)


def _smooth_envelope(x, max_scale_delta=0.15):
    anchors = np.linspace(0, x.shape[1] - 1, 6)
    scales = np.random.uniform(1.0 - max_scale_delta, 1.0 + max_scale_delta, size=6)
    envelope = np.interp(np.arange(x.shape[1]), anchors, scales)
    return x * envelope[None, :]


def _mix_with_shifted_clone(x, alpha=0.2):
    shift = np.random.randint(-25, 26)
    clone = np.roll(x, shift=shift, axis=1)
    return (1.0 - alpha) * x + alpha * clone


class _BaseECGAugment:
    def __init__(self, mode="weak"):
        self.mode = mode

    def __call__(self, x):
        x = _ensure_channel_first(x).copy()
        if self.mode == "weak":
            return self.weak_aug(x).astype(np.float32)
        if self.mode == "strong":
            return self.strong_aug(x).astype(np.float32)
        return x.astype(np.float32)


class ECGAugment(_BaseECGAugment):

    def weak_aug(self, x):
        x = _scale_amplitude(x, sigma=0.1)
        return _add_gaussian_noise(x, scale=0.01)

    def strong_aug(self, x):
        if np.random.rand() < 0.5:
            x = _segment_permutation(x, segments=5)
        if np.random.rand() < 0.5:
            x = _time_mask(x, min_len=50, max_len=200)
        return self.weak_aug(x)


class BasicECGAugment(_BaseECGAugment):

    def weak_aug(self, x):
        return _add_gaussian_noise(x, scale=0.005)

    def strong_aug(self, x):
        x = _time_shift(x, max_shift=30)
        if np.random.rand() < 0.5:
            x = _time_mask(x, min_len=20, max_len=80)
        return self.weak_aug(x)


class ECGMatchAugment(_BaseECGAugment):
    def weak_aug(self, x):
        ops = [
            lambda inp: _time_shift(inp, max_shift=20),
            lambda inp: _time_mask(inp, min_len=25, max_len=90, fill_value=inp.mean()),
            lambda inp: _add_gaussian_noise(inp, scale=0.02),
            lambda inp: np.flip(inp, axis=0).copy(),
        ]
        return ops[np.random.randint(len(ops))](x)

    def strong_aug(self, x):
        ops = [
            lambda inp: _time_shift(inp, max_shift=35),
            lambda inp: _time_mask(inp, min_len=40, max_len=140, repeats=2, fill_value=inp.mean()),
            lambda inp: _add_gaussian_noise(inp, scale=0.03),
            lambda inp: np.flip(inp, axis=0).copy(),
        ]
        for op in np.random.choice(ops, size=2, replace=False):
            x = op(x)
        return x


class AcquisitionAwareECGAugment(_BaseECGAugment):
    def weak_aug(self, x):
        x = _scale_amplitude(x, sigma=0.05)
        x = _baseline_wander(x, max_amplitude=0.03)
        return _add_gaussian_noise(x, scale=0.005)

    def strong_aug(self, x):
        x = _lead_gain_jitter(x, max_delta=0.25)
        x = _baseline_wander(x, max_amplitude=0.08)
        if np.random.rand() < 0.5:
            x = _lead_dropout(x, max_leads=2)
        return _add_gaussian_noise(x, scale=0.015)


class TemporalCorruptionECGAugment(_BaseECGAugment):
    def weak_aug(self, x):
        x = _time_shift(x, max_shift=12)
        return _time_mask(x, min_len=15, max_len=50, fill_value=x.mean())

    def strong_aug(self, x):
        x = _segment_permutation(x, segments=6)
        x = _time_shift(x, max_shift=40)
        return _time_mask(x, min_len=40, max_len=120, repeats=2, fill_value=x.mean())


class LeadAwareECGAugment(_BaseECGAugment):
    def weak_aug(self, x):
        return _lead_gain_jitter(x, max_delta=0.1)

    def strong_aug(self, x):
        x = _lead_gain_jitter(x, max_delta=0.3)
        if np.random.rand() < 0.7:
            x = _lead_dropout(x, max_leads=3)
        return _add_gaussian_noise(x, scale=0.01)


class FrequencyAwareECGAugment(_BaseECGAugment):
    def weak_aug(self, x):
        x = _frequency_mask(x, min_ratio=0.01, max_ratio=0.05)
        return _add_gaussian_noise(x, scale=0.004)

    def strong_aug(self, x):
        x = _frequency_mask(x, min_ratio=0.05, max_ratio=0.2)
        x = _baseline_wander(x, max_amplitude=0.05)
        return _add_gaussian_noise(x, scale=0.01)


class MorphologyPreservingMixedAugment(_BaseECGAugment):
    def weak_aug(self, x):
        x = _smooth_envelope(x, max_scale_delta=0.08)
        return _mix_with_shifted_clone(x, alpha=0.1)

    def strong_aug(self, x):
        x = _smooth_envelope(x, max_scale_delta=0.15)
        x = _mix_with_shifted_clone(x, alpha=0.25)
        return _time_mask(x, min_len=20, max_len=70, fill_value=x.mean())


def get_ptbxl_augmenter(name, mode):
    augmenters = {
        "ecg": ECGAugment,
        "fixmatch_basic": BasicECGAugment,
        "ecgmatch": ECGMatchAugment,
        "acquisition": AcquisitionAwareECGAugment,
        "temporal": TemporalCorruptionECGAugment,
        "lead": LeadAwareECGAugment,
        "frequency": FrequencyAwareECGAugment,
        "morphology": MorphologyPreservingMixedAugment,
    }
    if name not in augmenters:
        raise ValueError(f"Unsupported PTB-XL augmentation: {name}")
    return augmenters[name](mode=mode)