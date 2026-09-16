"""CPSC2018（CPSC Database + CPSC-Extra）→ ECGNPZDataset 格式预处理。

语料身份（2026-09-16 更正，勿再写作 "CPSC2018+2019"）：
  本脚本处理的两个子集**都属于 CPSC2018**，语料中**不含 CPSC2019**。
  - Training_WFDB/ (A0001.hea …) = **CPSC Database**，即 CPSC2018 公开训练集
    （官方 6877 条；实测 9 个 SNOMED 码，与官方 9 类一一对应，**MI = 0**）
  - Training_2/    (Q0001.hea …) = **CPSC-Extra**，即 CPSC2018 未被赛题使用的
    剩余记录（官方 3453 条；实测 72 个 SNOMED 码，含 MI/HYP）
  依据：PhysioNet/CinC 2020 官方数据说明（physionet.org/content/challenge-2020）
  列出 "CPSC Database 6,877" 与 "CPSC-Extra Database 3,453"，后者原文为
  "the CPSC2018 data that was not used"；本地两个 zip 亦名为
  china-physiological-signal-challenge-in-2018.zip 与
  china-12lead-ecg-challenge-database.zip（后者由 PhysioNet 官方 Kaggle 账号
  发布，描述为 "The data are from the China Physiological Signal Challenge
  in 2018 (CPSC2018)"）。
  另注：CPSC2019 官方任务是 QRS/心率**检测**，不含疾病分类标签，与本语料无关。

  ⚠️ 代码内部的 source 标签**仍写作 "cpsc2019"**（历史命名）。该字符串已烙进
  `splits/cpsc_seed*.csv` 的 patient_id 与 `data/cpsc_processed/*`，
  **不得更改**，否则全部已发布 split 与已训练模型将失配。

输入：
  --cpsc2018-root  含 Training_WFDB/ 的目录（= CPSC Database）
  --cpsc2019-root  含 Training_2/ 的目录（= CPSC-Extra；参数名保留历史命名）
  --output-root    输出目录

输出（与 preprocess_chapman.py 同构）：
  - metadata_single_label.csv: id/label/npy_path/fs/original_len/patient_id
    CPSC 每条记录 = 1 患者；patient_id = 记录名；无 strat_fold（由 train.py
    的 patient_wise_split 按 70/10/20 执行）
  - data/*.npy: float32 (12, 5000) 500Hz×10s
  - preprocess_summary.json: STROBE 计数 + SNOMED 码频次表 + 映射覆盖率

CPSC Database (Training_WFDB): 6844 条（zip 内 6877，解压丢失 33 条 A6845–A6877，待补）
    12 导联 500Hz 7500 采样(15s) → 截断到 5000(10s)
CPSC-Extra (Training_2):       3453 条，12 导联 500Hz 5000 采样(10s)
合计约 10297 条（两子集无重叠）
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
from src.data.mapping import SCP_TO_SUPERCLASS, SUPERCLASSES  # noqa: E402

PRIORITY = ["MI", "STTC", "CD", "HYP", "NORM"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess CPSC2018 (CPSC Database + CPSC-Extra) "
                    "into ECGNPZDataset format.")
    parser.add_argument("--cpsc2018-root", type=Path, required=True,
                        help="Directory containing Training_WFDB/ (= CPSC Database)")
    parser.add_argument("--cpsc2019-root", type=Path, required=True,
                        help="Directory containing Training_2/ (= CPSC-Extra, the "
                             "unused portion of CPSC2018; flag name kept for "
                             "historical compatibility)")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sampling-rate", type=int, default=500)
    parser.add_argument("--signal-length", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None, help="Cap records (debug).")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def parse_dx_line(hea_path: Path) -> list[str]:
    for line in hea_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        t = line.strip()
        if t.startswith("#Dx:") or t.startswith("# Dx:"):
            return [c.strip() for c in t.split(":", 1)[1].split(",") if c.strip()]
    return []


def codes_to_superclasses(codes: list[str]) -> list[str]:
    result = []
    for code in codes:
        sc = SCP_TO_SUPERCLASS.get(str(code))
        if sc is not None:
            result.append(sc)
    return result


def single_label(superclasses: list[str]) -> str | None:
    if not superclasses:
        return None
    for label in PRIORITY:
        if label in superclasses:
            return label
    return None


def process_record(hea_path: Path, target_fs: int, target_length: int) -> tuple[np.ndarray, list[str]] | None:
    try:
        signal, fs = load_signal(hea_path.with_suffix(""))
        sig = resample_and_fix_length(signal, fs, target_fs, target_length)
        codes = parse_dx_line(hea_path)
        return sig, codes
    except Exception as e:
        print(f"  [skip] {hea_path.name}: {e}")
        return None


def main() -> None:
    args = parse_args()
    data_dir = args.output_root / "data"
    if args.output_root.exists() and not args.overwrite:
        if (args.output_root / "metadata_single_label.csv").exists() or data_dir.exists():
            raise FileExistsError(
                f"Output exists at {args.output_root}. Pass --overwrite to replace.")
    args.output_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # 注意：dirs 中的 source 字符串会成为 patient_id 前缀（如 cpsc2019_Q0001），
    # 并已烙进 splits/cpsc_seed*.csv 与 data/cpsc_processed/*。
    # "cpsc2019" 是历史命名，实际语料为 CPSC-Extra（CPSC2018 未使用部分）。
    # **不得重命名**，否则全部已发布 split 与已训练模型失配。
    dirs = []
    d18 = args.cpsc2018_root / "Training_WFDB"
    if d18.exists():
        dirs.append(("cpsc2018", d18))
    d19 = args.cpsc2019_root / "Training_2"
    if d19.exists():
        dirs.append(("cpsc2019", d19))
    if not dirs:
        raise FileNotFoundError(f"No Training_WFDB/ or Training_2/ found")

    hea_paths = []
    for source, d in dirs:
        paths = sorted(d.rglob("*.hea"))
        hea_paths.extend((source, p) for p in paths)
        print(f"[{source}] {len(paths)} records in {d}")

    if args.limit:
        hea_paths = hea_paths[:args.limit]

    rows = []
    code_counter = Counter()
    unmapped_codes = Counter()
    mapped_count = 0
    skipped_count = 0
    label_counter = Counter()

    for i, (source, hea_path) in enumerate(hea_paths):
        result = process_record(hea_path, args.sampling_rate, args.signal_length)
        if result is None:
            skipped_count += 1
            continue
        signal, codes = result

        for c in codes:
            code_counter[c] += 1
            if c not in SCP_TO_SUPERCLASS:
                unmapped_codes[c] += 1

        superclasses = codes_to_superclasses(codes)
        label = single_label(superclasses)
        if label is None:
            skipped_count += 1
            continue

        record_name = hea_path.stem
        patient_id = f"{source}_{record_name}"
        npy_name = f"{patient_id}.npy"
        np.save(data_dir / npy_name, signal)

        rows.append({
            "id": patient_id,
            "label": label,
            "npy_path": npy_name,
            "fs": args.sampling_rate,
            "original_len": signal.shape[1],
            "patient_id": patient_id,
        })
        mapped_count += 1
        label_counter[label] += 1

        if (i + 1) % 1000 == 0:
            print(f"  processed {i+1}/{len(hea_paths)} ({mapped_count} mapped, {skipped_count} skipped)")

    df = pd.DataFrame(rows)
    df.to_csv(args.output_root / "metadata_single_label.csv", index=False)

    summary = {
        "total_records": len(hea_paths),
        "mapped_single_label": mapped_count,
        "skipped_no_label_or_error": skipped_count,
        "label_distribution": dict(label_counter),
        "top_codes": dict(code_counter.most_common(30)),
        "unmapped_codes": dict(unmapped_codes.most_common(20)),
        "sources": {s: sum(1 for _, p in hea_paths if _ == s) for s, _ in [(k, None) for k, _ in dirs]},
        "sampling_rate": args.sampling_rate,
        "signal_length": args.signal_length,
    }
    (args.output_root / "preprocess_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone: {mapped_count} mapped, {skipped_count} skipped")
    print(f"Label distribution: {dict(label_counter)}")
    if unmapped_codes:
        print(f"Unmapped codes ({len(unmapped_codes)}): {dict(unmapped_codes.most_common(10))}")


if __name__ == "__main__":
    main()