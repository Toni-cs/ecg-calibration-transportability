"""L2 移位阶梯变换（协议§3:44-48，eval-time，不重训练）。

13 档 = 降采样 2 + 导联 4 + 噪声 5 + 增益 2。
本模块实现全部 13 档（噪声 5 档用合成噪声，因 PhysioNet nstdb 需认证无法下载）。

语义声明（对抗性审查 R5/R6 修复）：
- leads6: 键名沿用历史结果文件。实际变换为**保留 8 个独立通道
  (I,II,V1-V6)**，移除 4 个线性可导出导联 (III,aVR,aVL,aVF)——完整 12 导联
  可由 I,II,V1-V6 线性重构（Goldberger/Wilson 电极关系），属"信息无损降档"，
  非标准 6 导联监护配置。
- leads3 = [I,II,V2]（非标准监护 3 导联 II+V1+V5，子集选择为协议预注册决定）。
- gain: 在 **per-record z-score 归一化之后**施加 (×0.5/×2)，不重新归一化。
  实测原始信号×2 再归一化与归一化后×2 逐位一致 (max|Δ|<1e-6)，即采集端增益
  误差会被 per-record z-score 完全抵消；本档模拟的是**归一化管线后的增益失配**
  （训练 augment 幅值仅 [0.8,1.2]），非采集端增益误差。
- noise: **合成噪声**（非 PTB-XL nstdb 真实噪声，因 PhysioNet 403 认证限制）。
  BWL=低频正弦(0.05-1Hz)模拟基线漂移；MA=带通白噪声(20-100Hz)模拟肌肉伪影；
  EM=低频漂移+随机步进模拟电极运动。SNR={24,12,6,0,-6}dB 控制强度。
  论文须标注此限制（合成噪声统计特性与真实 nstdb 不完全一致）。
"""
from __future__ import annotations

import numpy as np
from scipy.signal import decimate

LEAD_NAMES = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]

LEAD_SUBSETS = {
    6: [0, 1, 6, 7, 8, 9, 10, 11],
    3: [0, 1, 7],
    2: [0, 1],
    1: [1],
}


def shift_downsample(signal: np.ndarray, target_hz: int, orig_hz: int = 500) -> np.ndarray:
    """抗混叠降采样（scipy.signal.decimate，IIR Chebyshev II + filtfilt）。

    signal: (12, L) → (12, L * target_hz / orig_hz)
    """
    if target_hz >= orig_hz:
        return signal
    q = orig_hz // target_hz
    return decimate(signal, q=q, axis=1, ftype="iir").astype(np.float32)


def shift_leads(signal: np.ndarray, n_leads: int) -> np.ndarray:
    """导联置零（保留 n_leads 个导联，其余置零，保持 12 通道）。

    signal: (12, L) → (12, L) 置零非子集通道
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
    """增益变换（归一化后施加，不重新归一化）。

    signal: (12, L) → (12, L) * gain
    """
    return (signal * gain).astype(np.float32)


def _synthetic_noise(n_samples: int, noise_type: str, fs: int = 500,
                     rng: np.random.RandomState | None = None) -> np.ndarray:
    """生成单导联合成噪声（模拟 nstdb BWL/MA/EM 统计特性）。

    返回 (n_samples,) 噪声序列，单位与信号相同（归一化后 ~σ=1）。
    """
    if rng is None:
        rng = np.random.RandomState(42)
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
    """噪声注入（合成噪声，模拟 nstdb BWL/MA/EM）。

    signal: (12, L) → (12, L) + noise_scaled
    SNR = 10*log10(signal_power / noise_power)，控制噪声强度。
    BWL 为共模（所有导联相同），MA/EM 为差模（各导联独立）。
    mixed = BWL(共模) + MA(差模) + EM(差模)，三者等权叠加。
    """
    if rng is None:
        rng = np.random.RandomState(42)
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
    """返回 13 档 L2 移位（降采样 2 + 导联 4 + 噪声 5 + 增益 2）。

    每档: {name, type, params}
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


def apply_shift(signal: np.ndarray, shift: dict) -> np.ndarray:
    """对单条信号施加移位变换。"""
    t = shift["type"]
    p = shift["params"]
    if t == "downsample":
        return shift_downsample(signal, p["target_hz"])
    elif t == "leads":
        return shift_leads(signal, p["n_leads"])
    elif t == "gain":
        return shift_gain(signal, p["gain"])
    elif t == "noise":
        return shift_noise(signal, p["noise_type"], p["snr_db"])
    return signal