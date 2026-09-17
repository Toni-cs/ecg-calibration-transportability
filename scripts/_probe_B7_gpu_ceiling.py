"""B7: 量化 GPU 版离"带宽上限"还有多远 -> CUDA kernel 的理论天花板"""
import time, numpy as np, torch

rng = np.random.default_rng(0)
dev = "cuda"
print(torch.cuda.get_device_name(0))

for n in (2000, 5000, 10000):
    p = rng.beta(2, 2, n); y = (rng.random(n) < p).astype(float)
    bw = 0.45 * (n / 2000.0) ** (-0.2)

    def run(dtype, reps=20):
        tp = torch.from_numpy(p).to(dev).to(dtype)
        tl = torch.from_numpy(y).to(dev).to(dtype)
        pc = torch.clamp(tp, 1e-6, 1 - 1e-6)
        lp = torch.log(pc / (1 - pc))
        out = torch.empty(n, dtype=dtype, device=dev)
        # 纯访存参考：只做一次 n×n 的 exp + 归约，无逐行除法
        for _ in range(3):
            z = (lp[:, None] - lp[None, :]) / bw
            w = torch.exp(-0.5 * z * z)
            s = w.sum(1)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        for _ in range(reps):
            z = (lp[:, None] - lp[None, :]) / bw
            w = torch.exp(-0.5 * z * z)
            s = w.sum(1)
            out = torch.abs((w * tl[None, :]).sum(1) / torch.clamp(s, min=1e-12) - tp)
        torch.cuda.synchronize()
        t = (time.perf_counter() - t0) / reps
        # 访存量粗估：z,w,w*y,读lp 约 5 次 n^2 读写
        gb = 5 * n * n * torch.tensor([], dtype=dtype).element_size() / 1e9
        return t, gb / t

    t64, b64 = run(torch.float64)
    t32, b32 = run(torch.float32)
    print(f"  n={n:>6}  fp64: {t64*1000:>7.2f} ms ({b64:>6.1f} GB/s)   "
          f"fp32: {t32*1000:>7.2f} ms ({b32:>6.1f} GB/s)   加速 {t64/t32:.1f}x")

props = torch.cuda.get_device_properties(0)
print(f"  GPU: {props.name}, SM={props.multi_processor_count}, "
      f"显存={props.total_memory/1e9:.1f} GB")
print("  注：消费级 GPU 的 fp64 吞吐通常仅为 fp32 的 1/32~1/64，"
      "因此 fp64 路径是【算力受限】而非带宽受限")
