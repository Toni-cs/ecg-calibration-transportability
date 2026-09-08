"""等待所有12个P0实验完成，然后汇总结果。
这个脚本会循环检查直到所有12个transfer_result.json都生成，或python进程结束。
"""
import json
import time
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / "checkpoints" / "transfer"

directions = ["chapman_ptbxl", "cpsc_chapman", "cpsc_ptbxl", "ptbxl_chapman"]
seeds = [44, 45, 46]

def count_completed():
    count = 0
    for d in directions:
        for s in seeds:
            path = base / d / "inceptiontime" / f"seed{s}" / "transfer_result.json"
            if path.exists():
                count += 1
    return count

def python_running():
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Process python -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=10
        )
        return int(result.stdout.strip()) > 0
    except:
        return False

print(f"初始进度: {count_completed()}/12")
print("等待所有实验完成...")

max_wait = 7200  # 最多等待2小时
waited = 0
while waited < max_wait:
    completed = count_completed()
    if completed >= 12:
        print(f"\n所有12个实验完成！(等待了{waited}秒)")
        break
    if not python_running() and completed < 12:
        print(f"\nPython进程已结束，但只有{completed}/12完成。可能有实验失败。")
        break
    if waited % 300 == 0 and waited > 0:
        print(f"  已等待{waited}秒，{completed}/12完成...")
    time.sleep(30)
    waited += 30

# 汇总结果
print("\n" + "=" * 80)
print("P0补齐实验最终汇总")
print("=" * 80)

completed = 0
results = []
for d in directions:
    for s in seeds:
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

print(f"\n进度: {completed}/12 完成")
if completed > 0:
    sig_count = sum(1 for r in results if r[5] is True)
    print(f"ts方法显著为正: {sig_count}/{completed}")
    print("\n按方向汇总:")
    for d in directions:
        dir_results = [r for r in results if r[0] == d and r[2] is not None]
        if dir_results:
            sig = sum(1 for r in dir_results if r[5])
            print(f"  {d}: {sig}/{len(dir_results)} seed显著为正")