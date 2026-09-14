# -*- coding: utf-8 -*-
"""论文完整性检查：压缩/编辑前后的 \cite \ref \label、限制条目、数字、AI 腔"""
import re
import subprocess

PATH = r"D:\A1\ecg-lab-v2\paper\main.tex"
BS = chr(92)

cur = open(PATH, encoding="utf-8").read()
old = subprocess.run(["git", "show", "HEAD:paper/main.tex"],
                     capture_output=True, cwd=r"D:\A1\ecg-lab-v2").stdout.decode("utf-8")


def body(t: str) -> str:
    b = t.split(BS + "begin{document}", 1)[1].split(BS + "section*{Supplementary Materials}")[0]
    return re.sub(r"%.*", "", b)


ob, cb = body(old), body(cur)
cite = BS + "cite{"
ref = BS + "ref{"
lab = BS + "label{"

print(f"cite calls : {ob.count(cite)} -> {cb.count(cite)}")
print(f"ref calls  : {ob.count(ref)} -> {cb.count(ref)}")
print(f"labels     : {ob.count(lab)} -> {cb.count(lab)}")

pat = r"\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii)\)"
lim_pat = r"\((?:[ivx]+|x{0,2}(?:ix|iv|v?i{0,3}))\)"


def lim_items(t: str):
    s = t.split("Limitations and future work", 1)[1]
    s = s.split(BS + "section", 1)[0]
    return re.findall(lim_pat, s)


oi, ci = lim_items(ob), lim_items(cb)
print(f"limitation items: {len(oi)} -> {len(ci)}  missing: {sorted(set(oi) - set(ci)) or 'NONE'}")

nums_o = re.findall(r"\d+(?:[.,]\d+)?", ob)
nums_c = re.findall(r"\d+(?:[.,]\d+)?", cb)
print(f"numeric tokens: {len(set(nums_o))} -> {len(set(nums_c))} unique, "
      f"{len(nums_o)} -> {len(nums_c)} occurrences")
print(f"  vanished unique: {sorted(set(nums_o) - set(nums_c)) or 'NONE'}")

banned = re.findall(r"(delve|crucial|pivotal|comprehensive|It is worth noting|Notably,|Importantly,)",
                    cb, re.I)
print(f"AI-tells: {banned or 'NONE'}")
print(f"em-dash (---) in prose: {len(re.findall(chr(45) * 3, cb))}")
print(f"placeholder check: Zero Token={('Zero Token' in cur)}  example.com={('example.com' in cur)}")
