"""E 部分修正验证：直接用不同 d_state/d_conv/expand 构造模型并加载"""
import sys
sys.path.insert(0, "D:/A1/ecg-lab-v2")

import torch
from src.models.ecg_classifier import ECGClassifier
from src.models.s4_backbone import ECGMambaBackbone


def make_sd(d_state=16, d_conv=4, expand=2):
    """构造一个完整 ECGClassifier 的 state_dict（含分类头），但 backbone 用指定超参"""
    backbone = ECGMambaBackbone(in_channels=12, d_model=64, n_layers=2,
                                d_state=d_state, d_conv=d_conv, expand=expand)
    model = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
    model.backbone = backbone
    return model.state_dict()


print("=" * 70)
print("E. d_state/d_conv/expand 不匹配时 load_state_dict 行为")
print("=" * 70)

cases = [
    ("d_state", 32, 16, dict(d_state=32), dict(d_state=16)),
    ("d_conv", 8, 4, dict(d_conv=8), dict(d_conv=4)),
    ("expand", 4, 2, dict(expand=4), dict(expand=2)),
]

for name, train_val, eval_val, train_kw, eval_kw in cases:
    print(f"\n[E.{name}] 训练 {name}={train_val}, eval {name}={eval_val}")
    sd_train = make_sd(**train_kw)
    model_eval = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
    try:
        model_eval.load_state_dict(sd_train)
        print(f"  load_state_dict(strict=True): OK (意外！)")
    except RuntimeError as e:
        msg = str(e)
        print(f"  load_state_dict(strict=True): FAIL - RuntimeError")
        if "size mismatch" in msg:
            lines = [l for l in msg.split("\n") if "size mismatch" in l]
            print(f"  size mismatch 行数: {len(lines)}")
            for l in lines[:3]:
                print(f"    {l.strip()}")
        else:
            print(f"  错误类型: {msg[:200]}")

print()
print("=" * 70)
print("E.4 验证: load_state_dict 默认 strict=True 对 shape 不匹配的行为")
print("=" * 70)
sd_train = make_sd(d_state=32)
model_eval = ECGClassifier(in_channels=12, d_model=64, n_layers=2, num_classes=5, backbone_type="mamba")
eval_sd = model_eval.state_dict()
mismatch_keys = []
for k in sd_train:
    if k in eval_sd and sd_train[k].shape != eval_sd[k].shape:
        mismatch_keys.append((k, tuple(sd_train[k].shape), tuple(eval_sd[k].shape)))
print(f"d_state=32 vs d_state=16: shape 不匹配的 key 数量 = {len(mismatch_keys)}")
for k, s1, s2 in mismatch_keys[:8]:
    print(f"  {k}: 训练{s1} vs eval{s2}")