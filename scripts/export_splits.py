"""导出患者级划分索引（论文 Code/Data availability 承诺交付物）

用途：把 60 个种子实验实际使用的数据划分导出为 CSV，使任何人可从公开源
数据库精确重建本研究的数据划分，无需信任"划分逻辑描述"。

输出：splits/{dataset}[_sub4]_seed{S}.csv，列：
  record_id   预处理产物记录ID（npy stem，与 metadata_single_label.csv 一致）
  patient_id  患者ID
  split       train / val / cal / test（数据加载器语义，见下）
  in_train_loader  yes/no —— 该记录是否同时进入训练加载器
【重要·PTB-XL as-used 语义】train.py 的 build_ptbxl_datasets 中，carve 出的
val 患者记录仍保留在训练加载器（folds 1-8 全量训练，val 仅作早停监控）——
这是 60 个实验的实际运行口径，本导出如实反映（in_train_loader=yes 标注），
不做事后修饰。cal(fold9)/test(fold10) 与 folds1-8 患者零交集（已断言），
主终点评估不受影响。Chapman/CPSC 的 val 患者已从训练集正确剔除
（in_train_loader=no）。

与 builder 的 lockstep 约定：本脚本的划分逻辑与 scripts/train.py 的
build_ptbxl_datasets / build_chapman_datasets / build_cpsc_datasets 逐行
镜像。若 builder 修改划分逻辑，必须同步修改本脚本并用 --validate 对真实
builder 交叉验证（在有预处理数据的机器上运行）。

用法：
    python scripts/export_splits.py                 # 导出 seeds 42-46 全变体
    python scripts/export_splits.py --validate 42   # 与真实 builder 交叉验证
    python scripts/export_splits.py --seeds 42 43   # 指定种子
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.splits import (  # noqa: E402
    patient_wise_split, ptbxl_official_folds,
)
from src.data.mapping import SUBSPACE_CPSC, filter_subspace  # noqa: E402

SEEDS_DEFAULT = [42, 43, 44, 45, 46]
DATA_ROOTS = {
    "ptbxl": "data/ptbxl_processed",
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
}


def _carve_val_patients(pat_label: dict, frac: float, seed: int) -> set:
    """与 train.py _carve_val_patients 逐行镜像（lockstep：改动须同步）

    注意：必须用 rng.permutation 洗牌后取前 n_val 个（与 builder 完全一致），
    不能写成 rng.choice——RNG 消耗序列不同，选出的患者成员会不同。
    """
    rng = np.random.default_rng(seed)
    val_patients: set = set()
    for lab in sorted(set(pat_label.values())):
        members = sorted(p for p, l in pat_label.items() if l == lab)
        members = list(np.asarray(members, dtype=object)[rng.permutation(len(members))])
        n_val = max(1, int(round(len(members) * frac)))
        val_patients.update(members[:n_val])
    return val_patients


def _split_chapman_like(meta_f: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Chapman/CPSC 型划分：patient_wise_split(0.7,0.1,0.2) + 1/7 val carve。

    与 train.py build_chapman_datasets / build_cpsc_datasets 的划分段逐行镜像。
    """
    patients = meta_f["patient_id"].unique().tolist()
    pat_label = meta_f.groupby("patient_id")["label"].agg(
        lambda s: s.mode().iat[0]).to_dict()
    t3 = patient_wise_split(patients, pat_label,
                            ratios=(0.7, 0.1, 0.2), seed=seed)
    train_patients = sorted(set(t3["train"]))
    cal_patients = sorted(set(t3["cal"]))
    test_patients = sorted(set(t3["test"]))
    sub = {p: pat_label[p] for p in train_patients}
    val_patients = _carve_val_patients(sub, 1 / 7, seed + 100)
    train_patients = sorted(set(train_patients) - val_patients)

    def _s(pid):
        if pid in val_patients:
            return "val"
        if pid in train_patients:
            return "train"
        if pid in cal_patients:
            return "cal"
        return "test"

    out = pd.DataFrame({
        "record_id": meta_f["id"].astype(str),
        "patient_id": meta_f["patient_id"].astype(str),
    })
    out["split"] = out["patient_id"].map(_s)
    # Chapman/CPSC：val 已从训练集剔除 → in_train_loader = (split=='train')
    out["in_train_loader"] = np.where(out["split"] == "train", "yes", "no")
    return out.sort_values("record_id").reset_index(drop=True)


