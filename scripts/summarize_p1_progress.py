"""汇总P1补齐实验结果：检查6个resnet1d实验的完成状态和ts方法OOD ΔECE结果。"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / "checkpoints" / "transfer"

directions = ["chapman_cpsc", "ptbxl_cpsc"]
seeds = [44, 45, 46]

print("=" * 80)
print("P1补齐实验汇总 (resnet1d架构)")
print("=" * 80)

completed = 0
results = []

for d in directions:
    for s in seeds:
        path = base / d / "resnet1d" / f"seed{s}" / "transfer_result.json"
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

print(f"\n进度: {completed}/6 完成")
if completed > 0:
    sig_count = sum(1 for r in results if r[5] is True)
    print(f"ts方法显著为正: {sig_count}/{completed}")
    print("\n按方向汇总:")
    for d in directions:
        dir_results = [r for r in results if r[0] == d and r[2] is not None]
        if dir_results:
            sig = sum(1 for r in dir_results if r[5])
            print(f"  {d}: {sig}/{len(dir_results)} seed显著为正")