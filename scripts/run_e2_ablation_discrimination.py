"""E2: TS 组件消融 + 判别指标（60 实验全量）

=====================================================================
实验目标
=====================================================================
1. 3 阶段消融，分离温度缩放(TS)各组件对 Brier reliability 的贡献：
   Stage 1: TS only          — 单一全局温度 T，仅校准置信度锐度
   Stage 2: TS + binned T    — 按预测熵(不确定度)分 5 箱，每箱一个 T
   Stage 3: TS + binned + τ  — 在 binned 基础上优化分类阈值 τ_k

2. 判别指标(AUROC/AUPRC/F1/PPV/NPV/MCC)对 60 个实验全部计算。

=====================================================================
核心主张（正方论证）
=====================================================================
- 消融设计能分离各组件贡献，因为三阶段是严格嵌套的参数子集：
    Θ_1 = {T}                    ⊂ Θ_2 = {T, T_1..T_5}     ⊂ Θ_3 = {T, T_1..T_5, τ_1..τ_K}
  ΔReliability(Stage2−Stage1) = binned T 的边际贡献（控制全局 T 后）
  ΔReliability(Stage3−Stage2) = threshold opt 的边际贡献（控制 binned T 后）
  嵌套结构保证边际贡献可加性解释（无参数空间交叉）。

- TS 保持 argmax 不变（softmax(log p / T) 对 T>0 保序）：
    * accuracy / F1 / MCC 等 argmax 类指标在 Stage 1/2 与 raw 相同
    * AUROC/AUPRC 基于概率排序：二分类下 TS 是单调变换→严格不变；
      多分类 OvR 下 TS 不保证逐类保序→可能微变（脚本实测验证并报告）
    * Stage 3 的 threshold optimization 改变 argmax→F1/PPV/NPV/MCC 改变

=====================================================================
关键假设
=====================================================================
A1. binned temperature 的分箱变量=TS 校准后预测分布熵 H(TS(p))=−Σ p'_k log p'_k，
    其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 分箱变量
    为 H(p)（对原始概率分箱），两者不可直接比较，原因有二：
    (1) 分箱变量不同：E2 Stage2/3 为 H(TS(p))，E4 为 H(p)；
    (2) 结构不同：E2 Stage2/3 为 TS+binned（先全局 TS 再分箱温度），
        E4 为 binned-only（仅分箱温度，无前置全局 TS）。
    两者参数空间非嵌套亦非同构，故 ΔReliability 不可作边际贡献解释。
    假设：不确定度高的样本段需要不同的锐度校准（置信与不确定样本
    的 over/under-confidence 模式不同）。若该假设不成立，
    Stage2−Stage1 ≈ 0（脚本会如实报告）。
A2. threshold optimization 在 cal 集上拟合、test 集上评估。
    假设：cal 与 test 同分布（ID 假设）；OOD 下阈值迁移有衰减，
    脚本同时报告 cal 上最优 τ 在 test 上的表现（无偷看 test）。
A3. 每箱样本量 ≥ 10 才拟合该箱 T；否则该箱 T=1.0（不校准）。
    防止小箱过拟合（n_cal=60 的 smoke 场景下部分箱可能不足）。

=====================================================================
适用边界
=====================================================================
- 消融结论适用于本 60 实验的 (source, target, arch, seed) 组合，
  外推到新数据集需重新验证 A1（熵分箱的有效性）。
- threshold optimization 的收益上界受 cal 集大小限制：
  n_cal 小时 τ 估计方差大，Stage3−Stage2 可能含噪声。
- 多分类 AUROC "TS 不变" 是近似而非精确——脚本实测 |ΔAUROC| 并报告。

=====================================================================
输出
=====================================================================
1. results/ablation_ts_components.csv
   列: source, target, arch, seed, stage, brier_reliability, brier_resolution,
       brier_uncertainty, brier_raw, ece, smooth_ece, n_samples, T_global,
       T_binned(mean,min,max), threshold_norm
2. results/discrimination_metrics_60exp.csv
   列: source, target, arch, seed, split(cal/test), variant(raw/ts/binned/threshold),
       auroc, auprc, f1, ppv, npv, mcc, auroc_ts_minus_raw(诚实校验列)

调用:
    python scripts/run_e2_ablation_discrimination.py
    python scripts/run_e2_ablation_discrimination.py --limit 240  # 冒烟
    python scripts/run_e2_ablation_discrimination.py --pairs ptbxl_chapman  # 单对
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    roc_auc_score,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.utils.calibration import brier_parts, brier_raw, ece, smooth_ece, _validate_n_bins  # noqa: E402
from src.utils.calibration_methods import (  # noqa: E402
    apply_temperature_multiclass,
    fit_temperature_multiclass,
)
from train import (  # noqa: E402
    build_chapman_datasets,
    build_cpsc_datasets,
    build_ptbxl_datasets,
    create_dataloader,
    evaluate,
    set_seed,
)
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402
from src.utils.encoding_guard import (  # noqa: E402
    CACHE_STAMP_KEY,
    assert_cache_encoding,
    checkpoint_subspace,
    encoding_stamp,
)

# =====================================================================
# 配置
# =====================================================================

DATA_DIRS = {
    "ptbxl": str(_PROJECT_ROOT / "data" / "ptbxl_processed"),
    "chapman": str(_PROJECT_ROOT / "data" / "chapman_processed_v2"),
    "cpsc": str(_PROJECT_ROOT / "data" / "cpsc_processed"),
}

DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}

CKPT_ROOT = _PROJECT_ROOT / "checkpoints" / "transfer"
RESULTS_DIR = _PROJECT_ROOT / "results"
CACHE_DIR = _PROJECT_ROOT / "checkpoints" / "e2_probs_cache"

N_BINS_TEMPERATURE = 5      # binned temperature 箱数
MIN_SAMPLES_PER_BIN = 10    # 每箱最少样本数，不足则 T=1.0
N_BINS = 10                 # Brier reliability / ECE 评估分箱数（与 E3/E4/E6 及库默认一致）
EPS = 1e-12


# =====================================================================
# 1. Binned temperature（Stage 2 组件）
# =====================================================================

def _entropy(probs: np.ndarray) -> np.ndarray:
    """预测分布熵 H(p) = -Σ p_k log p_k（不确定度度量）"""
    p = np.clip(probs, EPS, 1.0)
    return -np.sum(p * np.log(p), axis=1)


def fit_binned_temperature(
    cal_probs: np.ndarray,
    cal_labels: np.ndarray,
    n_bins: int = N_BINS_TEMPERATURE,
) -> dict:
    """按预测熵分 n_bins 箱，每箱拟合一个温度 T

    分箱=等频分箱（quantile），保证每箱样本量均衡。
    每箱内用 fit_temperature_multiclass 拟合（多分类 NLL 最小化）。
    样本不足的箱 T=1.0（不校准，假设 A3）。

    Returns:
        {'temperatures': [T_0..T_{n_bins-1}],
         'bin_edges': entropy 分箱边界 (n_bins+1,)}
    """
    n_bins = _validate_n_bins(n_bins)  # R7-ATK-1：公共守卫，拦截 bool 穿透 + OOM
    ent = _entropy(cal_probs)
    bin_edges = np.quantile(ent, np.linspace(0, 1, n_bins + 1))
    bin_edges[0] = -np.inf       # 左端开放
    bin_edges[-1] = np.inf       # 右端闭
    bin_idx = np.digitize(ent, bin_edges[1:-1])  # 0..n_bins-1

    temperatures = []
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() < MIN_SAMPLES_PER_BIN:
            temperatures.append(1.0)
            continue
        try:
            params = fit_temperature_multiclass(cal_probs[mask], cal_labels[mask])
            temperatures.append(float(params["T"]))
        except Exception:
            temperatures.append(1.0)
    return {"temperatures": temperatures, "bin_edges": bin_edges.tolist()}


def apply_binned_temperature(probs: np.ndarray, params: dict) -> np.ndarray:
    """按样本熵分箱，用对应箱的 T 做温度缩放"""
    ent = _entropy(probs)
    bin_edges = np.asarray(params["bin_edges"])
    bin_idx = np.digitize(ent, bin_edges[1:-1])
    out = np.zeros_like(probs, dtype=float)
    for b, T in enumerate(params["temperatures"]):
        mask = bin_idx == b
        if not mask.any():
            continue
        out[mask] = apply_temperature_multiclass(
            probs[mask], {"T": float(T)}
        )
    return out


# =====================================================================
# 2. Threshold optimization（Stage 3 组件）
# =====================================================================

def predict_with_thresholds(probs: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """阈值调整后预测: argmax(p_k - τ_k)

    τ=0 退化为标准 argmax。τ_k 大→类 k 更难被预测（需更高 p_k）。
    """
    return (probs - thresholds[None, :]).argmax(axis=1)


def optimize_thresholds(
    cal_probs: np.ndarray,
    cal_labels: np.ndarray,
    n_classes: int,
) -> np.ndarray:
    """在 cal 集上优化阈值 τ 最大化 macro-F1

    用坐标下降+网格搜索（每类在 [-0.3, 0.3] 上 61 个点）。
    目标=macro-F1（对类别不平衡更稳健 than accuracy）。
    返回最优 τ (n_classes,)。
    """
    from scipy.optimize import minimize

    def neg_macro_f1(tau):
        preds = predict_with_thresholds(cal_probs, tau)
        return -f1_score(cal_labels, preds, average="macro", zero_division=0)

    res = minimize(
        neg_macro_f1,
        x0=np.zeros(n_classes),
        method="Nelder-Mead",
        options={"maxiter": 2000, "xatol": 1e-3, "fatol": 1e-5},
    )
    return np.clip(res.x, -0.5, 0.5)


# =====================================================================
# 3. 判别指标
# =====================================================================

def _npv(y_true, y_pred, n_classes):
    """NPV = TN/(TN+FN)，macro 平均"""
    cm = confusion_matrix(y_true, y_pred, labels=list(range(n_classes)))
    npvs = []
    for k in range(n_classes):
        tp = cm[k, k]
        fn = cm[:, k].sum() - tp
        fp = cm[k, :].sum() - tp
        tn = cm.sum() - tp - fn - fp
        denom = tn + fn
        npvs.append(tn / denom if denom > 0 else 0.0)
    return float(np.mean(npvs))


def compute_discrimination_metrics(
    probs: np.ndarray,
    labels: np.ndarray,
    thresholds: Optional[np.ndarray] = None,
) -> dict:
    """计算 AUROC/AUPRC/F1/PPV/NPV/MCC

    AUROC/AUPRC 基于概率（OvR），不受 argmax/threshold 影响。
    F1/PPV/NPV/MCC 基于 argmax(p - τ)；thresholds=None 时 τ=0（标准 argmax）。
    """
    n_classes = probs.shape[1]
    labels = np.asarray(labels, dtype=int)

    # --- AUROC / AUPRC（基于概率排序，OvR macro）---
    onehot = np.eye(n_classes)[labels]
    try:
        auroc = roc_auc_score(
            labels, probs, multi_class="ovr", average="macro"
        )
    except ValueError:
        auroc = float("nan")
    try:
        auprc = average_precision_score(onehot, probs, average="macro")
    except ValueError:
        auprc = float("nan")

    # --- argmax / threshold 类指标 ---
    if thresholds is None:
        preds = probs.argmax(axis=1)
    else:
        preds = predict_with_thresholds(probs, thresholds)

    f1 = f1_score(labels, preds, average="macro", zero_division=0)
    ppv = precision_score(labels, preds, average="macro", zero_division=0)
    npv = _npv(labels, preds, n_classes)
    try:
        mcc = matthews_corrcoef(labels, preds)
    except ValueError:
        mcc = 0.0

    return {
        "auroc": float(auroc),
        "auprc": float(auprc),
        "f1": float(f1),
        "ppv": float(ppv),
        "npv": float(npv),
        "mcc": float(mcc),
    }


# =====================================================================
# 4. Brier reliability（消融主量）
# =====================================================================

def calibration_reliability(probs: np.ndarray, labels: np.ndarray) -> dict:
    """Brier reliability + ECE + SmoothECE

    对多分类 top-label 场景：max_prob vs correct_mask 二值化
    （与 eval_transfer.py 主终点语义一致）。
    """
    max_prob = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    # 正方修补(P0-3): 显式传 n_bins=N_BINS，使 Brier reliability 分箱粒度可控
    b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)
    return {
        "brier_reliability": float(rel),
        "brier_resolution": float(res),
        "brier_uncertainty": float(unc),
        "brier_raw": float(brier_raw(max_prob, correct)),
        "ece": float(ece(max_prob, correct, n_bins=N_BINS)),
        "smooth_ece": float(smooth_ece(max_prob, correct)),
    }


# =====================================================================
# 5. 模型加载 + 前向推理（复用 eval_transfer 逻辑）
# =====================================================================

def _infer_arch_params(arch: str, sd: dict, args):
    """从 state_dict 推断 d_model / n_layers（复用 eval_transfer.py 逻辑）"""
    if arch == "mamba":
        inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
        import re
        layer_ids = {
            re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
            for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)
        }
        inferred_n_layers = len(layer_ids)
    elif "backbone.proj.weight" in sd:
        inferred_d_model = sd["backbone.proj.weight"].shape[0]
        inferred_n_layers = args.n_layers
    else:
        inferred_d_model = args.d_model
        inferred_n_layers = args.n_layers
    return inferred_d_model, inferred_n_layers


def _build(dataset: str, data_dir: str, seed: int, limit, subspace=None):
    builder = DATASET_BUILDERS[dataset]
    if dataset == "cpsc":
        ds, clusters = builder(data_dir, seed, limit=limit)
    elif subspace is not None:
        ds, clusters = builder(data_dir, seed, limit=limit, subspace=subspace)
    else:
        ds, clusters = builder(data_dir, seed, limit=limit)
    return ds, clusters


def load_probs_for_checkpoint(
    source: str, target: str, arch: str, seed: int, args, device
) -> Optional[dict]:
    """加载 checkpoint，在 source-cal 和 target-test 上前向推理

    返回:
        {'cal_probs': (Ncal,K), 'cal_labels': (Ncal,),
         'test_probs': (Ntest,K), 'test_labels': (Ntest,),
         'num_classes': K}
    或 None（checkpoint 不存在/加载失败）
    """
    ckpt_path = CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}" / "best_model.pt"
    if not ckpt_path.exists():
        return None

    # ---------- 编码护栏（必须在读缓存之前） ----------
    # 缓存里存的是「某套编码下的标签」，所以要先确定该用哪套：
    # 以 checkpoint 自存的 subspace 为准，并与运行时 SUBSPACE_CPSC 断言一致。
    # 本脚本原先直接用运行时常量重建标签，导致 09-10 重跑的
    # checkpoints/e2_probs_cache/*.npz（全部 62 份，mtime 09-10 12:30~12:40）
    # 目标标签与 09-08 的 checkpoint 语义错位（MI↔CD 互换）。
    # 参见 results/_L2_SHIFT_CONTAMINATION_NOTICE.md。
    run_dir = ckpt_path.parent
    set_seed(seed)
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    runtime_subspace = SUBSPACE_CPSC if num_classes == 4 else None
    subspace = checkpoint_subspace(run_dir, num_classes, runtime_subspace)
    encoding = encoding_stamp(num_classes, subspace)

    # 缓存路径（避免重复前向推理）
    cache_file = CACHE_DIR / f"{source}_{target}_{arch}_seed{seed}.npz"
    if args.use_cache and cache_file.exists():
        d = np.load(cache_file, allow_pickle=True)
        assert_cache_encoding(cache_file, d, num_classes, subspace,
                              allow_unstamped=args.allow_unstamped_cache)
        return {
            "cal_probs": d["cal_probs"], "cal_labels": d["cal_labels"],
            "test_probs": d["test_probs"], "test_labels": d["test_labels"],
            "num_classes": int(d["num_classes"]),
        }

    # 加载 checkpoint
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]
    ckpt_nc = ckpt.get("num_classes")
    if ckpt_nc is not None and ckpt_nc != num_classes:
        warnings.warn(f"{ckpt_path}: num_classes mismatch {ckpt_nc}≠{num_classes}, skip")
        return None

    d_model, n_layers = _infer_arch_params(arch, sd, args)
    model = ECGClassifier(
        in_channels=12, d_model=d_model, n_layers=n_layers,
        num_classes=num_classes, dropout=0.1, backbone_type=arch,
    ).to(device)
    try:
        model.load_state_dict(sd)
    except RuntimeError as e:
        warnings.warn(f"{ckpt_path}: load_state_dict failed: {e}")
        return None
    model.eval()

    # source-cal 前向
    src_ds, _ = _build(source, DATA_DIRS[source], seed, args.limit, subspace=subspace)
    cal_loader = create_dataloader(src_ds["cal"], args.batch_size, shuffle=False,
                                   num_workers=args.num_workers)
    cal_eval = evaluate(model, cal_loader, device, compute_calibration=False)

    # target-test 前向
    tgt_ds, _ = _build(target, DATA_DIRS[target], seed, args.limit, subspace=subspace)
    tgt_loader = create_dataloader(tgt_ds["test"], args.batch_size, shuffle=False,
                                   num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)

    result = {
        "cal_probs": cal_eval["probs"], "cal_labels": cal_eval["labels"],
        "test_probs": tgt_eval["probs"], "test_labels": tgt_eval["labels"],
        "num_classes": num_classes,
    }

    # 缓存
    if args.use_cache:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            cache_file,
            cal_probs=result["cal_probs"], cal_labels=result["cal_labels"],
            test_probs=result["test_probs"], test_labels=result["test_labels"],
            num_classes=num_classes,
            # 编码戳：无此戳的缓存一律被 assert_cache_encoding 拒绝
            **{CACHE_STAMP_KEY: encoding},
        )
    return result


# =====================================================================
# 6. 单实验：3 阶段消融 + 判别指标
# =====================================================================

def run_single_experiment(
    source: str, target: str, arch: str, seed: int, args
) -> Tuple[List[dict], List[dict]]:
    """对单个 (source, target, arch, seed) 运行 3 阶段消融 + 判别指标

    Returns:
        (ablation_rows, discrimination_rows)
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = load_probs_for_checkpoint(source, target, arch, seed, args, device)
    if data is None:
        print(f"  [SKIP] {source}_{target}/{arch}/seed{seed}: checkpoint unavailable")
        return [], []

    cal_p, cal_y = data["cal_probs"], data["cal_labels"]
    test_p, test_y = data["test_probs"], data["test_labels"]
    K = data["num_classes"]

    ablation_rows = []
    disc_rows = []

    # ===== Stage 1: TS only =====
    ts_params = fit_temperature_multiclass(cal_p, cal_y)
    T_global = float(ts_params["T"])
    cal_s1 = apply_temperature_multiclass(cal_p, ts_params)
    test_s1 = apply_temperature_multiclass(test_p, ts_params)

    # ===== Stage 2: TS + binned temperature =====
    # 正方修补(P0-3): 先做 TS（复用 Stage 1 的 ts_params 与 cal_s1/test_s1），
    # 再在 TS 校准后的概率上拟合并应用 binned-T。
    # 旧实现直接对 raw cal_p/test_p 做 binned-T（=binned only），导致
    # Stage 2 实际是 Θ={T_1..T_5} 而非 Θ={T_global, T_1..T_5 on TS output}，
    # 破坏了 Stage1 ⊂ Stage2 的嵌套关系，消融边际贡献不可解释。
    binned_params = fit_binned_temperature(cal_s1, cal_y)
    cal_s2 = apply_binned_temperature(cal_s1, binned_params)
    test_s2 = apply_binned_temperature(test_s1, binned_params)
    T_binned = binned_params["temperatures"]

    # ===== Stage 3: TS + binned + threshold optimization =====
    tau = optimize_thresholds(cal_s2, cal_y, K)
    # Stage3 概率=Stage2 概率（threshold 只改 argmax，不改概率）
    cal_s3, test_s3 = cal_s2, test_s2

    # ===== 消融 Brier reliability（test 集）=====
    for stage_name, probs in [
        ("raw", test_p),
        ("stage1_ts", test_s1),
        ("stage2_ts_binned", test_s2),
        ("stage3_ts_binned_threshold", test_s3),
    ]:
        rel = calibration_reliability(probs, test_y)
        row = {
            "source": source, "target": target, "arch": arch, "seed": seed,
            "stage": stage_name, "n_samples": len(test_y),
            "T_global": T_global if stage_name != "raw" else np.nan,
            "T_binned_mean": np.mean(T_binned) if "binned" in stage_name else np.nan,
            "T_binned_min": np.min(T_binned) if "binned" in stage_name else np.nan,
            "T_binned_max": np.max(T_binned) if "binned" in stage_name else np.nan,
            "threshold_norm": float(np.linalg.norm(tau)) if "threshold" in stage_name else 0.0,
        }
        row.update(rel)
        ablation_rows.append(row)

    # ===== 判别指标（60 实验全量）=====
    # variant: raw / ts / binned / threshold
    # AUROC/AUPRC 基于概率；F1/PPV/NPV/MCC 基于 argmax(p-τ)
    for split_name, probs, labels in [
        ("cal", cal_p, cal_y),
        ("test", test_p, test_y),
    ]:
        for variant, v_probs, v_tau in [
            ("raw", probs, None),
            ("ts", apply_temperature_multiclass(probs, ts_params), None),
            # 正方修补(P0-3): "binned" variant 须与 Stage 2 语义一致(TS+binned)，
            # "threshold" variant 须与 Stage 3 语义一致(TS+binned+τ)。
            # 旧实现直接 apply_binned_temperature(probs, ...) 是 binned only，
            # 与 ablation 表的 stage2_ts_binned 不一致。
            ("binned",
             apply_binned_temperature(
                 apply_temperature_multiclass(probs, ts_params), binned_params),
             None),
            ("threshold",
             apply_binned_temperature(
                 apply_temperature_multiclass(probs, ts_params), binned_params),
             tau),
        ]:
            m = compute_discrimination_metrics(v_probs, labels, thresholds=v_tau)
            row = {
                "source": source, "target": target, "arch": arch, "seed": seed,
                "split": split_name, "variant": variant,
            }
            row.update(m)
            disc_rows.append(row)

    # ===== 诚实校验：TS 对 AUROC 的影响 =====
    # 二分类: 严格不变(单调变换); 多分类 OvR: 可能微变
    raw_disc = compute_discrimination_metrics(test_p, test_y)
    ts_disc = compute_discrimination_metrics(test_s1, test_y)
    delta_auroc = ts_disc["auroc"] - raw_disc["auroc"]
    delta_auprc = ts_disc["auprc"] - raw_disc["auprc"]

    print(
        f"  [{source}_{target}/{arch}/s{seed}] "
        f"T={T_global:.3f} T_binned=[{np.mean(T_binned):.3f}±{np.std(T_binned):.3f}] "
        f"||τ||={np.linalg.norm(tau):.4f} | "
        f"Rel: raw={ablation_rows[0]['brier_reliability']:.4f} "
        f"s1={ablation_rows[1]['brier_reliability']:.4f} "
        f"s2={ablation_rows[2]['brier_reliability']:.4f} "
        f"s3={ablation_rows[3]['brier_reliability']:.4f} | "
        f"AUROC raw={raw_disc['auroc']:.4f} ts={ts_disc['auroc']:.4f} "
        f"Δ={delta_auroc:+.6f} (TS对AUROC影响, 多分类应≈0)"
    )

    # 把 ΔAUROC 校验列附加到 test/ts 行（供 CSV 审查）
    for r in disc_rows:
        if r["split"] == "test" and r["variant"] == "ts":
            r["auroc_ts_minus_raw"] = delta_auroc
            r["auprc_ts_minus_raw"] = delta_auprc
        else:
            r["auroc_ts_minus_raw"] = np.nan
            r["auprc_ts_minus_raw"] = np.nan

    return ablation_rows, disc_rows


