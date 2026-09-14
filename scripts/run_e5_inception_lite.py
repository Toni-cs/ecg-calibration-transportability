"""E5 实验：InceptionTime-Lite 训练 + 跨库迁移评估（协议§4 第3架构家族）

实验设计（E5 预注册）：
- 架构：InceptionTime-Lite（3 blocks, n_filters=48, ~310K 参数）
- 训练：3 语料库 × 5 种子 = 15 模型
- 迁移评估：6 方向 × 5 种子 = 30 评估
  6 方向 = 3 选 2 排列 = {(ptbxl→chapman), (ptbxl→cpsc), (chapman→ptbxl),
                          (chapman→cpsc), (cpsc→ptbxl), (cpsc→chapman)}
- 每个迁移实验应用 TS 校准，计算 Brier reliability 改善
- 输出：results/c3_inceptiontime_lite_30exp.csv

OOM 备选（4 级降级链，RTX 5060 8GB 约束）：
  Level 1: n_filters 48→32（参数量 ~310K → ~136K）
  Level 2: gradient checkpointing（use_checkpoint=True）
  Level 3: ResNet1D 不同超参变体（depth 3/5/7, width 32/64/128）
  Level 4: 诚实报告"2 架构家族 + BiMamba toy"（最坏情况，论文降级声明）

正方论证立场（InceptionTime-Lite 作为第3架构家族的合理性）：
  核心主张：架构家族的区分在于归纳偏置，而非深度。InceptionTime-Lite 保留
  InceptionTime 的三个关键归纳偏置（多尺度并行卷积 + bottleneck + maxpool 旁路），
  与 ResNet1D（串行残差）、BiMamba（选择性状态空间）在特征提取机制上正交。
  3 blocks vs 6 blocks 是深度选择，不改变家族归属。

  关键假设：
  H1（多尺度保留）：3 blocks 足以捕获 ECG 关键多尺度特征（P/QRS/T 波，80-200ms）
  H2（深度-校准解耦）：6→3 blocks 的深度减少主要影响判别性能，对校准迁移异质性影响二阶小
  H3（参数量-容量单调）：~310K 参数足以避免欠拟合退化解
  H4（BN 统计稳定）：3 blocks 的 BN running stats 在 batch_size=16 下能稳定收敛

  适用边界：
  - 3 vs 6 blocks：原始 6 blocks 在 seq_len=1000 上可能过深（每 block 不降采样）；
    3 blocks 是精度-效率权衡，若 test acc 显著低于其他架构（>5pp）需报告容量不足
  - 参数量上限：RTX 5060 8GB 约束下 n_filters=64（~555K）可能 OOM

  潜在攻击点（主动列出）：
  A1: "简化版是否算独立架构家族"——反驳：家族区分在归纳偏置而非深度
  A2: "参数量~310K 是否足够"——缓解：报告参数量与 acc 对比表，差距<2pp 则容量充足
  A3: "3 blocks 多尺度是否充分"——缓解：kernel 23 在 seq_len=1000 下覆盖 ~230ms
  A4: "OOM 备选的 ResNet1D 变体是否算独立"——缓解：备选 1/2 优先，备选 3 仅极端 OOM

用法：
    # 完整 E5（15 模型 + 30 迁移，GPU 30-45 小时）
    python scripts/run_e5_inception_lite.py

    # 冒烟测试（合成数据，2 epoch，1 种子）
    python scripts/run_e5_inception_lite.py --smoke

    # 仅训练不迁移（15 模型）
    python scripts/run_e5_inception_lite.py --no-transfer

    # OOM 备选 Level 1+2（减通道 + gradient checkpointing）
    python scripts/run_e5_inception_lite.py --n-filters 32 --use-checkpoint
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.models.inceptiontime_lite import (  # noqa: E402
    ECGInceptionTimeLite,
    build_inceptiontime_lite,
)
from src.utils.calibration import (  # noqa: E402
    benefit_inference,
    compute_all_metrics,
    fit_temperature,
    apply_temperature,
    smooth_ece,
)
from src.utils.calibration_methods import CALIBRATION_METHODS  # noqa: E402
from train import (  # noqa: E402
    set_seed,
    evaluate,
    train_model,
    create_dataloader,
    build_ptbxl_datasets,
    build_chapman_datasets,
    build_cpsc_datasets,
)
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402


# ===========================================================================
# 实验配置
# ===========================================================================
ARCH_NAME = "inceptiontime_lite"
SEEDS = [42, 43, 44, 45, 46]
DATASETS = ["ptbxl", "chapman", "cpsc"]
# 6 个迁移方向（3 选 2 排列）
TRANSFER_DIRECTIONS = [
    ("ptbxl", "chapman"),
    ("ptbxl", "cpsc"),
    ("chapman", "ptbxl"),
    ("chapman", "cpsc"),
    ("cpsc", "ptbxl"),
    ("cpsc", "chapman"),
]

DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}
# 数据目录（与现有实验一致）
DATASET_DIRS = {
    "ptbxl": str(PROJECT_ROOT / "data" / "ptbxl_processed"),
    "chapman": str(PROJECT_ROOT / "data" / "chapman_processed_v2"),
    "cpsc": str(PROJECT_ROOT / "data" / "cpsc_processed"),
}

OUTPUT_CSV = PROJECT_ROOT / "results" / "c3_inceptiontime_lite_30exp.csv"

# N1-r2 fix: 显式 n_bins 常量，与 run_e3_brier_dcr_ncv.py 对齐，避免依赖默认值
N_BINS = 10


# ===========================================================================
# Transfer result dict schema（R4 修复 Attack-1/4/6/7）
# ===========================================================================
# 统一所有 transfer result dict 的字段列表，避免 early-return dict（6字段）
# 与 normal result dict（20字段）schema 不一致导致 csv.DictWriter 在混合
# 时触发 ValueError（R3 终审裁决 P0-致命）。
# 字段顺序与 normal result dict（L526-545）保持一致，并补充 error/skipped
# 两个早返回专用字段，使所有构造点 schema 完全相同。
TRANSFER_RESULT_FIELDS = [
    "source", "target", "seed", "arch",
    "num_classes", "n_ood",
    "ood_acc_raw", "fitted_T",
    "ood_ece_raw", "ood_ece_ts",
    "ood_brier_raw", "ood_brier_ts",
    "delta_ece", "delta_ece_ci_low", "delta_ece_ci_high",
    "brier_reliability_improvement",
    "n_dropped_cal", "n_dropped_ood",
    "truncated", "subspace_filtered",
    "error", "skipped",
]


def _make_transfer_result(
    source: str,
    target: str,
    seed: int,
    arch: str = ARCH_NAME,
    num_classes: int = 0,
    n_ood: int = 0,
    ood_acc_raw: float = float("nan"),
    fitted_T: float = float("nan"),
    ood_ece_raw: float = float("nan"),
    ood_ece_ts: float = float("nan"),
    ood_brier_raw: float = float("nan"),
    ood_brier_ts: float = float("nan"),
    delta_ece: float = float("nan"),
    delta_ece_ci_low: float = float("nan"),
    delta_ece_ci_high: float = float("nan"),
    brier_reliability_improvement: float = float("nan"),
    n_dropped_cal: int = 0,
    n_dropped_ood: int = 0,
    truncated: bool = False,
    subspace_filtered: bool = False,
    error: Optional[str] = None,
    skipped: bool = False,
) -> dict:
    """构造字段完整的 transfer result dict（R4 修复 Attack-1/4/6/7）。

    统一所有 transfer result dict 的 schema。early-return / skipped / error
    路径下不可用的字段填入合理默认值（0 / False / nan / None），确保
    csv.DictWriter(fieldnames=TRANSFER_RESULT_FIELDS) 永远拿到字段一致的 dict。

    Attack-4: early-return dict 补齐 n_dropped_cal/n_dropped_ood/truncated/
              subspace_filtered（通过默认值 0/False 实现）
    Attack-6: early-return dict 补 arch 字段（通过 arch 参数实现）
    Attack-7: skipped/error dict 补齐所有缺失字段（通过默认值实现）
    """
    result = {
        "source": source,
        "target": target,
        "seed": seed,
        "arch": arch,
        "num_classes": num_classes,
        "n_ood": n_ood,
        "ood_acc_raw": ood_acc_raw,
        "fitted_T": fitted_T,
        "ood_ece_raw": ood_ece_raw,
        "ood_ece_ts": ood_ece_ts,
        "ood_brier_raw": ood_brier_raw,
        "ood_brier_ts": ood_brier_ts,
        "delta_ece": delta_ece,
        "delta_ece_ci_low": delta_ece_ci_low,
        "delta_ece_ci_high": delta_ece_ci_high,
        "brier_reliability_improvement": brier_reliability_improvement,
        "n_dropped_cal": n_dropped_cal,
        "n_dropped_ood": n_dropped_ood,
        "truncated": truncated,
        "subspace_filtered": subspace_filtered,
        "error": error,
        "skipped": skipped,
    }
    # R5 修复 Attack-2: schema 一致性运行时校验，确保所有构造点字段集合
    # 与 TRANSFER_RESULT_FIELDS 完全一致，任何字段增删都会立即触发 AssertionError。
    assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS), \
        f"Schema mismatch: {set(result.keys())} != {set(TRANSFER_RESULT_FIELDS)}"
    return result


# ===========================================================================
# OOM 检测与 4 级备选方案
# ===========================================================================
def is_oom_error(e: Exception) -> bool:
    """检测是否为 CUDA OOM 错误"""
    msg = str(e).lower()
    return (
        "out of memory" in msg
        or "cuda oom" in msg
        or "memory allocation" in msg
    )


def report_oom_level(level: int, detail: str) -> None:
    """OOM 备选方案触发报告"""
    print(f"\n{'='*60}")
    print(f"[OOM 备选] Level {level} 触发: {detail}")
    print(f"{'='*60}\n")


def try_train_with_oom_fallback(
    train_fn,
    config: dict,
    device: torch.device,
    n_filters: int = 48,
    use_checkpoint: bool = False,
) -> Tuple[Any, dict]:
    """带 4 级 OOM 备选的训练尝试

    Level 1: n_filters 48→32（参数量 ~310K → ~136K）
    Level 2: gradient checkpointing
    Level 3: ResNet1D 不同超参变体（depth 3/5/7, width 32/64/128）
    Level 4: 诚实报告"2 架构家族 + BiMamba toy"
    """
    oom_log = {"level": 0, "actions": []}
    # F3+S7 修复：第一项 level=0 使用用户传入的 n_filters/use_checkpoint，
    # 不再硬编码 {"n_filters": 48, "use_checkpoint": False} 导致命令行参数静默失效；
    # 同时消除原前两项均为 level=1 的重复（S7）。
    levels = [
        (0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint},
         f"用户指定配置（n_filters={n_filters}, checkpoint={use_checkpoint}）"),
        (1, {"n_filters": 32, "use_checkpoint": False}, "Level 1: n_filters 48→32（参数量 ~136K）"),
        (2, {"n_filters": 32, "use_checkpoint": True}, "Level 2: + gradient checkpointing"),
        (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 3, "width": 32},
         "Level 3: 退化为 ResNet1D 变体（depth=3, width=32）"),
        (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 5, "width": 64},
         "Level 3: ResNet1D 变体（depth=5, width=64）"),
        (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 7, "width": 128},
         "Level 3: ResNet1D 变体（depth=7, width=128）"),
    ]

    for level, params, desc in levels:
        try:
            # M1 修复：report_oom_level 条件改为 `if level > 0`，
            # 原条件 `level > 0 or params["n_filters"] != 48` 在用户指定 n_filters!=48
            # 时会对 level=0 的用户配置误报 OOM 备选触发，造成误导。
            report_oom_level(level, desc) if level > 0 else None
            model, extra = train_fn(params, device)
            oom_log["level"] = level
            oom_log["actions"].append(desc)
            oom_log["final_config"] = params
            return model, {**extra, "oom_log": oom_log}
        except RuntimeError as e:
            if is_oom_error(e):
                print(f"[OOM] {desc} 失败: {e}")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                oom_log["level"] = level
                oom_log["actions"].append(f"{desc} [FAILED: OOM]")
                continue
            raise
    # Level 4: 所有备选失败
    report_oom_level(4, "诚实报告'2 架构家族 + BiMamba toy'（论文降级声明）")
    oom_log["level"] = 4
    oom_log["actions"].append("Level 4: 诚实报告降级")
    return None, {"oom_log": oom_log, "degraded": True}


# ===========================================================================
# 数据集构建（复用 train.py 的 builders，处理 subspace）
# ===========================================================================
def build_dataset(
    dataset: str, seed: int, limit: Optional[int] = None,
    subspace: Optional[tuple] = None,
) -> Tuple[dict, Any]:
    builder = DATASET_BUILDERS[dataset]
    if dataset == "cpsc":
        ds, clusters = builder(DATASET_DIRS[dataset], seed, limit=limit)
    elif subspace is not None:
        ds, clusters = builder(DATASET_DIRS[dataset], seed, limit=limit, subspace=subspace)
    else:
        ds, clusters = builder(DATASET_DIRS[dataset], seed, limit=limit)
    return ds, clusters


# ===========================================================================
# 模型构建（InceptionTime-Lite，支持 OOM 备选参数）
# ===========================================================================
def build_model(
    num_classes: int,
    n_filters: int = 48,
    use_checkpoint: bool = False,
    d_model: int = 64,
    dropout: float = 0.1,
    arch_override: Optional[str] = None,
    depth: Optional[int] = None,
    width: Optional[int] = None,
) -> ECGClassifier:
    """构建 ECGClassifier（backbone=InceptionTime-Lite 或 OOM 备选 ResNet1D 变体）"""
    if arch_override == "resnet1d":
        # Level 3 备选：ResNet1D 变体
        from src.models.baselines import ECGResNet1D
        # F1 修复：用 depth 控制不同 block_layers 配置，真正构造不同 ResNet1D 变体
        # （原代码计算了 block_layers 但未使用，ECGClassifier 默认 block_layers=(2,2,2,2)，
        #   导致 depth=3/5/7 三个变体全部退化为同一默认配置，等同 Level 4 死代码）
        # depth=3→(1,1,1) 浅层窄, depth=5→(2,2,1) 中等, depth=7→(2,2,2,1) 深层宽
        block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}
        block_layers = block_layers_map.get(depth, (2, 2, 2, 2))
        resnet_d_model = width or d_model
        # 先构造 ECGClassifier（含 AttentionPooling + classifier head），
        # 再替换 backbone 为按 depth/width 真正构造的 ECGResNet1D
        model = ECGClassifier(
            in_channels=12, d_model=resnet_d_model, n_layers=2,
            num_classes=num_classes, dropout=dropout,
            backbone_type="resnet1d",
        )
        model.backbone = ECGResNet1D(
            in_channels=12, d_model=resnet_d_model,
            block_layers=block_layers, dropout=dropout,
        )
        return model
    # 默认：InceptionTime-Lite
    model = ECGClassifier(
        in_channels=12, d_model=d_model, n_layers=3,
        num_classes=num_classes, dropout=dropout,
        backbone_type="inceptiontime_lite",
    )
    # 若需自定义 n_filters/use_checkpoint，重建 backbone
    if n_filters != 48 or use_checkpoint:
        backbone = build_inceptiontime_lite(
            in_channels=12, d_model=d_model, n_filters=n_filters,
            bottleneck=n_filters, dropout=dropout, use_checkpoint=use_checkpoint,
        )
        model.backbone = backbone
    return model


# ===========================================================================
# 训练单个模型（1 语料库 × 1 种子）
# ===========================================================================
def train_single(
    dataset: str,
    seed: int,
    args: argparse.Namespace,
    device: torch.device,
    n_filters: int = 48,
    use_checkpoint: bool = False,
    arch_override: Optional[str] = None,
    depth: Optional[int] = None,
    width: Optional[int] = None,
) -> Tuple[Optional[nn.Module], dict]:
    """训练单个 InceptionTime-Lite 模型，返回 (model, info)

    F1 修复：增加 arch_override/depth/width 参数，使 Level 3 ResNet1D 变体
    能真正构造不同 depth/width 的 backbone，而非全部退到 Level 4 默认配置。
    - arch_override="resnet1d" 时，build_model 用 depth/width 构造真正 ResNet1D
    - depth 控制残差块层数：3→(1,1,1), 5→(2,2,1), 7→(2,2,2,1)（见 build_model）
    - width 控制 ResNet1D 通道数（d_model）
    """
    set_seed(seed)
    num_classes = DATASET_NUM_CLASSES[dataset]
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    arch_display = arch_override if arch_override else ARCH_NAME
    print(f"\n{'='*60}")
    print(f"[训练] {dataset} seed={seed} arch={arch_display} n_filters={n_filters}"
          f"{' depth='+str(depth) if depth else ''}{' width='+str(width) if width else ''}")
    print(f"{'='*60}")

    # 构建数据
    try:
        ds, clusters_test = build_dataset(dataset, seed, limit=args.limit, subspace=subspace)
    except FileNotFoundError as e:
        print(f"[SKIP] 数据集 {dataset} 不存在: {e}")
        return None, {"error": str(e), "skipped": True}

    loaders = {
        k: create_dataloader(ds[k], args.batch_size, shuffle=(k == "train"),
                             drop_last=(k == "train"), num_workers=args.num_workers)
        for k in ("train", "val", "cal", "test")
    }

    # 构建模型
    # F1 修复：传递 arch_override/depth/width 给 build_model，
    # 使 Level 3 ResNet1D 变体能真正按 depth/width 构造不同 backbone。
    model = build_model(
        num_classes=num_classes, n_filters=n_filters,
        use_checkpoint=use_checkpoint, d_model=args.d_model, dropout=0.1,
        arch_override=arch_override, depth=depth, width=width,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    print(f"[模型] 参数量: {n_params:,} (目标 200K-500K)")
    if n_params < 200_000:
        print(f"[WARN] 参数量 {n_params:,} < 200K 目标下界")
    elif n_params > 500_000:
        print(f"[WARN] 参数量 {n_params:,} > 500K 目标上界")

    # 训练
    # R5 修复 Attack-5: run_dir 使用动态 arch_display（含 OOM 备选 ResNet1D 标识），
    # 避免不同架构的 checkpoint 写入同一 ARCH_NAME 目录互相覆盖。
    run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "epochs": args.epochs, "lr": args.lr, "lr_min": 1e-6,
        "weight_decay": 1e-4, "patience": args.patience, "save_dir": str(run_dir),
    }
    # --resume: 尝试加载已有 checkpoint，跳过训练
    ckpt_file = run_dir / "best_model.pt"
    if getattr(args, 'resume', False) and ckpt_file.exists():
        print(f"[RESUME] 尝试加载 checkpoint: {ckpt_file}")
        try:
            checkpoint = torch.load(ckpt_file, weights_only=False, map_location=device)
            # 兼容不同 checkpoint 格式
            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])
            elif isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
                model.load_state_dict(checkpoint['state_dict'])
            else:
                model.load_state_dict(checkpoint)
            train_time = 0.0
            print(f"[RESUME] 成功加载 checkpoint，跳过训练")
        except (RuntimeError, KeyError) as e:
            print(f"[RESUME] 加载失败（可能架构不匹配）: {e}")
            print(f"[RESUME] 回退到正常训练")
            t0 = time.time()
            model = train_model(model, loaders["train"], loaders["val"], cfg, device)
            train_time = time.time() - t0
    else:
        t0 = time.time()
        model = train_model(model, loaders["train"], loaders["val"], cfg, device)
        train_time = time.time() - t0

    # ID 评估（test 集）
    test_eval = evaluate(model, loaders["test"], device, compute_calibration=True)
    cal_eval = evaluate(model, loaders["cal"], device, compute_calibration=False)

    # TS 校准（在 cal 拟合，test 报告）
    one_hot_cal = np.eye(num_classes)[cal_eval["labels"]]
    T = fit_temperature(cal_eval["probs"], one_hot_cal)
    probs_ts = apply_temperature(test_eval["probs"], T)
    max_probs_raw = test_eval["probs"].max(axis=1)
    max_probs_ts = probs_ts.max(axis=1)
    correct_mask = (test_eval["probs"].argmax(axis=1) == test_eval["labels"]).astype(float)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins
    ts_metrics = compute_all_metrics(max_probs_ts, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins

    # R3 修复4 [P0-严重]：info dict 使用 arch_display（含 OOM 备选 ResNet1D 标识，
    # arch_display 已在函数开头定义），并增加 arch_override/depth/width 字段，
    # 避免 CSV arch 列失真。
    info = {
        "dataset": dataset, "seed": seed, "arch": arch_display,
        "arch_override": arch_override,
        "depth": depth, "width": width,
        "n_params": n_params, "n_filters": n_filters,
        "use_checkpoint": use_checkpoint,
        "train_time_sec": train_time,
        "fitted_T": float(T),
        "id_acc_raw": float(test_eval["acc"]),
        "id_ece_raw": float(raw_metrics.get("ece", float("nan"))),
        "id_ece_ts": float(ts_metrics.get("ece", float("nan"))),
        "id_brier_raw": float(raw_metrics.get("brier_raw", float("nan"))),
        "id_brier_ts": float(ts_metrics.get("brier_raw", float("nan"))),
        "n_test": int(len(test_eval["labels"])),
    }
    print(f"[结果] acc={info['id_acc_raw']:.2f}% ECE(raw)={info['id_ece_raw']:.4f} "
          f"ECE(TS)={info['id_ece_ts']:.4f} Brier(raw)={info['id_brier_raw']:.4f} "
          f"Brier(TS)={info['id_brier_ts']:.4f} T={T:.3f} time={train_time:.0f}s")

    # 保存 checkpoint 路径供迁移评估复用
    ckpt_path = run_dir / "best_model.pt"
    info["ckpt_path"] = str(ckpt_path)
    info["model"] = model  # 内存中保留供迁移评估（避免重载）
    info["loaders"] = loaders
    info["cal_eval"] = cal_eval
    info["test_eval"] = test_eval
    info["clusters_test"] = clusters_test
    return model, info


# ===========================================================================
# 从 checkpoint 加载已训练模型（--transfer-only 模式）
# ===========================================================================
def load_and_evaluate_single(
    dataset: str,
    seed: int,
    args: argparse.Namespace,
    device: torch.device,
    n_filters: int = 48,
    use_checkpoint: bool = False,
) -> Tuple[Optional[nn.Module], dict]:
    """从 checkpoint 加载已训练模型并重新评估 cal/test 集（--transfer-only 模式）。

    跳过训练，直接加载 best_model.pt，重新运行 cal/test 评估以获取：
    - cal_eval（迁移评估 TS 校准所需的 cal 集概率/标签）
    - test_eval（ID 评估指标，补全训练结果表）
    返回与 train_single 兼容的 info dict，使 Phase 2 迁移评估无缝复用。
    """
    set_seed(seed)
    num_classes = DATASET_NUM_CLASSES[dataset]
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    print(f"\n{'='*60}")
    print(f"[加载] {dataset} seed={seed} arch={ARCH_NAME} n_filters={n_filters}")
    print(f"{'='*60}")

    # checkpoint 路径（与 train_single 的 run_dir 一致）
    run_dir = Path(args.save_dir) / dataset / ARCH_NAME / f"seed{seed}"
    ckpt_path = run_dir / "best_model.pt"
    if not ckpt_path.exists():
        print(f"[SKIP] checkpoint 不存在: {ckpt_path}")
        return None, {"error": f"checkpoint not found: {ckpt_path}", "skipped": True}

    # 构建数据
    try:
        ds, clusters_test = build_dataset(dataset, seed, limit=args.limit, subspace=subspace)
    except FileNotFoundError as e:
        print(f"[SKIP] 数据集 {dataset} 不存在: {e}")
        return None, {"error": str(e), "skipped": True}

    loaders = {
        k: create_dataloader(ds[k], args.batch_size, shuffle=(k == "train"),
                             drop_last=(k == "train"), num_workers=args.num_workers)
        for k in ("train", "val", "cal", "test")
    }

    # 构建模型并加载 checkpoint
    model = build_model(
        num_classes=num_classes, n_filters=n_filters,
        use_checkpoint=use_checkpoint, d_model=args.d_model, dropout=0.1,
    ).to(device)

    checkpoint = torch.load(ckpt_path, weights_only=False, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    print(f"[加载完成] {ckpt_path} (epoch={checkpoint.get('epoch', '?')}, "
          f"val_acc={checkpoint.get('val_acc', '?')})")

    n_params = sum(p.numel() for p in model.parameters())

    # ID 评估（test 集）+ cal 集评估（迁移 TS 校准所需）
    test_eval = evaluate(model, loaders["test"], device, compute_calibration=True)
    cal_eval = evaluate(model, loaders["cal"], device, compute_calibration=False)

    # TS 校准（在 cal 拟合，test 报告）
    one_hot_cal = np.eye(num_classes)[cal_eval["labels"]]
    T = fit_temperature(cal_eval["probs"], one_hot_cal)
    probs_ts = apply_temperature(test_eval["probs"], T)
    max_probs_raw = test_eval["probs"].max(axis=1)
    max_probs_ts = probs_ts.max(axis=1)
    correct_mask = (test_eval["probs"].argmax(axis=1) == test_eval["labels"]).astype(float)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins
    ts_metrics = compute_all_metrics(max_probs_ts, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins

    info = {
        "dataset": dataset, "seed": seed, "arch": ARCH_NAME,
        "arch_override": None, "depth": None, "width": None,
        "n_params": n_params, "n_filters": n_filters,
        "use_checkpoint": use_checkpoint,
        "train_time_sec": 0.0,  # 从 checkpoint 加载，未训练
        "fitted_T": float(T),
        "id_acc_raw": float(test_eval["acc"]),
        "id_ece_raw": float(raw_metrics.get("ece", float("nan"))),
        "id_ece_ts": float(ts_metrics.get("ece", float("nan"))),
        "id_brier_raw": float(raw_metrics.get("brier_raw", float("nan"))),
        "id_brier_ts": float(ts_metrics.get("brier_raw", float("nan"))),
        "n_test": int(len(test_eval["labels"])),
    }
    print(f"[结果] acc={info['id_acc_raw']:.2f}% ECE(raw)={info['id_ece_raw']:.4f} "
          f"ECE(TS)={info['id_ece_ts']:.4f} T={T:.3f} (从 checkpoint 加载)")

    info["ckpt_path"] = str(ckpt_path)
    info["model"] = model
    info["loaders"] = loaders
    info["cal_eval"] = cal_eval
    info["test_eval"] = test_eval
    info["clusters_test"] = clusters_test
    return model, info


# ===========================================================================
# 迁移评估（1 方向 × 1 种子）
# ===========================================================================
def eval_transfer_pair(
    source: str,
    target: str,
    seed: int,
    source_info: dict,
    args: argparse.Namespace,
    device: torch.device,
) -> dict:
    """S1 跨库迁移评估：源模型 → 目标 test，TS 校准 + Brier reliability 改善"""
    model = source_info["model"]
    cal_eval = source_info["cal_eval"]
    cal_probs = cal_eval["probs"]
    cal_labels = cal_eval["labels"]

    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    print(f"\n[迁移] {source}→{target} seed={seed}")
    try:
        tgt_ds, tgt_clusters = build_dataset(target, seed, limit=args.limit, subspace=subspace)
    except FileNotFoundError as e:
        print(f"[SKIP] 目标数据集 {target} 不存在: {e}")
        # R4 修复 Attack-1/6: 统一 schema + 补 arch 字段（原 dict 仅 5 字段，缺 arch）
        # R5 修复 Attack-1: 补传 num_classes/subspace_filtered，使 early-return dict
        # 与正常 result dict 语义一致（num_classes 按源/目标最小类数计算，
        # subspace_filtered 反映是否触发 5→4 子空间过滤），不再仅靠默认值占位。
        _fnf_num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
        return _make_transfer_result(
            source=source, target=target, seed=seed,
            arch=source_info.get("arch", ARCH_NAME),
            num_classes=_fnf_num_classes,
            subspace_filtered=bool(_fnf_num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
            error=str(e), skipped=True,
        )

    tgt_loader = create_dataloader(tgt_ds["test"], args.batch_size, shuffle=False,
                                   num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)
    ood_probs = tgt_eval["probs"]
    ood_labels = tgt_eval["labels"]

    # P0-7 修复：5-class source → 4-class target 时，cal_labels/ood_labels 可能
    # 含 >= num_classes 的标签，导致 np.eye(num_classes)[cal_labels] IndexError。
    # 截断超出 num_classes 的标签和概率列，确保 probs 与 labels 对齐。
    n_dropped_cal = int((cal_labels >= num_classes).sum())
    n_dropped_ood = int((ood_labels >= num_classes).sum())
    if n_dropped_cal > 0 or n_dropped_ood > 0:
        print(f"[WARN] {source}→{target} seed={seed}: 丢弃 "
              f"{n_dropped_cal} 个 cal + {n_dropped_ood} 个 ood 样本 "
              f"(标签 >= num_classes={num_classes})")
    cal_keep = cal_labels < num_classes
    ood_keep = ood_labels < num_classes
    cal_labels = cal_labels[cal_keep]
    cal_probs = cal_probs[cal_keep][:, :num_classes]
    ood_labels = ood_labels[ood_keep]
    ood_probs = ood_probs[ood_keep][:, :num_classes]
    # R3 修复1 [P0-致命]：同步截断 tgt_clusters，否则 benefit_inference 的
    # cluster bootstrap 会因 tgt_clusters 长度 != ood_probs 行数而 IndexError。
    tgt_clusters = tgt_clusters[ood_keep]
    # 截断后重新归一化概率（被丢弃类别的概率质量已移除）
    # S1 修复：若某行截断后全零，直接归一化会产生 NaN（0/0）。
    # 检测全零行并丢弃，避免 NaN 污染后续 TS 拟合与 metrics 计算。
    cal_row_sums = cal_probs.sum(axis=1, keepdims=True)
    cal_zero_rows = (cal_row_sums.flatten() == 0)
    if cal_zero_rows.any():
        print(f"[WARN] {source}→{target} seed={seed}: {cal_zero_rows.sum()} 个 cal 样本截断后全零，丢弃")
        # R3 修复5 [P0-中等]：累计全零行数到 n_dropped_cal，保持日志与统计字段一致。
        n_dropped_cal += int(cal_zero_rows.sum())
        cal_probs = cal_probs[~cal_zero_rows]
        cal_labels = cal_labels[~cal_zero_rows]
        cal_row_sums = cal_probs.sum(axis=1, keepdims=True)
    cal_probs = cal_probs / cal_row_sums

    ood_row_sums = ood_probs.sum(axis=1, keepdims=True)
    ood_zero_rows = (ood_row_sums.flatten() == 0)
    if ood_zero_rows.any():
        print(f"[WARN] {source}→{target} seed={seed}: {ood_zero_rows.sum()} 个 ood 样本截断后全零，丢弃")
        # R3 修复5 [P0-中等]：累计全零行数到 n_dropped_ood，与 cal 侧对称，
        # 确保 result dict 的 truncated 字段准确反映所有丢弃来源。
        n_dropped_ood += int(ood_zero_rows.sum())
        ood_probs = ood_probs[~ood_zero_rows]
        ood_labels = ood_labels[~ood_zero_rows]
        # R3 修复1 [P0-致命]：同步丢弃全零行对应的 tgt_clusters，保持长度对齐。
        tgt_clusters = tgt_clusters[~ood_zero_rows]
        ood_row_sums = ood_probs.sum(axis=1, keepdims=True)
    ood_probs = ood_probs / ood_row_sums

    # R3 修复2 [P0-严重]：截断+全零行丢弃后 cal/ood 可能为空数组，
    # 若不提前返回，fit_temperature 会返回 nan 并静默传播到后续 metrics。
    if len(cal_probs) == 0:
        print(f"[WARN] {source}→{target} seed={seed}: cal 集截断后为空，跳过 TS 校准")
        # R4 修复 Attack-1/2/4: 统一 schema + arch 用 source_info + 补截断统计字段
        # R5 修复 Attack-9: 补传 n_ood，使 early-return dict 与正常 result dict
        # schema 完全一致。R6 修复 Attack-4/5: n_ood 应反映实际 ood 样本数
        # （cal 空不代表 ood 空，cal/ood 独立截断，ood_probs 此时可能非空）。
        return _make_transfer_result(
            source=source, target=target, seed=seed,
            arch=source_info.get("arch", ARCH_NAME),
            num_classes=num_classes,
            n_ood=int(len(ood_probs)),
            n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
            truncated=True,
            subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
            error="cal set empty after truncation", skipped=True,
        )
    if len(ood_probs) == 0:
        print(f"[WARN] {source}→{target} seed={seed}: ood 集截断后为空，跳过迁移评估")
        # R4 修复 Attack-1/2/4: 统一 schema + arch 用 source_info + 补截断统计字段
        # R6 修复 Attack-4/5: n_ood 应反映实际 ood 样本数（与 cal 空路径 L716 对称，
        # 显式传 n_ood=int(len(ood_probs)) 而非依赖函数默认值 0，避免默认值掩盖
        # 实际样本数导致的静默错误）。
        return _make_transfer_result(
            source=source, target=target, seed=seed,
            arch=source_info.get("arch", ARCH_NAME),
            num_classes=num_classes,
            n_ood=int(len(ood_probs)),
            n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
            truncated=True,
            subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
            error="ood set empty after truncation", skipped=True,
        )

    # TS 校准（源 cal 拟合 → 目标 test 应用，S1 零样本迁移）
    one_hot_cal = np.eye(num_classes)[cal_labels]
    T = fit_temperature(cal_probs, one_hot_cal)
    ood_probs_ts = apply_temperature(ood_probs, T)

    max_probs_raw = ood_probs.max(axis=1)
    max_probs_ts = ood_probs_ts.max(axis=1)
    correct_mask = (ood_probs.argmax(axis=1) == ood_labels).astype(float)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins
    ts_metrics = compute_all_metrics(max_probs_ts, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins

    # Brier reliability 改善（主终点：TS 后 Brier 分解的 reliability 项改善）
    # Brier = uncertainty - resolution + reliability（Murphy 分解）
    # reliability 改善 = reliability_raw - reliability_ts（正值=校准有效）
    brier_raw = raw_metrics.get("brier_raw", float("nan"))
    brier_ts = ts_metrics.get("brier_raw", float("nan"))
    ece_raw = raw_metrics.get("ece", float("nan"))
    ece_ts = ts_metrics.get("ece", float("nan"))

    # benefit_inference 配对 bootstrap（ΔECE 的 CI）
    rng = np.random.default_rng(seed)
    try:
        benefit = benefit_inference(
            max_probs_raw, max_probs_ts, correct_mask,
            metric=smooth_ece, n_bootstrap=min(args.bootstrap, 2000),
            rng=rng, clusters=tgt_clusters,
        )
        delta_ece = float(benefit["benefit"])
        delta_ece_ci = [float(benefit["benefit_ci"][0]), float(benefit["benefit_ci"][1])]
    except Exception as e:
        print(f"[WARN] benefit_inference 失败: {e}")
        delta_ece = float(ece_raw - ece_ts)
        delta_ece_ci = [float("nan"), float("nan")]

    # R4 修复 Attack-1/2: 统一 schema + arch 用 source_info.get("arch", ARCH_NAME)
    # 替换硬编码 ARCH_NAME，确保迁移 CSV 中 arch 列反映源模型实际架构
    # （含 OOM 备选 ResNet1D 标识）而非全局常量。
    result = _make_transfer_result(
        source=source, target=target, seed=seed,
        arch=source_info.get("arch", ARCH_NAME),
        num_classes=num_classes,
        n_ood=int(len(ood_probs)),
        ood_acc_raw=float((ood_probs.argmax(1) == ood_labels).mean() * 100),
        fitted_T=float(T),
        ood_ece_raw=float(ece_raw),
        ood_ece_ts=float(ece_ts),
        ood_brier_raw=float(brier_raw),
        ood_brier_ts=float(brier_ts),
        delta_ece=delta_ece,
        delta_ece_ci_low=delta_ece_ci[0],
        delta_ece_ci_high=delta_ece_ci[1],
        brier_reliability_improvement=float(brier_raw - brier_ts),
        # R3 修复3 [P0-严重]：截断统计字段，供下游分析追踪子空间过滤与样本丢弃。
        n_dropped_cal=int(n_dropped_cal),
        n_dropped_ood=int(n_dropped_ood),
        truncated=bool((n_dropped_cal + n_dropped_ood) > 0),
        subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    )
    print(f"[迁移结果] {source}→{target} s{seed}: "
          f"acc={result['ood_acc_raw']:.2f}% "
          f"ECE(raw)={ece_raw:.4f}→ECE(TS)={ece_ts:.4f} "
          f"ΔECE={delta_ece:+.4f} "
          f"Brier(raw)={brier_raw:.4f}→Brier(TS)={brier_ts:.4f} "
          f"T={T:.3f}")
    return result


# ===========================================================================
# CSV 输出
# ===========================================================================
def write_csv(
    train_results: List[dict],
    transfer_results: List[dict],
    output_path: Path,
    oom_summary: Optional[dict] = None,
    arch_display: str = ARCH_NAME,
) -> None:
    """写入 E5 实验结果 CSV（含元信息头注释）"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        # 头注释
        # R5 修复 Attack-4: CSV 头注释使用动态 arch_display，反映实际架构
        # （含 OOM 备选 ResNet1D 标识），而非硬编码 ARCH_NAME 常量。
        f.write(f"# E5 {arch_display} 实验（3 blocks, ~310K 参数）\n")
        f.write(f"# 架构: {arch_display} (3 Inception modules, n_filters=48, bottleneck=48)\n")
        f.write(f"# 训练实验数: {len(train_results)} (3 语料库 × 5 种子 = 15)\n")
        f.write(f"# 迁移实验数: {len(transfer_results)} (6 方向 × 5 种子 = 30)\n")
        f.write(f"# 种子: {SEEDS}\n")
        f.write(f"# 语料库: {DATASETS}\n")
        f.write(f"# 迁移方向: {TRANSFER_DIRECTIONS}\n")
        if oom_summary:
            f.write(f"# OOM 备选触发: Level {oom_summary.get('max_level', 0)}\n")
            f.write(f"# OOM 降级实验数: {oom_summary.get('degraded_count', 0)}\n")
        f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # 训练结果表
        f.write("## 训练结果（15 模型）\n")
        if train_results:
            writer = csv.DictWriter(f, fieldnames=list(train_results[0].keys()))
            writer.writeheader()
            for r in train_results:
                # 过滤掉不可序列化的字段
                row = {k: v for k, v in r.items()
                       if k not in ("model", "loaders", "cal_eval", "test_eval", "clusters_test")}
                writer.writerow(row)
        f.write("\n")

        # 迁移结果表
        f.write("## 迁移评估结果（30 实验）\n")
        if transfer_results:
            # R4 修复 Attack-1: 使用统一 TRANSFER_RESULT_FIELDS 作为 fieldnames，
            # 并设置 extrasaction="ignore" 容忍任何意外多余字段，避免 ValueError。
            # 原代码 fieldnames=list(transfer_results[0].keys()) 在 early-return dict
            # （6字段）与 normal result dict（20字段）混合时，若首个为 early-return
            # 则 normal result 写入触发 ValueError: dict contains fields not in fieldnames。
            writer = csv.DictWriter(
                f, fieldnames=TRANSFER_RESULT_FIELDS, extrasaction="ignore",
            )
            writer.writeheader()
            for r in transfer_results:
                writer.writerow(r)

    print(f"\n[输出] CSV 已写入: {output_path}")


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="E5: InceptionTime-Lite 训练 + 跨库迁移评估")
    # 训练参数
    ap.add_argument("--epochs", type=int, default=50, help="训练 epoch 数")
    ap.add_argument("--batch-size", type=int, default=16, help="batch size")
    ap.add_argument("--lr", type=float, default=1e-3, help="学习率")
    ap.add_argument("--d-model", type=int, default=64, help="d_model")
    ap.add_argument("--patience", type=int, default=10, help="早停 patience")
    ap.add_argument("--bootstrap", type=int, default=10000, help="bootstrap B（默认 10000）")
    ap.add_argument("--num-workers", type=int, default=0, help="DataLoader workers")
    ap.add_argument("--save-dir", default="checkpoints/e5_inception_lite")
    ap.add_argument("--limit", type=int, default=None, help="冒烟截断")
    # OOM 备选
    ap.add_argument("--n-filters", type=int, default=48,
                    help="Inception n_filters（48=默认~310K, 32=OOM备选Level1~136K）")
    ap.add_argument("--use-checkpoint", action="store_true",
                    help="启用 gradient checkpointing（OOM 备选 Level 2）")
    # 实验范围
    ap.add_argument("--no-transfer", action="store_true", help="仅训练不迁移")
    ap.add_argument("--transfer-only", action="store_true",
                    help="跳过训练，从 checkpoint 加载已有模型仅做迁移评估（复用 best_model.pt）")
    ap.add_argument("--seeds", nargs="+", type=int, default=SEEDS, help="种子列表")
    ap.add_argument("--datasets", nargs="+", default=DATASETS, help="语料库列表")
    # 冒烟
    ap.add_argument("--smoke", action="store_true", help="冒烟测试（合成数据，2 epoch，1 种子）")
    # 断点续传
    ap.add_argument("--resume", action="store_true",
                    help="从已有 checkpoint 恢复，跳过训练直接进入迁移评估")
    args = ap.parse_args()

    if args.smoke:
        # 冒烟模式：只设置训练超参，seeds/datasets 保留命令行值（默认全部）
        # 用户想要快速冒烟可显式传 --seeds 42 --datasets ptbxl
        args.epochs = 2
        args.limit = 240 if args.limit is None else args.limit
        args.bootstrap = 200
        print(f"[冒烟模式] epochs=2, limit={args.limit}, bootstrap=200, "
              f"seeds={args.seeds}, datasets={args.datasets}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'#'*60}")
    print(f"# E5: InceptionTime-Lite 训练 + 跨库迁移评估")
    print(f"# 架构: {ARCH_NAME} (3 blocks, n_filters={args.n_filters}, "
          f"checkpoint={args.use_checkpoint})")
    print(f"# 设备: {device}")
    print(f"# 种子: {args.seeds}")
    print(f"# 语料库: {args.datasets}")
    print(f"# 迁移方向: {TRANSFER_DIRECTIONS}")
    print(f"# 输出: {OUTPUT_CSV}")
    print(f"{'#'*60}\n")

    # 参数量审计（训练前）
    print("[参数量审计] InceptionTime-Lite (n_filters=48, 3 blocks, d_model=64):")
    audit_model = build_inceptiontime_lite(in_channels=12, d_model=64, n_filters=48)
    audit = audit_model.count_parameters()
    print(f"  Backbone 总参数: {audit['total']:,}")
    for blk in audit["blocks"]:
        print(f"    Block {blk['block']}: {blk['params']:,}")
    print(f"  proj: {audit['proj']:,}, norm: {audit['norm']:,}")
    full_model = ECGClassifier(
        in_channels=12, d_model=64, n_layers=3, num_classes=5,
        backbone_type="inceptiontime_lite",
    )
    full_params = sum(p.numel() for p in full_model.parameters())
    print(f"  全模型（含 head）: {full_params:,}")
    assert 200_000 <= full_params <= 500_000, \
        f"参数量 {full_params:,} 不在目标 200K-500K 内！"
    print(f"  ✓ 参数量 {full_params:,} ∈ [200K, 500K] 目标区间\n")

    # ============ Phase 1: 训练 15 模型 ============
    print("=" * 60)
    if args.transfer_only:
        print("Phase 1: 从 checkpoint 加载 15 模型（跳过训练，--transfer-only 模式）")
    else:
        print("Phase 1: 训练 15 模型（3 语料库 × 5 种子）")
    print("=" * 60)

    train_results: List[dict] = []
    trained_models: Dict[Tuple[str, int], dict] = {}  # (dataset, seed) -> info
    oom_log = {"max_level": 0, "degraded_count": 0}

    if args.transfer_only:
        # --transfer-only 模式：从 checkpoint 加载已有模型，跳过训练
        for dataset in args.datasets:
            for seed in args.seeds:
                try:
                    model, info = load_and_evaluate_single(
                        dataset, seed, args, device,
                        n_filters=args.n_filters,
                        use_checkpoint=args.use_checkpoint,
                    )
                    if model is not None:
                        train_results.append(info)
                        trained_models[(dataset, seed)] = info
                except Exception as e:
                    print(f"[ERROR] 加载 {dataset} seed={seed} 失败: {e}")
                    traceback.print_exc()
    else:
        for dataset in args.datasets:
            for seed in args.seeds:
                try:
                    # P0-6 修复：通过 try_train_with_oom_fallback 激活 4 级 OOM 备选链
                    # （原代码直接调用 train_single，导致 OOM 备选链成为死代码）
                    # 适配 train_single(dataset, seed, args, dev, ...) 到 (params, dev) 接口
                    def _train_adapter(params, dev, _ds=dataset, _seed=seed):
                        # F1 修复：传递 arch/depth/width 给 train_single，
                        # 使 Level 3 ResNet1D 变体能真正构造不同 backbone
                        # （原闭包只提取 n_filters/use_checkpoint，arch/depth/width 被丢弃）
                        return train_single(
                            _ds, _seed, args, dev,
                            n_filters=params.get("n_filters", 48),
                            use_checkpoint=params.get("use_checkpoint", False),
                            arch_override=params.get("arch"),
                            depth=params.get("depth"),
                            width=params.get("width"),
                        )
                    model, info = try_train_with_oom_fallback(
                        _train_adapter, {}, device,
                        n_filters=args.n_filters, use_checkpoint=args.use_checkpoint,
                    )
                    if model is not None:
                        train_results.append(info)
                        trained_models[(dataset, seed)] = info
                    else:
                        oom_log["degraded_count"] += 1
                        oom_lvl = info.get("oom_log", {}).get("level", 4)
                        oom_log["max_level"] = max(oom_log["max_level"], oom_lvl)
                except RuntimeError as e:
                    if is_oom_error(e):
                        print(f"[OOM] {dataset} seed={seed} 训练 OOM: {e}")
                        torch.cuda.empty_cache() if torch.cuda.is_available() else None
                        oom_log["degraded_count"] += 1
                        oom_log["max_level"] = max(oom_log["max_level"], 4)
                    else:
                        print(f"[ERROR] {dataset} seed={seed} 训练失败: {e}")
                        traceback.print_exc()
                except Exception as e:
                    print(f"[ERROR] {dataset} seed={seed} 训练失败: {e}")
                    traceback.print_exc()

    print(f"\n[Phase 1 完成] 成功训练 {len(train_results)}/{len(args.datasets)*len(args.seeds)} 模型")
    if oom_log["degraded_count"] > 0:
        print(f"[OOM] {oom_log['degraded_count']} 个模型因 OOM 降级")

    # ============ Phase 2: 迁移评估 30 实验 ============
    transfer_results: List[dict] = []
    if not args.no_transfer and len(trained_models) > 0:
        print("\n" + "=" * 60)
        print("Phase 2: 迁移评估 30 实验（6 方向 × 5 种子）")
        print("=" * 60)

        for source, target in TRANSFER_DIRECTIONS:
            if source not in args.datasets or target not in args.datasets:
                continue
            for seed in args.seeds:
                if (source, seed) not in trained_models:
                    print(f"[SKIP] {source}→{target} seed={seed}: 源模型未训练")
                    continue
                try:
                    result = eval_transfer_pair(
                        source, target, seed,
                        trained_models[(source, seed)],
                        args, device,
                    )
                    transfer_results.append(result)
                except Exception as e:
                    print(f"[ERROR] {source}→{target} seed={seed} 迁移失败: {e}")
                    traceback.print_exc()
                    # R4 修复 Attack-1/2/7: 统一 schema + arch 用源模型 info + 补 skipped 字段
                    # （原 dict 仅 5 字段，缺 skipped 及 16 个统计字段）
                    transfer_results.append(_make_transfer_result(
                        source=source, target=target, seed=seed,
                        arch=trained_models[(source, seed)].get("arch", ARCH_NAME),
                        error=str(e), skipped=True,
                    ))

        print(f"\n[Phase 2 完成] 成功评估 {len(transfer_results)}/"
              f"{len(TRANSFER_DIRECTIONS)*len(args.seeds)} 迁移实验")

    # ============ Phase 3: 写入 CSV ============
    print("\n" + "=" * 60)
    print("Phase 3: 写入 CSV")
    print("=" * 60)

    # 序列化训练结果（过滤不可序列化字段）
    serializable_train = []
    for r in train_results:
        row = {k: v for k, v in r.items()
               if k not in ("model", "loaders", "cal_eval", "test_eval", "clusters_test")}
        serializable_train.append(row)

    # R5 修复 Attack-4: 推断实际 arch_display 传入 write_csv。
    # OOM 备选可能将 arch 从 inceptiontime_lite 改为 resnet1d，CSV 头注释需反映实际架构。
    # 优先取首个训练结果的 arch 字段（train_single 中已用 arch_display 赋值），
    # 无训练结果时回退到 ARCH_NAME。
    _csv_arch_display = train_results[0].get("arch", ARCH_NAME) if train_results else ARCH_NAME
    write_csv(serializable_train, transfer_results, OUTPUT_CSV, oom_summary=oom_log,
              arch_display=_csv_arch_display)

    # ============ Phase 4: 汇总报告 ============
    print("\n" + "=" * 60)
    print("E5 实验汇总")
    print("=" * 60)
    print(f"架构: {ARCH_NAME}")
    print(f"训练模型数: {len(train_results)} / {len(args.datasets)*len(args.seeds)}")
    print(f"迁移评估数: {len(transfer_results)} / {len(TRANSFER_DIRECTIONS)*len(args.seeds)}")
    if train_results:
        accs = [r.get("id_acc_raw", 0) for r in train_results]
        eces = [r.get("id_ece_raw", 0) for r in train_results]
        print(f"ID acc 均值: {np.mean(accs):.2f}% (sd={np.std(accs):.2f})")
        print(f"ID ECE(raw) 均值: {np.mean(eces):.4f} (sd={np.std(eces):.4f})")
    if transfer_results:
        valid = [r for r in transfer_results if "delta_ece" in r and not np.isnan(r.get("delta_ece", float("nan")))]
        if valid:
            decays = [r["delta_ece"] for r in valid]
            print(f"迁移 ΔECE 均值: {np.mean(decays):+.4f} (sd={np.std(decays):.4f}, n={len(decays)})")
            brier_imps = [r.get("brier_reliability_improvement", 0) for r in valid]
            print(f"Brier reliability 改善均值: {np.mean(brier_imps):+.4f} (sd={np.std(brier_imps):.4f})")
    if oom_log["degraded_count"] > 0:
        print(f"\n[OOM 降级] {oom_log['degraded_count']} 个实验降级 (max Level {oom_log['max_level']})")
        if oom_log["max_level"] >= 4:
            print("[警告] 触发 Level 4 备选：需诚实报告'2 架构家族 + BiMamba toy'")

    print(f"\n输出: {OUTPUT_CSV}")
    print("E5 实验完成！")


if __name__ == "__main__":
    main()
