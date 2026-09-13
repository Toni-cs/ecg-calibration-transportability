"""L2 shift-ladder eval-only experiment (preregistered protocol §3:44-48).

For each existing checkpoint, apply 8 shift transforms (downsample + lead drop + gain)
on the target test set, and evaluate raw ECE plus post-calibration ECE for 8 methods, plus ΔECE.
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


def _maxprob(p):
    return np.asarray(p).max(axis=1)


def _bin(p, labels):
    return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def shifted_eval(model, dataset, shift, device, batch_size=64,
                 pair_id: str = None, arch: str = None, train_seed: int = None):
    """Apply the shift to every signal in the dataset, then evaluate the model."""
    if pair_id is None or arch is None or train_seed is None:
        raise ValueError(
            "pair_id, arch, train_seed must be explicitly provided for reproducible seed derivation"
        )
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    # Derive the noise seed from the experiment parameters so that noise stays
    # independent across experiments, shifts, and shift types. Use hashlib.md5
    # instead of the built-in hash() to ensure cross-process reproducibility
    # (independent of PYTHONHASHSEED). The derived key includes
    # pair_id|arch|train_seed|shift_name, so distinct experiments/shifts/types
    # always obtain distinct seeds.
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
    ap.add_argument("--shifts", nargs="+", default=None, help="run only the specified shifts (e.g. noise24 noise12); default all")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    num_classes = min(DATASET_NUM_CLASSES[args.source], DATASET_NUM_CLASSES[args.target])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None
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
        # Unconditionally write the per-seed seed_strategy version marker,
        # consistent with run_e1a_l2_shift_full.py L433, so that
        # is_checkpoint_complete can validate it and silently mixing old/new
        # seed-strategy results during resume is avoided. (The marker must not
        # be placed inside the if out_path.exists() block, otherwise it would
        # never be written on the first run when the file does not yet exist.)
        all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION
        out_path = run_dir / "l2_shift_results.json"
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            sk = f"seed{seed}"
            if sk not in existing:
                existing[sk] = {}
            existing[sk].update(seed_results)
            existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # also written on resume
            all_results = existing
        out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
