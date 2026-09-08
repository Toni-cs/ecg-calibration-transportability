"""汇总P0补齐实验结果：检查12个目标实验的完成状态和ts方法OOD ΔECE结果。"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / "checkpoints" / "transfer"

directions = ["chapman_ptbxl", "cpsc_chapman", "cpsc_ptbxl", "ptbxl_chapman"]
seeds = [44, 45, 46]

print("=" * 80)
print("P0补齐实验进度汇总")
print("=" * 80)

completed = 0
total = 0
results = []

for d in directions:
    for s in seeds:
        total += 1
        path = base / d / "inceptiontime" / f"seed{s}" / "transfer_result.json"
        if path.exists():
            completed += 1
            data = json.loads(path.read_text(encoding="utf-8"))
            ts = data.get("methods", {}).get("ts", {})
            ood = ts.get("ood", {})
            delta_ece = ood.get("deltaECE", None)
            ci = ood.get("ci", [None, None])
            ci_low, ci_high = ci[0], ci[1]
            significant = ci_low is not None and ci_low > 0
            results.append((d, s, delta_ece, ci_low, ci_high, significant))
            status = "✅" if significant else "❌"
            print(f"{d}/seed{s}: ΔECE_OOD={delta_ece:+.4f} CI=[{ci_low:+.4f},{ci_high:+.4f}] {status}")
        else:
            results.append((d, s, None, None, None, None))
            print(f"{d}/seed{s:02d}: ⏳未完成")

print(f"\n进度: {completed}/{total} 完成")

if completed > 0:
    sig_count = sum(1 for r in results if r[5] is True)
    nonsig_count = sum(1 for r in results if r[5] is False)
    print(f"ts方法显著为正: {sig_count}/{completed}")
    print(f"ts方法不显著: {nonsig_count}/{completed}")

    print("\n按方向汇总:")
    for d in directions:
        dir_results = [r for r in results if r[0] == d and r[2] is not None]
        if dir_results:
            sig = sum(1 for r in dir_results if r[5])
            print(f"  {d}: {sig}/{len(dir_results)} seed显著为正")
        else:
            print(f"  {d}: 0/0 (未完成)")