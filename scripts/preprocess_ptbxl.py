"""PTB-XL v1.0.3 预处理 → ECGNPZDataset 消费格式（协议§2 + §13-1集成层）

输入：PTB-XL v1.0.3 官方目录（ptbxl_database.csv + records500/）
输出：--output-root 下
  - metadata_single_label.csv：列 id/label/npy_path/fs/original_len +
    **patient_id/strat_fold**（F2遗留补列：患者级划分与clusters bootstrap依赖）
  - data/*.npy：float32 (n_leads=12, seq_length=5000)，500Hz×10s定长
  - preprocess_summary.json：STROBE式计数（总数/未映射排除/写入/分布）

标签：src.data.mapping.MAP_TO_5SUPERCLASS（Wagner 2020 五超类体系，
优先级 MI>STTC>CD>HYP>NORM，协议§2固定；窦性速率语句SBRAD/STACH/SARRH
→NORM，协议R13，2026-09-02修订）；不可映射记录剔除并单列计数
（协议§2"STROBE流程图：排除逐类计数"），**不做重映射**。

可恢复重跑：npy信号文件与label无关。输出目录已存在且含data/*.npy时，
配合 --overwrite 传参，脚本将跳过已存在npy的信号加载/重写，仅据源码CSV
+当前映射重建 metadata 与 summary（label源更新时无需重写信号）。

划分不在此脚本做：strat_fold 原样入CSV，患者级四分割由 train.py
（folds1-8 train(+val患者级 carve) / fold9 cal / fold10 test，协议§2）执行。

用法：
    python scripts/preprocess_ptbxl.py \
        --source-root ./data/ptb-xl/1.0.3 \
        --output-root ./data/ptbxl_processed
    # label源(映射)更新后仅重建元数据：
    python scripts/preprocess_ptbxl.py \
        --source-root ./data/ptb-xl/1.0.3 \
        --output-root ./data/ptbxl_processed --overwrite
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 复用vendor预处理的信号加载/重采样定长逻辑（逐字同一实现，保证两库格式一致）
from preprocess_cinc2021 import load_signal, resample_and_fix_length  # noqa: E402
from src.data.mapping import MAP_TO_5SUPERCLASS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess PTB-XL v1.0.3 into the ECGNPZDataset format "
                    "(with patient_id/strat_fold columns, F2遗留)."
    )
    parser.add_argument("--source-root", type=Path, required=True,
                        help="PTB-XL root containing ptbxl_database.csv and records500/.")
    parser.add_argument("--output-root", type=Path, required=True,
                        help="Output directory (metadata_single_label.csv + data/*.npy).")
    parser.add_argument("--sampling-rate", type=int, default=500)
    parser.add_argument("--signal-length", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None, help="Cap records (debug only).")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def ensure_output_dirs(output_root: Path, overwrite: bool) -> Path:
    data_dir = output_root / "data"
    if output_root.exists() and not overwrite:
        if (output_root / "metadata_single_label.csv").exists() or data_dir.exists():
            raise FileExistsError(
                f"Output already exists at {output_root}. Pass --overwrite to replace it.")
    output_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def main() -> None:
    args = parse_args()
    db_csv = args.source_root / "ptbxl_database.csv"
    if not db_csv.exists():
        raise FileNotFoundError(f"ptbxl_database.csv not found under {args.source_root}")
    data_dir = ensure_output_dirs(args.output_root, args.overwrite)

    db = pd.read_csv(db_csv)
    need_cols = {"ecg_id", "patient_id", "filename_lr", "scp_codes", "strat_fold"}
    missing = need_cols - set(db.columns)
    if missing:
        raise KeyError(f"ptbxl_database.csv missing columns {missing} "
                       "(确认下载的是完整 v1.0.3，而非仅波形子集)")
    if args.limit is not None:
        db = db.head(args.limit)

    rows: list[dict[str, object]] = []
    counters = {"total_records": 0, "skipped_unmappable": 0, "skipped_signal_error": 0,
                "skipped_existing": 0, "written": 0}
    unmapped_examples: list[str] = []

    for rec in db.itertuples(index=False):
        counters["total_records"] += 1
        try:
            scp_codes = ast.literal_eval(rec.scp_codes)
        except (ValueError, SyntaxError):
            counters["skipped_unmappable"] += 1
            continue
        if not isinstance(scp_codes, dict) or not scp_codes:
            counters["skipped_unmappable"] += 1
            continue

        label = MAP_TO_5SUPERCLASS(scp_codes)
        if label is None:
            # 协议§2 STROBE：官方无类/技术伪影记录剔除并单列计数，不重映射
            counters["skipped_unmappable"] += 1
            if len(unmapped_examples) < 20:
                unmapped_examples.append(f"{rec.ecg_id}:{sorted(scp_codes)}")
            continue

        record_id = f"ptbxl_{int(rec.ecg_id)}"
        npy_path = data_dir / f"{record_id}.npy"
        record_path = args.source_root / str(rec.filename_lr)

        if npy_path.exists():
            # 可恢复重跑：npy信号文件与label无关，已存在则跳过信号加载/重写，
            # 直接以目标长度重建metadata行（resample_and_fix_length恒输出
            # target_length=5000，故original_len恒等于target_length）。
            original_len = args.signal_length
            counters["skipped_existing"] += 1
            rows.append({
                "id": record_id,
                "label": label,
                "npy_path": npy_path.name,
                "fs": args.sampling_rate,
                "original_len": original_len,
                "patient_id": int(rec.patient_id),
                "strat_fold": int(rec.strat_fold),
            })
            continue

        try:
            signal, source_fs = load_signal(record_path)
            signal = resample_and_fix_length(
                signal, source_fs=source_fs,
                target_fs=args.sampling_rate, target_length=args.signal_length)
        except Exception:
            counters["skipped_signal_error"] += 1
            continue

        np.save(npy_path, signal)
        counters["written"] += 1
        rows.append({
            "id": record_id,
            "label": label,
            "npy_path": npy_path.name,
            "fs": args.sampling_rate,
            "original_len": int(signal.shape[1]),
            "patient_id": int(rec.patient_id),
            "strat_fold": int(rec.strat_fold),
        })

    if not rows:
        raise RuntimeError("No samples were produced. Check source-root integrity.")

    metadata = pd.DataFrame(rows).sort_values("id").reset_index(drop=True)
    metadata_path = args.output_root / "metadata_single_label.csv"
    metadata.to_csv(metadata_path, index=False)

    n_patients = metadata["patient_id"].nunique()
    per_patient = metadata.groupby("patient_id").size()
    summary = {
        "source_root": str(args.source_root.resolve()),
        "output_root": str(args.output_root.resolve()),
        "sampling_rate": args.sampling_rate,
        "signal_length": args.signal_length,
        "counts": counters,
        "n_patients": int(n_patients),
        "records_per_patient": {"mean": float(per_patient.mean()),
                                 "max": int(per_patient.max())},
        "label_distribution": metadata["label"].value_counts().sort_index().to_dict(),
        "fold_distribution": metadata["strat_fold"].value_counts().sort_index().to_dict(),
        "unmapped_examples": unmapped_examples,
        "mapping": "src.data.mapping.MAP_TO_5SUPERCLASS (Wagner 2020; MI>STTC>CD>HYP>NORM)",
    }
    summary_path = args.output_root / "preprocess_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    print(f"Wrote {counters['written']} samples "
          f"({n_patients} patients) to {args.output_root}")
    print(f"Unmapped excluded (STROBE): {counters['skipped_unmappable']}")
    print(f"Label distribution: {summary['label_distribution']}")
    print(f"Metadata: {metadata_path}\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
