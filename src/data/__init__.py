# 数据加载子包: 5超类映射 + 患者级划分 + Dataset（协议§2防泄漏协议实现）

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

__all__ = [
    "SUPERCLASSES",
    "DEFAULT_PRIORITY",
    "SUBSPACE_CPSC",
    "SCP_TO_SUPERCLASS",
    "MAP_TO_5SUPERCLASS",
    "generate_mapping_variants",
    "CHAPMAN_TO_SUPERCLASS",
    "CPSC_TO_SUPERCLASS",
    "filter_subspace",
    "patient_wise_split",
    "ptbxl_official_folds",
    "assert_no_leakage",
    "coverage_report",
    "ECGNPZDataset",
    "SyntheticECGDatasetV2",
]
