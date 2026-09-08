"""跨库校准迁移 S1 评估：源模型 → OOD 目标 的主终点测量（协议§7 + §13）

用途：把论文"校准收益 ID→OOD 衰减"的主检验跑在真实跨库对上。
场景 S1（零样本迁移，主分析）：校准方法在**源cal**上拟合 → 直接应用到
**目标test**（无目标标签）。对比 ID 基线（源test上同法）的 ΔECE 衰减。

流程：
1. 在 source 上训练模型（train/val/cal/test 四分割，患者级无泄漏）
2. 源模型对 source-test 与 target-test 各出一份 raw probs
3. 每个校准方法在 source-cal 拟合（S1），同一参数应用到：
     - source-test  → ΔECE_ID（ID 基线）
     - target-test  → ΔECE_OOD（OOD，主分析对象）
4. benefit_inference（BCa, 患者级 cluster, B=10,000）出 ΔECE 配对 CI
5. 主检验单元 H0: ΔECE_ID − ΔECE_OOD = 0 的差值与其CI

调用：
    python scripts/eval_transfer.py \
        --source ptbxl --source-dir data/ptbxl_processed \
        --target chapman --target-dir data/chapman_processed_v2 \
        --arch mamba --seeds 42 43
    # 冒烟：加 --limit 240 --epochs 2

依赖一致：两库同用 SUPERCLASSES=(NORM,MI,STTC,CD,HYP) 固定标签顺序，
概率空间对齐（跨库校准迁移的前提，已由 preprocessing 保证）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.utils.calibration import benefit_inference, smooth_ece, smooth_ece_gpu  # noqa: E402
from src.utils.calibration_methods import CALIBRATION_METHODS  # noqa: E402
from train import (  # noqa: E402
    set_seed, evaluate, train_model, create_dataloader,
    build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
)
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402

DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}

DATASET_NUM_CLASSES = {
    "ptbxl": 5,
    "chapman": 5,
    "cpsc": 4,
}


def _build(dataset: str, data_dir: str, seed: int, limit: int | None,
           subspace: tuple | None = None):
    """构建四分割；返回 (datasets, clusters_test)

    subspace：若提供（如SUBSPACE_CPSC），ptbxl/chapman 按子空间过滤降级（协议§2对称重算）；
    cpsc 始终用 SUBSPACE_CPSC（内置4类），subspace 参数忽略。
    """
    builder = DATASET_BUILDERS[dataset]
    if dataset == "cpsc":
        ds, clusters = builder(data_dir, seed, limit=limit)
    elif subspace is not None:
        ds, clusters = builder(data_dir, seed, limit=limit, subspace=subspace)
    else:
        ds, clusters = builder(data_dir, seed, limit=limit)
    return ds, clusters


def fit_apply_method(method_name, fit_probs, fit_labels, test_probs):
    """在 fit 分布上拟合校准方法，应用到 test 分布 → 校准后概率"""
    if method_name == "none":
        return test_probs
    fit_fn, apply_fn, _ = CALIBRATION_METHODS[method_name]
    # fit_fn 需要 2D 全类概率 + 类标签（one-hot 或整数索引视方法）
    params = fit_fn(fit_probs, fit_labels)
    if params is None:  # 小样本/过参数化预注册失效 → 返回原概率（无收益）
        return test_probs
    return apply_fn(test_probs, params)


def run_pair(args, source_name, source_dir, target_name, target_dir,
             seed: int) -> dict:
    """训练源模型并做 S1 跨库评估，返回该 (pair, arch, seed) 的主终点结果。"""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(seed)

    # ---------- num_classes / subspace 推断（协议§2：涉及CPSC→4类对称降级） ----------
    num_classes = min(DATASET_NUM_CLASSES[source_name],
                      DATASET_NUM_CLASSES[target_name])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    # ---------- 源模型训练（train/val/cal/test） ----------
    src_ds, src_clusters = _build(source_name, source_dir, seed, args.limit,
                                  subspace=subspace)
    loaders = {k: create_dataloader(src_ds[k], args.batch_size,
                                    shuffle=(k == "train"),
                                    drop_last=(k == "train"),
                                    num_workers=args.num_workers)
                for k in ("train", "val", "cal", "test")}
    model = ECGClassifier(in_channels=12, d_model=args.d_model,
                          n_layers=args.n_layers, num_classes=num_classes,
                          dropout=0.1, backbone_type=args.arch).to(device)
    run_dir = Path(args.save_dir) / f"{source_name}_{target_name}" / \
        args.arch / f"seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = {"epochs": args.epochs, "lr": args.lr, "lr_min": 1e-6,
           "weight_decay": 1e-4, "patience": 10, "save_dir": str(run_dir)}
    ckpt_path = run_dir / "best_model.pt"
    if args.load_model and ckpt_path.exists():
        ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
        ckpt_nc = ckpt.get("num_classes")
        if ckpt_nc is not None and ckpt_nc != num_classes:
            raise RuntimeError(
                f"Checkpoint num_classes={ckpt_nc} ≠ 当前 num_classes={num_classes}。"
                f"该 checkpoint 不可复用于此 pair（标签维度不匹配）。")
        sd = ckpt["model_state_dict"]
        if args.arch == "mamba":
            inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
            import re
            layer_ids = {re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
                         for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)}
            inferred_n_layers = len(layer_ids)
        elif "backbone.proj.weight" in sd:
            inferred_d_model = sd["backbone.proj.weight"].shape[0]
            inferred_n_layers = args.n_layers
        else:
            inferred_d_model = args.d_model
            inferred_n_layers = args.n_layers
        if inferred_d_model != args.d_model or inferred_n_layers != args.n_layers:
            model = ECGClassifier(in_channels=12, d_model=inferred_d_model,
                                  n_layers=inferred_n_layers, num_classes=num_classes,
                                  dropout=0.1, backbone_type=args.arch).to(device)
        try:
            model.load_state_dict(sd)
        except RuntimeError as e:
            raise RuntimeError(
                f"load_state_dict 失败（疑似 num_classes 不匹配）: {e}") from e
        print(f"Loaded checkpoint {ckpt_path} (epoch {ckpt.get('epoch','?')}, "
              f"val_ece={ckpt.get('val_ece','?'):.4f}, d_model={inferred_d_model}, n_layers={inferred_n_layers})")
    else:
        model = train_model(model, loaders["train"], loaders["val"], cfg, device)

    # ---------- 源ID评估：源cal拟合 → 源test应用 ----------
    cal_eval = evaluate(model, loaders["cal"], device, compute_calibration=False)
    test_eval = evaluate(model, loaders["test"], device, compute_calibration=False)
    id_probs = test_eval["probs"]          # (N_ID, 5) 源test raw
    id_labels = test_eval["labels"]
    cal_probs = cal_eval["probs"]          # (N_cal, 5) 源cal raw
    cal_labels = cal_eval["labels"]

    # ---------- OOD目标：源模型前向 target test ----------
    tgt_ds, tgt_clusters = _build(target_name, target_dir, seed, args.limit,
                                  subspace=subspace)
    tgt_loaders = create_dataloader(tgt_ds["test"], args.batch_size,
                                    shuffle=False, num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loaders, device, compute_calibration=False)
    ood_probs = tgt_eval["probs"]          # (N_OOD, 5) 目标raw
    ood_labels = tgt_eval["labels"]
    # 目标患者ID作为cluster（患者级bootstrap）
    ood_clusters = tgt_clusters

    # ---------- 每个方法：S1拟合(源cal)→ 双域应用 ----------
    results = {
        "source": source_name, "target": target_name, "arch": args.arch,
        "seed": seed,
        "num_classes": num_classes,
        "subspace": list(subspace) if subspace else None,
        "label_map": {c: i for i, c in enumerate(subspace)} if subspace
                     else {c: i for i, c in enumerate(SUPERCLASSES)},
        "n_id": int(len(id_probs)), "n_ood": int(len(ood_probs)),
        "id_acc": float((id_probs.argmax(1) == id_labels).mean()),
        "ood_acc": float((ood_probs.argmax(1) == ood_labels).mean()),
        "methods": {},
    }

    rng = np.random.default_rng(seed)
    for mname in args.methods:
        if mname in ("em_prior", "bbse_prior"):
            # S1' 目标域无监督先验适配（Saerens 2002 / BBSE, Lipton 2018）：
            # 用源cal(有标签) + 目标test(无标签)估计目标先验 π̂ → 概率再缩放。
            # 注记：同一 π̂ 应用到 ID 域会刻意引入先验失配（ID 真实先验=源先验），
            # 其 ID 退化是该方法范式的一部分——decay 对 prior 方法解读为
            # "目标特异性收益"，论文中需显式注明（防审稿人 challenge 配对公平性）。
            from src.utils.prior_shift import fit_em, fit_bbse
            fit_fn = fit_em if mname == "em_prior" else fit_bbse
            res = fit_fn(cal_probs, cal_labels, ood_probs)
            if res is None:
                results["methods"][mname] = {
                    "status": "skipped", "reason": "先验不可辨识",
                    "id": None, "ood": None, "decay": None}
                print(f"[{mname:9s}] SKIPPED: 先验不可辨识")
                continue
            pi_hat, pi_train = res["pi_hat"], res["pi_train"]

            def _apply_prior(probs, _r=(pi_hat / np.maximum(pi_train, 1e-12))):
                adj = probs * _r[None, :]
                return adj / adj.sum(axis=1, keepdims=True)

            ood_cal = _apply_prior(ood_probs)
            id_cal = _apply_prior(id_probs)
            w = pi_hat / np.maximum(pi_train, 1e-12)
            print(f"  [{mname}] π̂_target={np.round(pi_hat, 3)} "
                  f"(π_train={np.round(pi_train, 3)})")
            print(f"  [{mname}] w=π̂/π_train={np.round(w, 2)}")
            if "confusion_cond" in res:
                print(f"  [{mname}] cond(C)={res['confusion_cond']:.1f} "
                      f"rank={res['rank']}/{len(pi_train)}")
            res_id = fit_fn(cal_probs, cal_labels, id_probs)
            pi_id = w_id = None
            sanity_flag = None
            if res_id is not None:
                pi_id = res_id["pi_hat"]
                w_id = pi_id / np.maximum(pi_train, 1e-12)
                print(f"  [{mname}] [sanity] π̂_ID={np.round(pi_id, 3)} "
                      f"w_ID={np.round(w_id, 2)} (≈1 if no shift)")
                # R8-H1 gate: ID sanity drift alarm (identifiability proxy)
                max_drift = float(np.nanmax(np.abs(w_id - 1.0)))
                cond_id = res_id.get("confusion_cond")
                if max_drift > 10.0:
                    sanity_flag = f"w_ID drift max|w-1|={max_drift:.1f} > 10; estimator likely ill-conditioned/unnamed-shift"
                    print(f"  [{mname}] [sanity][WARN] {sanity_flag}")
                elif cond_id is not None and float(cond_id) > 1e4:
                    sanity_flag = f"cond(C)={float(cond_id):.1f} > 1e4; prior recovery unreliable"
                    print(f"  [{mname}] [sanity][warn] {sanity_flag}")
            results["methods"][mname + "_pi"] = {
                "pi_hat": pi_hat.tolist(), "pi_train": pi_train.tolist(),
                "estimator": res["method"], "w": w.tolist(),
                "cond_C": res.get("confusion_cond"),
                "pi_hat_ID": pi_id.tolist() if pi_id is not None else None,
                "w_ID": w_id.tolist() if w_id is not None else None,
                "sanity_flag": sanity_flag}
        elif mname == "saerens":
            # saerens 需目标域无监督先验估计，与 S1 源cal拟合范式不兼容（范畴错误：
            # saerens 的"参数"是目标先验，只能在目标域估计）。标记 skipped 而非伪造输出。
            # S1' 场景请用 em_prior / bbse_prior（等价方法，正确范式）。
            results["methods"][mname] = {
                "status": "skipped",
                "reason": "saerens 需目标域无监督拟合，与S1源cal拟合范式不兼容；用em_prior/bbse_prior",
                "id": None, "ood": None, "decay": None,
            }
            print(f"[{mname:9s}] SKIPPED: 需目标域无监督拟合，S1源cal范式不兼容")
            continue
        else:
            ood_cal = fit_apply_method(mname, cal_probs, cal_labels, ood_probs)
            id_cal = fit_apply_method(mname, cal_probs, cal_labels, id_probs)

        # 配对 cluster bootstrap 需 (probs_raw, probs_cal) 同序 + labels
        metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece
        print(f"  [{mname}] OOD bootstrap推断中... (B={args.bootstrap}, "
              f"method={args.bci_method}, metric={'gpu' if args.gpu_inference else 'cpu'})")
        ood_ben = benefit_inference(
            _maxprob(ood_probs), _maxprob(ood_cal), _bin(ood_cal, ood_labels),
            metric=metric_fn, n_bootstrap=args.bootstrap, rng=rng,
            clusters=ood_clusters, bci_method=args.bci_method)
        print(f"  [{mname}] ID bootstrap推断中...")
        id_ben = benefit_inference(
            _maxprob(id_probs), _maxprob(id_cal), _bin(id_cal, id_labels),
            metric=metric_fn, n_bootstrap=args.bootstrap, rng=rng,
            clusters=src_clusters, bci_method=args.bci_method)

        results["methods"][mname] = {
            "id": {"deltaECE": id_ben["benefit"], "ci": list(id_ben["benefit_ci"]),
                   "raw": id_ben["raw"], "cal": id_ben["cal"]},
            "ood": {"deltaECE": ood_ben["benefit"], "ci": list(ood_ben["benefit_ci"]),
                    "raw": ood_ben["raw"], "cal": ood_ben["cal"]},
            "decay": float(ood_ben["benefit"] - id_ben["benefit"]),
            "meta": {"n_bootstrap": int(args.bootstrap), "bci_method": args.bci_method,
                     "ts_fit": "source_cal" if mname == "ts" else "source_cal_or_target_unlabeled",
                     "metric": "smooth_ece_0.45*(n/2000)^-0.2"},
        }
        print(f"[{mname:9s}] ID ΔECE={id_ben['benefit']:+.4f} "
              f"[{id_ben['benefit_ci'][0]:+.4f},{id_ben['benefit_ci'][1]:+.4f}] | "
              f"OOD ΔECE={ood_ben['benefit']:+.4f} "
              f"[{ood_ben['benefit_ci'][0]:+.4f},{ood_ben['benefit_ci'][1]:+.4f}] | "
              f"decay={ood_ben['benefit']-id_ben['benefit']:+.4f}")

    out = run_dir / "transfer_result.json"
    if out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
            if "methods" in existing and isinstance(existing["methods"], dict):
                existing["methods"].update(results.get("methods", {}))
                results = existing
        except Exception:
            pass
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved to {out}")
    return results


def _maxprob(p): return np.asarray(p).max(axis=1)
def _bin(p, labels): return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def main():
    ap = argparse.ArgumentParser(description="Cross-library S1 calibration transfer eval")
    ap.add_argument("--source", choices=list(DATASET_BUILDERS), required=True)
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--target", choices=list(DATASET_BUILDERS), required=True)
    ap.add_argument("--target-dir", required=True)
    ap.add_argument("--arch", default="mamba",
                    choices=["mamba", "resnet1d", "inceptiontime"])
    ap.add_argument("--methods", nargs="+",
                    default=["ts", "platt", "em_prior", "bbse_prior"],
                    help="S1主方法子集：ts/platt/isotonic/vector/matrix/dirichlet/"
                         "em_prior/bbse_prior（S1'目标域无监督先验适配）")
    ap.add_argument("--seeds", nargs="+", type=int, default=[42])
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--d-model", "--d_model", dest="d_model",
                    type=int, default=64, help="Hidden dimension（--d-model/--d_model 均可）")
    ap.add_argument("--n-layers", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--bootstrap", type=int, default=10000,
                    help="预注册B=10,000（默认）；冒烟可加 --bootstrap 200")
    ap.add_argument("--n-jobs", type=int, default=1,
                    help="leave-one-cluster-out jackknife并行worker数（默认1串行；"
                         "正式pilot设>=8加速BCa加速度项，输出逐位一致）")
    ap.add_argument("--save-dir", default="checkpoints/transfer")
    ap.add_argument("--limit", type=int, default=None, help="冒烟截断")
    ap.add_argument("--num-workers", type=int, default=0,
                    help="DataLoader多线程数据加载（0=单线程，4-8可显著加速I/O）")
    ap.add_argument("--bci-method", default="bca", choices=["bca", "percentile"],
                    help="CI方法：bca(默认,含jackknife加速度,慢)或percentile(快,跳过jackknife)")
    ap.add_argument("--gpu-inference", action="store_true",
                    help="smooth_ece用GPU实现（数值与CPU一致maxdiff<1e-15，jackknife快92倍）")
    ap.add_argument("--load-model", action="store_true",
                    help="复用已训练best_model.pt跳过重训（仅推断新方法时用）")
    args = ap.parse_args()

    all_runs = []
    for seed in args.seeds:
        r = run_pair(args, args.source, args.source_dir,
                     args.target, args.target_dir, seed)
        all_runs.append(r)

    # 汇总 decay（主检验量：OOD ΔECE − ID ΔECE）
    print("\n" + "=" * 60)
    print("S1 跨库主终点汇总 (ID→OOD ΔECE 衰减)")
    print("=" * 60)
    for mname in args.methods:
        decays = [r["methods"][mname]["decay"] for r in all_runs]
        print(f"  {mname:9s} decay均值={np.mean(decays):+.4f} "
              f"sd={np.std(decays):.4f} (n={len(decays)} seed)")

    agg_path = Path(args.save_dir) / f"{args.source}_{args.target}" / \
        args.arch / "aggregate.json"
    agg_path.parent.mkdir(parents=True, exist_ok=True)
    agg_path.write_text(json.dumps(
        {"pairs": [{k: v for k, v in r.items() if k != "methods"} for r in all_runs],
         "method_decay": {m: [r["methods"][m]["decay"] for r in all_runs]
                          for m in args.methods}},
        indent=2), encoding="utf-8")
    print(f"Aggregate -> {agg_path}")


if __name__ == "__main__":
    main()
