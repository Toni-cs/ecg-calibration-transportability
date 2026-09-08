"""数据完整性 QC：剔除含 NaN/Inf 的污染 ECG 记录（协议§13 数据完整性，R16）

背景：Chapman/PTB-XL 预处理（preprocess_*.py）在早期版本未对源信号做
isfinite QC，源 wfdb 里的坏导联段/人工伪迹采样（稀疏 NaN）被透传进
data/*.npy。ECGNPZDataset._load_signal 的 fail-fast 守卫会在运行时崩溃
（跨库 S1 前向 target test 时撞上），而非静默污染归一化统计量。

本脚本对**已产出**的 data 目录执行与 preprocess_*.py 的 QC 完全一致的过滤
（丢 0.1% 污染记录，标准 ECG QC；插值填充会引入系统性偏倚，故不采用）：
  1. 逐文件扫描 data/*.npy，收集含非有限值（NaN/Inf）的记录
  2. 把坏 npy 移到 <output_root>/quarantine_nonfinite/<id>.npy（不删除，可追溯）
  3. 从 metadata_single_label.csv 剔除对应行
  4. 写 qc_report.json（被剔除 id 清单 + 计数 + 标签分布影响）

用法（可复现）：
    python scripts/qc_drop_nonfinite.py --data-root data/chapman_processed_v2
对 PTB-XL 同样适用（--data-root data/ptbxl_processed）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def scan_nonfinite_ids(data_dir: Path) -> list[str]:
    """扫描 data/*.npy，返回 npy stem 中含非有限值的记录列表（可复现）"""
    bad = []
    for p in sorted(data_dir.glob("*.npy")):
        try:
            x = np.load(p, mmap_mode="r")
            if not np.isfinite(x).all():
                bad.append(p.stem)  # e.g. chapman_JS10765
        except Exception:
            bad.append(p.stem)  # 不可读也视为污染，一并 quarantine
    return bad


def qc_clean(output_root: Path, quarantine_name: str = "quarantine_nonfinite") -> dict:
    data_dir = output_root / "data"
    meta_csv = output_root / "metadata_single_label.csv"
    if not data_dir.is_dir() or not meta_csv.exists():
        raise FileNotFoundError(f"{output_root} 不是预处理产物目录"
                                f"(缺 data/ 或 metadata_single_label.csv)")

    meta = pd.read_csv(meta_csv)
    bad_ids = scan_nonfinite_ids(data_dir)
    if not bad_ids:
        print(f"[QC] {output_root}: 无污染记录，跳过")
        return {"n_scanned": len(meta), "n_removed": 0, "removed_ids": []}

    # 把坏 npy 移到 quarantine（不删除，可追溯）
    qdir = output_root / quarantine_name
    qdir.mkdir(parents=True, exist_ok=True)
    npy_removed = []
    for stem in bad_ids:
        src = data_dir / f"{stem}.npy"
        if src.exists():
            shutil.move(str(src), str(qdir / f"{stem}.npy"))
            npy_removed.append(stem)

    # 从 metadata 剔除对应行
    removed_meta = meta[meta["npy_path"].isin([f"{s}.npy" for s in npy_removed])]
    meta_clean = meta[~meta["npy_path"].isin([f"{s}.npy" for s in npy_removed])]
    meta_clean = meta_clean.reset_index(drop=True)
    meta_clean.to_csv(meta_csv, index=False)

    report = {
        "output_root": str(output_root.resolve()),
        "n_metadata_before": int(len(meta)),
        "n_metadata_after": int(len(meta_clean)),
        "n_removed": int(len(npy_removed)),
        "removed_ids": npy_removed,
        "label_dist_before": meta["label"].value_counts().sort_index().to_dict(),
        "label_dist_after": meta_clean["label"].value_counts().sort_index().to_dict(),
        "quarantine_dir": str(qdir.resolve()),
        "note": "剔除含NaN/Inf的污染记录（标准ECG QC；插值填充会引入偏倚故不采用）。"
                "对应 preprocess_*.py 的 isfinite QC 逻辑。",
    }
    (output_root / "qc_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[QC] {output_root}: 剔除 {len(npy_removed)}/{len(meta)} 条污染记录")
    print(f"  坏 id: {npy_removed}")
    print(f"  quarantine -> {qdir}\n  metadata 更新 + qc_report.json")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, required=True)
    args = ap.parse_args()
    qc_clean(args.data_root)


if __name__ == "__main__":
    main()
