"""验证 seed43 反方向 (chapman→ptbxl) 的独立指标：Brier / log loss / per-class top-1 acc。
裁定 seed43 的 +0.097 是否 ECE 指标假象。"""
import sys
import json
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.models.ecg_classifier import ECGClassifier
from train import set_seed, evaluate, create_dataloader, build_ptbxl_datasets, build_chapman_datasets

SEED = 43
ARCH = "inceptiontime"
D_MODEL = 32
N_LAYERS = 2
CKPT = ROOT / f"checkpoints/transfer/chapman_ptbxl/{ARCH}/seed{SEED}/best_model.pt"
JSON_PATH = CKPT.parent / "transfer_result.json"
SOURCE_DIR = ROOT / "data/chapman_processed_v2"
TARGET_DIR = ROOT / "data/ptbxl_processed"

CLASS_NAMES = ("NORM", "MI", "STTC", "CD", "HYP")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
set_seed(SEED)

model = ECGClassifier(in_channels=12, d_model=D_MODEL, n_layers=N_LAYERS,
                      num_classes=5, dropout=0.1, backbone_type=ARCH).to(device)
ckpt = torch.load(CKPT, weights_only=False, map_location=device)
_ckpt_nc = ckpt.get("num_classes")
if _ckpt_nc is not None and _ckpt_nc != 5:
    raise RuntimeError(f"Checkpoint num_classes={_ckpt_nc} ≠ 5")
model.load_state_dict(ckpt["model_state_dict"])
print(f"Loaded checkpoint {CKPT.name} (epoch {ckpt.get('epoch','?')})")

src_ds, _ = build_chapman_datasets(str(SOURCE_DIR), SEED, limit=None)
src_loader = create_dataloader(src_ds["test"], batch_size=64, shuffle=False, num_workers=0)
id_ev = evaluate(model, src_loader, device, compute_calibration=False)
id_probs_raw = id_ev["probs"]
id_labels = id_ev["labels"]

tgt_ds, _ = build_ptbxl_datasets(str(TARGET_DIR), SEED, limit=None)
tgt_loader = create_dataloader(tgt_ds["test"], batch_size=64, shuffle=False, num_workers=0)
ood_ev = evaluate(model, tgt_loader, device, compute_calibration=False)
ood_probs_raw = ood_ev["probs"]
ood_labels = ood_ev["labels"]

res = json.loads(JSON_PATH.read_text(encoding="utf-8"))
w = np.array(res["methods"]["bbse_prior_pi"]["w"])
w_id = np.array(res["methods"]["bbse_prior_pi"]["w_ID"])
print(f"\nBBSE w (OOD):  {w}")
print(f"BBSE w_ID:     {w_id}")
print(f"BBSE pi_hat:   {res['methods']['bbse_prior_pi']['pi_hat']}")

def apply_prior(probs, weights):
    adj = probs * weights[None, :]
    return adj / adj.sum(axis=1, keepdims=True)

ood_probs_bbse = apply_prior(ood_probs_raw, w)
id_probs_bbse = apply_prior(id_probs_raw, w)

def multiclass_brier(probs, labels, K=5):
    y_onehot = np.eye(K)[labels]
    return float(np.mean(np.sum((probs - y_onehot) ** 2, axis=1)))

def multiclass_log_loss(probs, labels, eps=1e-12):
    p_true = probs[np.arange(len(labels)), labels]
    return float(-np.mean(np.log(np.clip(p_true, eps, 1.0))))

def per_class_acc(probs, labels, K=5):
    preds = probs.argmax(1)
    out = {}
    for k in range(K):
        m = labels == k
        out[k] = float((preds[m] == k).mean()) if m.sum() > 0 else float('nan')
    return out

def per_class_count(labels, K=5):
    return {k: int((labels == k).sum()) for k in range(K)}

print(f"\n{'='*70}")
print(f"OOD (target=PTB-XL, n={len(ood_labels)})")
print(f"{'='*70}")
print(f"  {'Metric':<25} {'Raw':>12} {'BBSE':>12} {'Delta':>12}")
print(f"  {'-'*61}")
print(f"  {'ECE':<25} {res['methods']['bbse_prior']['ood']['raw']:>12.4f} {res['methods']['bbse_prior']['ood']['cal']:>12.4f} {res['methods']['bbse_prior']['ood']['deltaECE']:>+12.4f}")
print(f"  {'Brier (multiclass)':<25} {multiclass_brier(ood_probs_raw, ood_labels):>12.4f} {multiclass_brier(ood_probs_bbse, ood_labels):>12.4f} {multiclass_brier(ood_probs_bbse, ood_labels)-multiclass_brier(ood_probs_raw, ood_labels):>+12.4f}")
print(f"  {'Log loss':<25} {multiclass_log_loss(ood_probs_raw, ood_labels):>12.4f} {multiclass_log_loss(ood_probs_bbse, ood_labels):>12.4f} {multiclass_log_loss(ood_probs_bbse, ood_labels)-multiclass_log_loss(ood_probs_raw, ood_labels):>+12.4f}")
raw_acc = float((ood_probs_raw.argmax(1) == ood_labels).mean())
bbse_acc = float((ood_probs_bbse.argmax(1) == ood_labels).mean())
print(f"  {'Top-1 Accuracy':<25} {raw_acc:>12.4f} {bbse_acc:>12.4f} {bbse_acc-raw_acc:>+12.4f}")

