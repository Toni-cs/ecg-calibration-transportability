# Data loading subpackage: 5-superclass mapping + patient-wise split + Dataset (protocol Section 2 leakage-prevention implementation).

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
