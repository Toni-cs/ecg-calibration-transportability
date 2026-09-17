"""E4: 温度分布 + 分箱温度探索性评估（协议探索性分析，非主检验）

三件事：
  1. 60实验中拟合 T 值的分布（直方图统计量、跨方向/架构/种子变异）
  2. 按不确定度五分位分 5 箱的 binned temperature 评估
     - 每箱在 cal 上独立拟合一个 T，按不确定度分箱应用到 test
     - 对比 global-T vs binned-T 的 Brier reliability 改善
  3. 偏移敏感度：T 值随 L2 prior shift（8+档）的变化趋势

================================================================
核心主张（正方论证）
================================================================
M1. T 值分布分析能揭示"校准温度"跨实验的变异结构：
    - 跨方向变异 → OOD 难度是否反映在 T 上
    - 跨架构变异 → 不同 backbone 的过自信程度是否系统差异
    - 跨种子变异 → T 估计的统计稳定性
M2. Binned temperature（按不确定度分箱）能捕捉 T 的异质性：
    - 高不确定度箱可能需要更大 T（更激进平滑）
    - 低不确定度箱可能接近 identity（T≈1）
    - 若 binned-T 的 Brier reliability 优于 global-T，说明 T 不是常数
M3. 偏移敏感度刻画 T 对分布漂移的稳健性：
    - 若 T 随 shift 单调变化 → T 是 shift 的可辨识函数（可学习先验）
    - 若 T 近似不变 → T 是 shift-invariant（单点校准即可）

================================================================
关键假设（正方显式列出）
================================================================
A1. cal 集上拟合的 T 可代表该实验的"校准温度"（标准 TS 范式）
A2. 不确定度（熵）五分位定义的箱边界可从 cal 迁移到 test
    （即 cal 与 test 的不确定度分布相似——OOD 下可能违反，列为局限）
A3. binned T 假设同箱样本共享最优 T（T 是不确定度的分片常数函数）
A4. L2 shift 的 8+ 档构成 prior shift 的有意义代理
    （严格说 L2 shift 是协变量漂移而非纯 prior shift，列为局限）
A5. Brier reliability 是 binned-T 评估的合理指标（相比 ECE 无分箱偏差）

================================================================
适用边界（正方显式列出）
================================================================
B1. 探索性评估，不进入主检验（主检验由 eval_transfer.py 的 BCa CI 承担）
B2. 5 箱 quintile 是约定选择，未做箱数敏感性（3/7/10 箱）——列为局限
B3. 偏移敏感度依赖 l2_shift_results.json 可用性（24/60 实验有）
B4. binned-T 在 OOD 下的假设 A2 可能违反——结果解读需谨慎
B5. T 值重新拟合依赖 cal 集可复现（相同 seed 和数据分割）

================================================================
推理链条（从分布分析到结论）
================================================================
R1. 加载 60 checkpoint → 在 cal 上拟合 T_global → 得 T 分布
R2. T 分布的跨方向/架构/种子变异 → 揭示 T 的结构化变异源
R3. 按不确定度 quintile 分 5 箱 → 每箱拟合 T_bin → 得 T 的不确定度函数
R4. binned-T vs global-T 的 Brier reliability 对比 → 评估 T 异质性的实用价值
R5. 对有 l2_shift 的实验，每档 shift 重新拟合 T → T(shift) 曲线
R6. T(shift) 的单调性/不变性 → 判断 T 是否 shift-invariant

================================================================
潜在攻击点（正方主动列出薄弱环节）
================================================================
P1. binned-T 的箱边界在 cal 上 test 上定义，OOD 下箱边界可能漂移
    → 反方可能攻击：binned-T 的 OOD 收益是箱边界漂移的伪影
P2. 5 箱 quintile 是任意选择，未做敏感性
    → 反方可能攻击：结果依赖箱数选择
P3. 偏移敏感度只有 24/60 实验有 l2_shift 数据
    → 反方可能攻击：样本偏倚（有 l2_shift 的实验可能非随机子集）
P4. T 值拟合用 L-BFGS-B，可能局部最优
    → 反方可能攻击：T 分布的尾部是优化伪影
P5. Brier reliability 用 10 等宽分箱，与 binned-T 的 5 quintile 不一致
    → 反方可能攻击：评估指标与干预对象分箱不匹配

输出：
  results/temperature_distribution_analysis.csv
    - 每行: pair, arch, seed, T_global, n_cal, n_test,
            cal_entropy_mean, cal_entropy_std, fit_status
    - 跨方向/架构/种子变异汇总行
  results/binned_temperature_exploratory.csv
    - 每行: pair, arch, seed, bin_idx, n_cal_bin, n_test_bin,
            T_bin, T_global,
            brier_rel_raw, brier_rel_binned, brier_rel_global,
            delta_rel_binned_vs_raw, delta_rel_global_vs_raw,
            bin_entropy_lo, bin_entropy_hi
  - 偏移敏感度: results/temperature_distribution_analysis.csv 的 shift 行

调用：
    python scripts/run_e4_temperature_analysis.py
    # 子集：
    python scripts/run_e4_temperature_analysis.py --pairs ptbxl_chapman --archs resnet1d --seeds 42
    # 跳过偏移敏感度（无 l2_shift 数据时）：
    python scripts/run_e4_temperature_analysis.py --skip-shift-sensitivity
    # 缓存 probs 加速重跑：
    python scripts/run_e4_temperature_analysis.py --cache-dir checkpoints/e4_cache
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
import torch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402
from src.utils.encoding_guard import checkpoint_subspace  # noqa: E402
from src.data.l2_shifts import get_l2_shifts, apply_shift  # noqa: E402
from src.utils.calibration import (  # noqa: E402
    fit_temperature, apply_temperature, brier_parts, brier_raw, smooth_ece,
    _validate_n_bins,
)
from train import (  # noqa: E402
    set_seed, evaluate, create_dataloader,
    build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
)

# =====================================================================
# 实验网格（与 eval_transfer.py 对齐）
# =====================================================================
DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}
DATASET_DIRS = {
    "ptbxl": "data/ptbxl_processed",
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
}
ALL_PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
ALL_ARCHS = ["mamba", "resnet1d", "inceptiontime"]
ALL_SEEDS = [42, 43, 44, 45, 46]

N_BINS = 5  # binned temperature 箱数（quintile）
BRIER_N_BINS = 10  # Brier reliability 等宽分箱数（与 calibration.brier_parts 默认一致）
T_MIN, T_MAX = 0.01, 100.0  # 与 calibration.py 对齐


# =====================================================================
# 工具函数
# =====================================================================
def _maxprob(p: np.ndarray) -> np.ndarray:
    return np.asarray(p).max(axis=1)


def _correct_mask(p: np.ndarray, labels: np.ndarray) -> np.ndarray:
    return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def predictive_entropy(probs: np.ndarray) -> np.ndarray:
    """多分类预测熵 H[p] = -Σ p_k log p_k（不确定度度量）。

    高熵 = 高不确定度；低熵 = 模型自信。
    用作 binned temperature 的分箱变量。
    """
    probs = np.asarray(probs, dtype=float)
    p_clip = np.clip(probs, 1e-12, 1.0)
    return -np.sum(probs * np.log(p_clip), axis=1)


def brier_reliability_top(probs: np.ndarray, labels: np.ndarray) -> float:
    """Top-label Brier reliability（Murphy 分解的 reliability 项）。

    用 max-prob 作为预测置信度，correct_mask 作为标签，BRIER_N_BINS 等宽分箱。
    与 calibration.brier_parts 一致（二分类视角的 top-label 校准）。
    """
    mp = _maxprob(probs)
    cm = _correct_mask(probs, labels)
    _, rel, _, _ = brier_parts(mp, cm, n_bins=BRIER_N_BINS)
    return float(rel)


def brier_raw_top(probs: np.ndarray, labels: np.ndarray) -> float:
    """Top-label raw Brier score = mean((maxprob - correct)^2)。"""
    mp = _maxprob(probs)
    cm = _correct_mask(probs, labels)
    return float(brier_raw(mp, cm))


def quintile_edges(values: np.ndarray, n_bins: int = N_BINS) -> np.ndarray:
    """计算 n_bins 分位数的箱边界（n_bins+1 个点，含 0% 和 100%）。"""
    n_bins = _validate_n_bins(n_bins)  # R7-ATK-1：公共守卫，拦截 bool 穿透 + OOM
    qs = np.linspace(0, 1, n_bins + 1)
    edges = np.quantile(values, qs)
    # 去重保护（若 values 有大量同值，edges 可能重复）
    edges = np.unique(edges)
    if len(edges) < n_bins + 1:
        # 退化情况：用等宽回退
        edges = np.linspace(values.min(), values.max() + 1e-9, n_bins + 1)
    edges[0] = -np.inf  # 第一箱左开
    edges[-1] = np.inf  # 最后箱右闭
    return edges


def assign_bins(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """按 edges 分箱，返回每个样本的箱索引（0-based）。

    edges[0]=-inf, edges[-1]=inf；箱 i = [edges[i], edges[i+1])
    """
    bin_idx = np.digitize(values, edges[1:-1], right=False)
    return bin_idx.astype(int)


# =====================================================================
# Checkpoint 加载（复用 eval_transfer.py 的逻辑）
# =====================================================================
def load_checkpoint(
    pair: str, arch: str, seed: int, save_dir: Path,
    d_model: int = 64, n_layers: int = 2,
) -> tuple[torch.nn.Module, int, int, int]:
    """加载 checkpoint，返回 (model, inferred_d_model, inferred_n_layers, num_classes)。

    与 eval_transfer.py 的推断逻辑一致：从 state_dict 反推 d_model/n_layers。
    """
    source, target = pair.split("_")
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    run_dir = save_dir / pair / arch / f"seed{seed}"
    ckpt_path = run_dir / "best_model.pt"
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]
    ckpt_nc = ckpt.get("num_classes")
    if ckpt_nc is not None and ckpt_nc != num_classes:
        raise RuntimeError(
            f"Checkpoint num_classes={ckpt_nc} ≠ {num_classes} for {pair}/{arch}/seed{seed}"
        )

    # 从 state_dict 反推架构参数（与 eval_transfer.py 一致）
    if arch == "mamba":
        inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
        import re
        layer_ids = {re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
                     for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)}
        inferred_n_layers = len(layer_ids)
    elif "backbone.proj.weight" in sd:
        inferred_d_model = sd["backbone.proj.weight"].shape[0]
        inferred_n_layers = n_layers
    else:
        inferred_d_model = d_model
        inferred_n_layers = n_layers

    model = ECGClassifier(
        in_channels=12, d_model=inferred_d_model, n_layers=inferred_n_layers,
        num_classes=num_classes, dropout=0.1, backbone_type=arch,
    ).to(device)
    model.load_state_dict(sd)
    model.eval()
    return model, inferred_d_model, inferred_n_layers, num_classes


def build_datasets(pair: str, seed: int, limit: Optional[int] = None,
                   run_dir: Optional[Path] = None):
    """构建 source 和 target 的四分割数据集，返回 (src_ds, tgt_ds, src_clusters, tgt_clusters, num_classes, subspace)。

    编码护栏（2026-09-17）：4 类口径下**必须**提供 `run_dir`（该 checkpoint 所在
    目录）。标签将按 `run_dir/transfer_result.json` 自存的 `subspace` 重建，并与
    运行时 `SUBSPACE_CPSC` 断言一致，不符即 raise。原先只用运行时常量，
    导致 09-11 产出的 3 份温度 CSV 落在污染窗口内。
    参见 results/_TEMPERATURE_CONTAMINATION_NOTICE.md。
    """
    source, target = pair.split("_")
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    runtime_subspace = SUBSPACE_CPSC if num_classes == 4 else None
    if num_classes == 4:
        if run_dir is None:
            raise RuntimeError(
                "[编码护栏] build_datasets 在 4 类口径下必须提供 run_dir，"
                "以便按 checkpoint 自存的 subspace 重建标签。")
        subspace = checkpoint_subspace(run_dir, num_classes, runtime_subspace)
    else:
        subspace = runtime_subspace

    src_builder = DATASET_BUILDERS[source]
    tgt_builder = DATASET_BUILDERS[target]

    src_dir = str(_PROJECT_ROOT / DATASET_DIRS[source])
    tgt_dir = str(_PROJECT_ROOT / DATASET_DIRS[target])

    if source == "cpsc":
        src_ds, src_clusters = src_builder(src_dir, seed, limit=limit)
    else:
        src_ds, src_clusters = src_builder(src_dir, seed, limit=limit, subspace=subspace)
    if target == "cpsc":
        tgt_ds, tgt_clusters = tgt_builder(tgt_dir, seed, limit=limit)
    else:
        tgt_ds, tgt_clusters = tgt_builder(tgt_dir, seed, limit=limit, subspace=subspace)

    return src_ds, tgt_ds, src_clusters, tgt_clusters, num_classes, subspace


def get_probs_labels(
    model: torch.nn.Module, dataset, device, batch_size: int = 64,
) -> tuple[np.ndarray, np.ndarray]:
    """对 dataset 做前向，返回 (probs, labels)。"""
    loader = create_dataloader(dataset, batch_size, shuffle=False, num_workers=0)
    ev = evaluate(model, loader, device, compute_calibration=False)
    return ev["probs"], ev["labels"]


def shifted_probs_labels(
    model: torch.nn.Module, dataset, shift: dict, device,
    pair_id: str = None, arch: str = None, train_seed: int = None,
) -> tuple[np.ndarray, np.ndarray]:
    """对 dataset 每条信号施加 shift 后前向，返回 (probs, labels)。

    与 eval_l2_shift.py 的 shifted_eval 一致。
    """
    if pair_id is None or arch is None or train_seed is None:
        raise ValueError(
            "pair_id, arch, train_seed must be explicitly provided for reproducible seed derivation"
        )
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    # P0-1 R3修复：基于实验参数派生噪声种子，确保跨实验/跨档/跨移位类型噪声独立。
    # 使用 hashlib.md5 代替内置 hash()，保证跨进程可复现（不受 PYTHONHASHSEED 影响）。
    # 派生键包含 pair_id|arch|train_seed|shift_name，不同实验/不同档/不同移位类型
    # 必然获得不同种子。注意：此变更使已有结果不可精确复现，需重跑受影响实验
    # （见 docs/p0r2_final_verdict.md §2.2）。
    noise_seed = int(
        hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest()[:8], 16
    ) % (2**32)
    rng = np.random.RandomState(noise_seed)
    with torch.no_grad():
        for i in range(n):
            x, y = dataset[i]
            sig = x.numpy()
            sig_s = apply_shift(sig, shift, rng=rng)
            x_s = torch.from_numpy(sig_s).unsqueeze(0).to(device)
            _, probs = model(x_s)
            probs = probs.cpu().numpy()
            all_probs.append(probs[0])
            all_labels.append(int(y))
    return np.array(all_probs), np.array(all_labels)


# =====================================================================
# 缓存（避免重复加载模型）
# =====================================================================
def cache_key(pair: str, arch: str, seed: int) -> str:
    return f"{pair}__{arch}__seed{seed}"


def load_cache(cache_dir: Optional[Path], pair: str, arch: str, seed: int) -> Optional[dict]:
    if cache_dir is None:
        return None
    p = cache_dir / f"{cache_key(pair, arch, seed)}.npz"
    if not p.exists():
        return None
    d = np.load(p, allow_pickle=True)
    return {k: d[k] for k in d.files}


def save_cache(cache_dir: Path, pair: str, arch: str, seed: int, data: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{cache_key(pair, arch, seed)}.npz"
    np.savez(p, **data)


# =====================================================================
# 核心：T 拟合 + binned T
# =====================================================================
def fit_global_T(cal_probs: np.ndarray, cal_labels: np.ndarray) -> tuple[float, str]:
    """全局温度拟合（与 fit_temperature 一致，多分类单一 T）。"""
    try:
        # one-hot 编码（fit_temperature 期望 val_y 与 val_p 同形状）
        n_classes = cal_probs.shape[1]
        y_onehot = np.eye(n_classes)[cal_labels]
        T = fit_temperature(cal_probs, y_onehot, method="L-BFGS-B")
        return float(np.clip(T, T_MIN, T_MAX)), "ok"
    except Exception as e:
        warnings.warn(f"fit_global_T failed: {e}")
        return 1.0, f"fail:{type(e).__name__}"


def fit_binned_T(
    cal_probs: np.ndarray, cal_labels: np.ndarray, n_bins: int = N_BINS,
) -> tuple[np.ndarray, np.ndarray, list]:
    """按不确定度（熵）quintile 分箱，每箱独立拟合 T。

    Returns:
        T_per_bin: (n_bins,) 每箱的 T
        bin_edges: (n_bins+1,) 箱边界（含 -inf, inf）
        bin_records: list of dict，每箱的详细信息
    """
    ent = predictive_entropy(cal_probs)
    edges = quintile_edges(ent, n_bins=n_bins)
    bin_idx = assign_bins(ent, edges)

    n_classes = cal_probs.shape[1]
    T_per_bin = np.ones(n_bins, dtype=float)
    bin_records = []

    for b in range(n_bins):
        mask = bin_idx == b
        n_b = int(mask.sum())
        rec = {"bin_idx": b, "n_cal_bin": n_b,
               "entropy_lo": float(edges[b]) if np.isfinite(edges[b]) else -np.inf,
               "entropy_hi": float(edges[b + 1]) if np.isfinite(edges[b + 1]) else np.inf,
               "entropy_mean": float(ent[mask].mean()) if n_b > 0 else float("nan")}
        if n_b < n_classes * 2:  # 样本不足，跳过拟合
            rec["T_bin"] = 1.0
            rec["status"] = f"insufficient_samples(n={n_b})"
            bin_records.append(rec)
            continue
        try:
            y_oh = np.eye(n_classes)[cal_labels[mask]]
            T_b = fit_temperature(cal_probs[mask], y_oh, method="L-BFGS-B")
            T_b = float(np.clip(T_b, T_MIN, T_MAX))
            T_per_bin[b] = T_b
            rec["T_bin"] = T_b
            rec["status"] = "ok"
        except Exception as e:
            rec["T_bin"] = 1.0
            rec["status"] = f"fail:{type(e).__name__}"
        bin_records.append(rec)

    return T_per_bin, edges, bin_records


def apply_binned_T(
    probs: np.ndarray, T_per_bin: np.ndarray, bin_edges: np.ndarray,
) -> np.ndarray:
    """按不确定度分箱应用对应 T 到 probs。

    每个样本根据自身熵分箱，用该箱的 T 做温度缩放。
    """
    ent = predictive_entropy(probs)
    bin_idx = assign_bins(ent, bin_edges)
    out = probs.copy()
    for b in range(len(T_per_bin)):
        mask = bin_idx == b
        if not mask.any():
            continue
        out[mask] = apply_temperature(probs[mask], T_per_bin[b])
    return out


def apply_global_T(probs: np.ndarray, T: float) -> np.ndarray:
    """全局 T 应用。"""
    return apply_temperature(probs, T)


# =====================================================================
# 单实验处理
# =====================================================================
def process_one(
    pair: str, arch: str, seed: int, save_dir: Path,
    cache_dir: Optional[Path], device: torch.device,
    d_model: int = 64, n_layers: int = 2,
) -> dict:
    """处理单个实验，返回分布分析 + binned 评估记录。

    Returns:
        dict with keys:
            dist: dict（一行 temperature_distribution_analysis）
            binned: list[dict]（N_BINS 行 binned_temperature_exploratory）
            shift: list[dict]（偏移敏感度行，可能为空）
    """
    source, target = pair.split("_")
    key = cache_key(pair, arch, seed)

    # ---------- 加载 probs/labels（优先缓存） ----------
    cache = load_cache(cache_dir, pair, arch, seed)
    if cache is not None:
        cal_probs = cache["cal_probs"]
        cal_labels = cache["cal_labels"]
        id_probs = cache["id_probs"]
        id_labels = cache["id_labels"]
        ood_probs = cache["ood_probs"]
        ood_labels = cache["ood_labels"]
    else:
        model, _, _, num_classes = load_checkpoint(
            pair, arch, seed, save_dir, d_model=d_model, n_layers=n_layers
        )
        src_ds, tgt_ds, _, _, _, _ = build_datasets(
            pair, seed, limit=None,
            run_dir=save_dir / pair / arch / f"seed{seed}")

        cal_loader = create_dataloader(src_ds["cal"], 64, shuffle=False, num_workers=0)
        id_loader = create_dataloader(src_ds["test"], 64, shuffle=False, num_workers=0)
        ood_loader = create_dataloader(tgt_ds["test"], 64, shuffle=False, num_workers=0)

        cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
        id_ev = evaluate(model, id_loader, device, compute_calibration=False)
        ood_ev = evaluate(model, ood_loader, device, compute_calibration=False)

        cal_probs, cal_labels = cal_ev["probs"], cal_ev["labels"]
        id_probs, id_labels = id_ev["probs"], id_ev["labels"]
        ood_probs, ood_labels = ood_ev["probs"], ood_ev["labels"]

        if cache_dir is not None:
            save_cache(cache_dir, pair, arch, seed, {
                "cal_probs": cal_probs, "cal_labels": cal_labels,
                "id_probs": id_probs, "id_labels": id_labels,
                "ood_probs": ood_probs, "ood_labels": ood_labels,
            })
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ---------- 1. 全局 T 拟合 ----------
    T_global, fit_status = fit_global_T(cal_probs, cal_labels)
    cal_ent = predictive_entropy(cal_probs)

    # ID / OOD 上的 global-T Brier reliability
    id_rel_raw = brier_reliability_top(id_probs, id_labels)
    id_rel_global = brier_reliability_top(apply_global_T(id_probs, T_global), id_labels)
    ood_rel_raw = brier_reliability_top(ood_probs, ood_labels)
    ood_rel_global = brier_reliability_top(apply_global_T(ood_probs, T_global), ood_labels)

    dist_record = {
        "pair": pair, "arch": arch, "seed": seed,
        "source": source, "target": target,
        "T_global": T_global, "fit_status": fit_status,
        "n_cal": int(len(cal_probs)),
        "n_id": int(len(id_probs)),
        "n_ood": int(len(ood_probs)),
        "cal_entropy_mean": float(cal_ent.mean()),
        "cal_entropy_std": float(cal_ent.std()),
        "id_rel_raw": id_rel_raw,
        "id_rel_global_T": id_rel_global,
        "id_delta_rel_global": id_rel_global - id_rel_raw,
        "ood_rel_raw": ood_rel_raw,
        "ood_rel_global_T": ood_rel_global,
        "ood_delta_rel_global": ood_rel_global - ood_rel_raw,
    }

    # ---------- 2. Binned T 评估 ----------
    T_per_bin, bin_edges, bin_records = fit_binned_T(cal_probs, cal_labels, n_bins=N_BINS)

    # 应用 binned-T 到 ID 和 OOD
    id_probs_binned = apply_binned_T(id_probs, T_per_bin, bin_edges)
    ood_probs_binned = apply_binned_T(ood_probs, T_per_bin, bin_edges)

    # 全局 binned-T Brier reliability（在整个 test 集上一次计算，非 per-bin 均值）
    # M2 核心比较：binned-T 的全局 Brier reliability vs global-T 的全局 Brier reliability
    # 注意：per-bin 均值 ≠ 全局 Brier reliability（Brier reliability 是加权非线性，不可加）
    id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
    ood_rel_binned_global = brier_reliability_top(ood_probs_binned, ood_labels)
    dist_record["id_rel_binned_T"] = id_rel_binned_global
    dist_record["ood_rel_binned_T"] = ood_rel_binned_global
    dist_record["id_delta_rel_binned_vs_global"] = id_rel_binned_global - id_rel_global
    dist_record["ood_delta_rel_binned_vs_global"] = ood_rel_binned_global - ood_rel_global

    binned_records = []
    for rec in bin_records:
        b = rec["bin_idx"]
        # 该箱在 test 上的样本
        id_ent = predictive_entropy(id_probs)
        ood_ent = predictive_entropy(ood_probs)
        id_bin_mask = assign_bins(id_ent, bin_edges) == b
        ood_bin_mask = assign_bins(ood_ent, bin_edges) == b

        # 箱级 Brier reliability（在箱内样本上）
        if id_bin_mask.sum() > 0:
            id_rel_raw_b = brier_reliability_top(id_probs[id_bin_mask], id_labels[id_bin_mask])
            id_rel_binned_b = brier_reliability_top(
                id_probs_binned[id_bin_mask], id_labels[id_bin_mask])
            id_rel_global_b = brier_reliability_top(
                apply_global_T(id_probs[id_bin_mask], T_global), id_labels[id_bin_mask])
        else:
            id_rel_raw_b = id_rel_binned_b = id_rel_global_b = float("nan")

        if ood_bin_mask.sum() > 0:
            ood_rel_raw_b = brier_reliability_top(ood_probs[ood_bin_mask], ood_labels[ood_bin_mask])
            ood_rel_binned_b = brier_reliability_top(
                ood_probs_binned[ood_bin_mask], ood_labels[ood_bin_mask])
            ood_rel_global_b = brier_reliability_top(
                apply_global_T(ood_probs[ood_bin_mask], T_global), ood_labels[ood_bin_mask])
        else:
            ood_rel_raw_b = ood_rel_binned_b = ood_rel_global_b = float("nan")

        binned_records.append({
            "pair": pair, "arch": arch, "seed": seed,
            "bin_idx": b,
            "n_cal_bin": rec["n_cal_bin"],
            "n_id_bin": int(id_bin_mask.sum()),
            "n_ood_bin": int(ood_bin_mask.sum()),
            "T_bin": rec["T_bin"],
            "T_global": T_global,
            "bin_entropy_lo": rec["entropy_lo"],
            "bin_entropy_hi": rec["entropy_hi"],
            "bin_entropy_mean": rec["entropy_mean"],
            "id_rel_raw": id_rel_raw_b,
            "id_rel_binned_T": id_rel_binned_b,
            "id_rel_global_T": id_rel_global_b,
            "id_delta_binned_vs_raw": id_rel_binned_b - id_rel_raw_b,
            "id_delta_global_vs_raw": id_rel_global_b - id_rel_raw_b,
            "id_delta_binned_vs_global": id_rel_binned_b - id_rel_global_b,
            "ood_rel_raw": ood_rel_raw_b,
            "ood_rel_binned_T": ood_rel_binned_b,
            "ood_rel_global_T": ood_rel_global_b,
            "ood_delta_binned_vs_raw": ood_rel_binned_b - ood_rel_raw_b,
            "ood_delta_global_vs_raw": ood_rel_global_b - ood_rel_raw_b,
            "ood_delta_binned_vs_global": ood_rel_binned_b - ood_rel_global_b,
            "fit_status": rec["status"],
        })

    # ---------- 3. 偏移敏感度（若有 l2_shift 数据） ----------
    shift_records = []
    # 偏移敏感度：对每档 shift 重新拟合 T
    # 注意：这里在 OOD test 上施加 shift 后拟合 T（用 cal 的 shift 版本拟合）
    # 严格语义：T(shift) = argmin NLL(cal_shift; T)
    # 即：cal 集信号施加 shift → 模型前向 → 拟合 T
    # 这刻画"校准温度对输入漂移的敏感度"
    # 为避免重复加载模型，仅在 cache 未命中时跳过（cache 命中时无模型）
    # → 改为：单独函数处理偏移敏感度，按需加载模型

    return {"dist": dist_record, "binned": binned_records, "shift": shift_records}


def process_shift_sensitivity(
    pair: str, arch: str, seed: int, save_dir: Path,
    device: torch.device, shifts: list,
    d_model: int = 64, n_layers: int = 2,
) -> list:
    """偏移敏感度：对每档 L2 shift，在 cal_shift 上拟合 T，返回 T(shift) 记录。

    语义：cal 集信号施加 shift → 模型前向得 cal_shift_probs → 拟合 T_shift。
    这刻画"校准温度对输入分布漂移的敏感度"。
    """
    try:
        model, _, _, num_classes = load_checkpoint(
            pair, arch, seed, save_dir, d_model=d_model, n_layers=n_layers
        )
        src_ds, tgt_ds, _, _, _, _ = build_datasets(
            pair, seed, limit=None,
            run_dir=save_dir / pair / arch / f"seed{seed}")
    except FileNotFoundError:
        return []

    records = []
    # baseline T（无 shift）
    try:
        cal_loader = create_dataloader(src_ds["cal"], 64, shuffle=False, num_workers=0)
        cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
        cal_probs_base = cal_ev["probs"]
        cal_labels_base = cal_ev["labels"]
        T_base, status_base = fit_global_T(cal_probs_base, cal_labels_base)
    except Exception as e:
        T_base, status_base = float("nan"), f"fail:{type(e).__name__}"

    records.append({
        "pair": pair, "arch": arch, "seed": seed,
        "shift_name": "baseline",
        "shift_type": "none",
        "T_shift": T_base,
        "T_relative": 1.0,
        "cal_entropy_mean": float(predictive_entropy(cal_probs_base).mean())
            if status_base == "ok" else float("nan"),
        "n_cal": int(len(cal_probs_base)) if status_base == "ok" else 0,
        "fit_status": status_base,
    })

    for shift in shifts:
        try:
            cal_probs_s, cal_labels_s = shifted_probs_labels(
                model, src_ds["cal"], shift, device,
                pair_id=pair, arch=arch, train_seed=seed,
            )
            T_s, status_s = fit_global_T(cal_probs_s, cal_labels_s)
            ent_mean = float(predictive_entropy(cal_probs_s).mean())
            records.append({
                "pair": pair, "arch": arch, "seed": seed,
                "shift_name": shift["name"],
                "shift_type": shift["type"],
                "T_shift": T_s,
                "T_relative": T_s / T_base if T_base > 0 else float("nan"),
                "cal_entropy_mean": ent_mean,
                "n_cal": int(len(cal_probs_s)),
                "fit_status": status_s,
            })
        except Exception as e:
            records.append({
                "pair": pair, "arch": arch, "seed": seed,
                "shift_name": shift["name"],
                "shift_type": shift["type"],
                "T_shift": float("nan"),
                "T_relative": float("nan"),
                "cal_entropy_mean": float("nan"),
                "n_cal": 0,
                "fit_status": f"fail:{type(e).__name__}",
            })

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return records


# =====================================================================
# 分布汇总统计
# =====================================================================
def summarize_distribution(dist_records: list) -> list:
    """对 T_global 分布做汇总统计，返回额外行（arch=SUMMARY）。"""
    if not dist_records:
        return []
    Ts = np.array([r["T_global"] for r in dist_records if r["fit_status"] == "ok"])
    if len(Ts) == 0:
        return []

    summary_rows = []
    # 全局汇总
    summary_rows.append({
        "pair": "ALL", "arch": "SUMMARY", "seed": -1,
        "source": "", "target": "",
        "T_global": float(np.mean(Ts)),
        "fit_status": f"n={len(Ts)},mean",
        "n_cal": int(np.median([r["n_cal"] for r in dist_records])),
        "n_id": int(np.median([r["n_id"] for r in dist_records])),
        "n_ood": int(np.median([r["n_ood"] for r in dist_records])),
        "cal_entropy_mean": float(np.mean([r["cal_entropy_mean"] for r in dist_records])),
        "cal_entropy_std": float(np.mean([r["cal_entropy_std"] for r in dist_records])),
        "id_rel_raw": float("nan"),
        "id_rel_global_T": float("nan"),
        "id_delta_rel_global": float("nan"),
        "id_rel_binned_T": float("nan"),
        "id_delta_rel_binned_vs_global": float("nan"),
        "ood_rel_raw": float("nan"),
        "ood_rel_global_T": float("nan"),
        "ood_delta_rel_global": float("nan"),
        "ood_rel_binned_T": float("nan"),
        "ood_delta_rel_binned_vs_global": float("nan"),
    })

    # 跨方向汇总
    for pair in ALL_PAIRS:
        pair_Ts = [r["T_global"] for r in dist_records
                   if r["pair"] == pair and r["fit_status"] == "ok"]
        if len(pair_Ts) >= 2:
            summary_rows.append({
                "pair": pair, "arch": "PAIR_MEAN", "seed": -1,
                "source": "", "target": "",
                "T_global": float(np.mean(pair_Ts)),
                "fit_status": f"n={len(pair_Ts)},pair_mean",
                "n_cal": 0, "n_id": 0, "n_ood": 0,
                "cal_entropy_mean": float("nan"), "cal_entropy_std": float("nan"),
                "id_rel_raw": float("nan"), "id_rel_global_T": float("nan"),
                "id_delta_rel_global": float("nan"),
                "id_rel_binned_T": float("nan"), "id_delta_rel_binned_vs_global": float("nan"),
                "ood_rel_raw": float("nan"), "ood_rel_global_T": float("nan"),
                "ood_delta_rel_global": float("nan"),
                "ood_rel_binned_T": float("nan"), "ood_delta_rel_binned_vs_global": float("nan"),
            })

    # 跨架构汇总
    for arch in ALL_ARCHS:
        arch_Ts = [r["T_global"] for r in dist_records
                   if r["arch"] == arch and r["fit_status"] == "ok"]
        if len(arch_Ts) >= 2:
            summary_rows.append({
                "pair": "ALL", "arch": f"{arch}_MEAN", "seed": -1,
                "source": "", "target": "",
                "T_global": float(np.mean(arch_Ts)),
                "fit_status": f"n={len(arch_Ts)},arch_mean",
                "n_cal": 0, "n_id": 0, "n_ood": 0,
                "cal_entropy_mean": float("nan"), "cal_entropy_std": float("nan"),
                "id_rel_raw": float("nan"), "id_rel_global_T": float("nan"),
                "id_delta_rel_global": float("nan"),
                "id_rel_binned_T": float("nan"), "id_delta_rel_binned_vs_global": float("nan"),
                "ood_rel_raw": float("nan"), "ood_rel_global_T": float("nan"),
                "ood_delta_rel_global": float("nan"),
                "ood_rel_binned_T": float("nan"), "ood_delta_rel_binned_vs_global": float("nan"),
            })

    # 分布统计量行
    summary_rows.append({
        "pair": "ALL", "arch": "DIST_STATS", "seed": -1,
        "source": "", "target": "",
        "T_global": float(np.std(Ts)),
        "fit_status": f"n={len(Ts)},std",
        "n_cal": int(np.median(Ts)),
        "n_id": float(np.percentile(Ts, 25)),
        "n_ood": float(np.percentile(Ts, 75)),
        "cal_entropy_mean": float(np.median(Ts)),
        "cal_entropy_std": float(Ts.min()),
        "id_rel_raw": float(Ts.max()),
        "id_rel_global_T": float(np.percentile(Ts, 5)),
        "id_delta_rel_global": float(np.percentile(Ts, 95)),
        "id_rel_binned_T": float("nan"),
        "id_delta_rel_binned_vs_global": float("nan"),
        "ood_rel_raw": float(np.mean(np.abs(Ts - 1.0))),  # 平均偏离 1.0
        "ood_rel_global_T": float("nan"),
        "ood_delta_rel_global": float("nan"),
        "ood_rel_binned_T": float("nan"),
        "ood_delta_rel_binned_vs_global": float("nan"),
    })

    return summary_rows


# =====================================================================
# CSV 写入
# =====================================================================
def write_csv(records: list, path: Path, fieldnames: list) -> None:
    """写 CSV（不依赖 pandas，避免环境问题）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)


