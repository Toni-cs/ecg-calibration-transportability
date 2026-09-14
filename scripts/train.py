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
import pandas as pd
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
    smooth_ece, benefit_inference, two_layer_benefit_inference,
)
from src.data.datasets import ECGNPZDataset
from src.data.splits import patient_wise_split
from src.data.mapping import SUPERCLASSES

# N1-r2 fix: 显式 n_bins 常量，与 run_e3_brier_dcr_ncv.py 对齐，避免依赖默认值
N_BINS = 10


def set_seed(seed: int, deterministic: bool = False):
    import random
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
        cal_metrics = compute_all_metrics(max_probs, correct_mask, n_bins=N_BINS, n_bootstrap=0)  # N1-r2 fix: explicit n_bins
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
                'num_classes': getattr(model, 'num_classes', None),
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
            'num_classes': getattr(model, 'num_classes', None),
            'val_acc': val_metrics['acc'],
            'val_ece': val_metrics.get('ece', float('nan')),
        }, ckpt_path)

    # 修复[FATAL-2]：weights_only=False（自保存文件，含python标量）
    checkpoint = torch.load(ckpt_path, weights_only=False)
    model.load_state_dict(checkpoint['model_state_dict'])

    return model


def _carve_val_patients(pat_label: dict, frac: float, seed: int) -> set:
    """患者级val carve：按患者多数标签分层随机抽frac比例患者（确定性）"""
    rng = np.random.default_rng(seed)
    val_patients: set = set()
    for lab in sorted(set(pat_label.values())):
        members = sorted(p for p, l in pat_label.items() if l == lab)
        members = list(np.asarray(members, dtype=object)[rng.permutation(len(members))])
        n_val = max(1, int(round(len(members) * frac)))
        val_patients.update(members[:n_val])
    return val_patients


def _pos_of_patients(meta: 'pd.DataFrame', patients) -> np.ndarray:
    return np.sort(np.flatnonzero(meta['patient_id'].isin(set(patients)).to_numpy()))


def _build_npz_datasets(meta: 'pd.DataFrame', meta_csv: Path, pos: dict,
                        label_map: dict):
    """按行号位置切分构建 ECGNPZDataset（roles: train/val→cal/cal/test）"""
    from src.data.datasets import ECGNPZDataset
    roles = {'train': 'train', 'val': 'cal', 'cal': 'cal', 'test': 'test'}
    return {
        name: ECGNPZDataset(meta_csv, split_indices=p.tolist(),
                            label_map=label_map, split_role=roles[name])
        for name, p in pos.items()
    }


