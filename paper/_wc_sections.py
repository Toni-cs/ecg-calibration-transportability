# -*- coding: utf-8 -*-
"""按 section 统计主文字数，定位可压缩区域"""
import re

t = open(r"D:\A1\ecg-lab-v2\paper\main.tex", encoding="utf-8").read()
body = t.split("\\begin{document}", 1)[1]
main_text = body.split("\\section*{Supplementary Materials}")[0]


def wc(s: str) -> int:
    s = re.sub(r"%.*", "", s)
    s = re.sub(r"\\begin\{(table|figure|tabular|longtable)\}.*?\\end\{\1\}", " ", s, flags=re.S)
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", " ", s)
    s = re.sub(r"[{}$&~^_\\]", " ", s)
    return len([w for w in s.split() if any(c.isalpha() for c in w)])


# 按 \section / \subsection 切分
parts = re.split(r"(\\section\*?\{[^}]*\}|\\subsection\*?\{[^}]*\})", main_text)
cur = "(front matter)"
rows = []
for p in parts:
    if p.startswith("\\section") or p.startswith("\\subsection"):
        title = re.sub(r"\\[a-z]+\*?\{|\}", "", p)
        cur = title
        rows.append([cur, 0])
    else:
        if rows:
            rows[-1][1] += wc(p)
        else:
            rows.append([cur, wc(p)])

total = 0
for name, n in rows:
    total += n
    if n > 120:
        print(f"{n:5d}  {name[:70]}")
print(f"{total:5d}  TOTAL (approx)")
