"""生成全方法表 LaTeX（正反方向 seed42）。"""
import json
from pathlib import Path

rows = [
    ("Temperature Scaling (TS)", "ts", 1),
    ("Isotonic (OvR)", "isotonic", None),
    ("Per-class Platt", "platt", 10),
    ("Vector scaling", "vector", 5),
    ("Matrix scaling", "matrix", 25),
    ("Dirichlet", "dirichlet", 30),
    ("Saerens EM", "em_prior", None),
    ("BBSE", "bbse_prior", None),
]

def load(pair, seed, fname="transfer_result_full.json"):
    f = Path("checkpoints/transfer") / pair / "inceptiontime" / seed / fname
    if not f.exists():
        f = f.parent / "transfer_result.json"
    return json.loads(f.read_text(encoding="utf-8"))

fwd = load("ptbxl_chapman", "seed42")
rev = load("chapman_ptbxl", "seed42")

lines = []
lines.append(r"\begin{table}[t]")
lines.append(r"\centering")
lines.append(r"\caption{S1 zero-shot transfer, all methods (InceptionTime, seed 42). "
             r"$\Delta$ECE $=$ ECE$_{raw}-$ECE$_{cal}$ (positive $=$ benefit); "
             r"decay $=$ $\Delta$ECE$_{OOD}-\Delta$ECE$_{ID}$. "
             r"Matrix scaling did not converge in the reverse direction "
             r"(ID raw ECE $0.016$ leaves no optimization headroom).}")
lines.append(r"\label{tab:fullmethods}")
lines.append(r"\begin{tabular}{lrrrrrr}")
lines.append(r"\toprule")
lines.append(r" & \multicolumn{3}{c}{PTB-XL$\to$Chapman} & \multicolumn{3}{c}{Chapman$\to$PTB-XL} \\")
lines.append(r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}")
lines.append(r"Method & ID & OOD & decay & ID & OOD & decay \\")
lines.append(r"\midrule")
for name, key, npar in rows:
    f = fwd["methods"].get(key)
    r = rev["methods"].get(key)
    if f is None or r is None:
        continue
    lines.append(
        f"{name} & {f['id']['deltaECE']:+.3f} & {f['ood']['deltaECE']:+.3f} & "
        f"{f['decay']:+.3f} & {r['id']['deltaECE']:+.3f} & {r['ood']['deltaECE']:+.3f} & "
        f"{r['decay']:+.3f} \\\\")
lines.append(r"\bottomrule")
lines.append(r"\end{tabular}")
lines.append(r"\end{table}")
print("\n".join(lines))