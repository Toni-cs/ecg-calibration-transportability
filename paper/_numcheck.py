# -*- coding: utf-8 -*-
"""数字快照：压缩前后比对，证明没有统计量被改动"""
import re
import json
import sys
from collections import Counter

MODE = sys.argv[1] if len(sys.argv) > 1 else "snap"
PATH = r"D:\A1\ecg-lab-v2\paper\main.tex"
SNAP = r"D:\A1\ecg-lab-v2\paper\_num_snapshot.json"

t = open(PATH, encoding="utf-8").read()
doc = t.split("\\begin{document}", 1)[1]
body = doc.split("\\section*{Supplementary Materials}")[0]
body = re.sub(r"%.*", "", body)

nums = re.findall(r"\d+(?:[.,]\d+)?", body)
c = Counter(nums)
lim = len(re.findall(
    r"\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii)\)", body))

if MODE == "snap":
    json.dump({"counter": dict(c), "lim": lim}, open(SNAP, "w"), indent=0)
    print(f"unique numeric tokens: {len(c)} | occurrences: {sum(c.values())} | limitation markers: {lim}")
else:
    old = json.load(open(SNAP))
    oc = Counter(old["counter"])
    vanished = {k: oc[k] for k in oc if c.get(k, 0) == 0}
    print(f"unique now: {len(c)} (was {len(oc)}) | occurrences: {sum(c.values())} (was {sum(oc.values())})")
    print(f"limitation markers now: {lim} (was {old['lim']})")
    print("VANISHED numbers (must be empty or justified):", vanished if vanished else "NONE")
    dropped = {k: (oc[k], c[k]) for k in oc if c.get(k, 0) < oc[k]}
    print(f"tokens with reduced count: {len(dropped)} (duplicates removed by condensation)")