def _split_ptbxl(meta: pd.DataFrame, seed: int,
                 subspace: tuple | None) -> pd.DataFrame:
    """PTB-XL 划分：官方折 1-8/9/10 + folds1-8 内 12.5% 患者级 val carve。

    与 train.py build_ptbxl_datasets 的划分段逐行镜像（lockstep）。
    as-used 语义：训练加载器 = folds1-8 全量记录（含 val 患者记录），
    见模块 docstring。
    """
    split_meta = meta
    if subspace is not None:
        rep = filter_subspace(meta["label"].tolist(), subspace)
        split_meta = meta.iloc[rep["kept_indices"]].reset_index(drop=True)

    folds_df = split_meta[["patient_id"]].assign(fold=split_meta["strat_fold"])
    splits = ptbxl_official_folds(folds_df)
    train_pos = np.sort(np.asarray(splits["train"]["records"], dtype=int))
    meta18 = split_meta.loc[train_pos]
    pat_label = meta18.groupby("patient_id")["label"].agg(
        lambda s: s.mode().iat[0]).to_dict()
    val_patients = _carve_val_patients(pat_label, 0.125, seed + 100)
    # 统一为 str 集合：meta 的 patient_id 可能是 int64，_s() 里按 str 比较
    val_patients = {str(p) for p in val_patients}
    cal_patients = sorted(set(np.asarray(splits["cal"]["patients"], dtype=object).tolist()))
    test_patients = sorted(set(np.asarray(splits["test"]["patients"], dtype=object).tolist()))

    def _s(row):
        pid = str(row["patient_id"])
        fold = int(row["fold"])
        if pid in val_patients:
            return "val"
        if fold == 9:
            return "cal"
        if fold == 10:
            return "test"
        return "train"

    out = pd.DataFrame({
        "record_id": split_meta["id"].astype(str),
        "patient_id": split_meta["patient_id"].astype(str),
        "fold": split_meta["strat_fold"].astype(int),
    })
    out["split"] = out.apply(_s, axis=1)
    # as-used：训练加载器 = 全部 folds1-8 记录（含 val 患者，见模块 docstring）
    out["in_train_loader"] = np.where(out["fold"] <= 8, "yes", "no")
    return out.drop(columns=["fold"]).sort_values("record_id").reset_index(drop=True)


def export_all(seeds: list[int], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    jobs = [
        ("ptbxl_seed{seed}.csv", "ptbxl", None),
        ("ptbxl_sub4_seed{seed}.csv", "ptbxl", SUBSPACE_CPSC),
        ("chapman_seed{seed}.csv", "chapman", None),
        ("chapman_sub4_seed{seed}.csv", "chapman", SUBSPACE_CPSC),
        ("cpsc_seed{seed}.csv", "cpsc", None),  # cpsc builder 内部固定子空间
    ]
    for seed in seeds:
        for name_tpl, ds, subspace in jobs:
            meta = pd.read_csv(Path(DATA_ROOTS[ds]) / "metadata_single_label.csv")
            if ds == "ptbxl":
                df = _split_ptbxl(meta, seed, subspace)
            elif ds == "chapman":
                meta_f = meta
                if subspace is not None:
                    rep = filter_subspace(meta["label"].tolist(), subspace)
                    meta_f = meta.iloc[rep["kept_indices"]].reset_index(drop=True)
                df = _split_chapman_like(meta_f, seed)
            else:  # cpsc：builder 内部固定 SUBSPACE_CPSC
                rep = filter_subspace(meta["label"].tolist(), SUBSPACE_CPSC)
                meta_f = meta.iloc[rep["kept_indices"]].reset_index(drop=True)
                df = _split_chapman_like(meta_f, seed)
            path = out_dir / name_tpl.format(seed=seed)
            df.to_csv(path, index=False)
            written.append(path)
            print(f"[export] {path.name}: {len(df)} records "
                  f"({df['split'].value_counts().to_dict()})")
    return written


def validate_against_builders(seed: int) -> bool:
    """在有预处理数据的机器上：与真实 builder 交叉验证（最强保证）"""
    from train import (  # noqa: E402  延迟导入（torch 重）
        build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
    )
    ok = True
    checks = [
        ("ptbxl", dict(subspace=None), "ptbxl"),
        ("ptbxl", dict(subspace=SUBSPACE_CPSC), "ptbxl_sub4"),
        ("chapman", dict(subspace=None), "chapman"),
        ("chapman", dict(subspace=SUBSPACE_CPSC), "chapman_sub4"),
        ("cpsc", {}, "cpsc"),
    ]
    for ds, kwargs, name in checks:
        builder = {"ptbxl": build_ptbxl_datasets,
                   "chapman": build_chapman_datasets,
                   "cpsc": build_cpsc_datasets}[ds]
        datasets, _ = builder(DATA_ROOTS[ds], seed, limit=None, **kwargs)
        csv = pd.read_csv(Path("splits") / f"{name}_seed{seed}.csv")
        for split_name in ("train", "val", "cal", "test"):
            ids_builder = set(map(str, datasets[split_name].record_ids))
            if split_name == "train":
                ids_csv = set(csv.loc[csv["in_train_loader"] == "yes", "record_id"])
            else:
                ids_csv = set(csv.loc[csv["split"] == split_name, "record_id"])
            match = ids_builder == ids_csv
            ok &= match
            print(f"  [{name}/{split_name}] builder={len(ids_builder)} "
                  f"csv={len(ids_csv)} {'MATCH' if match else 'MISMATCH'}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS_DEFAULT)
    ap.add_argument("--out-dir", type=Path, default=Path("splits"))
    ap.add_argument("--validate", type=int, default=None, metavar="SEED",
                    help="与真实 builder 交叉验证指定种子（需本地预处理数据）")
    args = ap.parse_args()
    if args.validate is not None:
        ok = validate_against_builders(args.validate)
        sys.exit(0 if ok else 1)
    export_all(args.seeds, args.out_dir)


if __name__ == "__main__":
    main()
