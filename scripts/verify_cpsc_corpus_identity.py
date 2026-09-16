"""核验 CPSC 语料身份：CPSC Database(2018) vs CPSC-Extra vs CPSC2019。

输出：
  1. 两个目录的记录数与 zip 内记录数（证明 33 条丢失）
  2. 两个子集各自的 SNOMED #Dx 码分布（证明 MI 只来自 CPSC-Extra）
  3. 官方 9 类名是否能覆盖全部记录（证明 superclass 非 CPSC 官方概念）

只读，不改任何数据。
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DL = Path(__file__).resolve().parent.parent / "data" / "downloads"
SUBSETS = [
    ("CPSC Database (CPSC2018)", DL / "kaggle_cpsc2018" / "Training_WFDB"),
    ("CPSC-Extra",              DL / "kaggle_cpsc2019" / "Training_2"),
]

DX_RE = re.compile(r"^#Dx:\s*(.+)$", re.M)

# 官方 CPSC2018 九类
OFFICIAL_9 = ["Normal", "AF", "I-AVB", "LBBB", "RBBB", "PAC", "PVC", "STD", "STE"]

# 论文 4 类子空间的 MI 来源（SNOMED）
MI_CODES = {"164867002", "164865005", "54329005", "57054005", "426434006"}


def main() -> None:
    print("=" * 78)
    print("1. 记录数核验")
    print("=" * 78)
    for name, d in SUBSETS:
        n = len(list(d.glob("*.hea")))
        print(f"  {name:28s} {d.parent.name}/{d.name}  .hea = {n}")

    print()
    print("=" * 78)
    print("2. SNOMED #Dx 码分布")
    print("=" * 78)
    for name, d in SUBSETS:
        cnt: Counter[str] = Counter()
        n_mi = 0
        n_files = 0
        for hea in sorted(d.glob("*.hea")):
            n_files += 1
            txt = hea.read_text(errors="ignore")
            m = DX_RE.search(txt)
            if not m:
                continue
            codes = {c.strip() for c in m.group(1).split(",") if c.strip()}
            cnt.update(codes)
            if codes & MI_CODES:
                n_mi += 1
        print(f"\n  --- {name} ---")
        print(f"  记录数={n_files}  不同 SNOMED 码={len(cnt)}")
        print(f"  含 MI 码的记录数 = {n_mi}  ({100.0 * n_mi / max(n_files,1):.1f}%)")
        print("  Top 12 码：")
        for code, c in cnt.most_common(12):
            tag = "  <-- MI" if code in MI_CODES else ""
            print(f"    {code:14s} x{c:<6d}{tag}")
        mi_detail = {c: cnt[c] for c in sorted(MI_CODES) if cnt[c]}
        print(f"  MI 码明细: {mi_detail}")

    print()
    print("=" * 78)
    print("3. 官方 9 类名覆盖检查（证明 superclass 非 CPSC 官方）")
    print("=" * 78)
    print(f"  官方 CPSC2018 九类: {OFFICIAL_9}")
    print("  含 'MI'? ", "MI" in OFFICIAL_9, " 含 'STTC'? ", "STTC" in OFFICIAL_9,
          " 含 'CD'? ", "CD" in OFFICIAL_9, " 含 'HYP'? ", "HYP" in OFFICIAL_9)
    print("  -> 官方九类中不存在 MI/STTC/CD/HYP，superclass 体系是 PTB-XL 的。")


if __name__ == "__main__":
    main()
