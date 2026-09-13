"""Audit every per-experiment transfer_result.json against the numbers the
manuscript reports.

v2: the first pass compared the OOD CI counts against the C2 claim, but C2 is
about the ID endpoint, and the degenerate-CI count is restricted to supporting
(positive) cells. Both are fixed here, and every other checkable number in the
manuscript is added.
"""
import collections
import glob
import json

RECORDS = []
for f in sorted(glob.glob("checkpoints/transfer/**/transfer_result.json", recursive=True)):
    d = json.load(open(f, encoding="utf-8"))
    ts = d["methods"]["ts"]
    RECORDS.append({
        "path": f,
        "pair": f"{d['source']}->{d['target']}",
        "arch": d["arch"],
        "seed": d["seed"],
        "ood": ts["ood"]["deltaECE"], "ood_ci": ts["ood"]["ci"],
        "id": ts["id"]["deltaECE"], "id_ci": ts["id"]["ci"],
        "meta": ts.get("meta", {}),
        "id_acc": d.get("id_acc"), "ood_acc": d.get("ood_acc"),
        "n_id": d.get("n_id"), "n_ood": d.get("n_ood"),
    })

main = [r for r in RECORDS if r["arch"] != "mamba"]
it = [r for r in main if r["arch"] == "inceptiontime"]
rn = [r for r in main if r["arch"] == "resnet1d"]

def n(seq): return len(seq)

# --- OOD endpoint ---------------------------------------------------------
ood_pos = [r for r in main if r["ood"] > 0]
ood_cex = [r for r in main if r["ood_ci"][0] <= 0]
widths = {id(r): r["ood_ci"][1] - r["ood_ci"][0] for r in main}
narrow = [r for r in main if widths[id(r)] < 0.005]
sup_degen = [r for r in main if r["ood"] > 0 and widths[id(r)] < 3e-4]
sup_nondeg = [r for r in main if r["ood"] > 0 and widths[id(r)] >= 3e-4]

# --- ID endpoint ----------------------------------------------------------
id_cont_zero = [r for r in main if r["id_ci"][0] <= 0 <= r["id_ci"][1]]
id_above = [r for r in main if r["id_ci"][0] > 0]
id_below = [r for r in main if r["id_ci"][1] < 0]
id_pos = [r for r in main if r["id"] > 0]
id_lt_01 = [r for r in main if r["id"] < -0.01]

mean = lambda xs: sum(xs) / len(xs)
id_mean, ood_mean = mean([r["id"] for r in main]), mean([r["ood"] for r in main])

checks = [
    ("[OOD] positive 51/60", n(ood_pos), 51),
    ("[OOD] InceptionTime 27/30", n([r for r in it if r["ood"] > 0]), 27),
    ("[OOD] ResNet1D 24/30", n([r for r in rn if r["ood"] > 0]), 24),
    ("[OOD] counter-examples 9", n(ood_cex), 9),
    ("[OOD] narrow CI <0.005, 52/60", n(narrow), 52),
    ("[OOD] supporting+degenerate 6", n(sup_degen), 6),
    ("[OOD] excl. degenerate positive 45", n(sup_nondeg), 45),
    ("[OOD] excl. degen IT 24", n([r for r in sup_nondeg if r["arch"] == "inceptiontime"]), 24),
    ("[OOD] excl. degen RN 21", n([r for r in sup_nondeg if r["arch"] == "resnet1d"]), 21),
    ("[ID] CIs containing zero 23/60", n(id_cont_zero), 23),
    ("[ID] CI lower bound >0, 34/60", n(id_above), 34),
    ("[ID] CI entirely below 0, 3/60", n(id_below), 3),
    ("[ID] positive point estimates 47/60", n(id_pos), 47),
    ("[ID] dECE < -0.01, 2/60", n(id_lt_01), 2),
    ("[meta] n_bootstrap 10000 x60", n([r for r in main if r["meta"].get("n_bootstrap") == 10000]), 60),
    ("[meta] bci_method bca x60", n([r for r in main if r["meta"].get("bci_method") == "bca"]), 60),
    ("[meta] metric smooth_ece x60",
     n([r for r in main if str(r["meta"].get("metric", "")).startswith("smooth_ece")]), 60),
    ("[meta] ts_fit source_cal x60", n([r for r in main if r["meta"].get("ts_fit") == "source_cal"]), 60),
]

print(f"{'claim':40s} {'json':>6s} {'paper':>6s}  verdict")
fails = []
for name, got, want in checks:
    ok = got == want
    if not ok:
        fails.append(name)
    print(f"{name:40s} {got:6d} {want:6d}  {'PASS' if ok else '*** FAIL ***'}")

print()
print(f"ID mean  = {id_mean:+.6f}   (paper: +0.0083)")
print(f"OOD mean = {ood_mean:+.6f}   (paper: +0.0159)")
print(f"OOD/ID ratio = {ood_mean/id_mean:.2f}x   (paper: about 1.9x)")
print(f"ID cells < -0.01: {[(r['pair'], r['arch'], r['seed'], round(r['id'], 6)) for r in id_lt_01]}")

# counter-example pattern claims
print()
print("counter-example pattern claims:")
ce = sorted(ood_cex, key=lambda r: r["ood"])
low_acc = [r for r in ce if r["ood_acc"] <= 0.50]
hi_acc = [r for r in ce if r["ood_acc"] > 0.5]
gap = [r for r in ce if (r["id_acc"] - r["ood_acc"]) >= 0.18]
print(f"  OOD accuracy <= 0.50 : {len(low_acc)}/9  (paper 6/9)")
print(f"  OOD accuracy  > 0.50 : {len(hi_acc)}/9   (paper 3/9)")
print(f"  ID-OOD gap >= 0.18   : {len(gap)}/9  (paper 7/9)")
for r in ce:
    print(f"    {r['pair']:20s} {r['arch']:13s} s{r['seed']}  id_acc={r['id_acc']:.3f} "
          f"ood_acc={r['ood_acc']:.3f} gap={r['id_acc']-r['ood_acc']:+.3f}")

# majority-class baseline: paper says OOD accuracy below baseline in 4 of 6 directions
print()
print("OOD accuracy vs 0.25 majority-class baseline (paper: below in 4 of 6 directions):")
by = collections.defaultdict(list)
for r in main:
    by[r["pair"]].append(r)
below = 0
for pair in sorted(by):
    m = mean([r["ood_acc"] for r in by[pair]])
    flag = m < 0.25
    below += flag
    print(f"  {pair:22s} mean ood_acc={m:.3f}  {'BELOW' if flag else ''}")
print(f"  directions below baseline: {below} (paper 4)")

print()
print(f"TOTAL FAILED CHECKS: {len(fails)} -> {fails}")
