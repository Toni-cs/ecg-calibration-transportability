#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""剖析单个 MambaBlock 的训练步耗时构成，定位真正的瓶颈。

在真实形状（B=16, L=5000, d_model=64, ED=128, N=16）下分别计时：
  in_proj / conv1d / x_proj / dt_proj / selective_scan
前向与反向分开测，便于判断是算力瓶颈还是 Python 启动开销。

用法::

    /c/python/python.exe scripts/profile_mamba_step.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from mambapy.mamba import Mamba, MambaConfig  # noqa: E402


def timeit(fn, reps=3, warmup=1):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / reps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--seq-len", type=int, default=5000)
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--d-state", type=int, default=16)
    ap.add_argument("--d-conv", type=int, default=4)
    ap.add_argument("--expand", type=int, default=2)
    ap.add_argument("--dt-rank", type=int, default=None,
                    help="默认与 mambapy 一致（d_model//16）")
    args = ap.parse_args()

    if not torch.cuda.is_available():
        print("CUDA 不可用")
        return
    dev = torch.device("cuda")

    ED = args.d_model * args.expand
    N = args.d_state
    dt_rank = args.dt_rank if args.dt_rank else args.d_model // 16
    B, L = args.batch, args.seq_len

    print(f"B={B}  L={L}  d_model={args.d_model}  ED={ED}  N={N}  dt_rank={dt_rank}")
    print(f"扫描张量形状 (B, ED, L, N) = ({B}, {ED}, {L}, {N}) "
          f"= {B*ED*L*N/1e6:.1f} M 元素 ({B*ED*L*N*4/1e9:.2f} GB fp32)")
    print(f"npo2(L) = {2**((L-1).bit_length())}  -> 实际扫描张量 "
          f"{B*ED*2**((L-1).bit_length())*N*4/1e9:.2f} GB\n")

    cfg = MambaConfig(d_model=args.d_model, n_layers=1, d_state=N,
                      d_conv=args.d_conv, expand_factor=args.expand,
                      dt_rank=dt_rank)
    m = Mamba(cfg).to(dev).float().train()
    blk = m.layers[0].mixer

    x = torch.randn(B, L, args.d_model, device=dev)
    z = torch.randn(B, L, ED, device=dev)

    # --- 各子模块的前向成本 ---
    print(f"{'模块':<18}{'前向 ms':>10}{'占比':>8}")
    print("-" * 38)

    xz = blk.in_proj(x)
    xb, _ = xz.chunk(2, dim=-1)

    t_inproj = timeit(lambda: blk.in_proj(x))
    xc = xb.transpose(1, 2)
    t_conv = timeit(lambda: blk.conv1d(xc)[:, :, :L])
    xs = F.silu(xb)
    t_xproj = timeit(lambda: blk.x_proj(xs))
    deltaBC = blk.x_proj(xs)
    dlt = deltaBC[..., :dt_rank]
    t_dtproj = timeit(lambda: blk.dt_proj.weight @ dlt.transpose(1, 2))

    delta = blk.dt_proj.weight @ dlt.transpose(1, 2)
    delta = delta.transpose(1, 2)
    delta = F.softplus(delta + blk.dt_proj.bias)
    A = -torch.exp(blk.A_log.float())
    Bm = deltaBC[..., dt_rank:dt_rank + N]
    Cm = deltaBC[..., dt_rank + N:]
    t_scan = timeit(lambda: blk.selective_scan(xs, delta, A, Bm, Cm, blk.D.float()))

    total_fwd = t_inproj + t_conv + t_xproj + t_dtproj + t_scan
    for name, t in [("in_proj", t_inproj), ("conv1d", t_conv),
                    ("x_proj", t_xproj), ("dt_proj", t_dtproj),
                    ("selective_scan", t_scan)]:
        print(f"{name:<18}{t*1000:>10.1f}{t/total_fwd*100:>7.1f}%")
    print("-" * 38)
    print(f"{'前向合计':<18}{total_fwd*1000:>10.1f}{100:>7.1f}%")

    # --- 整个 block 的前向/反向 ---
    print()
    t_blk_fwd = timeit(lambda: blk(x))
    out = blk(x)
    t_blk_bwd = timeit(lambda: torch.autograd.grad(out.sum(), [p for p in blk.parameters()],
                                                    retain_graph=False, allow_unused=True))

    # 单层 Mamba（含残差/norm）的完整前向
    t_layer_fwd = timeit(lambda: m.layers[0](x))

    print(f"{'block 前向':<18}{t_blk_fwd*1000:>10.1f} ms")
    print(f"{'block 反向':<18}{t_blk_bwd*1000:>10.1f} ms")
    print(f"{'layer 前向':<18}{t_layer_fwd*1000:>10.1f} ms")

    n_blocks = 4  # ECGClassifier 的 mamba 骨干：2 层 x 双向
    est_fwd = t_blk_fwd * n_blocks
    est_bwd = t_blk_bwd * n_blocks
    print(f"\n4 个 block（2 层双向）估算：前向 {est_fwd*1000:.0f} ms + "
          f"反向 {est_bwd*1000:.0f} ms = {(est_fwd+est_bwd)*1000:.0f} ms/步")
    print(f"对应 s/样本 = {(est_fwd+est_bwd)/B:.4f}")


if __name__ == "__main__":
    main()
