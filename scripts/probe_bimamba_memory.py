#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""探测 BiMamba（arch 名 "mamba"）在真实训练配置下的显存与耗时。

真实配置（来自 scripts/eval_transfer.py 默认值 + 数据集实际形状）：
    B=16, L=5000（data/*/data/*.npy 为 (12, 5000)）, d_model=64, n_layers=2

BiMambaBlock 每层含 **两个** Mamba（前向 + 反向），故 n_layers=2 → 4 个 Mamba 块。
mambapy 的 pscan 会物化 (B, L, ED, N) 中间张量（ED=d_model*expand=128, N=16）。

用法::

    /c/python/python.exe scripts/probe_bimamba_memory.py
    /c/python/python.exe scripts/probe_bimamba_memory.py --batch 8 16 32 --layers 2
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
from pathlib import Path

import torch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402


def probe(batch: int, seq_len: int, layers: int, d_model: int, num_classes: int,
          device: torch.device, backward: bool = True, ckpt: bool = False,
          pscan: bool = True) -> dict:
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(device)

    model = ECGClassifier(
        in_channels=12, d_model=d_model, n_layers=layers,
        num_classes=num_classes, dropout=0.1, backbone_type="mamba",
    ).to(device)
    model.train()

    # 关闭 pscan -> 走 selective_scan_seq（顺序扫描，内存 O(B·ED·N)，无 (B,L,ED,N) 物化）
    if not pscan:
        for m in model.modules():
            cfg = getattr(m, "config", None)
            if cfg is not None and hasattr(cfg, "pscan"):
                cfg.pscan = False

    if ckpt:
        from torch.utils.checkpoint import checkpoint as _ck
        for blk in model.backbone.layers:
            orig = blk.forward

            def make(fn):
                def wrapped(x):
                    return _ck(fn, x, use_reentrant=False)
                return wrapped

            blk.forward = make(orig)

    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    x = torch.randn(batch, 12, seq_len, device=device)
    y = torch.randint(0, num_classes, (batch,), device=device)
    crit = torch.nn.CrossEntropyLoss()

    def one_step():
        logits, _p = model(x)
        loss = crit(logits, y)
        if backward:
            loss.backward()
            opt.step()
            opt.zero_grad(set_to_none=True)

    t0 = time.perf_counter()
    ok, err = True, ""
    try:
        one_step()                    # 预热（含 cuBLAS/cuDNN 初始化）
        torch.cuda.synchronize(device)
        warm = time.perf_counter() - t0
        torch.cuda.reset_peak_memory_stats(device)
        t0 = time.perf_counter()
        one_step()
        torch.cuda.synchronize(device)
        dt = time.perf_counter() - t0
        peak = torch.cuda.max_memory_allocated(device) / 1e9
    except torch.cuda.OutOfMemoryError:
        dt = float("nan")
        peak = float("nan")
        ok = False
        err = "OOM"
        torch.cuda.empty_cache()

    del model, opt, x, y
    gc.collect()
    torch.cuda.empty_cache()
    return {"batch": batch, "seq_len": seq_len, "layers": layers, "ckpt": ckpt,
            "pscan": pscan, "peak_gb": peak, "sec": dt, "ok": ok, "err": err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, nargs="+", default=[16])
    ap.add_argument("--seq-len", type=int, default=5000)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--num-classes", type=int, default=5)
    ap.add_argument("--ckpt", action="store_true",
                    help="对每个 BiMambaBlock 启用梯度检查点")
    ap.add_argument("--no-pscan", action="store_true",
                    help="关闭 pscan，走顺序扫描（内存 O(B·ED·N)）")
    args = ap.parse_args()

    if not torch.cuda.is_available():
        print("CUDA 不可用，退出")
        return
    dev = torch.device("cuda")
    p = torch.cuda.get_device_properties(0)
    print(f"GPU: {p.name}  {p.total_memory/1e9:.2f} GB")
    print(f"配置: L={args.seq_len} d_model={args.d_model} n_layers={args.layers} "
          f"(= {args.layers*2} 个 Mamba 块)  检查点={args.ckpt}  pscan={not args.no_pscan}")
    print(f"{'B':>4} {'峰值GB':>9} {'步耗时s':>9}  状态")
    for b in args.batch:
        r = probe(b, args.seq_len, args.layers, args.d_model, args.num_classes,
                  dev, ckpt=args.ckpt, pscan=not args.no_pscan)
        if r["ok"]:
            print(f"{b:>4} {r['peak_gb']:>9.2f} {r['sec']:>9.2f}  OK")
        else:
            print(f"{b:>4} {'-':>9} {r['sec']:>9.2f}  {r['err']}")


if __name__ == "__main__":
    main()
