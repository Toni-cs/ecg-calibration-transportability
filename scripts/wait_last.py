import time, json
from pathlib import Path

p = Path("checkpoints/transfer/ptbxl_chapman/inceptiontime/seed46/transfer_result.json")
for i in range(80):
    if p.exists():
        break
    if i % 4 == 0:
        print(f"等待... {i*30}秒")
    time.sleep(30)

if p.exists():
    data = json.loads(p.read_text(encoding="utf-8"))
    ts = data.get("methods", {}).get("ts", {}).get("ood", {})
    print(f"完成! ptbxl_chapman/seed46: ΔECE_OOD={ts.get('deltaECE')}, CI={ts.get('ci')}")
else:
    print("超时: 40分钟内未完成")