"""验证 4类 ptbxl→cpsc 全 8 方法 OOD 正收益是否被独立指标（Brier/log loss/per-class acc）支持。
参照 verify_seed43_metrics.py 的 5类裁定逻辑，对 4类 ptbxl→cpsc 重写。"""
import sys, json
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.models.ecg_classifier import ECGClassifier
from src.data.mapping import SUBSPACE_CPSC
from src.utils.calibration_methods import CALIBRATION_METHODS
from src.utils.prior_shift import fit_em, fit_bbse
from train import set_seed, evaluate, create_dataloader, build_ptbxl_datasets, build_cpsc_datasets

SEED = 42
ARCH = "inceptiontime"
D_MODEL = 64
N_LAYERS = 2
K = 4
CLASS_NAMES = SUBSPACE_CPSC

CKPT = ROOT / f"checkpoints/transfer/ptbxl_cpsc/{ARCH}/seed{SEED}/best_model.pt"
JSON_PATH = CKPT.parent / "transfer_result.json"
SOURCE_DIR = ROOT / "data/ptbxl_processed"
TARGET_DIR = ROOT / "data/cpsc_processed"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
set_seed(SEED)

model = ECGClassifier(in_channels=12, d_model=D_MODEL, n_layers=N_LAYERS,
                      num_classes=K, dropout=0.1, backbone_type=ARCH).to(device)
ckpt = torch.load(CKPT, weights_only=False, map_location=device)
_ckpt_nc = ckpt.get("num_classes")
if _ckpt_nc is not None and _ckpt_nc != K:
    raise RuntimeError(f"Checkpoint num_classes={_ckpt_nc} != {K}")
model.load_state_dict(ckpt["model_state_dict"])
print(f"Loaded {CKPT.name} (epoch {ckpt.get('epoch','?')})")

src_ds, _ = build_ptbxl_datasets(str(SOURCE_DIR), SEED, limit=None, subspace=SUBSPACE_CPSC)
tgt_ds, _ = build_cpsc_datasets(str(TARGET_DIR), SEED, limit=None)

cal_loader = create_dataloader(src_ds["cal"], batch_size=64, shuffle=False, num_workers=0)
src_test_loader = create_dataloader(src_ds["test"], batch_size=64, shuffle=False, num_workers=0)
tgt_test_loader = create_dataloader(tgt_ds["test"], batch_size=64, shuffle=False, num_workers=0)

cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
ood_ev = evaluate(model, tgt_test_loader, device, compute_calibration=False)
cal_probs, cal_labels = cal_ev["probs"], cal_ev["labels"]
ood_probs_raw, ood_labels = ood_ev["probs"], ood_ev["labels"]

res = json.loads(JSON_PATH.read_text(encoding="utf-8"))

def multiclass_brier(probs, labels, K=K):
    y_onehot = np.eye(K)[labels]
    return float(np.mean(np.sum((probs - y_onehot) ** 2, axis=1)))

def multiclass_log_loss(probs, labels, eps=1e-12):
    p_true = probs[np.arange(len(labels)), labels]
    return float(-np.mean(np.log(np.clip(p_true, eps, 1.0))))

def per_class_acc(probs, labels, K=K):
    preds = probs.argmax(1)
    out = {}
    for k in range(K):
        m = labels == k
        out[k] = float((preds[m] == k).mean()) if m.sum() > 0 else float('nan')
    return out

def per_class_count(labels, K=K):
    return {k: int((labels == k).sum()) for k in range(K)}

def apply_prior(probs, weights):
    adj = probs * weights[None, :]
    return adj / adj.sum(axis=1, keepdims=True)

methods_ood = {}
for mname in ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet"]:
    fit_fn, apply_fn, _ = CALIBRATION_METHODS[mname]
    params = fit_fn(cal_probs, cal_labels)
    if params is None:
        methods_ood[mname] = ood_probs_raw
    else:
        methods_ood[mname] = apply_fn(ood_probs_raw, params)

for mname, fit_fn in [("em_prior", fit_em), ("bbse_prior", fit_bbse)]:
    result = fit_fn(cal_probs, cal_labels, ood_probs_raw)
    if result is None:
        methods_ood[mname] = ood_probs_raw
    else:
        w = result["pi_hat"] / result["pi_train"]
        methods_ood[mname] = apply_prior(ood_probs_raw, w)

print(f"\n{'='*80}")
print(f"4类 ptbxl→cpsc 独立指标验证 (OOD n={len(ood_labels)})")
print(f"{'='*80}")
print(f"  {'Method':<14} {'ΔECE':>8} {'ΔBrier':>8} {'ΔLogLoss':>9} {'ΔAcc':>8} {'判定':>6}")
print(f"  {'-'*60}")

raw_brier = multiclass_brier(ood_probs_raw, ood_labels)
raw_log = multiclass_log_loss(ood_probs_raw, ood_labels)
raw_acc = float((ood_probs_raw.argmax(1) == ood_labels).mean())

for mname in ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"]:
    p = methods_ood[mname]
    d_ece = res["methods"][mname]["ood"]["deltaECE"]
    d_brier = multiclass_brier(p, ood_labels) - raw_brier
    d_log = multiclass_log_loss(p, ood_labels) - raw_log
    d_acc = float((p.argmax(1) == ood_labels).mean()) - raw_acc
    ok = "✓" if (d_brier <= 0.001 and d_log <= 0.5) else "✗"
    print(f"  {mname:<14} {d_ece:>+8.4f} {d_brier:>+8.4f} {d_log:>+9.4f} {d_acc:>+8.4f} {ok:>6}")

print(f"\n  Raw: Brier={raw_brier:.4f} LogLoss={raw_log:.4f} Acc={raw_acc:.4f}")

print(f"\n  Per-class top-1 accuracy (OOD):")
print(f"  {'Class':<8} {'Count':>6} {'Raw':>8}", end="")
for mname in ["bbse_prior", "em_prior", "vector"]:
    print(f" {mname[:7]:>8}", end="")
print()
counts = per_class_count(ood_labels)
raw_pc = per_class_acc(ood_probs_raw, ood_labels)
for k in range(K):
    print(f"  {CLASS_NAMES[k]:<8} {counts[k]:>6} {raw_pc[k]:>8.4f}", end="")
    for mname in ["bbse_prior", "em_prior", "vector"]:
        pc = per_class_acc(methods_ood[mname], ood_labels)
        print(f" {pc[k]:>8.4f}", end="")
    print()