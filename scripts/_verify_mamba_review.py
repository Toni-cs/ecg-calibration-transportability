"""mamba 深度审查验证脚本"""
import sys
sys.path.insert(0, "D:/A1/ecg-lab-v2")

import torch
import torch.nn as nn
from src.models.ecg_classifier import ECGClassifier
from src.models.s4_backbone import ECGMambaBackbone, BiMambaBlock


print("=" * 70)
print("A. mamba d_model 推断验证")
print("=" * 70)
model = ECGClassifier(in_channels=12, d_model=64, n_layers=4, num_classes=5, backbone_type="mamba")
sd = model.state_dict()
print(f"backbone.proj.weight 存在? {'backbone.proj.weight' in sd}")
print(f"backbone.stem.0.weight 存在? {'backbone.stem.0.weight' in sd}")
print(f"backbone.stem.0.weight.shape = {tuple(sd['backbone.stem.0.weight'].shape)}")
print(f"推断 d_model = sd['backbone.stem.0.weight'].shape[0] = {sd['backbone.stem.0.weight'].shape[0]}")
print(f"真实 d_model = 64, 匹配? {sd['backbone.stem.0.weight'].shape[0] == 64}")

print()
print("=" * 70)
print("B. mamba n_layers 推断验证")
print("=" * 70)
for true_n_layers in [1, 2, 4, 6]:
    model = ECGClassifier(in_channels=12, d_model=64, n_layers=true_n_layers, num_classes=5, backbone_type="mamba")
    sd = model.state_dict()
    cnt = sum(1 for k in sd if k.endswith(".mixer.in_proj.weight"))
    print(f"  真实 n_layers={true_n_layers}: mixer.in_proj.weight 计数={cnt}, 当前(错误)推断={cnt}, 正确推断={cnt // 2}")

print()
print("详细: n_layers=2 的所有 mixer.in_proj.weight keys:")
model = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
sd = model.state_dict()
for k in sd:
    if k.endswith(".mixer.in_proj.weight"):
        print(f"  {k}  shape={tuple(sd[k].shape)}")

print()
print("=" * 70)
print("C. BiMambaBlock 对变长序列的兼容性")
print("=" * 70)
model = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
model.eval()
for seq_len in [5000, 2500, 1250, 100, 10, 1]:
    x = torch.randn(2, 12, seq_len)
    try:
        with torch.no_grad():
            logits, probs = model(x)
        print(f"  seq_len={seq_len:>5}: OK, output shape={tuple(logits.shape)}")
    except Exception as e:
        print(f"  seq_len={seq_len:>5}: FAIL - {type(e).__name__}: {e}")

print()
print("=" * 70)
print("D. BN running stats 与降采样（数值稳定性）")
print("=" * 70)
torch.manual_seed(42)
model = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
model.train()
for _ in range(50):
    x = torch.randn(16, 12, 5000)
    model(x)
model.eval()
bn = model.backbone.stem[1]
print(f"BN running_mean stats: mean={bn.running_mean.mean().item():.4f}, std={bn.running_mean.std().item():.4f}")
print(f"BN running_var stats:  mean={bn.running_var.mean().item():.4f}, std={bn.running_var.std().item():.4f}")
print(f"BN num_batches_tracked = {bn.num_batches_tracked.item()}")

with torch.no_grad():
    x_5000 = torch.randn(4, 12, 5000)
    x_1250 = torch.randn(4, 12, 1250)
    feat_5000 = model.backbone(x_5000)
    feat_1250 = model.backbone(x_1250)
print(f"seq_len=5000 backbone output: mean={feat_5000.mean().item():.4f}, std={feat_5000.std().item():.4f}")
print(f"seq_len=1250 backbone output: mean={feat_1250.mean().item():.4f}, std={feat_1250.std().item():.4f}")

print()
print("=" * 70)
print("E. d_state/d_conv/expand 不匹配时 load_state_dict 是否失败")
print("=" * 70)

print("\n[E.1] d_state 不匹配 (训练=32, eval=16)")
model_train = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
sd_train = ECGMambaBackbone(in_channels=12, d_model=64, n_layers=2, d_state=32).state_dict()
sd_full = model_train.state_dict()
for k in sd_full:
    if k in sd_train:
        sd_full[k] = sd_train[k]
