"""训练脚本: ECG分类器训练（对抗性审查P0修复版）

修复清单（第一轮对抗审查）：
- [FATAL-1] 删除ECGClassifier不存在的kwargs（pooling/use_mamba）
- [FATAL-2] torch.load(weights_only=False)
- [FATAL-6] 全局种子管理 + 合成数据固定缓存（不再每epoch重随）
- [HIGH-7]  温度语义单一化：训练时T≡1冻结，温度只做后验TS
- [HIGH-8]  fit_temperature使用2D one-hot标准多分类分支（Guo et al. 2017）
- [HIGH-9]  train/val/cal/test四分割：ECE早停用val、温度拟合用cal、
            最终报告只用test（各集互不重叠）
- [HIGH-12] 梯度裁剪 + NaN防护
- [HIGH-13] val/test loader drop_last=False + loss按样本数加权
- [HIGH-14] bootstrap固定rng + 早停路径跳过CI（只在最终报告算）
- [MED-17]  checkpoint目录含dataset/seed，互相不覆盖

用法：
    python scripts/train.py --dataset synthetic --epochs 5
    python scripts/train.py --dataset ptbxl --data_dir ./data/ptbxl
"""

import os
import sys
import random
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.ecg_classifier import ECGClassifier
from src.utils.calibration import (
    compute_all_metrics, fit_temperature, apply_temperature, plot_reliability_diagram,
    smooth_ece, benefit_inference,
)