def build_ptbxl_datasets(data_dir: str, seed: int, limit: Optional[int] = None,
                         subspace: Optional[tuple] = None):
    """真实PTB-XL四分割（协议§2）：folds1-8 train(+患者级val carve)/fold9 cal/fold10 test

    - 划分用 src.data.splits.ptbxl_official_folds（官方strat_fold，患者不跨折）
    - val carve：folds1-8内部按患者多数标签分层抽12.5%患者（患者级，防记录级泄漏）
    - assert_no_leakage 硬性断言 train/val/cal/test 患者两两不交（协议§2硬性脚本）
    - 返回 clusters_test（test记录的患者ID，按数据集顺序对齐）供主终点
      benefit_inference(clusters=) 患者级cluster bootstrap（F2遗留接线）
    - subspace：若提供（如SUBSPACE_CPSC），按子空间过滤并降级label_map（协议§2对称重算）
    """
    from src.data.splits import ptbxl_official_folds, assert_no_leakage
    from src.data.mapping import SUPERCLASSES

    data_dir = Path(data_dir)
    meta_csv = data_dir / 'metadata_single_label.csv'
    if not meta_csv.exists():
        raise FileNotFoundError(
            f"{meta_csv} 不存在——先运行 scripts/preprocess_ptbxl.py 生成")
    meta = pd.read_csv(meta_csv)
    missing = {'patient_id', 'strat_fold'} - set(meta.columns)
    if missing:
        raise KeyError(
            f"metadata 缺少列 {missing}（patient_id 为 F2 遗留必需列；"
            "请用 preprocess_ptbxl.py 重新预处理，vendor cinc 脚本不产出该列）")

    if subspace is not None:
        from src.data.mapping import filter_subspace
        rep = filter_subspace(meta['label'].tolist(), subspace)
        if rep['n_dropped'] > 0:
            print(f"[ptbxl] 子空间降级: 保留{rep['n_kept']}条 "
                  f"(子空间{rep['allowed']})，剔除{rep['n_dropped']}条 "
                  f"(分布{rep['dropped_counts']})")
        kept_indices = rep['kept_indices']
        meta_f = meta.iloc[kept_indices].reset_index(drop=True)
        label_map = {c: i for i, c in enumerate(subspace)}
        split_meta = meta_f
    else:
        label_map = {c: i for i, c in enumerate(SUPERCLASSES)}  # NORM,MI,STTC,CD,HYP→0..4
        kept_indices = None
        split_meta = meta

    unknown = sorted(set(split_meta['label']) - set(label_map))
    if unknown:
        raise KeyError(f"标签超出超类体系: {unknown}")

    folds_df = split_meta[['patient_id']].assign(fold=split_meta['strat_fold'])
    splits = ptbxl_official_folds(folds_df)

    # ---- folds1-8 内患者级 val carve（12.5%患者，按患者多数标签分层）----
    train_pos = np.sort(np.asarray(splits['train']['records'], dtype=int))
    meta18 = split_meta.loc[train_pos]
    pat_label = meta18.groupby('patient_id')['label'].agg(
        lambda s: s.mode().iat[0]).to_dict()
    val_patients = _carve_val_patients(pat_label, 0.125, seed + 100)
    train_patients = sorted(set(pat_label) - val_patients)

    cal_patients = sorted(set(np.asarray(splits['cal']['patients'], dtype=object).tolist()))
    test_patients = sorted(set(np.asarray(splits['test']['patients'], dtype=object).tolist()))

    # 硬性断言：四split患者两两不交（协议§2）
    assert_no_leakage({
        'train': train_patients, 'val': sorted(val_patients),
        'cal': cal_patients, 'test': test_patients,
    })

    def _pos_of(patients):
        return _pos_of_patients(split_meta, patients)

    pos = {'train': np.sort(train_pos), 'val': _pos_of(val_patients),
           'cal': _pos_of(cal_patients), 'test': _pos_of(test_patients)}
    if limit is not None:  # debug专用：每split截前 limit//4 条（确定性）
        pos = {k: v[:max(limit // 4, 20)] for k, v in pos.items()}

    # clusters_test 必须与 test 数据集顺序一致（split_indices保持给定顺序）
    clusters_test = split_meta.loc[pos['test'], 'patient_id'].to_numpy().astype(int)

    if kept_indices is not None:
        pos_orig = {k: np.array([kept_indices[i] for i in v], dtype=int)
                    for k, v in pos.items()}
    else:
        pos_orig = pos
    datasets = _build_npz_datasets(meta, meta_csv, pos_orig, label_map)

    print(f"[ptbxl] 患者级四分割: train({len(train_patients)}p/{len(pos['train'])}r) "
          f"val({len(val_patients)}p/{len(pos['val'])}r) "
          f"cal({len(cal_patients)}p/{len(pos['cal'])}r) "
          f"test({len(test_patients)}p/{len(pos['test'])}r)")
    print(f"[ptbxl] 标签分布(test): "
          f"{pd.Series(split_meta.loc[pos['test'], 'label']).value_counts().to_dict()}")
    return datasets, clusters_test


def build_chapman_datasets(data_dir: str, seed: int, limit: Optional[int] = None,
                           subspace: Optional[tuple] = None):
    """真实Chapman-Shaoxing四分割（协议§2：患者级分层70/10/20，固定种子）

    - patient_wise_split(0.7, 0.1, 0.2)→train/cal/test（患者多数标签分层）
    - val carve：train内部再抽1/7患者（→总比例≈60/10/10/20，患者级）
    - 每患者1条ECG（Zheng 2022），patient_id=记录号stem（preprocess输出）
    - assert_no_leakage 四split硬断言；clusters_test 接线同 ptbxl
    - subspace：若提供（如SUBSPACE_CPSC），按子空间过滤并降级label_map（协议§2对称重算）
    """
    from src.data.splits import patient_wise_split, assert_no_leakage
    from src.data.mapping import SUPERCLASSES

    data_dir = Path(data_dir)
    meta_csv = data_dir / 'metadata_single_label.csv'
    if not meta_csv.exists():
        raise FileNotFoundError(
            f"{meta_csv} 不存在——先运行 scripts/preprocess_chapman.py 生成")
    meta = pd.read_csv(meta_csv)
    if 'patient_id' not in meta.columns:
        raise KeyError("metadata 缺少 patient_id 列（请用 preprocess_chapman.py）")

    if subspace is not None:
        from src.data.mapping import filter_subspace
        rep = filter_subspace(meta['label'].tolist(), subspace)
        if rep['n_dropped'] > 0:
            print(f"[chapman] 子空间降级: 保留{rep['n_kept']}条 "
                  f"(子空间{rep['allowed']})，剔除{rep['n_dropped']}条 "
                  f"(分布{rep['dropped_counts']})")
        kept_indices = rep['kept_indices']
        meta_f = meta.iloc[kept_indices].reset_index(drop=True)
        label_map = {c: i for i, c in enumerate(subspace)}
        split_meta = meta_f
    else:
        label_map = {c: i for i, c in enumerate(SUPERCLASSES)}
        kept_indices = None
        split_meta = meta

    unknown = sorted(set(split_meta['label']) - set(label_map))
    if unknown:
        raise KeyError(f"标签超出超类体系: {unknown}")

    patients = split_meta['patient_id'].unique().tolist()
    pat_label = split_meta.groupby('patient_id')['label'].agg(
        lambda s: s.mode().iat[0]).to_dict()
    t3 = patient_wise_split(patients, pat_label,
                            ratios=(0.7, 0.1, 0.2), seed=seed)
    train_patients = sorted(set(t3['train']))
    cal_patients = sorted(set(t3['cal']))
    test_patients = sorted(set(t3['test']))

    # train 内 val carve：1/7 train患者 → 总体≈60/10/10/20
    sub = {p: pat_label[p] for p in train_patients}
    val_patients = _carve_val_patients(sub, 1 / 7, seed + 100)
    train_patients = sorted(set(train_patients) - val_patients)

    assert_no_leakage({
        'train': train_patients, 'val': sorted(val_patients),
        'cal': cal_patients, 'test': test_patients,
    })

    pos = {name: _pos_of_patients(split_meta, ps) for name, ps in
           {'train': train_patients, 'val': val_patients,
            'cal': cal_patients, 'test': test_patients}.items()}
    if limit is not None:
        pos = {k: v[:max(limit // 4, 20)] for k, v in pos.items()}

    clusters_test = split_meta.loc[pos['test'], 'patient_id'].to_numpy().astype(str)

    if kept_indices is not None:
        pos_orig = {k: np.array([kept_indices[i] for i in v], dtype=int)
                    for k, v in pos.items()}
    else:
        pos_orig = pos
    datasets = _build_npz_datasets(meta, meta_csv, pos_orig, label_map)

    print(f"[chapman] 患者级四分割: train({len(train_patients)}p/{len(pos['train'])}r) "
          f"val({len(val_patients)}p/{len(pos['val'])}r) "
          f"cal({len(cal_patients)}p/{len(pos['cal'])}r) "
          f"test({len(test_patients)}p/{len(pos['test'])}r)")
    print(f"[chapman] 标签分布(test): "
          f"{pd.Series(split_meta.loc[pos['test'], 'label']).value_counts().to_dict()}")
    return datasets, clusters_test


def build_cpsc_datasets(data_dir: str, seed: int, limit: Optional[int] = None):
    """CPSC2018+2019 四分割（协议§2：4类降级子空间，患者级分层70/10/20）

    - SUBSPACE_CPSC={NORM,CD,STTC,MI}（4类）；HYP(n=11)用filter_subspace剔除并计数
    - patient_wise_split(0.7, 0.1, 0.2)→train/cal/test（患者多数标签分层）
    - val carve：train内部再抽1/7患者（→总比例≈60/10/10/20，患者级）
    - 每条记录=1患者（patient_id=记录名），无strat_fold
    - assert_no_leakage 四split硬断言；clusters_test 接线同 ptbxl/chapman
    """
    from src.data.splits import patient_wise_split, assert_no_leakage
    from src.data.mapping import SUBSPACE_CPSC, filter_subspace

    data_dir = Path(data_dir)
    meta_csv = data_dir / 'metadata_single_label.csv'
    if not meta_csv.exists():
        raise FileNotFoundError(
            f"{meta_csv} 不存在——先运行 scripts/preprocess_cpsc.py 生成")
    meta = pd.read_csv(meta_csv)
    if 'patient_id' not in meta.columns:
        raise KeyError("metadata 缺少 patient_id 列（请用 preprocess_cpsc.py）")

    rep = filter_subspace(meta['label'].tolist(), SUBSPACE_CPSC)
    if rep['n_dropped'] > 0:
        print(f"[cpsc] 子空间降级: 保留{rep['n_kept']}条 "
              f"(子空间{rep['allowed']})，剔除{rep['n_dropped']}条 "
              f"(分布{rep['dropped_counts']})")
    kept_indices = rep['kept_indices']
    meta_f = meta.iloc[kept_indices].reset_index(drop=True)

    label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}
    unknown = sorted(set(meta_f['label']) - set(label_map))
    if unknown:
        raise KeyError(f"标签超出降级子空间: {unknown}")

    patients = meta_f['patient_id'].unique().tolist()
    pat_label = meta_f.groupby('patient_id')['label'].agg(
        lambda s: s.mode().iat[0]).to_dict()
    t3 = patient_wise_split(patients, pat_label,
                            ratios=(0.7, 0.1, 0.2), seed=seed)
    train_patients = sorted(set(t3['train']))
    cal_patients = sorted(set(t3['cal']))
    test_patients = sorted(set(t3['test']))

    sub = {p: pat_label[p] for p in train_patients}
    val_patients = _carve_val_patients(sub, 1 / 7, seed + 100)
    train_patients = sorted(set(train_patients) - val_patients)

    assert_no_leakage({
        'train': train_patients, 'val': sorted(val_patients),
        'cal': cal_patients, 'test': test_patients,
    })

    pos = {name: _pos_of_patients(meta_f, ps) for name, ps in
           {'train': train_patients, 'val': val_patients,
            'cal': cal_patients, 'test': test_patients}.items()}
    if limit is not None:
        pos = {k: v[:max(limit // 4, 20)] for k, v in pos.items()}

    clusters_test = meta_f.loc[pos['test'], 'patient_id'].to_numpy().astype(str)

    pos_orig = {k: np.array([kept_indices[i] for i in v], dtype=int)
                for k, v in pos.items()}
    datasets = _build_npz_datasets(meta, meta_csv, pos_orig, label_map)

    print(f"[cpsc] 患者级四分割: train({len(train_patients)}p/{len(pos['train'])}r) "
          f"val({len(val_patients)}p/{len(pos['val'])}r) "
          f"cal({len(cal_patients)}p/{len(pos['cal'])}r) "
          f"test({len(test_patients)}p/{len(pos['test'])}r)")
    print(f"[cpsc] 标签分布(test): "
          f"{pd.Series(meta_f.loc[pos['test'], 'label']).value_counts().to_dict()}")
    return datasets, clusters_test


def main():
    parser = argparse.ArgumentParser(description='Train ECG Classifier')
    parser.add_argument('--dataset', type=str, default='synthetic',
                        choices=['synthetic', 'ptbxl', 'chapman', 'cpsc'])
    parser.add_argument('--data_dir', type=str, default='./data')
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--batch_size', type=int, default=16)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--d_model', type=int, default=64,  # 修复：512会OOM
                        help='Hidden dimension')
    parser.add_argument('--n_layers', type=int, default=2)
    parser.add_argument('--arch', type=str, default='mamba',
                        choices=['mamba', 'resnet1d', 'inceptiontime'],
                        help='主干架构（协议§4三架构：mamba主/resnet1d/inceptiontime基线）')
    parser.add_argument('--num_classes', type=int, default=5)
    parser.add_argument('--seq_length', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--save_dir', type=str, default='checkpoints')
    parser.add_argument('--limit', type=int, default=None,
                        help='[debug] ptbxl每split截前limit/4条记录，冒烟用')
    parser.add_argument('--two-layer', action='store_true',
                        help='启用两层联合bootstrap（协议§7:117；温度拟合集不确定性'
                             '传入CI。真实数据阶段默认建议开启）')
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
        clusters_test = None  # 合成数据无患者结构（协议§11已登记）
    elif args.dataset == 'ptbxl':
        datasets, clusters_test = build_ptbxl_datasets(
            args.data_dir, args.seed, limit=args.limit)
    elif args.dataset == 'chapman':
        datasets, clusters_test = build_chapman_datasets(
            args.data_dir, args.seed, limit=args.limit)
    elif args.dataset == 'cpsc':
        datasets, clusters_test = build_cpsc_datasets(
            args.data_dir, args.seed, limit=args.limit)
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
        backbone_type=args.arch,
    ).to(device)

    print(f"Model arch={args.arch}: d_model={args.d_model}, n_layers={args.n_layers}, "
          f"params={sum(p.numel() for p in model.parameters()):,}")

    # 保存目录含seed+arch（修复[MED-17]）
    run_dir = Path(args.save_dir) / args.dataset / args.arch / f"seed{args.seed}"
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

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins
    cal_m = compute_all_metrics(max_probs_cal, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # N1-r2 fix: explicit n_bins

    # 论文主终点：ΔECE配对cluster bootstrap推断（benefit_inference，配对CI）
    # F2修复：n_bootstrap=10000（预注册§7:116 B=10,000，此前2000为违约）；
    # BCa默认（delete-group jackknife加速度）；真实数据（ptbxl）传患者级
    # clusters=clusters_test→leave-one-cluster-out（F2遗留已接线）
    rng = np.random.default_rng(args.seed)
    benefit = benefit_inference(
        max_probs_raw, max_probs_cal, correct_mask,
        metric=smooth_ece,  # 无分箱偏差的主估计量
        n_bootstrap=10000,
        rng=rng,
        clusters=clusters_test,  # 合成=None→记录级delete-group；ptbxl=患者ID
    )
    print(f"\n[主终点] SmoothECE raw={benefit['raw']:.4f} -> cal={benefit['cal']:.4f}")
    print(f"[主终点] ΔECE={benefit['benefit']:.4f} "
          f"[95% CI: {benefit['benefit_ci'][0]:.4f}, {benefit['benefit_ci'][1]:.4f}] "
          f"(配对bootstrap, {benefit['method']})")
    print(f"[次要] 比值R={benefit['ratio']:.2f} [{benefit['ratio_ci'][0]:.2f}, {benefit['ratio_ci'][1]:.2f}]")

    # 两层联合bootstrap（F2修复：协议§7:117实现就绪，--two-layer启用）
    if getattr(args, 'two_layer', False):
        two = two_layer_benefit_inference(
            probs_raw, labels_test=correct_mask,
            fit_probs=cal_eval['probs'],
            fit_labels=np.eye(args.num_classes)[cal_eval['labels']],
            fit_fn=fit_temperature,
            apply_fn=apply_temperature,
            metric=smooth_ece,
            b_val=200, b_test=2000,
            rng=np.random.default_rng(args.seed + 1),
        )
        print(f"[两层bootstrap] T̂={two['t_hat']:.4f} (sd={two['t_std']:.4f}) "
              f"ΔECE={two['benefit']:.4f} "
              f"[95% CI: {two['benefit_ci'][0]:.4f}, {two['benefit_ci'][1]:.4f}] "
              f"(T不确定性⊕重采样, B_val={two['b_val']}×B_test={two['b_test']})")

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
