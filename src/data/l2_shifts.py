"""L2 shift ladder transforms (protocol Section 3:44-48, eval-time, no retraining).

13 levels = 2 downsampling + 4 leads + 5 noise + 2 gain. This module implements all 13
levels (the 5 noise levels use synthetic noise because PhysioNet's nstdb requires
authentication and cannot be downloaded).

Semantics note:
- leads6: the key name is kept for compatibility with historical result files. The actual
  transform **keeps 8 independent channels (I, II, V1-V6)** and removes the 4 linearly
  derivable leads (III, aVR, aVL, aVF). The full 12-lead set is linearly reconstructable
  from I, II, V1-V6 (Goldberger/Wilson electrode relations), so this is a "lossless
  downgrade", not a standard 6-lead monitoring configuration.
- leads3 = [I, II, V2] (not the standard monitoring 3-lead II+V1+V5; the subset choice is
  a preregistered protocol decision).
- gain: applied **after per-record z-score normalization** (x0.5 / x2), without
  re-normalizing. Empirically, scaling the raw signal by 2 then normalizing is bit-identical
  to normalizing then scaling by 2 (max|delta| < 1e-6), i.e. acquisition-side gain error is
  fully cancelled by per-record z-score; this level instead simulates **post-normalization
  gain mismatch** (training augmentation uses amplitude only in [0.8, 1.2]), not
  acquisition-side gain error.
- noise: **synthetic noise** (not real PTB-XL nstdb noise, due to PhysioNet 403
  authentication limits). BWL = low-frequency sine (0.05-1 Hz) for baseline drift;
  MA = band-pass white noise (20-100 Hz) for muscle artifact; EM = low-frequency drift +
  random steps for electrode motion. SNR = {24, 12, 6, 0, -6} dB controls intensity.
  The paper must note this limitation (synthetic noise statistics differ from real nstdb).
"""
from __future__ import annotations

import numpy as np
from scipy.signal import decimate

# Shared SEED_STRATEGY_VERSION definition (eliminates the duplicated definition across
# eval_l2_shift.py and run_e1a_l2_shift_full.py, a DRY violation). Legacy results used
# RandomState(42) (legacy_42); new results use md5-derived seeds (md5_v1). is_checkpoint_complete
# checks this version and treats a mismatch as incomplete (needs rerun), preventing mixed use.
# Both scripts must stay in sync when the version is bumped.
SEED_STRATEGY_VERSION = "md5_v1"

LEAD_NAMES = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]

LEAD_SUBSETS = {
    6: [0, 1, 6, 7, 8, 9, 10, 11],
    3: [0, 1, 7],
    2: [0, 1],
    1: [1],
}


def shift_downsample(signal: np.ndarray, target_hz: int, orig_hz: int = 500) -> np.ndarray:
    """Anti-aliasing downsampling (scipy.signal.decimate, IIR Chebyshev II + filtfilt).

    signal: (12, L) -> (12, L * target_hz / orig_hz)
    """
    if target_hz >= orig_hz:
        return signal
    q = orig_hz // target_hz
    return decimate(signal, q=q, axis=1, ftype="iir").astype(np.float32)


def shift_leads(signal: np.ndarray, n_leads: int) -> np.ndarray:
    """Zero out leads (keep n_leads leads, zero the rest, preserve 12 channels).

    signal: (12, L) -> (12, L) with non-subset channels zeroed
    """
    if n_leads >= 12:
        return signal
    keep = LEAD_SUBSETS[n_leads]
    out = signal.copy()
    mask = np.ones(12, dtype=bool)
    mask[keep] = False
    out[mask] = 0.0
    return out.astype(np.float32)


def shift_gain(signal: np.ndarray, gain: float) -> np.ndarray:
    """Gain transform (applied after normalization, no re-normalization).

    signal: (12, L) -> (12, L) * gain
    """
    return (signal * gain).astype(np.float32)


