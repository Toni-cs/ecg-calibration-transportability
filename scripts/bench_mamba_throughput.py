#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BiMamba 训练吞吐扫描：找出 30 格网格可行的 (batch, chunk, ckpt, amp) 组合。

只关心训练步的真实耗时（前向+反向+优化器步），用真实形状 L=5000 / 12 导联。

用法::

    /c/python/python.exe scripts/bench_mamba_throughput.py
    /c/python/python.exe scripts/bench_mamba_throughput.py --reps 3
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
from src.models.mamba_chunked import enable_chunked_scan  # noqa: E402

# 论文网格的真实规模：6 个 pair，源域训练集大小（见 splits/*_seed42.csv）
TRAIN_SIZES = {"chapman": 12143, "cpsc": 6172, "ptbxl": 15051}
# 每个源域在 6 个 pair 中出现 2 次
SOURCE_MULT = {k: 2 for k in TRAIN_SIZES}
# 实测 best-epoch 中位数 ~8，patience=10 -> 约 18 个 epoch 会被真正跑完
EPOCHS = 18
SEEDS = 5


def total_steps(batch: int) -> int:
    """整个 30 格网格的总训练步数。"""
    per_seed = sum(SOURCE_MULT[s] * -(-n // batch) * EPOCHS for s, n in TRAIN_SIZES.items())
    return per_seed * SEEDS


def bench_one(batch, seq_len, layers, d_model, num_classes, chunk, ckpt, amp,
              device, reps=2):
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(device)

    model = ECGClassifier(in_channels=12, d_model=d_model, n_layers=layers,
                          num_classes=num_classes, dropout=0.1,
                          backbone_type="mamba").to(device)
    model.train()
    if chunk:
        enable_chunked_scan(model, chunk=chunk, use_checkpoint=ckpt, verbose=False)

    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    crit = torch.nn.CrossEntropyLoss()
    x = torch.randn(batch, 12, seq_len, device=device)
    y = torch.randint(0, num_classes, (batch,), device=device)
    scaler = torch.amp.GradScaler("cuda", enabled=amp)

    def step():
        opt.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            logits, _ = model(x)
            loss = crit(logits, y)
        scaler.scale(loss).backward()
        scaler.step(opt)
        scaler.update()

    res = {"batch": batch, "chunk": chunk, "ckpt": ckpt, "amp": amp,
           "ok": True, "peak_gb": float("nan"), "sec": float("nan")}
    try:
        step()
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
        t0 = time.perf_counter()
        for _ in range(reps):
            step()
        torch.cuda.synchronize(device)
        dt = (time.perf_counter() - t0) / reps
        res["peak_gb"] = torch.cuda.max_memory_allocated(device) / 1e9
        res["sec"] = dt
    except torch.cuda.OutOfMemoryError:
        res["ok"] = False
        torch.cuda.empty_cache()
    except RuntimeError as e:
        res["ok"] = False
        res["err"] = str(e)[:60]
        torch.cuda.empty_cache()

    del model, opt, x, y, scaler
    gc.collect()
    torch.cuda.empty_cache()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq-len", type=int, default=5000)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--num-classes", type=int, default=5)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--mem-limit", type=float, default=7.0,
                    help="可接受的峰值显存上限（GB），留出评测阶段余量")
    args = ap.parse_args()

    if not torch.cuda.is_available():
        print("CUDA 不可用")
        return
    dev = torch.device("cuda")
    p = torch.cuda.get_device_properties(0)
    total_gb = p.total_memory / 1e9
    print(f"GPU: {p.name}  {total_gb:.2f} GB")
    print(f"L={args.seq_len}  d_model={args.d_model}  n_layers={args.layers} "
          f"({args.layers*2} 个 Mamba 块)  num_classes={args.num_classes}")

    # 30 格网格的总步数（按 batch 而定）
    print(f"\n网格规模：6 pair x {SEEDS} seeds，按实测约 {EPOCHS} epoch 计")
    for b in (8, 16, 32):
        print(f"  B={b:>3} -> 总训练步数 {total_steps(b):,}")

    configs = [
        # (batch, chunk, ckpt, amp)
        (16, 500, True, False),   # 已知基线
        (16, 500, True, True),
        (16, 500, False, False),
        (8, 500, False, False),
        (8, 500, False, True),
        (16, 1000, True, True),
        (16, 250, True, True),
        (32, 500, True, True),
        (24, 500, True, True),
        (16, 500, False, True),
    ]

    print(f"\n{'B':>4} {'chunk':>6} {'ckpt':>5} {'amp':>4} {'峰值GB':>8} {'步耗时s':>9} "
          f"{'s/样本':>9} {'30格预计':>10}")
    rows = []
    for b, chunk, ckpt, amp in configs:
        r = bench_one(b, args.seq_len, args.layers, args.d_model, args.num_classes,
                      chunk, ckpt, amp, dev, reps=args.reps)
        if r["ok"] and r["peak_gb"] <= args.mem_limit:
            per_sample = r["sec"] / b
            hours = r["sec"] * total_steps(b) / 3600
            print(f"{b:>4} {chunk:>6} {str(ckpt):>5} {str(amp):>4} {r['peak_gb']:>8.2f} "
                  f"{r['sec']:>9.2f} {per_sample:>9.4f} {hours:>8.1f} h")
            rows.append((hours, b, chunk, ckpt, amp, r["peak_gb"], r["sec"]))
        elif r["ok"]:
            print(f"{b:>4} {chunk:>6} {str(ckpt):>5} {str(amp):>4} {r['peak_gb']:>8.2f} "
                  f"{r['sec']:>9.2f} {'—':>9}   超显存上限")
        else:
            print(f"{b:>4} {chunk:>6} {str(ckpt):>5} {str(amp):>4} {'—':>8} "
                  f"{'—':>9} {'—':>9}   {r.get('err', 'OOM')}")

    if rows:
        rows.sort()
        h, b, chunk, ckpt, amp, peak, sec = rows[0]
        print(f"\n>>> 最优可行配置：B={b} chunk={chunk} ckpt={ckpt} amp={amp}  "
              f"峰值 {peak:.2f} GB，{sec:.2f} s/step，30 格预计 {h:.1f} h（{h/24:.1f} 天）")


if __name__ == "__main__":
    main()
