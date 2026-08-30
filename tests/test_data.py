"""数据加载模块单元测试（Builder-1交付：映射/划分/Dataset/覆盖报告）

运行: python -m pytest tests/test_data.py -v
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.mapping import (
    SUPERCLASSES,
    DEFAULT_PRIORITY,
    SUBSPACE_CPSC,
    SCP_TO_SUPERCLASS,
    MAP_TO_5SUPERCLASS,
    generate_mapping_variants,
    CHAPMAN_TO_SUPERCLASS,
    CPSC_TO_SUPERCLASS,
    filter_subspace,
)
from src.data.splits import (
    patient_wise_split,
    ptbxl_official_folds,
    assert_no_leakage,
    coverage_report,
)
from src.data.datasets import ECGNPZDataset, SyntheticECGDatasetV2


# ===========================================================================
# 1. 映射测试
# ===========================================================================

class TestMapping:
    def test_sinus_rhythm_is_norm(self):
        assert SCP_TO_SUPERCLASS["426783006"] == "NORM"

    def test_mapping_table_size(self):
        # 任务要求：至少60个常见诊断码
        assert len(SCP_TO_SUPERCLASS) >= 60

    def test_priority_mi_over_norm(self):
        # 病理优先于正常（默认优先级 MI>STTC>CD>HYP>NORM）
        assert MAP_TO_5SUPERCLASS({"NORM": 100.0, "IMI": 100.0}) == "MI"

    def test_priority_sttc_over_cd(self):
        # 缺血/ST-T优先于传导
        assert MAP_TO_5SUPERCLASS({"1AVB": 100.0, "ISC_": 100.0}) == "STTC"

    def test_priority_cd_over_hyp(self):
        assert MAP_TO_5SUPERCLASS({"LVH": 100.0, "1AVB": 100.0}) == "CD"

    def test_priority_hyp_over_norm(self):
        assert MAP_TO_5SUPERCLASS({"NORM": 100.0, "LVH": 100.0}) == "HYP"

    def test_norm_only_record(self):
        assert MAP_TO_5SUPERCLASS({"SR": 100.0, "NORM": 100.0}) == "NORM"

    def test_rhythm_extension(self):
        # 纯节律记录的扩展映射（敏感性分析对象）
        assert MAP_TO_5SUPERCLASS({"AFIB": 100.0}) == "STTC"
        assert MAP_TO_5SUPERCLASS({"426783006": 100.0}) == "NORM"

    def test_unmapped_returns_none(self):
        assert MAP_TO_5SUPERCLASS({"不存在的码": 100.0}) is None
        assert MAP_TO_5SUPERCLASS({}) is None

    def test_explicit_none_code(self):
        # 官方无类码显式标记None（计数报告用，不猜类）
        assert MAP_TO_5SUPERCLASS({"251139008": 100.0}) is None

    def test_use_weights_filters_zero(self):
        assert MAP_TO_5SUPERCLASS({"IMI": 0.0, "NORM": 100.0}, use_weights=True) == "NORM"
        # 默认关闭权重过滤（官方aggregation行为）
        assert MAP_TO_5SUPERCLASS({"IMI": 0.0, "NORM": 100.0}) == "MI"

    def test_priority_rules_validation(self):
        with pytest.raises(ValueError):
            MAP_TO_5SUPERCLASS({"IMI": 100.0}, priority_rules=("MI", "NORM"))

    def test_three_variants_exist_and_differ(self):
        variants = list(generate_mapping_variants())
        assert len(variants) >= 3
        names = [v["name"] for v in variants]
        assert len(set(names)) == len(names)
        # 变体1：优先级反转 → NORM优先于MI
        v1 = variants[0]
        assert MAP_TO_5SUPERCLASS(v1["probe_codes"], v1["priority"],
                                  code_overrides=v1["code_overrides"]) == "NORM"
        # 变体2：STTC>MI
        v2 = variants[1]
        assert MAP_TO_5SUPERCLASS(v2["probe_codes"], v2["priority"],
                                  code_overrides=v2["code_overrides"]) == "STTC"
        # 变体3：10370003 歧义项 CD→STTC
        v3 = variants[2]
        assert SCP_TO_SUPERCLASS["10370003"] == "CD"  # 基线
        assert MAP_TO_5SUPERCLASS(v3["probe_codes"], v3["priority"],
                                  code_overrides=v3["code_overrides"]) == "STTC"
        # 默认优先级下三个变体的行为均与基线不同（确实"不同"的实质性验证）
        assert DEFAULT_PRIORITY != v1["priority"]
        assert DEFAULT_PRIORITY != v2["priority"]
        assert MAP_TO_5SUPERCLASS(v3["probe_codes"]) == "CD"

    def test_chapman_mapping(self):
        assert CHAPMAN_TO_SUPERCLASS["NSR"] == "NORM"
        assert CHAPMAN_TO_SUPERCLASS["AFIB"] == "STTC"
        assert CHAPMAN_TO_SUPERCLASS["AFLT"] == "STTC"
        assert CHAPMAN_TO_SUPERCLASS["SB"] == "STTC"
        assert CHAPMAN_TO_SUPERCLASS["1AVB"] == "CD"
        assert CHAPMAN_TO_SUPERCLASS["RBBB"] == "CD"

    def test_cpsc_mapping_and_subspace(self):
        assert CPSC_TO_SUPERCLASS["Normal"] == "NORM"
        assert CPSC_TO_SUPERCLASS["AF"] == "STTC"
        assert CPSC_TO_SUPERCLASS["I-AVB"] == "CD"
        assert CPSC_TO_SUPERCLASS["LBBB"] == "CD"
        assert CPSC_TO_SUPERCLASS["RBBB"] == "CD"
        assert CPSC_TO_SUPERCLASS["STD"] == "STTC"
        assert CPSC_TO_SUPERCLASS["STE"] == "STTC"
        # CPSC无HYP：子空间{NORM, CD, STTC}与协议§2一致
        assert set(SUBSPACE_CPSC) == {"NORM", "CD", "STTC"}
        assert "HYP" not in CPSC_TO_SUPERCLASS.values()

    def test_filter_subspace(self):
        labels = ["NORM", "CD", "STTC", "HYP", "MI", None]
        rep = filter_subspace(labels, SUBSPACE_CPSC)
        assert rep["kept_indices"] == [0, 1, 2]
        assert rep["dropped_indices"] == [3, 4, 5]
        assert rep["n_kept"] == 3 and rep["n_dropped"] == 3
        assert rep["kept_counts"] == {"NORM": 1, "CD": 1, "STTC": 1}
        assert rep["dropped_counts"] == {"HYP": 1, "MI": 1, "None": 1}


# ===========================================================================
# 2. 划分测试
# ===========================================================================

def _make_500_patients(seed: int = 0):
    rng = np.random.default_rng(seed)
    pids = [f"P{i:04d}" for i in range(500)]
    # 不均匀层结构，锻炼最大余数法
    labels = {p: str(rng.choice([0, 1, 2, 3, 4], p=[0.4, 0.2, 0.2, 0.1, 0.1]))
              for p in pids}
    return pids, labels


class TestSplits:
    def test_ratio_approx_70_10_20(self):
        pids, labels = _make_500_patients()
        splits = patient_wise_split(pids, labels, seed=42)
        n = 500
        assert abs(len(splits["train"]) / n - 0.7) <= 0.05
        assert abs(len(splits["cal"]) / n - 0.1) <= 0.05
        assert abs(len(splits["test"]) / n - 0.2) <= 0.05

    def test_no_leakage_passes(self):
        pids, labels = _make_500_patients()
        splits = patient_wise_split(pids, labels, seed=42)
        assert assert_no_leakage(splits, patient_ids=pids) is True
        # 覆盖性：三集并集=全体患者（患者不丢）
        assert set(splits["train"]) | set(splits["cal"]) | set(splits["test"]) == set(pids)

    def test_leakage_raises_with_ids(self):
        bad = {"train": [1, 2, 3, 4], "cal": [4, 5], "test": [5, 6]}
        with pytest.raises(ValueError) as ei:
            assert_no_leakage(bad)
        msg = str(ei.value)
        assert "4" in msg and "5" in msg  # 列出泄漏ID
        assert "train∩cal" in msg

    def test_determinism_same_seed(self):
        pids, labels = _make_500_patients()
        s1 = patient_wise_split(pids, labels, seed=123)
        s2 = patient_wise_split(pids, labels, seed=123)
        assert s1 == s2

    def test_callable_label_source(self):
        pids, labels = _make_500_patients()
        splits = patient_wise_split(pids, lambda p: labels[p], seed=42)
        assert len(splits["train"]) > 0

    def test_ratio_sum_validation(self):
        with pytest.raises(ValueError):
            patient_wise_split([f"P{i}" for i in range(50)],
                               {f"P{i}": "NORM" for i in range(50)},
                               ratios=(0.7, 0.1, 0.1))

    def test_ptbxl_official_folds(self):
        # 合成100患者×2记录，fold=患者数%10+1
        rng = np.random.default_rng(3)
        rows = []
        for p in range(100):
            fold = p % 10 + 1
            for r in range(2):
                rows.append({"patient_id": f"pt{p:03d}", "fold": fold,
                             "ecg_id": f"e{p}_{r}", "noise": rng.normal()})
        df = pd.DataFrame(rows)
        splits = ptbxl_official_folds(df)
        assert len(splits["train"]["records"]) == 160   # folds 1-8
        assert len(splits["cal"]["records"]) == 20      # fold 9
        assert len(splits["test"]["records"]) == 20     # fold 10
        assert len(splits["train"]["patients"]) == 80
        assert assert_no_leakage(splits) is True
        # fold=10的记录全部落入test
        test_pos = set(splits["test"]["records"].tolist())
        for pos in test_pos:
            assert df.iloc[pos]["fold"] == 10

    def test_ptbxl_folds_validates_columns(self):
        with pytest.raises(KeyError):
            ptbxl_official_folds(pd.DataFrame({"patient_id": [1]}))
        with pytest.raises(ValueError):
            ptbxl_official_folds(pd.DataFrame({"patient_id": [1], "fold": [11]}))

    def test_coverage_report(self):
        rep = coverage_report({
            "train": ["NORM"] * 7 + ["MI"] * 3,
            "cal": ["NORM"] * 9 + ["HYP"] * 1,
            "test": ["NORM"] * 5 + ["STTC"] * 4 + ["CD"] * 1,
        })
        # 每类支持数（含0——空类单列）
        assert rep["per_split"]["train"]["MI"] == 3
        assert rep["per_split"]["train"]["HYP"] == 0
        assert rep["per_split"]["cal"]["HYP"] == 1
        assert rep["per_split_total"]["train"] == 10
        # 并集=5超类全出现
        assert set(rep["union"]) == set(SUPERCLASSES)
        # 交集：只有NORM在三个split都有
        assert rep["intersection"] == ["NORM"]
        assert set(rep["missing_per_split"]["train"]) == {"STTC", "CD", "HYP"}
        assert set(rep["missing_per_split"]["cal"]) == {"MI", "STTC", "CD"}
        assert set(rep["missing_per_split"]["test"]) == {"MI", "HYP"}


# ===========================================================================
# 3. Dataset 测试
# ===========================================================================

@pytest.fixture()
def npy_dataset_dir(tmp_path):
    """模拟 preprocess_cinc2021.py 输出：data/*.npy + metadata_single_label.csv"""
    rng = np.random.default_rng(11)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows = []
    labels = ["Normal", "Rhythm", "CD", "ST", "Other"]
    for i in range(10):
        # 非零均值/非单位方差的原始信号（验证per-record z-score确在本模块执行）
        x = rng.normal(loc=5.0 + i, scale=2.0 + 0.1 * i, size=(12, 100)).astype(np.float32)
        np.save(data_dir / f"rec{i:04d}.npy", x)
        rows.append({
            "id": f"rec{i:04d}",
            "label": labels[i % len(labels)],
            "npy_path": f"rec{i:04d}.npy",
            "fs": 500,
            "original_len": 100,
        })
    csv = tmp_path / "metadata_single_label.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    return tmp_path


class TestDatasets:
    def test_load_shape_and_label(self, npy_dataset_dir):
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv")
        assert len(ds) == 10
        x, y = ds[0]
        assert x.shape == (12, 100)
        assert x.dtype.__str__().startswith("torch.float32")
        assert isinstance(y, int)
        assert ds.classes == sorted(set(ds.raw_labels))

    def test_per_record_zscore(self, npy_dataset_dir):
        # preprocess产物未归一化 → Dataset内逐导联z-score，均值≈0、方差≈1
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv")
        x, _ = ds[3]
        np_x = x.numpy()
        assert np.allclose(np_x.mean(axis=1), 0.0, atol=1e-5)
        assert np.allclose(np_x.std(axis=1), 1.0, atol=1e-3)

    def test_split_indices(self, npy_dataset_dir):
        # 顺序保持（不排序、不重排）；重复索引按给定次数保留
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                           split_indices=[7, 2, 0])
        assert len(ds) == 3
        assert ds.record_ids == ["rec0007", "rec0002", "rec0000"]
        ds_dup = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                               split_indices=[7, 2, 2, 0])
        assert ds_dup.record_ids == ["rec0007", "rec0002", "rec0002", "rec0000"]
        with pytest.raises(IndexError):
            ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                          split_indices=[10])

    def test_missing_column_raises(self, npy_dataset_dir, tmp_path):
        bad = tmp_path / "bad.csv"
        pd.DataFrame({"id": ["a"], "label": ["NORM"]}).to_csv(bad, index=False)
        with pytest.raises(KeyError):
            ECGNPZDataset(bad)

    def test_fit_apply_stats_protocol(self, npy_dataset_dir):
        train = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                              split_indices=list(range(7)))
        eval_ = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                              split_indices=[7, 8, 9])
        stats = train.fit_train_stats()
        assert train.normalize == "global"
        assert set(stats) >= {"mean", "std", "n_records", "n_samples"}
        assert stats["mean"].shape == (12,) and stats["std"].shape == (12,)
        assert stats["n_records"] == 7
        eval_.apply_stats(stats)
        x, _ = eval_[0]
        assert x.shape == (12, 100)
        # global模式下：以train统计量归一化的非train数据不再零均值
        assert not np.allclose(x.numpy().mean(axis=1), 0.0, atol=1e-4)

    def test_global_mode_requires_stats(self, npy_dataset_dir):
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                           normalize="global")
        with pytest.raises(RuntimeError):
            _ = ds[0]

    def test_transform_applied(self, npy_dataset_dir):
        calls = []

        def fake_augment(x):
            calls.append(1)
            return x + 1.0

        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                           transform=fake_augment)
        x, _ = ds[0]
        assert calls and np.allclose(x.numpy().mean(), 1.0, atol=1e-5)  # z-score后+1

    def test_synthetic_v2_structure(self):
        syn = SyntheticECGDatasetV2(n_patients=30, records_per_patient=4,
                                    n_leads=12, seq_length=200, seed=7)
        assert len(syn) == 120
        x, y = syn[0]
        assert x.shape == (12, 200)
        assert set(np.unique(syn.y)) <= set(range(5))
        assert set(np.unique(syn.record_patient)) == set(syn.patient_ids.tolist())

    def test_synthetic_v2_deterministic(self):
        a = SyntheticECGDatasetV2(n_patients=5, records_per_patient=2,
                                  seq_length=100, seed=3)
        b = SyntheticECGDatasetV2(n_patients=5, records_per_patient=2,
                                  seq_length=100, seed=3)
        assert np.array_equal(a.X, b.X) and np.array_equal(a.y, b.y)

    def test_synthetic_v2_split_no_leakage(self):
        syn = SyntheticECGDatasetV2(n_patients=40, records_per_patient=3,
                                    seq_length=100, seed=5)
        sp = syn.split_by_patient(seed=5)
        patients = {k: v["patients"] for k, v in sp.items()}
        assert assert_no_leakage(patients) is True
        rec_union = np.concatenate([v["record_indices"] for v in sp.values()])
        assert sorted(rec_union.tolist()) == list(range(len(syn)))  # 记录不丢不重
        n = len(syn)
        assert abs(len(sp["train"]["record_indices"]) / n - 0.7) <= 0.05


# ===========================================================================
# 4. 攻击报告回归测试（修复验证者新增）
# ===========================================================================

class TestRegressionRecordLeakage:
    """[MAJOR-2] assert_no_leakage 对记录级输入静默返回True"""

    # 攻击者原始反例：P1/P2跨split泄漏，记录级输入+patient_of_record必须检出
    ATTACK_CASE = {
        "train": ["P1_rec1", "P1_rec2", "P2_rec1"],
        "cal": ["P5_r1"],
        "test": ["P1_rec3", "P2_rec2"],
    }
    ATTACK_MAP = {
        "P1_rec1": "P1", "P1_rec2": "P1", "P1_rec3": "P1",
        "P2_rec1": "P2", "P2_rec2": "P2", "P5_r1": "P5",
    }

    def test_record_level_leakage_detected_with_patient_of_record(self):
        with pytest.raises(ValueError) as ei:
            assert_no_leakage(self.ATTACK_CASE, patient_of_record=self.ATTACK_MAP)
        msg = str(ei.value)
        assert "P1" in msg and "P2" in msg          # 泄漏的患者ID被点名
        assert "train∩test" in msg

    def test_record_level_clean_passes_and_list_or_set_values_supported(self):
        clean = {
            "train": {"P1_rec1", "P1_rec2", "P2_rec1"},  # set
            "cal": ["P5_r1"],                             # list
            "test": ("P3_rec1", "P4_rec1"),               # tuple
        }
        full_map = dict(self.ATTACK_MAP, P3_rec1="P3", P4_rec1="P4")
        assert assert_no_leakage(clean, patient_of_record=full_map) is True

    def test_unknown_record_raises_keyerror(self):
        with pytest.raises(KeyError):
            assert_no_leakage({"train": ["ghost_rec"]},
                              patient_of_record={"a": "P1"})

    def test_patient_level_assumption_documented_when_no_mapping(self):
        # 不提供 patient_of_record 时行为不变，但"假设输入已是患者级"必须写明
        doc = assert_no_leakage.__doc__ or ""
        assert "患者级" in doc and "假设" in doc


class TestRegressionNaNPatient:
    """[MAJOR-3] NaN patient_id 跨split泄漏未检出"""

    def test_ptbxl_folds_nan_patient_id_raises(self):
        # 攻击者原始反例：nan同时进train(fold1)和test(fold10)且断言通过
        df = pd.DataFrame({
            "patient_id": [np.nan, np.nan, 1.0, 2.0, 3.0, 4.0],
            "fold": [1, 10, 1, 2, 9, 10],
        })
        with pytest.raises(ValueError, match="patient_id含缺失值"):
            ptbxl_official_folds(df)

    def test_assert_no_leakage_nan_ids_raise(self):
        # float('nan')对象互不相等，旧实现set交集漏检
        with pytest.raises(ValueError, match="NaN"):
            assert_no_leakage({
                "train": [np.nan, 1.0],
                "cal": [float("nan"), 2.0],
                "test": [3.0],
            })


class TestRegressionSplitRoleGuard:
    """[MAJOR-4] fit_train_stats 无split角色守卫 / apply_stats 无来源校验"""

    def test_fit_train_stats_rejects_test_role(self, npy_dataset_dir):
        test_ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                                split_indices=[7, 8, 9], split_role="test")
        with pytest.raises(ValueError, match="只允许从train split拟合"):
            test_ds.fit_train_stats()

    def test_stats_source_recorded_and_apply_validates(self, npy_dataset_dir):
        train = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                              split_indices=list(range(7)), split_role="train")
        stats = train.fit_train_stats()
        assert stats["source"] == "train"
        cal = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                            split_indices=[7, 8], split_role="cal")
        cal.apply_stats(stats)  # source=='train' → 正常通过
        with pytest.raises(ValueError, match="source"):
            cal.apply_stats({"mean": np.zeros(12), "std": np.ones(12),
                             "source": "test"})
        with pytest.raises(ValueError, match="source"):
            cal.apply_stats({"mean": np.zeros(12), "std": np.ones(12)})

    def test_invalid_split_role_rejected(self, npy_dataset_dir):
        with pytest.raises(ValueError, match="split_role"):
            ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                          split_role="validation")


class TestRegressionSignalValidity:
    """[MAJOR-5] NaN信号静默传播 / [MINOR-7] 损坏npy无路径 / [MINOR-9] 损坏状态"""

    def test_nan_signal_raises_with_path(self, npy_dataset_dir):
        x = np.zeros((12, 100), dtype=np.float32)
        x[3, 7] = np.nan
        np.save(npy_dataset_dir / "data" / "rec0003.npy", x)
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv")
        with pytest.raises(ValueError) as ei:
            _ = ds[3]
        assert "rec0003.npy" in str(ei.value)   # 含路径可定位
        assert "NaN" in str(ei.value)

    def test_inf_signal_raises_with_path(self, npy_dataset_dir):
        x = np.zeros((12, 100), dtype=np.float32)
        x[0, 0] = np.inf
        np.save(npy_dataset_dir / "data" / "rec0001.npy", x)
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv")
        with pytest.raises(ValueError, match="rec0001.npy"):
            _ = ds[1]

    def test_fit_train_stats_not_polluted_by_nan_and_no_corrupted_state(self, npy_dataset_dir):
        # 一条NaN记录 → fit直接raise（不再静默产出全NaN统计量），
        # 且失败不留下"normalize已切global"的损坏状态（MINOR-9）
        x = np.zeros((12, 100), dtype=np.float32)
        x[5, 9] = np.nan
        np.save(npy_dataset_dir / "data" / "rec0006.npy", x)
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv",
                           split_indices=[6], split_role="train")
        with pytest.raises(ValueError, match="rec0006.npy"):
            ds.fit_train_stats()
        assert ds.normalize == "per_record"
        assert ds.stats_ is None

    def test_corrupted_npy_raises_with_path(self, npy_dataset_dir):
        (npy_dataset_dir / "data" / "rec0005.npy").write_bytes(b"corrupted!")
        ds = ECGNPZDataset(npy_dataset_dir / "metadata_single_label.csv")
        with pytest.raises(ValueError) as ei:
            _ = ds[5]
        assert "rec0005.npy" in str(ei.value)   # 含路径可定位
        assert "损坏" in str(ei.value)


class TestRegressionFoldParsing:
    """[MINOR-6] fold小数静默吸收 + NaN崩溃信息不可定位"""

    def test_fold_decimal_raises_with_row(self):
        df = pd.DataFrame({"patient_id": ["a", "b"], "fold": [1.5, 10]})
        with pytest.raises(ValueError) as ei:
            ptbxl_official_folds(df)
        assert "1.5" in str(ei.value) and "第0行" in str(ei.value)

    def test_fold_nan_raises_with_row(self):
        df = pd.DataFrame({"patient_id": ["a", "b"], "fold": [1, np.nan]})
        with pytest.raises(ValueError) as ei:
            ptbxl_official_folds(df)
        assert "第1行" in str(ei.value) and "缺失" in str(ei.value)

    def test_fold_none_raises_with_row(self):
        df = pd.DataFrame({"patient_id": ["a", "b"], "fold": [1, None]})
        with pytest.raises(ValueError, match="第1行"):
            ptbxl_official_folds(df)


class TestRegressionMappingDeterminism:
    """[MINOR-10] allowed元组顺序随PYTHONHASHSEED漂移 / [MINOR-11] 文档笔误"""

    def test_filter_subspace_allowed_sorted_regardless_of_hash_seed(self):
        rep = filter_subspace(["NORM", "CD"], allowed=["STTC", "NORM", "CD"])
        assert rep["allowed"] == ("CD", "NORM", "STTC")  # 固定字典序，非插入序
        rep2 = filter_subspace([], allowed=set(SUPERCLASSES))
        assert rep2["allowed"] == tuple(sorted(SUPERCLASSES))

    def test_mapping_docstring_count_corrected(self):
        import src.data.mapping as m
        assert "44条" in (m.__doc__ or "")
        assert "42条" not in (m.__doc__ or "")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