def write_dist_csv(dist_records: list, summary_rows: list, path: Path) -> None:
    fieldnames = [
        "pair", "arch", "seed", "source", "target",
        "T_global", "fit_status",
        "n_cal", "n_id", "n_ood",
        "cal_entropy_mean", "cal_entropy_std",
        "id_rel_raw", "id_rel_global_T", "id_delta_rel_global",
        "id_rel_binned_T", "id_delta_rel_binned_vs_global",
        "ood_rel_raw", "ood_rel_global_T", "ood_delta_rel_global",
        "ood_rel_binned_T", "ood_delta_rel_binned_vs_global",
    ]
    write_csv(dist_records + summary_rows, path, fieldnames)


def write_binned_csv(binned_records: list, path: Path) -> None:
    fieldnames = [
        "pair", "arch", "seed", "bin_idx",
        "n_cal_bin", "n_id_bin", "n_ood_bin",
        "T_bin", "T_global",
        "bin_entropy_lo", "bin_entropy_hi", "bin_entropy_mean",
        "id_rel_raw", "id_rel_binned_T", "id_rel_global_T",
        "id_delta_binned_vs_raw", "id_delta_global_vs_raw", "id_delta_binned_vs_global",
        "ood_rel_raw", "ood_rel_binned_T", "ood_rel_global_T",
        "ood_delta_binned_vs_raw", "ood_delta_global_vs_raw", "ood_delta_binned_vs_global",
        "fit_status",
    ]
    write_csv(binned_records, path, fieldnames)


