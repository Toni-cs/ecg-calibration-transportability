"""Chapman-Shaoxing (ecg-arrhythmia 1.0.0, 20265患者) 预处理 → ECGNPZDataset 格式

输入：PhysioNet ecg-arrhythmia 1.0.0 解压目录
      （a-large-scale-...-1.0.0/WFDBRecords/XX/XXX/JSxxxxx.hea，#Dx: SNOMED码）
输出：与 preprocess_ptbxl.py 同构
  - metadata_single_label.csv：id/label/npy_path/fs/original_len/patient_id
    （Chapman每患者1条ECG，patient_id=记录号stem；无strat_fold——划分由
    train.py的 patient_wise_split 按协议§2患者级70/10/20执行）
  - data/*.npy：float32 (12, 5000) 500Hz×10s
  - preprocess_summary.json：STROBE计数 + 未映射SNOMED码频次表 + 码表覆盖率

Chapman 专用码表覆写（code_overrides，不动全局 SCP_TO_SUPERCLASS）：
  全局表为 CINC2021 定制，把 426177001(SB窦缓)/427084000(ST窦速) 归 STTC；
  但在 Chapman 语境这两者是**正常窦性节律的速率变体**，按 ECG 五超类应归
  NORM（窦性）。不覆写则 Chapman 91% 样本被判 STTC（严重类失衡伪影）。
  ——跨库语义冲突，登记协议敏感性对象，覆写仅作用于 Chapman 预处理。

用法：
    python scripts/preprocess_chapman.py \
        --source-root ./data/downloads/ecg-arrhythmia-1.0.0/a-large-scale-...-1.0.0 \
        --output-root ./data/chapman_processed_v2
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from preprocess_cinc2021 import load_signal, resample_and_fix_length  # noqa: E402
from src.data.mapping import SCP_TO_SUPERCLASS, MAP_TO_5SUPERCLASS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess Chapman-Shaoxing (ecg-arrhythmia 1.0.0) into "
                    "the ECGNPZDataset format.")
    parser.add_argument("--source-root", type=Path, required=True,
                        help="Directory containing WFDBRecords/ and ConditionNames_SNOMED-CT.csv")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sampling-rate", type=int, default=500)
    parser.add_argument("--signal-length", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None, help="Cap records (debug only).")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def parse_dx_line(hea_path: Path) -> list[str]:
    """解析 .hea 中 '#Dx: code,code,...'（该数据集无空格前缀变体，两种都兼容）"""
    for line in hea_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        t = line.strip()
        if t.startswith("#Dx:") or t.startswith("# Dx:"):
            return [c.strip() for c in t.split(":", 1)[1].split(",") if c.strip()]
    return []


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
    wfdb_root = args.source_root / "WFDBRecords"
    if not wfdb_root.exists():
        raise FileNotFoundError(f"WFDBRecords/ not found under {args.source_root}")
    data_dir = ensure_output_dirs(args.output_root, args.overwrite)

    # Chapman 专用码表覆写（不动全局表，防污染PTB-XL；见模块docstring）：
    # 窦缓/窦速在Chapman属正常窦性节律速率变体 → NORM（全局表为CINC2021归STTC）
    chapman_overrides = {
        "426177001": "NORM",  # SB sinus bradycardia → 窦性正常
        "427084000": "NORM",  # ST sinus tachycardia → 窦性正常
        "427393009": "NORM",  # SA sinus arrhythmia → 窦性正常（R12扩展，与R13 SARRH→NORM跨库对齐）
    }

    hea_paths = sorted(wfdb_root.rglob("*.hea"))
    if args.limit is not None:
        hea_paths = hea_paths[: args.limit]
    if not hea_paths:
        raise FileNotFoundError(f"No .hea files under {wfdb_root}")

    rows: list[dict[str, object]] = []
    counters = {"total_headers": 0, "skipped_missing_dx": 0, "skipped_unmappable": 0,
                "skipped_signal_error": 0, "skipped_nonfinite": 0,  # QC：污染信号不计
                "skipped_existing": 0, "written": 0}
    unmapped_code_freq: Counter = Counter()

    for hea_path in hea_paths:
        counters["total_headers"] += 1
        dx_codes = parse_dx_line(hea_path)
        if not dx_codes:
            counters["skipped_missing_dx"] += 1
            continue
        scp = {c: 1.0 for c in dx_codes}
        label = MAP_TO_5SUPERCLASS(scp, code_overrides=chapman_overrides)
        if label is None:
            counters["skipped_unmappable"] += 1
            for c in dx_codes:
                if str(c) not in SCP_TO_SUPERCLASS or SCP_TO_SUPERCLASS[str(c)] is None:
                    unmapped_code_freq[str(c)] += 1
            continue
        stem = hea_path.stem  # JSxxxxx（每患者1条ECG，patient_id=记录号）
        record_id = f"chapman_{stem}"
        npy_path = data_dir / f"{record_id}.npy"
        record_path = hea_path.with_suffix("")

        if npy_path.exists():
            # 可恢复重跑：npy信号与label无关，已存在则跳过信号加载/重写，
            # 仅据当前映射重建metadata行（R12/R13语义更新后无需重写信号）。
            counters["skipped_existing"] += 1
            rows.append({
                "id": record_id,
                "label": label,
                "npy_path": npy_path.name,
                "fs": args.sampling_rate,
                "original_len": args.signal_length,
                "patient_id": stem,  # 字符串patient_id（patient_wise_split兼容Hashable）
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

        # QC（R16，协议§13数据完整性）：源信号含NaN/Inf（坏导联段/人工伪迹
        # 采样）必须在此剔除——否则非有限值会静默传播进校准误差与训练/评估
        # （ECGNPZDataset._load_signal 的 fail-fast 守卫会在运行时崩溃）。丢
        # 0.1%污染记录是标准ECG QC（人工伪迹）；插值填充会引入系统性偏倚。
        if not np.isfinite(signal).all():
            counters["skipped_nonfinite"] += 1
            continue

        np.save(npy_path, signal)
        rows.append({
            "id": record_id,
            "label": label,
            "npy_path": npy_path.name,
            "fs": args.sampling_rate,
            "original_len": int(signal.shape[1]),
            "patient_id": stem,  # 字符串patient_id（patient_wise_split兼容Hashable）
        })
        counters["written"] += 1

    if not rows:
        raise RuntimeError("No samples produced. Check Dx parsing and mapping coverage.")

    metadata = pd.DataFrame(rows).sort_values("id").reset_index(drop=True)
    metadata_path = args.output_root / "metadata_single_label.csv"
    metadata.to_csv(metadata_path, index=False)

    # 码表覆盖率分析（对照ConditionNames_SNOMED-CT全表，用于码表扩展决策）
    cond_csv = args.source_root / "ConditionNames_SNOMED-CT.csv"
    coverage_note = {}
    if cond_csv.exists():
        cond = pd.read_csv(cond_csv, encoding="utf-8-sig")
        for _, r in cond.iterrows():
            code = str(r["Snomed_CT"]).strip()
            in_table = code in SCP_TO_SUPERCLASS
            coverage_note[code] = {
                "acronym": r["Acronym Name"], "mapped": in_table,
                "target": SCP_TO_SUPERCLASS.get(code) if in_table else None,
                "unmapped_freq": unmapped_code_freq.get(code, 0),
            }

    summary = {
        "source_root": str(args.source_root.resolve()),
        "output_root": str(args.output_root.resolve()),
        "sampling_rate": args.sampling_rate,
        "signal_length": args.signal_length,
        "counts": counters,
        "n_patients": int(metadata["patient_id"].nunique()),
        "label_distribution": metadata["label"].value_counts().sort_index().to_dict(),
        "unmapped_code_freq": dict(unmapped_code_freq.most_common()),
        "mapping_coverage": coverage_note or None,
        "mapping": "src.data.mapping.MAP_TO_5SUPERCLASS (MI>STTC>CD>HYP>NORM); "
                   "patient_id=记录号stem（每患者1条ECG）; "
                   f"Chapman覆写: {', '.join(f'{k}→{v}' for k, v in chapman_overrides.items())}"
                   "（窦性家族，跨库语义冲突登记§10-T1）",
    }
    summary_path = args.output_root / "preprocess_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    print(f"Wrote {counters['written']} samples to {args.output_root}")
    print(f"Unmapped excluded: {counters['skipped_unmappable']} "
          f"(码频: {dict(unmapped_code_freq.most_common(10))})")
    print(f"Label distribution: {summary['label_distribution']}")
    print(f"Metadata: {metadata_path}\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
