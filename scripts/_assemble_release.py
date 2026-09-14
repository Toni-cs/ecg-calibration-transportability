# -*- coding: utf-8 -*-
"""组装 GitHub 发布 repo（一次性脚本，不属于研究代码）

从 ecg-lab-v2 精选文件复制到 D:/A1/ecg-release：
  code(src/ + 核心scripts) + splits/ + 精选results + 协议docs
排除：raw npy、checkpoints、内部对抗评审文档、批量启动器。
"""
import os
import shutil

SRC = r"D:\A1\ecg-lab-v2"
DST = r"D:\A1\ecg-release"

SCRIPTS = [
    # 预处理（4 数据库入口）
    "preprocess_ptbxl.py", "preprocess_chapman.py", "preprocess_cpsc.py",
    "preprocess_cinc2021.py", "qc_drop_nonfinite.py",
    # 划分导出（论文承诺交付物）
    "export_splits.py",
    # 训练与评估主链
    "train.py", "eval_transfer.py", "eval_l2_shift.py",
    "run_all_experiments.py", "merge_results.py", "gen_full_table.py",
    # 实验入口 E2-E6
    "run_e2_ablation_discrimination.py", "run_e3_brier_dcr_ncv.py",
    "run_e4_temperature_analysis.py", "run_e5_inception_lite.py",
    "run_e6_reliability_diagrams.py",
    # 统计验证与复算
    "validate_decomposition.py", "verify_matrix_dirichlet.py",
    "rerun_bca10000.py", "deployment_holdout_recompute.py",
    "summarize_l2_shifts.py",
]

RESULTS = [
    "ablation_ts_components.csv", "bh_fdr_correction.csv",
    "bootstrap_diagnostics.csv", "binned_temperature_exploratory.csv",
    "c1_brier_reliability.csv", "c1_brier_reliability_summary.csv",
    "c1_dcr_ncv_multiclass.csv", "c1_dcr_ncv_summary.csv",
    "c3_crossfit_results.csv", "c3_inceptiontime_lite_30exp.csv",
    "c4_resnet1d_8method.csv",
    "decomposition_validation_n20000.csv",
    "decomposition_validation_n500_seeds4.csv",
    "deployment_metrics.csv", "deployment_holdout_recompute.csv",
    "discrimination_metrics_60exp.csv",
    "l2_shift_full_390cells.csv", "l2_shift_full_780cells_detail.csv",
    "l2_shift_full_summary.json",
    "meta_analytic_pooled.csv", "predictability_3arch.csv",
    "predictability_sensitivity.json", "robustness_validation_5seeds.csv",
    "temperature_distribution_analysis.csv", "temperature_shift_sensitivity.csv",
]

DOCS = [
    "EXPERIMENT_PROTOCOL.md",
    "PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md",
    "PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md",
    "osf_archive_manifest.json",
]


def copy(src_root, dst_root, files, sub=""):
    for f in files:
        s = os.path.join(src_root, sub, f)
        d = os.path.join(dst_root, sub, f)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)


def main():
    if os.path.exists(DST):
        raise SystemExit(f"{DST} 已存在，先确认再删")
    os.makedirs(DST)

    # src/ 全量（剔除 __pycache__）
    for r, ds, fs in os.walk(os.path.join(SRC, "src")):
        ds[:] = [d for d in ds if d != "__pycache__"]
        rel = os.path.relpath(r, SRC)
        os.makedirs(os.path.join(DST, rel), exist_ok=True)
        for f in fs:
            if f.endswith(".py"):
                shutil.copy2(os.path.join(r, f), os.path.join(DST, rel, f))

    copy(SRC, DST, SCRIPTS, "scripts")
    copy(SRC, DST, sorted(os.listdir(os.path.join(SRC, "splits"))), "splits")
    copy(SRC, DST, RESULTS, "results")
    copy(SRC, DST, DOCS, "docs")
    shutil.copy2(os.path.join(SRC, "requirements.txt"),
                 os.path.join(DST, "requirements.txt"))

    n = sum(len(fs) for _, _, fs in os.walk(DST))
    print(f"[ok] {DST}: {n} files")


if __name__ == "__main__":
    main()