# =====================================================================
# 7. 主入口
# =====================================================================

def discover_checkpoints() -> List[Tuple[str, str, str, int]]:
    """扫描 CKPT_ROOT，返回所有 (source, target, arch, seed) 组合"""
    pairs = []
    for pair_dir in sorted(CKPT_ROOT.iterdir()):
        if not pair_dir.is_dir() or "_" not in pair_dir.name:
            continue
        source, target = pair_dir.name.split("_", 1)
        if source not in DATASET_BUILDERS or target not in DATASET_BUILDERS:
            continue
        for arch_dir in sorted(pair_dir.iterdir()):
            if not arch_dir.is_dir():
                continue
            arch = arch_dir.name
            for seed_dir in sorted(arch_dir.iterdir()):
                if not seed_dir.is_dir():
                    continue
                if (seed_dir / "best_model.pt").exists():
                    seed = int(seed_dir.name.replace("seed", ""))
                    pairs.append((source, target, arch, seed))
    return pairs


def main():
    ap = argparse.ArgumentParser(description="E2: TS消融 + 判别指标")
    ap.add_argument("--pairs", nargs="+", default=None,
                    help="指定 pair（如 ptbxl_chapman）；默认全部60")
    ap.add_argument("--archs", nargs="+", default=None,
                    help="指定 arch；默认全部")
    ap.add_argument("--seeds", nargs="+", type=int, default=None,
                    help="指定 seed；默认全部")
    ap.add_argument("--limit", type=int, default=None, help="冒烟截断样本数")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--d-model", dest="d_model", type=int, default=64)
    ap.add_argument("--n-layers", dest="n_layers", type=int, default=2)
    ap.add_argument("--num-workers", type=int, default=0)
    ap.add_argument("--use-cache", action="store_true", default=True,
                    help="缓存前向推理 probs（默认开）")
    ap.add_argument("--no-cache", dest="use_cache", action="store_false")
    ap.add_argument("--allow-unstamped-cache", action="store_true", default=False,
                    help="放行不带编码戳的旧缓存（危险：09-10 那批为污染值，"
                         "仅在你已人工确认其标签编码时才使用）")
    ap.add_argument("--output-ablation", default=str(RESULTS_DIR / "ablation_ts_components.csv"))
    ap.add_argument("--output-discrimination", default=str(RESULTS_DIR / "discrimination_metrics_60exp.csv"))
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 发现 checkpoint
    all_ckpts = discover_checkpoints()
    if args.pairs:
        all_ckpts = [c for c in all_ckpts if f"{c[0]}_{c[1]}" in args.pairs]
    if args.archs:
        all_ckpts = [c for c in all_ckpts if c[2] in args.archs]
    if args.seeds:
        all_ckpts = [c for c in all_ckpts if c[3] in args.seeds]

    print(f"E2 消融+判别: {len(all_ckpts)} 个 checkpoint")
    print(f"  输出1: {args.output_ablation}")
    print(f"  输出2: {args.output_discrimination}")
    print(f"  缓存: {CACHE_DIR} (use_cache={args.use_cache})")
    print()

    all_ablation = []
    all_discrimination = []
    for i, (src, tgt, arch, seed) in enumerate(all_ckpts, 1):
        print(f"[{i}/{len(all_ckpts)}] {src}_{tgt}/{arch}/seed{seed}")
        ab_rows, disc_rows = run_single_experiment(src, tgt, arch, seed, args)
        all_ablation.extend(ab_rows)
        all_discrimination.extend(disc_rows)

    # ===== 输出 CSV =====
    df_abl = pd.DataFrame(all_ablation)
    df_disc = pd.DataFrame(all_discrimination)

    # 消融表：加边际贡献列
    if not df_abl.empty:
        pivot_rel = df_abl.pivot_table(
            index=["source", "target", "arch", "seed"],
            columns="stage", values="brier_reliability",
        )
        if "stage1_ts" in pivot_rel.columns and "raw" in pivot_rel.columns:
            df_abl["delta_rel_vs_raw"] = df_abl["brier_reliability"] - \
                df_abl.merge(pivot_rel["raw"].reset_index(),
                             on=["source", "target", "arch", "seed"],
                             how="left")["raw"]

    df_abl.to_csv(args.output_ablation, index=False, float_format="%.6f")
    df_disc.to_csv(args.output_discrimination, index=False, float_format="%.6f")

    print(f"\n{'='*70}")
    print(f"消融结果: {args.output_ablation} ({len(df_abl)} rows)")
    print(f"判别指标: {args.output_discrimination} ({len(df_disc)} rows)")

    # ===== 汇总统计 =====
    if not df_abl.empty:
        print(f"\n--- 消融 Brier reliability 汇总 (test, mean±std) ---")
        for stage in ["raw", "stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold"]:
            sub = df_abl[df_abl["stage"] == stage]
            if not sub.empty:
                r = sub["brier_reliability"]
                print(f"  {stage:30s}: {r.mean():.4f} ± {r.std():.4f}")

        # 边际贡献
        s1 = df_abl[df_abl["stage"] == "stage1_ts"]["brier_reliability"].mean()
        s2 = df_abl[df_abl["stage"] == "stage2_ts_binned"]["brier_reliability"].mean()
        s3 = df_abl[df_abl["stage"] == "stage3_ts_binned_threshold"]["brier_reliability"].mean()
        raw = df_abl[df_abl["stage"] == "raw"]["brier_reliability"].mean()
        print(f"\n--- 边际贡献 (reliability 降低=好) ---")
        print(f"  Stage1 TS only:           {raw:.4f} → {s1:.4f} (Δ={s1-raw:+.4f})")
        print(f"  Stage2 +binned T:         {s1:.4f} → {s2:.4f} (Δ={s2-s1:+.4f})")
        print(f"  Stage3 +threshold opt:    {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f}, ≡0 by construction: threshold只改argmax不改概率)")

    if not df_disc.empty:
        print(f"\n--- 判别指标汇总 (test, mean) ---")
        test_disc = df_disc[df_disc["split"] == "test"]
        for variant in ["raw", "ts", "binned", "threshold"]:
            sub = test_disc[test_disc["variant"] == variant]
            if not sub.empty:
                print(f"  {variant:10s}: "
                      f"AUROC={sub['auroc'].mean():.4f} "
                      f"AUPRC={sub['auprc'].mean():.4f} "
                      f"F1={sub['f1'].mean():.4f} "
                      f"PPV={sub['ppv'].mean():.4f} "
                      f"NPV={sub['npv'].mean():.4f} "
                      f"MCC={sub['mcc'].mean():.4f}")

        # 诚实报告：TS 对 AUROC 的影响
        ts_rows = test_disc[test_disc["variant"] == "ts"]
        if "auroc_ts_minus_raw" in ts_rows.columns:
            deltas = ts_rows["auroc_ts_minus_raw"].dropna()
            if not deltas.empty:
                print(f"\n--- TS 对 AUROC 影响校验 (诚实报告) ---")
                print(f"  ΔAUROC(ts−raw): mean={deltas.mean():+.6f} "
                      f"max|Δ|={deltas.abs().max():.6f} "
                      f"(二分类应=0, 多分类OvR可能微变)")
                print(f"  注: TS保持argmax→F1/MCC不变; "
                      f"AUROC基于概率排序, 多分类下TS非逐类单调→可能微变")

    print(f"\n{'='*70}")
    print("E2 完成。")


if __name__ == "__main__":
    main()
