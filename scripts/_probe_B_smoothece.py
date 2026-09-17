"""方案B 实测：SmoothECE 分块/融合/截断，能否毫秒级且精确？

B1. 复现基线耗时 + chunk 是否生效
B2. 行分块（现有代码已做）是否精确、是否提速
B3. 单遍融合（去临时量）提速
B4. GPU 版冷/热
B5. 截断核（banded Gaussian）+ 排序前缀和，精度-速度权衡
"""
import sys, time
import numpy as np

sys.path.insert(0, "d:/A1/ecg-lab-v2/src")
from utils.calibration import smooth_ece, smooth_ece_gpu

rng = np.random.default_rng(0)


def make(n):
    p = rng.beta(2, 2, n)
    y = (rng.random(n) < p).astype(float)
    return p, y


def timeit(fn, *a, reps=5, warm=1, **kw):
    for _ in range(warm):
        fn(*a, **kw)
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        r = fn(*a, **kw)
        ts.append(time.perf_counter() - t0)
    return min(ts), r


print("=" * 70)
print("[B1] 基线：原始 smooth_ece 耗时 + chunk 是否生效")
print("=" * 70)
for n in (500, 1000, 2000, 2057, 5000, 10000):
    p, y = make(n)
    chunk = max(1, int(2e7 // n))
    t, r = timeit(smooth_ece, p, y)
    print(f"  n={n:>6}  chunk={chunk:>7}  生效={chunk < n!s:>5}  "
          f"t={t*1000:>8.2f} ms  SmoothECE={r:.6f}")

print()
print("=" * 70)
print("[B2] 行分块 = 现有代码已做的事：精确性 + 是否提速")
print("=" * 70)


def smooth_ece_chunked(probs, labels, bandwidth=None, chunk=256):
    probs = np.asarray(probs, float); labels = np.asarray(labels, float)
    n = len(probs)
    if bandwidth is None:
        bandwidth = 0.45 * (n / 2000.0) ** (-0.2)
    pc = np.clip(probs, 1e-6, 1 - 1e-6)
    lp = np.log(pc / (1 - pc))
    out = np.empty(n)
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        z = (lp[s:e, None] - lp[None, :]) / bandwidth
        w = np.exp(-0.5 * z * z)
        out[s:e] = np.abs((w * labels[None, :]).sum(1) / np.maximum(w.sum(1), 1e-12)
                          - probs[s:e])
    return float(out.mean())


for n in (2000, 5000):
    p, y = make(n)
    ref = smooth_ece(p, y)
    for ch in (256, 1024):
        r = smooth_ece_chunked(p, y, chunk=ch)
        t, _ = timeit(smooth_ece_chunked, p, y, chunk=ch)
        print(f"  n={n} chunk={ch:>5}: t={t*1000:>8.2f} ms  Δ={abs(r-ref):.3e}  "
              f"精确={abs(r-ref) < 1e-12}")

print()
print("=" * 70)
print("[B3] 单遍融合（减少临时量 / float32 / numexpr）")
print("=" * 70)


def smooth_ece_fused(probs, labels, bandwidth=None, chunk=512):
    """单遍：不物化 z 与 w 两个中间量，原地算"""
    probs = np.asarray(probs, float); labels = np.asarray(labels, float)
    n = len(probs)
    if bandwidth is None:
        bandwidth = 0.45 * (n / 2000.0) ** (-0.2)
    pc = np.clip(probs, 1e-6, 1 - 1e-6)
    lp = np.log(pc / (1 - pc))
    inv2h2 = -0.5 / (bandwidth * bandwidth)
    out = np.empty(n)
    buf = np.empty((chunk, n))
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        m = e - s
        b = buf[:m]
        np.subtract(lp[s:e, None], lp[None, :], out=b)
        np.square(b, out=b)
        b *= inv2h2
        np.exp(b, out=b)
        out[s:e] = np.abs((b @ labels) / np.maximum(b.sum(1), 1e-12) - probs[s:e])
    return float(out.mean())


try:
    import numexpr as ne
    HAS_NE = True
except ImportError:
    HAS_NE = False
print(f"  numexpr 可用: {HAS_NE}")

for n in (2000, 5000):
    p, y = make(n)
    ref = smooth_ece(p, y)
    t0, r0 = timeit(smooth_ece, p, y)
    t3, r3 = timeit(smooth_ece_fused, p, y)
    print(f"  n={n}: 原版 {t0*1000:>7.2f} ms | 融合 {t3*1000:>7.2f} ms "
          f"({t0/t3:.2f}x)  Δ={abs(r3-ref):.3e}")

print()
print("=" * 70)
print("[B4] GPU 版 冷/热")
print("=" * 70)
for n in (2000, 5000):
    p, y = make(n)
    ref = smooth_ece(p, y)
    import torch
    torch.cuda.synchronize()
    t_cold0 = time.perf_counter()
    r = smooth_ece_gpu(p, y)
    torch.cuda.synchronize()
    t_cold = time.perf_counter() - t_cold0
    torch.cuda.synchronize()
    ts = []
    for _ in range(10):
        t0 = time.perf_counter(); smooth_ece_gpu(p, y); torch.cuda.synchronize()
        ts.append(time.perf_counter() - t0)
    print(f"  n={n}: 冷={t_cold*1000:>8.2f} ms  热={min(ts)*1000:>7.3f} ms  "
          f"Δ={abs(r-ref):.3e}")

print()
print("=" * 70)
print("[B5] 截断核（banded Gaussian）：精度-速度权衡")
print("=" * 70)


def smooth_ece_banded(probs, labels, bandwidth=None, R=6.0):
    """排序 + 截断：只累加 |lp_i-lp_j| <= R*h 的项。近似（丢弃 exp(-R^2/2) 以下的权重）"""
    probs = np.asarray(probs, float); labels = np.asarray(labels, float)
    n = len(probs)
    if bandwidth is None:
        bandwidth = 0.45 * (n / 2000.0) ** (-0.2)
    pc = np.clip(probs, 1e-6, 1 - 1e-6)
    lp = np.log(pc / (1 - pc))
    order = np.argsort(lp)
    lps = lp[order]; ys = labels[order]
    out = np.empty(n)
    win = R * bandwidth
    left = np.searchsorted(lps, lps - win, side="left")
    right = np.searchsorted(lps, lps + win, side="right")
    for i in range(n):
        a, b = left[i], right[i]
        d = (lps[a:b] - lps[i]) / bandwidth
        w = np.exp(-0.5 * d * d)
        out[order[i]] = abs((w * ys[a:b]).sum() / w.sum() - probs[order[i]])
    return float(out.mean())


for n in (2000, 5000):
    p, y = make(n)
    ref = smooth_ece(p, y)
    t0, _ = timeit(smooth_ece, p, y, reps=3)
    for R in (4.0, 5.0, 6.0, 8.0):
        t, r = timeit(smooth_ece_banded, p, y, R=R, reps=3)
        print(f"  n={n} R={R}: t={t*1000:>7.2f} ms  值={r:.6f}  Δ={abs(r-ref):.3e}")

print()
print("=" * 70)
print("[B6] bootstrap 场景（真实瓶颈）：重复调用 200 次")
print("=" * 70)
n = 2000
p, y = make(n)
for name, fn in (("原版CPU", smooth_ece), ("融合CPU", smooth_ece_fused),
                 ("GPU热", smooth_ece_gpu)):
    t0 = time.perf_counter()
    for b in range(200):
        idx = rng.integers(0, n, n)
        fn(p[idx], y[idx])
    print(f"  200次 bootstrap, n={n}: {name:<8} {time.perf_counter()-t0:>7.2f} s")