print(f"\n  Per-class top-1 accuracy (OOD):")
print(f"  {'Class':<10} {'Count':>8} {'Raw Acc':>12} {'BBSE Acc':>12} {'Delta':>12}")
print(f"  {'-'*54}")
raw_pc = per_class_acc(ood_probs_raw, ood_labels)
bbse_pc = per_class_acc(ood_probs_bbse, ood_labels)
counts = per_class_count(ood_labels)
for k in range(5):
    delta = bbse_pc[k] - raw_pc[k] if not (np.isnan(raw_pc[k]) or np.isnan(bbse_pc[k])) else float('nan')
    print(f"  {CLASS_NAMES[k]:<10} {counts[k]:>8} {raw_pc[k]:>12.4f} {bbse_pc[k]:>12.4f} {delta:>+12.4f}")

print(f"\n{'='*70}")
print(f"ID (source=Chapman, n={len(id_labels)})")
print(f"{'='*70}")
print(f"  {'Metric':<25} {'Raw':>12} {'BBSE':>12} {'Delta':>12}")
print(f"  {'-'*61}")
print(f"  {'ECE':<25} {res['methods']['bbse_prior']['id']['raw']:>12.4f} {res['methods']['bbse_prior']['id']['cal']:>12.4f} {res['methods']['bbse_prior']['id']['deltaECE']:>+12.4f}")
print(f"  {'Brier (multiclass)':<25} {multiclass_brier(id_probs_raw, id_labels):>12.4f} {multiclass_brier(id_probs_bbse, id_labels):>12.4f} {multiclass_brier(id_probs_bbse, id_labels)-multiclass_brier(id_probs_raw, id_labels):>+12.4f}")
print(f"  {'Log loss':<25} {multiclass_log_loss(id_probs_raw, id_labels):>12.4f} {multiclass_log_loss(id_probs_bbse, id_labels):>12.4f} {multiclass_log_loss(id_probs_bbse, id_labels)-multiclass_log_loss(id_probs_raw, id_labels):>+12.4f}")
raw_acc_id = float((id_probs_raw.argmax(1) == id_labels).mean())
bbse_acc_id = float((id_probs_bbse.argmax(1) == id_labels).mean())
print(f"  {'Top-1 Accuracy':<25} {raw_acc_id:>12.4f} {bbse_acc_id:>12.4f} {bbse_acc_id-raw_acc_id:>+12.4f}")

print(f"\n  Per-class top-1 accuracy (ID):")
print(f"  {'Class':<10} {'Count':>8} {'Raw Acc':>12} {'BBSE Acc':>12} {'Delta':>12}")
print(f"  {'-'*54}")
raw_pc_id = per_class_acc(id_probs_raw, id_labels)
bbse_pc_id = per_class_acc(id_probs_bbse, id_labels)
counts_id = per_class_count(id_labels)
for k in range(5):
    delta = bbse_pc_id[k] - raw_pc_id[k] if not (np.isnan(raw_pc_id[k]) or np.isnan(bbse_pc_id[k])) else float('nan')
    print(f"  {CLASS_NAMES[k]:<10} {counts_id[k]:>8} {raw_pc_id[k]:>12.4f} {bbse_pc_id[k]:>12.4f} {delta:>+12.4f}")

print(f"\n{'='*70}")
print("裁定：BBSE OOD ΔECE=+0.097 是否指标假象？")
print(f"{'='*70}")
ood_brier_delta = multiclass_brier(ood_probs_bbse, ood_labels) - multiclass_brier(ood_probs_raw, ood_labels)
ood_logloss_delta = multiclass_log_loss(ood_probs_bbse, ood_labels) - multiclass_log_loss(ood_probs_raw, ood_labels)
ood_acc_delta = bbse_acc - raw_acc
print(f"  ECE delta:     +0.097 (改善)")
print(f"  Brier delta:   {ood_brier_delta:+.4f} ({'改善' if ood_brier_delta < 0 else '恶化'})")
print(f"  LogLoss delta: {ood_logloss_delta:+.4f} ({'改善' if ood_logloss_delta < 0 else '恶化'})")
print(f"  Acc delta:     {ood_acc_delta:+.4f} ({'改善' if ood_acc_delta > 0 else '恶化'})")
if ood_brier_delta < 0 and ood_logloss_delta < 0:
    print("\n  => Brier 和 LogLoss 都改善：+0.097 不是 ECE 假象，是真实改善")
elif ood_brier_delta > 0 or ood_logloss_delta > 0:
    print("\n  => Brier 或 LogLoss 恶化：+0.097 可能是 ECE 假象（ECE 不惩罚类覆盖）")