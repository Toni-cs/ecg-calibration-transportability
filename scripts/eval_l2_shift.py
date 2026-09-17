"""L2 移位阶梯 eval-only 实验（协议§3:44-48）。

对每个已有 checkpoint，在 target test 上做 8 档移位变换（降采样+导联+增益），
评估 raw ECE + 8 方法校准后 ECE + ΔECE。
"""
from __future__ import annotations
import argparse, json, sys, hashlib
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.models.ecg_classifier import ECGClassifier
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES
from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION, SEED_STRATEGY_VERSION
from src.utils.calibration_methods import CALIBRATION_METHODS
from src.utils.prior_shift import fit_em, fit_bbse
from src.utils.calibration import smooth_ece
from train import set_seed, evaluate, create_dataloader, build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets

DATASET_BUILDERS = {"ptbxl": build_ptbxl_datasets, "chapman": build_chapman_datasets, "cpsc": build_cpsc_datasets}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}


# 编码护栏已抽到共享模块（2026-09-17）：同一缺陷在 7 个脚本里重复了 10 次，
# 必须只有一份实现，否则修了这里、漏了那里。见 src/utils/encoding_guard.py。
# 本脚本原先只用运行时的 `SUBSPACE_CPSC` 重建标签，于是当该常量在两次改动之间
# 变化、而 checkpoint 是旧编码训练的时候，标签与 probs 错位（MI↔CD 互换，
# 占 38.3% 样本），全部指标被静默污染。2026-09-09~09-16 真实发生过一次：
# 本脚本产出的 60 个 `l2_shift_results.json`（09-10~09-13）与两张
# `l2_shift_full_*` 表（09-12）全部中招，经验判定见
# `scripts/verify_l2_shift_encoding.py` 与
# `results/_L2_SHIFT_CONTAMINATION_NOTICE.md`。
from src.utils.encoding_guard import (  # noqa: E402
    checkpoint_subspace,
    encoding_stamp,
)


def _maxprob(p):
    return np.asarray(p).max(axis=1)


def _bin(p, labels):
    return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def shifted_eval(model, dataset, shift, device, batch_size=64,
                 pair_id: str = None, arch: str = None, train_seed: int = None):
    """对 dataset 的每条信号施加 shift 后评估 model。"""
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
    # 必然获得不同种子。注意：此变更使已有 l2_shift_results.json 不可精确复现，
    # 需重跑受影响实验（见 docs/p0r2_final_verdict.md §2.2）。
    noise_seed = int(
        hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest()[:8], 16
    ) % (2**32)
    rng = np.random.RandomState(noise_seed)
    for i in range(n):
        x, y = dataset[i]
        sig = x.numpy()
        sig_s = apply_shift(sig, shift, rng=rng)
        x_s = torch.from_numpy(sig_s).unsqueeze(0).to(device)
        with torch.no_grad():
            _, probs = model(x_s)
            probs = probs.cpu().numpy()
        all_probs.append(probs[0])
        all_labels.append(int(y))
    return np.array(all_probs), np.array(all_labels)