model_eval_default = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
try:
    model_eval_default.load_state_dict(sd_full)
    print("  load_state_dict: OK (意外)")
except Exception as e:
    print(f"  load_state_dict: FAIL - {type(e).__name__}")
    missing = [k for k in sd_full if k not in model_eval_default.state_dict()]
    shape_mismatch = []
    eval_sd = model_eval_default.state_dict()
    for k in sd_full:
        if k in eval_sd and sd_full[k].shape != eval_sd[k].shape:
            shape_mismatch.append((k, tuple(sd_full[k].shape), tuple(eval_sd[k].shape)))
    print(f"  shape 不匹配的 key 数量: {len(shape_mismatch)}")
    for k, s1, s2 in shape_mismatch[:5]:
        print(f"    {k}: 训练{s1} vs eval{s2}")

print("\n[E.2] d_conv 不匹配 (训练=8, eval=4)")
sd_train = ECGMambaBackbone(in_channels=12, d_model=64, n_layers=2, d_conv=8).state_dict()
sd_full = model_train.state_dict()
for k in sd_full:
    if k in sd_train:
        sd_full[k] = sd_train[k]
model_eval_default = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
try:
    model_eval_default.load_state_dict(sd_full)
    print("  load_state_dict: OK (意外)")
except Exception as e:
    print(f"  load_state_dict: FAIL - {type(e).__name__}")
    eval_sd = model_eval_default.state_dict()
    shape_mismatch = [(k, tuple(sd_full[k].shape), tuple(eval_sd[k].shape)) for k in sd_full if k in eval_sd and sd_full[k].shape != eval_sd[k].shape]
    print(f"  shape 不匹配的 key 数量: {len(shape_mismatch)}")
    for k, s1, s2 in shape_mismatch[:5]:
        print(f"    {k}: 训练{s1} vs eval{s2}")

print("\n[E.3] expand 不匹配 (训练=4, eval=2)")
sd_train = ECGMambaBackbone(in_channels=12, d_model=64, n_layers=2, expand=4).state_dict()
sd_full = model_train.state_dict()
for k in sd_full:
    if k in sd_train:
        sd_full[k] = sd_train[k]
model_eval_default = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
try:
    model_eval_default.load_state_dict(sd_full)
    print("  load_state_dict: OK (意外)")
except Exception as e:
    print(f"  load_state_dict: FAIL - {type(e).__name__}")
    eval_sd = model_eval_default.state_dict()
    shape_mismatch = [(k, tuple(sd_full[k].shape), tuple(eval_sd[k].shape)) for k in sd_full if k in eval_sd and sd_full[k].shape != eval_sd[k].shape]
    print(f"  shape 不匹配的 key 数量: {len(shape_mismatch)}")
    for k, s1, s2 in shape_mismatch[:5]:
        print(f"    {k}: 训练{s1} vs eval{s2}")

print()
print("=" * 70)
print("F. 额外发现: mamba 的 mixer.in_proj.weight 也可用于推断 d_model")
print("=" * 70)
model = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
sd = model.state_dict()
k = [k for k in sd if k.endswith(".mixer.in_proj.weight")][0]
print(f"{k}.shape = {tuple(sd[k].shape)}")
print(f"in_proj.weight.shape = (2 * expand * d_model, d_model) = (2*2*64, 64) = (256, 64)")
print(f"推断 d_model = in_proj.weight.shape[1] = {sd[k].shape[1]}")
print(f"推断 expand = in_proj.weight.shape[0] / (2 * d_model) = {sd[k].shape[0] // (2 * sd[k].shape[1])}")

print()
print("=" * 70)
print("G. 额外发现: A_log 可推断 d_state, conv1d.weight 可推断 d_conv")
print("=" * 70)
k_alog = [k for k in sd if k.endswith(".mixer.A_log")][0]
k_conv = [k for k in sd if k.endswith(".mixer.conv1d.weight")][0]
print(f"A_log.shape = {tuple(sd[k_alog].shape)} = (expand * d_model, d_state) = (128, 16)")
print(f"推断 d_state = A_log.shape[1] = {sd[k_alog].shape[1]}")
print(f"conv1d.weight.shape = {tuple(sd[k_conv].shape)} = (d_inner, 1, d_conv) = (128, 1, 4)")
print(f"推断 d_conv = conv1d.weight.shape[2] = {sd[k_conv].shape[2]}")