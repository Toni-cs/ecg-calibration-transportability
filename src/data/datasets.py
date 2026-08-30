"""数据集模块: 消费 preprocess_cinc2021.py 输出的 npy + metadata CSV

关键事实（已核对 scripts/preprocess_cinc2021.py 源码）：
- 输出 ``metadata_single_label.csv``，列名固定为
  ``id, label, npy_path, fs, original_len``；npy_path 是文件名（相对 data 目录）
- npy 形状为 ``(n_leads=12, seq_length)``（通道优先），float32
- **预处理脚本只做重采样+定长(补零/截断)过滤，不做任何归一化** —— 因此
  per-record z-score（逐导联）在本模块的 Dataset 内执行（协议§2"归一化统计量
  只来自train split"由此约束：per-record 模式天然只用单条记录自身，无跨集泄漏；
  全局统计量模式必须 fit_train_stats()(仅train实例)/apply_stats()(其他实例)）

归一化协议（对应协议§2）：
- normalize="per_record"（默认）：逐记录逐导联 z-score，μ/σ来自该记录自身；
  对任一split都无信息泄漏，无需全局统计
- normalize="global"：逐导联全局 μ/σ；统计量只能来自train split实例的
  fit_train_stats()，val/cal/test实例通过 apply_stats() 复用——任何在非train
  split上重新拟合统计量的用法都违反协议且会被本模块拒绝（apply_stats只接受
  显式传入的统计量，不做自动拟合）

增广（transform）只应挂在train实例上（协议§2"增广只作用于train"），本模块
不代为判断——由调用方通过split_indices保证。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping as MappingType, Optional, Sequence

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from src.data.splits import DEFAULT_RATIOS, patient_wise_split

__all__ = ["ECGNPZDataset", "SyntheticECGDatasetV2"]

_EPS = 1e-8  # 防止零方差导联除零（恒定导联→输出全0）


class ECGNPZDataset(Dataset):
    """ECG npy 数据集（消费 preprocess_cinc2021.py 输出格式）

    参数
    ----
    metadata_csv : str|Path
        preprocess 输出的 metadata_single_label.csv（列: id/label/npy_path/...）
    data_dir : str|Path, optional
        npy 目录；默认 metadata_csv 同级的 ``data/``（与preprocess输出结构一致）
    split_indices : 序列, optional
        保留的metadata行位置索引（患者级划分后传入该split的行号；顺序保持）
    transform : callable, optional
        对归一化后的信号 (n_leads, seq) 做变换（增广只用于train，协议§2）
    normalize : str
        "per_record"（默认）| "global" | None
    label_map : dict, optional
        {原始标签串: 类别索引}；缺省按排序后的唯一标签自动编码。
        CINC2021预处理产物标签为 {"Normal","Rhythm","CD","ST","Other"}
        （ECGMatch式4组+Normal），如需映射到Wagner 5超类在此显式提供。
    expected_leads : int
        导联数校验（默认12；L2移位阶梯中降导联是eval-time置零，不在此处理）
    split_role : str
        本实例的split角色（"train"/"cal"/"test"，默认"train"）。协议§2守卫：
        fit_train_stats() 只允许 split_role=="train" 的实例调用；stats dict
        携带 ``source=split_role`` 溯源字段，apply_stats() 只接受
        source=="train" 的统计量（防"在非train split上冒充统计量"）。

    __getitem__ 返回 ``(signal: float32 tensor (n_leads, seq), label: int)``
    """

    _VALID_SPLIT_ROLES = ("train", "cal", "test")

    def __init__(
        self,
        metadata_csv,
        data_dir=None,
        split_indices: Optional[Sequence[int]] = None,
        transform: Optional[Callable] = None,
        normalize: str = "per_record",
        label_map: Optional[MappingType] = None,
        expected_leads: int = 12,
        split_role: str = "train",
    ):
        if normalize not in ("per_record", "global", None):
            raise ValueError(f"normalize必须是'per_record'/'global'/None, 得到: {normalize}")
        if split_role not in self._VALID_SPLIT_ROLES:
            raise ValueError(
                f"split_role必须是{'/'.join(self._VALID_SPLIT_ROLES)}, 得到: {split_role!r}"
            )
        self.metadata_csv = Path(metadata_csv)
        if not self.metadata_csv.exists():
            raise FileNotFoundError(f"metadata CSV不存在: {self.metadata_csv}")
        self.data_dir = Path(data_dir) if data_dir is not None else self.metadata_csv.parent / "data"

        meta = pd.read_csv(self.metadata_csv)
        missing_cols = {"id", "label", "npy_path"} - set(meta.columns)
        if missing_cols:
            raise KeyError(
                f"metadata CSV缺少必需列 {missing_cols}（preprocess_cinc2021.py "
                f"输出列为 id/label/npy_path/fs/original_len）"
            )
        if split_indices is not None:
            idx = np.asarray(split_indices, dtype=int)
            if idx.size and (idx.min() < 0 or idx.max() >= len(meta)):
                raise IndexError(
                    f"split_indices越界: [{idx.min()}, {idx.max()}] "
                    f"vs 行数 {len(meta)}"
                )
            meta = meta.iloc[idx].reset_index(drop=True)
        self.metadata = meta

        self.record_ids = meta["id"].tolist()
        self.raw_labels = meta["label"].tolist()
        if label_map is not None:
            unknown = sorted(set(self.raw_labels) - set(label_map))
            if unknown:
                raise KeyError(f"出现label_map未覆盖的标签: {unknown}")
            self.classes = sorted(label_map, key=lambda k: label_map[k])
            self.class_to_idx = dict(label_map)
        else:
            self.classes = sorted(set(self.raw_labels))
            self.class_to_idx = {c: i for i, c in enumerate(self.classes)}
        self.y = np.array([self.class_to_idx[c] for c in self.raw_labels], dtype=np.int64)

        self.transform = transform
        self.normalize = normalize
        self.expected_leads = expected_leads
        self.split_role = split_role
        self.stats_: Optional[dict] = None  # 全局统计量（只允许来自train fit）

        paths = []
        for name in meta["npy_path"]:
            p = self.data_dir / str(name)
            if not p.exists():
                raise FileNotFoundError(f"npy文件缺失: {p}")
            paths.append(p)
        self.npy_paths = paths

    def __len__(self) -> int:
        return len(self.npy_paths)

    def _load_signal(self, path: Path) -> np.ndarray:
        try:
            x = np.load(path, allow_pickle=False)
        except Exception as e:
            # 损坏/不可读的npy必须带路径可定位（MINOR-7）
            raise ValueError(f"损坏或不可读的npy: {path}") from e
        if x.ndim != 2:
            raise ValueError(f"期望2D信号(n_leads, seq), 得到shape {x.shape}: {path}")
        if x.shape[0] != self.expected_leads:
            raise ValueError(
                f"导联数不符: {x.shape[0]} != expected_leads={self.expected_leads}: {path}"
            )
        x = x.astype(np.float32, copy=False)
        if not np.isfinite(x).all():
            # NaN/Inf静默传播会污染归一化统计量与训练（MAJOR-5），fail-fast
            raise ValueError(f"信号含NaN/Inf: {path}")
        return x

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        """逐导联归一化：per_record用自身统计；global用train拟合统计"""
        if self.normalize is None:
            return x
        if self.normalize == "per_record":
            mu = x.mean(axis=1, keepdims=True)
            sd = x.std(axis=1, keepdims=True)
            return (x - mu) / (sd + _EPS)  # 零方差导联(x-mu)=0 → 输出全0
        if self.stats_ is None:
            raise RuntimeError(
                "normalize='global'但尚未设置统计量：必须先在train实例调用"
                "fit_train_stats()，再对其余实例apply_stats()（协议§2："
                "归一化统计量只来自train split）"
            )
        mu = self.stats_["mean"][:, None]
        sd = self.stats_["std"][:, None]
        return (x - mu) / (sd + _EPS)

    def __getitem__(self, idx: int):
        x = self._load_signal(self.npy_paths[idx])
        x = self._normalize(x)
        if self.transform is not None:
            x = self.transform(x)
        return torch.as_tensor(np.ascontiguousarray(x), dtype=torch.float32), int(self.y[idx])

    # ---------------- 全局统计量协议（统计量只来自train） ----------------

    def fit_train_stats(self) -> dict:
        """在**本实例**（必须是train split实例）上拟合逐导联全局 μ/σ

        流式累加 sum/sumsq，避免一次性载入全部信号。统计量**成功计算完毕后**
        才写入 stats_ 并切换到 global 归一化模式（先算完、后提交：迭代中途
        失败不留下"normalize已切global但统计量缺失/被污染"的损坏状态）。
        结果dict携带 ``source``（=split_role，恒为"train"）供 apply_stats
        溯源校验。其余split实例必须用 apply_stats() 复用本结果。

        违反协议（split_role != "train"，如在test split实例上调用）时
        raise ValueError——归一化统计量只允许从train split拟合（协议§2）。
        """
        if self.split_role != "train":
            raise ValueError("归一化统计量只允许从train split拟合（协议§2）")
        n_leads = None
        total, s, sq = 0, None, None
        for path in self.npy_paths:
            x = self._load_signal(path)
            if n_leads is None:
                n_leads = x.shape[0]
                s = np.zeros(n_leads, dtype=np.float64)
                sq = np.zeros(n_leads, dtype=np.float64)
            elif x.shape[0] != n_leads:
                raise ValueError(f"导联数不一致: {x.shape[0]} vs {n_leads}")
            s += x.sum(axis=1)
            sq += (x.astype(np.float64) ** 2).sum(axis=1)
            total += x.shape[1]
        if not total:
            raise RuntimeError("空数据集，无法拟合统计量")
        mean = s / total
        var = np.maximum(sq / total - mean ** 2, 0.0)  # 数值防护：方差非负
        stats = {"mean": mean, "std": np.sqrt(var),
                 "n_records": len(self.npy_paths), "n_samples": total,
                 "source": self.split_role}
        self.stats_ = stats  # 成功计算完才提交（MINOR-9：失败不留损坏状态）
        if self.normalize == "per_record":
            self.normalize = "global"  # 拟合成功后激活全局模式
        return stats

    def apply_stats(self, stats: MappingType) -> None:
        """应用**来自train split**的全局统计量（val/cal/test实例专用）

        统计量只能由train实例的fit_train_stats()产生后显式传入——本方法
        不做任何数据统计，从接口上杜绝"用val/cal/test重算统计量"的泄漏路径。
        统计量dict必须携带 ``source=="train"`` 溯源字段（fit_train_stats
        自动写入），缺失或非"train"一律拒绝（防统计量被非train实例冒充）。
        """
        source = stats.get("source")
        if source != "train":
            raise ValueError(
                f"统计量来源校验失败: 期望source=='train', 得到source={source!r}"
                "（协议§2：归一化统计量只来自train split）"
            )
        mean = np.asarray(stats["mean"], dtype=np.float64)
        std = np.asarray(stats["std"], dtype=np.float64)
        probe = self._load_signal(self.npy_paths[0]) if self.npy_paths else None
        if probe is not None and mean.shape[0] != probe.shape[0]:
            raise ValueError(
                f"统计量导联数 {mean.shape[0]} 与数据导联数 {probe.shape[0]} 不一致"
            )
        self.stats_ = {"mean": mean, "std": std, "source": source}
        if self.normalize == "per_record":
            self.normalize = "global"


class SyntheticECGDatasetV2(Dataset):
    """多患者结构合成ECG数据集（无需外部数据；供泄漏断言/划分测试/冒烟训练）

    与 scripts/train.py 的 SyntheticECGDataset（修复FATAL-6：__init__一次性
    生成并缓存，epoch间不再重随）同思路，但增加患者层级：
    - 每患者一个潜在类别先验 + 患者级信号偏置 → 同患者记录强相关，
      记录级随机划分会人为乐观，患者级划分才公平——因此适合做泄漏断言测试
    - 记录标签以 prob=0.85 忠于患者潜在类别，其余均匀重抽
    - 信号 = 类别基础形态 + 患者偏置 + 记录级噪声（float32, (n_leads, seq)）

    属性：X (n_records, n_leads, seq), y, patient_ids, record_patient
    """

    def __init__(
        self,
        n_patients: int = 50,
        records_per_patient: int = 4,
        n_leads: int = 12,
        seq_length: int = 1000,
        n_classes: int = 5,
        seed: int = 42,
        label_loyalty: float = 0.85,
    ):
        if n_patients < 1 or records_per_patient < 1:
            raise ValueError("n_patients与records_per_patient必须>=1")
        g = np.random.default_rng(seed)
        self.n_patients = n_patients
        self.records_per_patient = records_per_patient
        self.n_classes = n_classes
        self.patient_ids = np.arange(1, n_patients + 1)
        self.patient_class = g.integers(0, n_classes, size=n_patients)
        # 患者级偏置让同患者记录相关（模拟真实"同一患者多条记录"结构）
        patient_offset = g.normal(0.0, 0.05, size=(n_patients, n_leads, 1))
        class_wave = g.normal(0.0, 1.0, size=(n_classes, n_leads, seq_length))

        X = np.empty((n_patients * records_per_patient, n_leads, seq_length), dtype=np.float32)
        y = np.empty(n_patients * records_per_patient, dtype=np.int64)
        rec_patient = np.empty(n_patients * records_per_patient, dtype=np.int64)
        k = 0
        for p in range(n_patients):
            for _ in range(records_per_patient):
                c = int(self.patient_class[p])
                if g.random() >= label_loyalty:
                    c = int(g.integers(0, n_classes))
                X[k] = (class_wave[c] + patient_offset[p]
                        + g.normal(0.0, 0.1, size=(n_leads, seq_length))).astype(np.float32)
                y[k] = c
                rec_patient[k] = self.patient_ids[p]
                k += 1
        self.X = X
        self.y = y
        self.record_patient = rec_patient

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, idx: int):
        return torch.as_tensor(self.X[idx]), int(self.y[idx])

    def patient_label_map(self) -> dict:
        """患者多数标签映射（供 patient_wise_split 的 label_for_patient 参数）"""
        return {int(pid): int(c) for pid, c in zip(self.patient_ids, self.patient_class)}

    def split_by_patient(
        self,
        ratios: Sequence[float] = DEFAULT_RATIOS,
        seed: int = 42,
    ) -> dict[str, dict]:
        """患者级划分→记录索引视图（{"train": {"patients": [...], "record_indices": array}, ...}）

        与 src.data.splits.patient_wise_split 同种子同逻辑，便于测试泄漏断言。
        """
        splits = patient_wise_split(
            self.patient_ids.tolist(),
            self.patient_label_map(),
            ratios=ratios,
            seed=seed,
        )
        out = {}
        for name, pids in splits.items():
            pid_set = set(pids)
            rec_idx = np.flatnonzero(np.isin(self.record_patient, list(pid_set)))
            out[name] = {"patients": list(pids), "record_indices": rec_idx}
        return out


if __name__ == "__main__":
    import tempfile

    # 自检：合成npy+CSV → ECGNPZDataset 归一化与全局统计协议
    rng = np.random.default_rng(0)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_dir = root / "data"
        data_dir.mkdir()
        rows = []
        for i in range(6):
            x = rng.normal(5.0, 2.0, size=(12, 200)).astype(np.float32)  # 非零均值/方差
            np.save(data_dir / f"R{i}.npy", x)
            rows.append({"id": f"R{i}", "label": "Normal" if i % 2 else "MI",
                         "npy_path": f"R{i}.npy", "fs": 500, "original_len": 200})
        pd.DataFrame(rows).to_csv(root / "metadata_single_label.csv", index=False)
        ds = ECGNPZDataset(root / "metadata_single_label.csv")
        x, y = ds[0]
        assert x.shape == (12, 200) and isinstance(y, int)
        assert abs(float(x.mean()) ) < 1e-5, "per-record z-score应使均值≈0"
        stats = ds.fit_train_stats()
        assert ds.normalize == "global" and stats["mean"].shape == (12,)
        ds2 = ECGNPZDataset(root / "metadata_single_label.csv")
        ds2.apply_stats(stats)
        x2, _ = ds2[0]
        assert x2.shape == (12, 200)
    # 自检：SyntheticECGDatasetV2 患者级划分无泄漏
    syn = SyntheticECGDatasetV2(n_patients=30, records_per_patient=4, seq_length=200, seed=7)
    assert len(syn) == 120
    sp = syn.split_by_patient(seed=7)
    from src.data.splits import assert_no_leakage
    assert assert_no_leakage({k: v["patients"] for k, v in sp.items()}) is True
    assert sum(len(v["record_indices"]) for v in sp.values()) == 120
    print("[自检] 数据集模块通过")