def write_shift_csv(shift_records: list, path: Path) -> None:
    fieldnames = [
        "pair", "arch", "seed", "shift_name", "shift_type",
        "T_shift", "T_relative", "cal_entropy_mean", "n_cal", "fit_status",
    ]
    write_csv(shift_records, path, fieldnames)


# =====================================================================
# 主流程
# =====================================================================
def discover_experiments(save_dir: Path, pairs: list, archs: list, seeds: list) -> list:
    """发现实际存在的实验（checkpoint 存在）。"""
    exps = []
    for pair in pairs:
        for arch in archs:
            for seed in seeds:
                ckpt = save_dir / pair / arch / f"seed{seed}" / "best_model.pt"
                if ckpt.exists():
                    exps.append((pair, arch, seed))
    return exps


def main():
    global N_BINS
    ap = argparse.ArgumentParser(description="E4: 温度分布 + 分箱温度探索性评估")
    ap.add_argument("--save-dir", default="checkpoints/transfer")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--cache-dir", default=None,
                    help="probs 缓存目录（加速重跑，避免重复加载模型）")
    ap.add_argument("--pairs", nargs="+", default=ALL_PAIRS)
    ap.add_argument("--archs", nargs="+", default=ALL_ARCHS)
    ap.add_argument("--seeds", nargs="+", type=int, default=ALL_SEEDS)
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--n-layers", type=int, default=2)
    ap.add_argument("--n-bins", type=int, default=N_BINS,
                    help="binned temperature 箱数（默认 5 quintile）")
    ap.add_argument("--skip-binned", action="store_true",
                    help="跳过 binned temperature 评估")
    ap.add_argument("--skip-shift-sensitivity", action="store_true",
                    help="跳过偏移敏感度（无 l2_shift 数据或加速）")
    ap.add_argument("--shifts", nargs="+", default=None,
                    help="只跑指定 shift 档（如 fs250 noise12），默认全部")
    args = ap.parse_args()

    N_BINS = args.n_bins

    save_dir = _PROJECT_ROOT / args.save_dir
    results_dir = _PROJECT_ROOT / args.results_dir
    cache_dir = _PROJECT_ROOT / args.cache_dir if args.cache_dir else None
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 发现实验
    exps = discover_experiments(save_dir, args.pairs, args.archs, args.seeds)
    print(f"发现 {len(exps)} 个实验（checkpoint 存在）")
    if not exps:
        print("无实验可跑，退出。")
        return

    # L2 shifts
    all_shifts = get_l2_shifts()
    if args.shifts:
        shifts = [s for s in all_shifts if s["name"] in args.shifts]
    else:
        shifts = all_shifts

    # ---------- 主循环 ----------
    all_dist = []
    all_binned = []
    all_shift = []

    for i, (pair, arch, seed) in enumerate(exps, 1):
        print(f"\n[{i}/{len(exps)}] {pair}/{arch}/seed{seed}", flush=True)
        try:
            res = process_one(
                pair, arch, seed, save_dir, cache_dir, device,
                d_model=args.d_model, n_layers=args.n_layers,
            )
            all_dist.append(res["dist"])
            if not args.skip_binned:
                all_binned.extend(res["binned"])
            print(f"  T_global={res['dist']['T_global']:.4f} "
                  f"(status={res['dist']['fit_status']})", flush=True)
        except Exception as e:
            print(f"  [FAIL] {type(e).__name__}: {e}", flush=True)
            all_dist.append({
                "pair": pair, "arch": arch, "seed": seed,
                "source": pair.split("_")[0], "target": pair.split("_")[1],
                "T_global": float("nan"), "fit_status": f"fail:{type(e).__name__}",
                "n_cal": 0, "n_id": 0, "n_ood": 0,
                "cal_entropy_mean": float("nan"), "cal_entropy_std": float("nan"),
                "id_rel_raw": float("nan"), "id_rel_global_T": float("nan"),
                "id_delta_rel_global": float("nan"),
                "id_rel_binned_T": float("nan"), "id_delta_rel_binned_vs_global": float("nan"),
                "ood_rel_raw": float("nan"), "ood_rel_global_T": float("nan"),
                "ood_delta_rel_global": float("nan"),
                "ood_rel_binned_T": float("nan"), "ood_delta_rel_binned_vs_global": float("nan"),
            })

        # 偏移敏感度（按需，每实验单独加载模型）
        if not args.skip_shift_sensitivity:
            try:
                shift_recs = process_shift_sensitivity(
                    pair, arch, seed, save_dir, device, shifts,
                    d_model=args.d_model, n_layers=args.n_layers,
                )
                all_shift.extend(shift_recs)
                if shift_recs:
                    T_base = shift_recs[0]["T_shift"]
                    print(f"  偏移敏感度: T_baseline={T_base:.4f}, "
                          f"{len(shift_recs)-1} 档 shift", flush=True)
            except Exception as e:
                print(f"  [SHIFT FAIL] {type(e).__name__}: {e}", flush=True)

    # ---------- 汇总 + 写 CSV ----------
    summary_rows = summarize_distribution(all_dist)

    dist_path = results_dir / "temperature_distribution_analysis.csv"
    binned_path = results_dir / "binned_temperature_exploratory.csv"
    shift_path = results_dir / "temperature_shift_sensitivity.csv"

    write_dist_csv(all_dist, summary_rows, dist_path)
    print(f"\n分布分析 -> {dist_path} ({len(all_dist)} 实验 + {len(summary_rows)} 汇总行)")

    if not args.skip_binned and all_binned:
        write_binned_csv(all_binned, binned_path)
        print(f"Binned 评估 -> {binned_path} ({len(all_binned)} 行 = {len(all_dist)} 实验 × {N_BINS} 箱)")

    if not args.skip_shift_sensitivity and all_shift:
        write_shift_csv(all_shift, shift_path)
        print(f"偏移敏感度 -> {shift_path} ({len(all_shift)} 行)")

    # ---------- 控制台汇总 ----------
    print("\n" + "=" * 70)
    print("E4 探索性评估汇总")
    print("=" * 70)
    ok_Ts = [r["T_global"] for r in all_dist if r["fit_status"] == "ok"]
    if ok_Ts:
        Ts = np.array(ok_Ts)
        print(f"T_global 分布 (n={len(Ts)}):")
        print(f"  mean={np.mean(Ts):.4f}  std={np.std(Ts):.4f}")
        print(f"  median={np.median(Ts):.4f}  IQR=[{np.percentile(Ts,25):.4f}, {np.percentile(Ts,75):.4f}]")
        print(f"  range=[{Ts.min():.4f}, {Ts.max():.4f}]")
        print(f"  mean|T-1|={np.mean(np.abs(Ts-1.0)):.4f}  (偏离 identity 的平均量)")

    # 跨方向变异
    print("\n跨方向 T 变异:")
    for pair in args.pairs:
        pair_Ts = [r["T_global"] for r in all_dist
                   if r["pair"] == pair and r["fit_status"] == "ok"]
        if len(pair_Ts) >= 2:
            print(f"  {pair:<16} mean={np.mean(pair_Ts):.4f} std={np.std(pair_Ts):.4f} n={len(pair_Ts)}")

    # 跨架构变异
    print("\n跨架构 T 变异:")
    for arch in args.archs:
        arch_Ts = [r["T_global"] for r in all_dist
                   if r["arch"] == arch and r["fit_status"] == "ok"]
        if len(arch_Ts) >= 2:
            print(f"  {arch:<14} mean={np.mean(arch_Ts):.4f} std={np.std(arch_Ts):.4f} n={len(arch_Ts)}")

    # Binned vs global 汇总（全局 Brier reliability，非 per-bin 均值）
    # M2 核心比较：binned-T 的全局 Brier reliability vs global-T 的全局 Brier reliability
    # 注意：per-bin 均值 ≠ 全局 Brier reliability（加权非线性，不可加），故用全局值
    id_delta_global = [r.get("id_delta_rel_binned_vs_global", float("nan")) for r in all_dist
                       if np.isfinite(r.get("id_delta_rel_binned_vs_global", float("nan")))]
    ood_delta_global = [r.get("ood_delta_rel_binned_vs_global", float("nan")) for r in all_dist
                        if np.isfinite(r.get("ood_delta_rel_binned_vs_global", float("nan")))]
    if id_delta_global:
        print(f"\nBinned vs Global Brier reliability (ID, 全局, n={len(id_delta_global)}):")
        print(f"  mean Δrel = {np.mean(id_delta_global):+.6f}  (负=binned 更优)")
        print(f"  median Δrel = {np.median(id_delta_global):+.6f}")
        n_better = int(np.sum(np.array(id_delta_global) < 0))
        print(f"  binned 更优: {n_better}/{len(id_delta_global)} 实验")
    if ood_delta_global:
        print(f"Binned vs Global Brier reliability (OOD, 全局, n={len(ood_delta_global)}):")
        print(f"  mean Δrel = {np.mean(ood_delta_global):+.6f}  (负=binned 更优)")
        print(f"  median Δrel = {np.median(ood_delta_global):+.6f}")
        n_better = int(np.sum(np.array(ood_delta_global) < 0))
        print(f"  binned 更优: {n_better}/{len(ood_delta_global)} 实验")

    # 偏移敏感度汇总
    if not args.skip_shift_sensitivity and all_shift:
        print("\n偏移敏感度 T(shift) 汇总:")
        for shift_name in ["baseline"] + [s["name"] for s in shifts]:
            recs = [r for r in all_shift if r["shift_name"] == shift_name
                    and r["fit_status"] == "ok"]
            if recs:
                T_vals = [r["T_shift"] for r in recs]
                print(f"  {shift_name:<10} mean={np.mean(T_vals):.4f} "
                      f"std={np.std(T_vals):.4f} n={len(T_vals)}")

    print("\n" + "=" * 70)
    print("正方论证声明：本评估为探索性，结果不进入主检验。")
    print("核心主张 M1-M3、假设 A1-A5、边界 B1-B5、攻击点 P1-P5 见脚本 docstring。")
    print("=" * 70)


if __name__ == "__main__":
    main()
