"""Merge the 4-method backup and 6-method results into the full 8-method table."""
import json
from pathlib import Path

PAIRS = [
    ("ptbxl_chapman", "seed42"),
    ("chapman_ptbxl", "seed42"),
    ("chapman_ptbxl", "seed43"),
]

for pair, seed in PAIRS:
    d = Path("checkpoints/transfer") / pair / "inceptiontime" / seed
    f6 = d / "transfer_result.json"
    merged = None
    for bak in ("transfer_result_4method.json", "transfer_result_6method.json"):
        fb = d / bak
        if fb.exists():
            rb = json.loads(fb.read_text(encoding="utf-8"))
            if merged is None:
                merged = json.loads(f6.read_text(encoding="utf-8"))
            for k, v in rb["methods"].items():
                if k not in merged["methods"]:
                    merged["methods"][k] = v
    if merged is None:
        print(f"[skip] {d}: no backup file")
        continue
    out = d / "transfer_result_full.json"
    out.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(f"[ok] {out}: {sorted(merged['methods'].keys())}")