def _synthetic_noise(n_samples: int, noise_type: str, fs: int = 500,
                     rng: np.random.RandomState | None = None) -> np.ndarray:
    """Generate single-lead synthetic noise (mimics nstdb BWL/MA/EM statistics).

    Returns a (n_samples,) noise sequence in the same units as the signal (std ~1 after normalization).
    """
    if rng is None:
        raise ValueError(
            "rng must be explicitly provided; RandomState(42) fallback was removed "
            "to prevent cross-experiment seed collision"
        )
    t = np.arange(n_samples) / fs

    if noise_type == "bwl":
        f1, f2 = 0.15, 0.5
        noise = (0.3 * np.sin(2 * np.pi * f1 * t + rng.uniform(0, 2 * np.pi))
                 + 0.2 * np.sin(2 * np.pi * f2 * t + rng.uniform(0, 2 * np.pi))
                 + 0.1 * np.polyval(rng.uniform(-0.01, 0.01, size=3), t - t.mean()))
    elif noise_type == "ma":
        raw = rng.randn(n_samples)
        from scipy.signal import butter, filtfilt
        b, a = butter(2, [20 / (fs / 2), 100 / (fs / 2)], btype="band")
        noise = filtfilt(b, a, raw)
    elif noise_type == "em":
        noise = np.zeros(n_samples)
        n_steps = max(1, n_samples // fs)
        for _ in range(n_steps):
            idx = rng.randint(0, n_samples)
            amp = rng.uniform(-0.5, 0.5)
            decay = rng.uniform(0.5, 2.0)
            noise += amp * np.exp(-np.maximum(np.arange(n_samples) - idx, 0) / (decay * fs))
        noise += 0.1 * np.sin(2 * np.pi * 0.3 * t + rng.uniform(0, 2 * np.pi))
    else:
        noise = np.zeros(n_samples)

    noise = noise - noise.mean()
    if noise.std() > 1e-12:
        noise = noise / noise.std()
    return noise.astype(np.float32)


def shift_noise(signal: np.ndarray, noise_type: str, snr_db: float,
                fs: int = 500, rng: np.random.RandomState | None = None) -> np.ndarray:
    """Noise injection (synthetic noise, mimics nstdb BWL/MA/EM).

    signal: (12, L) -> (12, L) + noise_scaled
    SNR = 10*log10(signal_power / noise_power), controlling noise intensity.
    BWL is common-mode (same across all leads); MA/EM are differential-mode (independent per lead).
    mixed = BWL (common) + MA (differential) + EM (differential), combined with equal weight.
    """
    if rng is None:
        raise ValueError(
            "rng must be explicitly provided; RandomState(42) fallback was removed "
            "to prevent cross-experiment seed collision"
        )
    n_leads, n_samples = signal.shape
    sig_power = np.mean(signal ** 2)
    if sig_power < 1e-12:
        return signal.astype(np.float32)
    noise_power = sig_power / (10 ** (snr_db / 10))

    if noise_type == "bwl":
        noise_1d = _synthetic_noise(n_samples, "bwl", fs, rng)
        noise = np.tile(noise_1d[None, :], (n_leads, 1))
    elif noise_type == "mixed":
        bwl_1d = _synthetic_noise(n_samples, "bwl", fs, rng)
        bwl = np.tile(bwl_1d[None, :], (n_leads, 1))
        ma = np.stack([_synthetic_noise(n_samples, "ma", fs, rng)
                       for _ in range(n_leads)])
        em = np.stack([_synthetic_noise(n_samples, "em", fs, rng)
                       for _ in range(n_leads)])
        noise = (bwl + ma + em) / 3.0
    else:
        noise = np.stack([_synthetic_noise(n_samples, noise_type, fs, rng)
                          for _ in range(n_leads)])

    noise = noise - noise.mean()
    if noise.std() > 1e-12:
        noise = noise / noise.std()
    noise = noise * np.sqrt(noise_power)
    return (signal + noise).astype(np.float32)


def get_l2_shifts() -> list[dict]:
    """Return the 13 L2 shift levels (2 downsampling + 4 leads + 5 noise + 2 gain).

    Each level: {name, type, params}
    """
    shifts = []
    for hz in [250, 125]:
        shifts.append({
            "name": f"fs{hz}",
            "type": "downsample",
            "params": {"target_hz": hz},
        })
    for n in [6, 3, 2, 1]:
        shifts.append({
            "name": f"leads{n}",
            "type": "leads",
            "params": {"n_leads": n},
        })
    for snr in [24, 12, 6, 0, -6]:
        shifts.append({
            "name": f"noise{snr}",
            "type": "noise",
            "params": {"noise_type": "mixed", "snr_db": snr},
        })
    for g in [0.5, 2.0]:
        shifts.append({
            "name": f"gain{g}",
            "type": "gain",
            "params": {"gain": g},
        })
    return shifts


def apply_shift(signal: np.ndarray, shift: dict,
                rng: np.random.RandomState | None = None) -> np.ndarray:
    """Apply a single shift transform to one signal.

    rng: random generator, used only for noise-type shifts. Passing the same rng ensures each
    signal in a loop gets different noise (rng state advances each call). For noise-type shifts,
    rng=None raises ValueError immediately (no silent fallback to RandomState(42), which would
    cause cross-experiment seed collisions and the hidden bug of identical noise on equal-length
    signals).
    """
    t = shift["type"]
    p = shift["params"]
    if rng is None and t == "noise":
        raise ValueError("rng must be provided for noise shifts")
    if t == "downsample":
        return shift_downsample(signal, p["target_hz"])
    elif t == "leads":
        return shift_leads(signal, p["n_leads"])
    elif t == "gain":
        return shift_gain(signal, p["gain"])
    elif t == "noise":
        return shift_noise(signal, p["noise_type"], p["snr_db"], rng=rng)
    return signal
