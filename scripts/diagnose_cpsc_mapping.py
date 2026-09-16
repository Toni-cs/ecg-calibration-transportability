"""诊断 CPSC 预处理映射质量：HYP 来源、多标签、skipped、446813000 去向。

注：下面的 source 标签 "cpsc2018"/"cpsc2019" 是**历史内部命名**，与
preprocess_cpsc.py 中写入 patient_id 前缀的标签一致，故保留。实际语料身份为
"cpsc2018" = CPSC Database，"cpsc2019" = **CPSC-Extra**（非 CPSC2019）。
详见 docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md。
"""
from __future__ import annotations
import pathlib, json
from collections import Counter
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
from src.data.mapping import SCP_TO_SUPERCLASS

from8 = _PROJECT_ROOT / "data/downloads/kaggle_cpsc2018/Training_WFDB"
from9 = _PROJECT_ROOT / "data/downloads/kaggle_cpsc2019/Training_2"

PRIORITY = ["MI", "STTC", "CD", "HYP", "NORM"]

def parse_dx(hea):
    for line in hea.read_text(encoding="utf-8", errors="ignore").splitlines():
        t = line.strip()
        if t.startswith("#Dx:") or t.startswith("# Dx:"):
            return [c.strip() for c in t.split(":", 1)[1].split(",") if c.strip()]
    return []

def codes_to_sc(codes):
    r = []
    for c in codes:
        sc = SCP_TO_SUPERCLASS.get(str(c))
        if sc is not None:
            r.append(sc)
    return r

def single_label(scs):
    for lbl in PRIORITY:
        if lbl in scs:
            return lbl
    return None

all_records = []
for d, src in [(from8, "cpsc2018"), (from9, "cpsc2019")]:
    for hea in sorted(d.rglob("*.hea")):
        codes = parse_dx(hea)
        scs = codes_to_sc(codes)
        lbl = single_label(scs)
        all_records.append((src, hea.stem, codes, scs, lbl))

total = len(all_records)
mapped = [r for r in all_records if r[4] is not None]
skipped = [r for r in all_records if r[4] is None]
multi = [r for r in all_records if len(r[2]) > 1]

print(f"=== 总览 ===")
print(f"Total: {total}, Mapped: {len(mapped)}, Skipped: {len(skipped)}, Multi-label: {len(multi)}")

print(f"\n=== Skipped ({len(skipped)}) ===")
for s, n, c, sc, lbl in skipped:
    print(f"  {s}_{n}: codes={c} superclasses={sc}")

print(f"\n=== HYP 记录 ({sum(1 for r in mapped if r[4]=='HYP')}) ===")
hyp_records = [r for r in mapped if r[4] == "HYP"]
for s, n, c, sc, lbl in hyp_records:
    print(f"  {s}_{n}: codes={c} superclasses={sc} -> {lbl}")

print(f"\n=== 446813000 (left atrial hypertrophy) 去向 ===")
code446 = [r for r in all_records if "446813000" in r[2]]
print(f"  Total occurrences: {len(code446)}")
fate = Counter(r[4] for r in code446)
print(f"  Label fate: {dict(fate)}")
for s, n, c, sc, lbl in code446[:8]:
    print(f"    {s}_{n}: codes={c} superclasses={sc} -> {lbl}")

print(f"\n=== 多标签统计 ===")
multi_sc = Counter(len(r[3]) for r in multi)
print(f"  Multi-label record count by #superclasses: {dict(multi_sc)}")
multi_fate = Counter(r[4] for r in multi)
print(f"  Multi-label final label distribution: {dict(multi_fate)}")

print(f"\n=== HYP 相关 SNOMED 码出现频次 ===")
hyp_codes = [c for r in all_records for c in r[2] if SCP_TO_SUPERCLASS.get(c) == "HYP"]
print(f"  HYP-code occurrences: {len(hyp_codes)}, distinct: {len(set(hyp_codes))}")
for code, cnt in Counter(hyp_codes).most_common():
    print(f"    {code}: {cnt}")

print(f"\n=== 优先级压制统计 ===")
for r in multi:
    if "HYP" in r[3] and r[4] != "HYP":
        pass
suppressed_hyp = [r for r in multi if "HYP" in r[3] and r[4] != "HYP"]
print(f"  HYP被更高优先级压制: {len(suppressed_hyp)}")
sup_by = Counter(r[4] for r in suppressed_hyp)
print(f"  压制HYP的胜出类: {dict(sup_by)}")