"""验证 matrix scaling 与 Dirichlet 是否数学等价（同函数族两种参数化）。"""
import sys
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.models.ecg_classifier import ECGClassifier
from src.utils.calibration_methods import fit_matrix_scaling, apply_matrix_scaling, fit_dirichlet, apply_dirichlet
from train import set_seed, evaluate, create_dataloader, build_ptbxl_datasets, build_chapman_datasets

SEED, ARCH, D_MODEL, N_LAYERS = 42, "inceptiontime", 32, 2
CKPT = ROOT / f"checkpoints/transfer/ptbxl_chapman/{ARCH}/seed{SEED}/best_model.pt"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
set_seed(SEED)
model = ECGClassifier(in_channels=12, d_model=D_MODEL, n_layers=N_LAYERS,
                      num_classes=5, dropout=0.1, backbone_type=ARCH).to(device)
_ckpt = torch.load(CKPT, weights_only=False, map_location=device)
_ckpt_nc = _ckpt.get("num_classes")
if _ckpt_nc is not None and _ckpt_nc != 5:
    raise RuntimeError(f"Checkpoint num_classes={_ckpt_nc} ≠ 5")
model.load_state_dict(_ckpt["model_state_dict"])

src_ds, _ = build_ptbxl_datasets(str(ROOT / "data/ptbxl_processed"), SEED, limit=None)
cal_loader = create_dataloader(src_ds["cal"], batch_size=64, shuffle=False, num_workers=0)
test_loader = create_dataloader(src_ds["test"], batch_size=64, shuffle=False, num_workers=0)
cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
test_ev = evaluate(model, test_loader, device, compute_calibration=False)
cal_probs, cal_labels = cal_ev["probs"], cal_ev["labels"]
test_probs = test_ev["probs"]

pm = fit_matrix_scaling(cal_probs, cal_labels)
pd = fit_dirichlet(cal_probs, cal_labels)
out_m = apply_matrix_scaling(test_probs, pm)
out_d = apply_dirichlet(test_probs, pd)

diff = np.abs(out_m - out_d)
print(f"n_params matrix={pm['n_params']} dirichlet={pd['n_params']}")
print(f"max|p_mat - p_dir| = {diff.max():.2e}")
print(f"mean|p_mat - p_dir| = {diff.mean():.2e}")
print(f"\nmatrix M (近似恒等?):")
print(np.round(pm['M'], 4))
print(f"matrix b: {np.round(pm['b'], 4)}")