def set_seed(seed: int, deterministic: bool = False):
    """全局种子管理（numpy/random/torch/cuda）"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'


class ECGDataset(Dataset):
    """ECG数据集基类（子类实现__getitem__和__len__）"""

    def __init__(self, data_dir: str, split: str = 'train'):
        self.data_dir = Path(data_dir)
        self.split = split
        self.samples = []

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        raise NotImplementedError


class SyntheticECGDataset(ECGDataset):
    """合成ECG数据集（种子固定，__init__时一次性生成并缓存）

    修复[FATAL-6]：旧版在__getitem__里每次重新randn，val集每个epoch都是
    新的随机数据，ECE早停等于对纯噪声做模型选择。现在缓存固定张量。
    """

    def __init__(
        self,
        n_samples: int = 1000,
        n_leads: int = 12,
        seq_length: int = 1000,
        n_classes: int = 5,
        split: str = 'train',
        seed: int = 42,
    ):
        super().__init__(data_dir="", split=split)
        self.n_classes = n_classes
        g = torch.Generator().manual_seed(seed)
        self.X = torch.randn(n_samples, n_leads, seq_length, generator=g)
        self.y = torch.randint(0, n_classes, (n_samples,), generator=g)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], int(self.y[idx])


def create_dataloader(
    dataset: Dataset,
    batch_size: int = 32,
    num_workers: int = 0,
    shuffle: bool = True,
    drop_last: bool = False,  # 修复[HIGH-13]：val/test不丢尾批
) -> DataLoader:
    """创建DataLoader"""
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=True,
        drop_last=drop_last,
    )


def train_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    epoch: int,
    max_grad_norm: float = 1.0,
) -> Dict[str, float]:
    """训练一个epoch（含梯度裁剪与NaN防护）"""
    model.train()
    total_loss = 0.0
    total_samples = 0
    correct = 0

    for batch_idx, (x, y) in enumerate(dataloader):
        x, y = x.to(device), y.to(device)

        optimizer.zero_grad()
        logits, _ = model(x, return_probs=False)
        loss = F.cross_entropy(logits, y)

        if not torch.isfinite(loss):  # NaN防护
            print(f"[WARN] Epoch {epoch} batch {batch_idx}: non-finite loss, skipped")
            optimizer.zero_grad()
            continue

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)  # 修复[HIGH-12]
        optimizer.step()

        bs = y.size(0)
        total_loss += loss.item() * bs  # 修复[HIGH-13]：按样本数加权
        total_samples += bs
        _, predicted = logits.max(1)
        correct += predicted.eq(y).sum().item()

    return {
        'train_loss': total_loss / max(total_samples, 1),
        'train_acc': 100. * correct / max(total_samples, 1),
    }


def evaluate(
    model: nn.Module,
    dataloader: DataLoader,
    device: torch.device,
    compute_calibration: bool = True,
) -> Dict[str, Any]:
    """评估模型（返回probs矩阵供后续温度拟合复用）"""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    all_probs, all_labels = [], []

    with torch.no_grad():
        for x, y in dataloader:
            x, y = x.to(device), y.to(device)
            logits, probs = model(x)
            loss = F.cross_entropy(logits, y)

            bs = y.size(0)
            total_loss += loss.item() * bs
            _, predicted = logits.max(1)
            correct += predicted.eq(y).sum().item()
            total += bs

            all_probs.append(probs.cpu().numpy())
            all_labels.append(y.cpu().numpy())

    all_probs = np.concatenate(all_probs, axis=0)
    all_labels = np.concatenate(all_labels, axis=0)

    results = {
        'loss': total_loss / max(total, 1),
        'acc': 100. * correct / max(total, 1),
        'probs': all_probs,
        'labels': all_labels,
    }

    if compute_calibration:
        if all_probs.ndim != 2:  # 修复[MED-20]：静默错误分支改为报错
            raise ValueError(f"evaluate期望2D概率矩阵，得到ndim={all_probs.ndim}")
        max_probs = all_probs.max(axis=1)
        correct_mask = (all_probs.argmax(axis=1) == all_labels).astype(float)
        cal_metrics = compute_all_metrics(max_probs, correct_mask, n_bootstrap=0)
        results.update(cal_metrics)

    return results


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    config: Dict[str, Any],
    device: torch.device,
) -> nn.Module:
    """完整训练流程：ECE早停用val集（模型选择），温度与最终报告用cal/test"""
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.get('lr', 1e-3),
        weight_decay=config.get('weight_decay', 1e-4),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=config.get('epochs', 100),
        eta_min=config.get('lr_min', 1e-6),
    )

    best_ece = float('inf')
    patience = config.get('patience', 10)
    patience_counter = 0

    save_dir = Path(config['save_dir'])
    save_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = save_dir / 'best_model.pt'

    epochs = config.get('epochs', 100)
    for epoch in range(epochs):
        train_metrics = train_epoch(model, train_loader, optimizer, device, epoch)
        val_metrics = evaluate(model, val_loader, device, compute_calibration=True)
        scheduler.step()

        print(f"Epoch {epoch+1}/{epochs} | "
              f"train_loss={train_metrics['train_loss']:.4f} "
              f"train_acc={train_metrics['train_acc']:.2f}% | "
              f"val_loss={val_metrics['loss']:.4f} "
              f"val_acc={val_metrics['acc']:.2f}% "
              f"ECE={val_metrics.get('ece', float('nan')):.4f}")

        current_ece = val_metrics.get('ece', float('inf'))
        if current_ece < best_ece:
            best_ece = current_ece
            patience_counter = 0
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'val_acc': val_metrics['acc'],
                'val_ece': current_ece,
            }, ckpt_path)
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch+1}")
                break

    if not ckpt_path.exists():
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'val_acc': val_metrics['acc'],
            'val_ece': val_metrics.get('ece', float('nan')),
        }, ckpt_path)

    # 修复[FATAL-2]：weights_only=False（自保存文件，含python标量）
    checkpoint = torch.load(ckpt_path, weights_only=False)
    model.load_state_dict(checkpoint['model_state_dict'])

    return model


def main():
    parser = argparse.ArgumentParser(description='Train ECG Classifier')
    parser.add_argument('--dataset', type=str, default='synthetic',
                        choices=['synthetic', 'ptbxl', 'chapman'])
    parser.add_argument('--data_dir', type=str, default='./data')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--batch_size', type=int, default=16)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--d_model', type=int, default=64,  # 修复：512会OOM
                        help='Hidden dimension')
    parser.add_argument('--n_layers', type=int, default=2)
    parser.add_argument('--num_classes', type=int, default=5)
    parser.add_argument('--seq_length', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--save_dir', type=str, default='checkpoints')
    args = parser.parse_args()

    set_seed(args.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}, seed={args.seed}")

    # ============ 四分割：train / val / cal / test（修复[HIGH-9]） ============
    if args.dataset == 'synthetic':
        datasets = {
            'train': SyntheticECGDataset(800, 12, args.seq_length, args.num_classes, 'train', seed=args.seed),
            'val':   SyntheticECGDataset(200, 12, args.seq_length, args.num_classes, 'val',   seed=args.seed + 1),
            'cal':   SyntheticECGDataset(200, 12, args.seq_length, args.num_classes, 'cal',   seed=args.seed + 2),
            'test':  SyntheticECGDataset(200, 12, args.seq_length, args.num_classes, 'test',  seed=args.seed + 3),
        }
    else:
        raise NotImplementedError(f"Dataset {args.dataset} not implemented yet")

    loaders = {
        'train': create_dataloader(datasets['train'], args.batch_size, shuffle=True, drop_last=True),
        'val':   create_dataloader(datasets['val'], args.batch_size, shuffle=False),
        'cal':   create_dataloader(datasets['cal'], args.batch_size, shuffle=False),
        'test':  create_dataloader(datasets['test'], args.batch_size, shuffle=False),
    }

    # ============ 模型：learnable_temp=False（修复[HIGH-7]） ============
    model = ECGClassifier(
        in_channels=12,
        d_model=args.d_model,
        n_layers=args.n_layers,
        num_classes=args.num_classes,
        dropout=0.1,
        learnable_temp=False,  # T≡1冻结训练；温度只做后验TS
    ).to(device)

    print(f"Model: d_model={args.d_model}, n_layers={args.n_layers}, "
          f"params={sum(p.numel() for p in model.parameters()):,}")

    # 保存目录含seed（修复[MED-17]）
    run_dir = Path(args.save_dir) / args.dataset / f"seed{args.seed}"
    run_dir.mkdir(parents=True, exist_ok=True)

    config = {
        'epochs': args.epochs,
        'lr': args.lr,
        'lr_min': 1e-6,
        'weight_decay': 1e-4,
        'patience': 10,
        'save_dir': str(run_dir),
    }

    model = train_model(model, loaders['train'], loaders['val'], config, device)

    # ============ 最终协议：温度在cal拟合，指标只在test报告 ============
    print(f"\n{'='*60}\nFinal Evaluation (temperature fitted on cal, reported on test)\n{'='*60}")

    cal_eval = evaluate(model, loaders['cal'], device, compute_calibration=False)
    test_eval = evaluate(model, loaders['test'], device, compute_calibration=True)

    probs_raw = test_eval['probs']        # (N, C)
    labels = test_eval['labels']          # (N,)
    max_probs_raw = probs_raw.max(axis=1)
    correct_mask = (probs_raw.argmax(axis=1) == labels).astype(float)

    # 修复[HIGH-8]+反例-1：fit_temperature走2D分支，且只用cal自己的标签
    # （第二轮反例验证发现旧接线用了test标签配cal概率——既泄漏又错配）
    one_hot_cal = np.eye(args.num_classes)[cal_eval['labels']]
    T = fit_temperature(cal_eval['probs'], one_hot_cal)
    print(f"Fitted temperature (on cal, cal labels): {T:.4f}")

    # 应用温度：2D矩阵级（全局TS不改变argmax，AUROC不变sanity check见协议）
    probs_cal = apply_temperature(probs_raw, T)
    max_probs_cal = probs_cal.max(axis=1)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bootstrap=1000)
    cal_m = compute_all_metrics(max_probs_cal, correct_mask, n_bootstrap=1000)

    # 论文主终点：ΔECE配对cluster bootstrap推断（benefit_inference，配对CI）
    rng = np.random.default_rng(args.seed)
    benefit = benefit_inference(
        max_probs_raw, max_probs_cal, correct_mask,
        metric=smooth_ece,  # 无分箱偏差的主估计量
        n_bootstrap=2000,
        rng=rng,
    )
    print(f"\n[主终点] SmoothECE raw={benefit['raw']:.4f} -> cal={benefit['cal']:.4f}")
    print(f"[主终点] ΔECE={benefit['benefit']:.4f} "
          f"[95% CI: {benefit['benefit_ci'][0]:.4f}, {benefit['benefit_ci'][1]:.4f}] (配对bootstrap)")
    print(f"[次要] 比值R={benefit['ratio']:.2f} [{benefit['ratio_ci'][0]:.2f}, {benefit['ratio_ci'][1]:.2f}]")

    print(f"\nTest (raw):  acc={test_eval['acc']:.2f}%  ECE={raw_metrics['ece']:.4f} "
          f"[{raw_metrics['ece_ci_95'][0]:.4f}, {raw_metrics['ece_ci_95'][1]:.4f}]  "
          f"Brier(raw)={raw_metrics['brier_raw']:.4f}")
    print(f"Test (TS):   ECE={cal_m['ece']:.4f} "
          f"[{cal_m['ece_ci_95'][0]:.4f}, {cal_m['ece_ci_95'][1]:.4f}]  "
          f"Brier(TS)={cal_m['brier_raw']:.4f}")

    # Sanity check：全局TS不改变argmax（AUROC不变）
    assert np.array_equal(probs_raw.argmax(axis=1), probs_cal.argmax(axis=1)), \
        "全局温度缩放不应改变argmax——管道有bug"

    # 绘制校准曲线
    try:
        fig = plot_reliability_diagram(
            max_probs_cal, correct_mask,
            title=f"Reliability Diagram (T={T:.3f})",
            save_path=str(run_dir / 'reliability_diagram.png'),
        )
        import matplotlib.pyplot as plt
        plt.close(fig)  # 修复[MED-20]：close防内存泄漏
        print(f"\nReliability diagram saved to {run_dir}/reliability_diagram.png")
    except Exception as e:
        import traceback
        print(f"Warning: Could not plot reliability diagram: {e}")
        traceback.print_exc()

    print("\nTraining complete!")


if __name__ == '__main__':
    main()
