"""患者级划分与泄漏断言模块（协议§2防泄漏协议的实现）

功能：
1. ``patient_wise_split``：患者级分层划分 train/cal/test（Chapman/CPSC 70/10/20，
   固定种子；分层键=患者多数标签；numpy Generator）
2. ``ptbxl_official_folds``：PTB-XL官方10折加载（folds 1-8训练 / 9校准 / 10测试；
   引用 Wagner 2020: strat_fold 由分层采样得到且尊重患者归属，fold 9/10
   经过人工复核、标签质量更高）
3. ``assert_no_leakage``：硬性断言 train/cal/test 患者ID交集为空
   （协议§2"硬性断言脚本：进CI与复现仓库"）；支持 ``patient_of_record``
   把记录级输入先归一化为患者级再查交集；NaN/None ID一律拒绝
   （NaN对象互不相等，set交集无法检出跨集泄漏）
4. ``coverage_report``：逐类支持数 + 并集/交集诊断（协议§2类别覆盖检查表，
   空类单列）

设计要点：
- 重采样单元=患者（与协议§7 cluster bootstrap一致）——划分绝不按记录打乱
- 分层键=患者多数标签（多记录患者取众数，并列时取排序最前的标签，确定性）
- 微小层（患者数<3）整体并入train：记录级随机只会产生伪独立性，患者级
  保证同一层患者不跨集（无泄漏；代价是微小层的划分方差，协议§7已知）
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Callable, Hashable, Iterable, Mapping as MappingType, Optional, Sequence

import numpy as np
import pandas as pd

from src.data.mapping import SUPERCLASSES

__all__ = [
    "patient_wise_split",
    "ptbxl_official_folds",
    "assert_no_leakage",
    "coverage_report",
]

DEFAULT_RATIOS = (0.7, 0.1, 0.2)


def _resolve_label_for_patient(
    patient_ids: Sequence,
    label_for_patient,
) -> dict:
    """把 label_for_patient（Mapping或callable）解析为 {pid: stratum}"""
    if isinstance(label_for_patient, MappingType):
        mapping = label_for_patient
        missing = [p for p in patient_ids if p not in mapping]
        if missing:
            raise KeyError(f"label_for_patient缺少患者分层键: {missing[:5]} ...")
        return {p: mapping[p] for p in patient_ids}
    if callable(label_for_patient):
        return {p: label_for_patient(p) for p in patient_ids}
    raise TypeError("label_for_patient必须是Mapping或callable(pid)->stratum")


def patient_wise_split(
    patient_ids: Sequence[Hashable],
    label_for_patient,
    ratios: Sequence[float] = DEFAULT_RATIOS,
    seed: int = 42,
) -> dict[str, list]:
    """患者级分层划分：返回 {"train": [...], "cal": [...], "test": [...]}

    - 按患者分层键（患者多数标签）分层；层内用 numpy Generator(seed) 洗牌
    - 层内配额用最大余数法（largest remainder）保证总比例最接近ratios
    - 患者数<3的层整体并入train（见模块docstring设计要点）
    - ratios之和必须为1（容差1e-9）

    注意：患者数很少时 cal/test 可能为空（如总计<10），此时raise提示扩数据，
    而不是静默返回空集——协议要求每个split可独立用于拟合/评估。
    """
    if len(ratios) != 3:
        raise ValueError(f"ratios必须是(train,cal,test)三元组, 得到: {ratios}")
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError(f"ratios之和必须为1, 得到: {sum(ratios)}")
    patient_ids = list(patient_ids)
    n_total = len(patient_ids)
    if n_total == 0:
        raise ValueError("patient_ids为空")
    strata = _resolve_label_for_patient(patient_ids, label_for_patient)

    rng = np.random.default_rng(seed)
    by_stratum: dict = defaultdict(list)
    for p in patient_ids:
        by_stratum[strata[p]].append(p)

    split_names = ("train", "cal", "test")
    splits: dict[str, list] = {name: [] for name in split_names}
    for _, members in sorted(by_stratum.items(), key=lambda kv: str(kv[0])):
        members = np.asarray(members, dtype=object)
        members = members[rng.permutation(len(members))]  # 层内患者洗牌
        n = len(members)
        if n < 3:
            splits["train"].extend(members.tolist())
            continue
        raw = [r * n for r in ratios]
        quota = [int(np.floor(x)) for x in raw]
        remainder = n - sum(quota)
        # 最大余数法：按小数部分降序把剩余名额分给对应split
        order = sorted(range(3), key=lambda i: raw[i] - quota[i], reverse=True)
        for k in range(remainder):
            quota[order[k % 3]] += 1
        start = 0
        for name, q in zip(split_names, quota):
            splits[name].extend(members[start:start + q].tolist())
            start += q

    for name in split_names:
        if not splits[name]:
            raise ValueError(
                f"划分后split '{name}' 为空（患者总数={n_total}），"
                "请扩大数据规模或调整ratios"
            )
    return splits


def ptbxl_official_folds(meta_df: pd.DataFrame) -> dict:
    """PTB-XL官方10折划分（Wagner 2020协议：folds 1-8训练/9校准/10测试）

    引用（Wagner et al., Sci Data 2020, v1.0.3 说明）：strat_fold 通过分层采样
    （stratified by patient and age/sex）获得且尊重患者归属（同一患者所有记录
    同折）；fold 9/10 记录经过至少一次人工复核、标签质量更高，官方推荐
    folds 1-8 训练 / fold 9 验证(=本研究的cal) / fold 10 测试。

    参数
    ----
    meta_df : DataFrame
        必须含 'patient_id' 与 'fold' 两列（fold=strat_fold, 取值1..10）。
        patient_id 不允许含缺失值（NaN对象互不相等，同一患者会被拆进
        不同split且set交集漏检，MAJOR-3）；fold 必须是1..10的整数，
        缺失值/小数/非数值均raise并给出行号（MINOR-6）。

    返回
    ----
    {"train": {"patients": ndarray, "records": ndarray(位置索引)},
     "cal":   {...}, "test": {...}}
    """
    for col in ("patient_id", "fold"):
        if col not in meta_df.columns:
            raise KeyError(f"meta_df缺少必需列 '{col}'")
    if meta_df["patient_id"].isna().any():
        bad_rows = np.flatnonzero(
            meta_df["patient_id"].isna().to_numpy()
        ).tolist()
        raise ValueError(
            f"patient_id含缺失值，禁止参与划分（NaN对象互不相等、跨split"
            f"泄漏无法用set交集检出；缺失行: {bad_rows[:10]}）"
        )
    out_of_range: set = set()
    folds_parsed: list[int] = []
    for i, f in enumerate(meta_df["fold"].tolist()):
        try:
            missing = pd.isna(f)
        except (TypeError, ValueError):
            missing = False
        if missing:
            raise ValueError(f"fold列第{i}行含缺失值")
        try:
            fval = float(f)
        except (TypeError, ValueError):
            raise ValueError(f"fold列第{i}行含非数值: {f!r}")
        if not np.isfinite(fval) or fval != int(fval):
            raise ValueError(f"fold列含非整数值: {f}（第{i}行）")
        fi = int(fval)
        if not (1 <= fi <= 10):
            out_of_range.add(fi)
        folds_parsed.append(fi)
    if out_of_range:
        raise ValueError(f"fold列出现官方范围(1..10)之外的取值: {sorted(out_of_range)}")
    folds = np.array(folds_parsed)

    records_pos = np.arange(len(meta_df))
    spec = {"train": (1, 8), "cal": (9, 9), "test": (10, 10)}
    out: dict[str, dict] = {}
    for name, (lo, hi) in spec.items():
        mask = (folds >= lo) & (folds <= hi)
        idx = records_pos[mask]
        if len(idx) == 0:
            raise ValueError(f"split '{name}' (folds {lo}-{hi}) 为空")
        out[name] = {
            "patients": pd.unique(meta_df["patient_id"].to_numpy()[mask]),
            "records": idx,
        }
    return out


def _as_patient_set(value) -> set:
    """归一化split值：list/set/tuple/ndarray 或 {"patients": ...}/{"patient_ids": ...}"""
    if isinstance(value, dict):
        for key in ("patients", "patient_ids"):
            if key in value:
                value = value[key]
                break
        else:
            raise KeyError("split值若为dict必须含 'patients' 或 'patient_ids' 键")
    return set(value)


def _as_record_set(value) -> set:
    """归一化记录级split值：list/set/tuple/ndarray 或 {"records": ...}/{"record_ids": ...}"""
    if isinstance(value, dict):
        for key in ("records", "record_ids"):
            if key in value:
                value = value[key]
                break
        else:
            raise KeyError("记录级split值若为dict必须含 'records' 或 'record_ids' 键")
    return set(value)


def _nan_like_ids(ids: set) -> list:
    """找出集合中NaN/None类ID（pd.unique每次返回不同nan对象，set交集会漏配）"""
    bad = []
    for v in ids:
        try:
            if pd.isna(v):
                bad.append(v)
        except (TypeError, ValueError):
            continue  # 不可判isna的奇异对象不视为缺失
    return bad


def assert_no_leakage(
    splits_dict: dict,
    patient_ids: Optional[Iterable] = None,
    patient_of_record: Optional[MappingType] = None,
) -> bool:
    """硬性断言：各split的患者ID两两交集为空；违反时raise ValueError

    参数
    ----
    splits_dict : dict
        {"train": 患者ID容器, "cal": ..., "test": ...}；值可以是
        list/set/tuple/ndarray，也可以是 {"patients": ...} 形式
        （与 ptbxl_official_folds 输出兼容）。
    patient_ids : 可选
        全体合法患者ID；提供时额外断言各split只含已注册患者（防脏ID）。
    patient_of_record : Mapping, optional
        {记录ID: 患者ID}。提供时，splits_dict 的值被解释为**记录级**ID，
        先逐条归一化为患者ID再查交集——直接把记录级输入当患者级处理
        会静默漏检"同一患者跨集"的泄漏（MAJOR-2）；映射中缺失的记录ID
        raise KeyError。**不提供时，输入被假设已是患者级**：本函数无记录
        映射可依据、不校验该假设，返回True仅表示"按患者级解释无交集"。

    返回
    ----
    True（无泄漏）。

    违反
    ----
    ValueError，消息中列出泄漏的患者ID及出现的split对；输入ID含
    NaN/None时同样raise（NaN对象互不相等，set交集无法检出）。
    """
    if patient_of_record is not None:
        sets: dict = {}
        for name, val in splits_dict.items():
            mapped: set = set()
            for rec in _as_record_set(val):
                if rec not in patient_of_record:
                    raise KeyError(
                        f"patient_of_record缺少记录ID: {rec!r}（split '{name}'）"
                    )
                mapped.add(patient_of_record[rec])
            sets[name] = mapped
    else:
        sets = {name: _as_patient_set(val) for name, val in splits_dict.items()}
    nan_ids = {name: ids for name, ids in
               ((name, _nan_like_ids(s)) for name, s in sets.items()) if ids}
    if nan_ids:
        raise ValueError(
            f"[LEAKAGE] 输入ID含NaN/None，禁止参与划分（NaN对象互不相等、"
            f"set交集无法检出跨split泄漏）: {nan_ids}"
        )
    if patient_ids is not None:
        known = set(patient_ids)
        unknown = {name: sorted(s - known, key=str) for name, s in sets.items()}
        unknown = {name: ids for name, ids in unknown.items() if ids}
        if unknown:
            raise ValueError(f"split中包含未注册的患者ID: {unknown}")
    leaks: dict = defaultdict(list)
    leaked_ids: set = set()
    for (n1, s1), (n2, s2) in combinations(sets.items(), 2):
        inter = s1 & s2
        if inter:
            leaked_ids |= inter
            leaks[f"{n1}∩{n2}"] = sorted(inter, key=str)
    if leaked_ids:
        raise ValueError(
            f"[LEAKAGE] 发现{len(leaked_ids)}个患者同时出现在多个split: "
            f"{sorted(leaked_ids, key=str)}; 明细: {dict(leaks)}"
        )
    return True


def coverage_report(labels_per_split: MappingType[str, Iterable]) -> dict:
    """逐类支持数 + 并集/交集诊断（协议§2类别覆盖检查表；空类单列）

    参数
    ----
    labels_per_split : dict
        {split名: 标签序列}（None标签归入"None"键，单列计数）。

    返回
    ----
    dict：
        classes            参与统计的类清单（5超类恒在，即使计数为0——空类单列）
        per_split          {split: {class: count}}（含0计数）
        per_split_total    {split: n}
        union              所有split中出现过的类
        intersection       所有split中均出现的类
        missing_per_split  {split: [union中有而该split缺失的类]}
    """
    classes = set(SUPERCLASSES)
    observed: dict[str, Counter] = {}
    for name, labels in labels_per_split.items():
        cnt = Counter(
            lbl if lbl is not None else "None" for lbl in labels
        )
        observed[name] = cnt
        classes |= set(cnt.keys())
    ordered_classes = sorted(classes, key=str)
    per_split = {name: {c: int(cnt.get(c, 0)) for c in ordered_classes}
                 for name, cnt in observed.items()}
    present = {name: {c for c, n in d.items() if n > 0} for name, d in per_split.items()}
    union = set().union(*present.values()) if present else set()
    intersection = set.intersection(*present.values()) if present else set()
    return {
        "classes": ordered_classes,
        "per_split": per_split,
        "per_split_total": {name: sum(d.values()) for name, d in per_split.items()},
        "union": sorted(union, key=str),
        "intersection": sorted(intersection, key=str),
        "missing_per_split": {
            name: sorted(union - present[name], key=str) for name in present
        },
    }


if __name__ == "__main__":
    # 自检：500患者分层划分 + 泄漏断言 + 覆盖报告
    rng = np.random.default_rng(0)
    pids = [f"P{i:04d}" for i in range(500)]
    labels = {p: str(rng.integers(0, 5)) for p in pids}
    splits = patient_wise_split(pids, labels, seed=42)
    sizes = {k: len(v) for k, v in splits.items()}
    assert abs(sizes["train"] / 500 - 0.7) < 0.05
    assert abs(sizes["cal"] / 500 - 0.1) < 0.05
    assert abs(sizes["test"] / 500 - 0.2) < 0.05
    assert assert_no_leakage(splits, pids) is True
    try:
        assert_no_leakage({"train": [1, 2, 3], "cal": [3], "test": [4]})
        raise AssertionError("应检出泄漏")
    except ValueError as e:
        assert "3" in str(e)
    rep = coverage_report({"train": ["NORM"] * 7 + ["MI"] * 3,
                           "test": ["NORM"] * 5 + ["STTC"] * 5})
    assert rep["missing_per_split"]["test"] == ["MI"]
    assert "STTC" in rep["missing_per_split"]["train"]
    print("[自检] 划分模块通过：", sizes)