def main():
    ap = argparse.ArgumentParser(description="L2 shift eval-only")
    ap.add_argument("--source", required=True, choices=list(DATASET_BUILDERS))
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--target", required=True, choices=list(DATASET_BUILDERS))
    ap.add_argument("--target-dir", required=True)
    ap.add_argument("--arch", default="inceptiontime", choices=["mamba", "resnet1d", "inceptiontime"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[42])
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--n-layers", type=int, default=2)
    ap.add_argument("--save-dir", default="checkpoints/transfer")
    ap.add_argument("--methods", nargs="+", default=["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"])
    ap.add_argument("--shifts", nargs="+", default=None, help="只跑指定档（如 noise24 noise12），默认全部")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    num_classes = min(DATASET_NUM_CLASSES[args.source], DATASET_NUM_CLASSES[args.target])
    # 注：这里**故意不**预先用运行时常量算 subspace —— 它必须等读到 checkpoint
    # 之后由编码护栏（见下方循环内的 checkpoint_subspace 调用）确定。
    all_shifts = get_l2_shifts()
    if args.shifts:
        shifts = [s for s in all_shifts if s["name"] in args.shifts]
    else:
        shifts = all_shifts
    all_results = {}

    for seed in args.seeds:
        set_seed(seed)
        run_dir = Path(args.save_dir) / f"{args.source}_{args.target}" / args.arch / f"seed{seed}"
        ckpt_path = run_dir / "best_model.pt"
        if not ckpt_path.exists():
            print(f"[skip] {ckpt_path} not found")
            continue

        ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
        sd = ckpt["model_state_dict"]
        ckpt_nc = ckpt.get("num_classes")
        if ckpt_nc is not None and ckpt_nc != num_classes:
            raise RuntimeError(f"Checkpoint num_classes={ckpt_nc} != {num_classes}")
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
        model = ECGClassifier(in_channels=12, d_model=inferred_d_model, n_layers=inferred_n_layers,
                              num_classes=num_classes, dropout=0.1, backbone_type=args.arch).to(device)
        model.load_state_dict(sd)
        print(f"Loaded {ckpt_path.name} (epoch {ckpt.get('epoch','?')}, d_model={inferred_d_model}, n_layers={inferred_n_layers})")

        # 编码护栏：以 checkpoint 自存的 subspace 为准，且必须与运行时一致。
        # 见 checkpoint_subspace() 的 docstring 与
        # results/_L2_SHIFT_CONTAMINATION_NOTICE.md。
        subspace = checkpoint_subspace(
            run_dir, num_classes,
            SUBSPACE_CPSC if num_classes == 4 else None)
        # 编码戳：写进 JSON 顶层，供下游（step2_predictability.py）与断点续传
        # （is_checkpoint_complete）证明/校验本文件是在哪套标签编码下算出的。
        encoding = encoding_stamp(num_classes, subspace)

        src_builder = DATASET_BUILDERS[args.source]
        tgt_builder = DATASET_BUILDERS[args.target]
        if args.source == "cpsc":
            src_ds, _ = src_builder(args.source_dir, seed, limit=None)
        else:
            src_ds, _ = src_builder(args.source_dir, seed, limit=None, subspace=subspace)
        if args.target == "cpsc":
            tgt_ds, _ = tgt_builder(args.target_dir, seed, limit=None)
        else:
            tgt_ds, _ = tgt_builder(args.target_dir, seed, limit=None, subspace=subspace)

        cal_loader = create_dataloader(src_ds["cal"], batch_size=64, shuffle=False, num_workers=0)
        cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
        cal_probs, cal_labels = cal_ev["probs"], cal_ev["labels"]

        seed_results = {}
        for shift in shifts:
            ood_probs, ood_labels = shifted_eval(
                model, tgt_ds["test"], shift, device,
                pair_id=f"{args.source}_{args.target}", arch=args.arch, train_seed=seed,
            )
            raw_ece = smooth_ece(_maxprob(ood_probs), _bin(ood_probs, ood_labels))
            mean_conf = float(np.mean(np.max(ood_probs, axis=1)))
            pred_entropy = float(np.mean(-np.sum(ood_probs * np.log(np.clip(ood_probs, 1e-12, 1)), axis=1)))
            cal_pi = np.bincount(cal_labels, minlength=ood_probs.shape[1]).astype(float)
            cal_pi = cal_pi / cal_pi.sum()
            ood_pi_hat = np.mean(ood_probs, axis=0)
            pi_shift_l1 = float(np.sum(np.abs(ood_pi_hat - cal_pi)))

            method_results = {"raw_ece": float(raw_ece), "mean_conf": mean_conf,
                               "pred_entropy": pred_entropy, "pi_shift_l1": pi_shift_l1}
            for mname in args.methods:
                if mname in CALIBRATION_METHODS:
                    fit_fn, apply_fn, _ = CALIBRATION_METHODS[mname]
                    params = fit_fn(cal_probs, cal_labels)
                    if params is None:
                        method_results[mname] = {"cal_ece": float(raw_ece), "delta_ece": 0.0, "status": "skipped"}
                        continue
                    cal_probs_m = apply_fn(ood_probs, params)
                    protocol = "S1"
                elif mname in ("em_prior", "bbse_prior"):
                    fit_fn = fit_em if mname == "em_prior" else fit_bbse
                    result = fit_fn(cal_probs, cal_labels, ood_probs)
                    if result is None:
                        method_results[mname] = {"cal_ece": float(raw_ece), "delta_ece": 0.0, "status": "skipped"}
                        continue
                    w = result["pi_hat"] / np.maximum(result["pi_train"], 1e-12)
                    adj = ood_probs * w[None, :]
                    cal_probs_m = adj / adj.sum(axis=1, keepdims=True)
                    protocol = "S1'"
                else:
                    continue
                cal_ece = smooth_ece(_maxprob(cal_probs_m), _bin(cal_probs_m, ood_labels))
                method_results[mname] = {
                    "cal_ece": float(cal_ece),
                    "delta_ece": float(cal_ece - raw_ece),
                    "protocol": protocol,
                }
            seed_results[shift["name"]] = method_results
            print(f"  [{shift['name']}] raw={raw_ece:.4f} " +
                  " ".join(f"{m}={method_results[m]['delta_ece']:+.4f}" for m in args.methods if m in method_results))

        all_results[f"seed{seed}"] = seed_results
        # P0-1 R7修复（Attack-1）：无条件写入 per-seed seed_strategy 版本标记，
        # 与 run_e1a_l2_shift_full.py L433 一致，供 is_checkpoint_complete 校验，
        # 避免断点续传时新旧种子策略结果静默混用。R6修复错误地将标记写入放在
        # if out_path.exists() 条件块内，首次运行时文件不存在导致标记永远不写入。
        all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION
        out_path = run_dir / "l2_shift_results.json"
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            sk = f"seed{seed}"
            if sk not in existing:
                existing[sk] = {}
            existing[sk].update(seed_results)
            existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 续传也写入
            all_results = existing
        all_results["label_encoding"] = encoding
        out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()