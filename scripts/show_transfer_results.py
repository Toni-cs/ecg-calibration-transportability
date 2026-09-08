import json, sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
pairs = [
    ("cpsc_ptbxl", "seed42"),
    ("cpsc_chapman", "seed42"),
    ("ptbxl_cpsc", "seed42"),
    ("chapman_cpsc", "seed42"),
]
for pair, seed in pairs:
    p = root / f"checkpoints/transfer/{pair}/inceptiontime/{seed}/transfer_result.json"
    if not p.exists():
        print(f"\n=== {pair} {seed}: NOT FOUND ===")
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    print(f"\n=== {r['source']}->{r['target']} {seed} (num_classes={r['num_classes']}) ===")
    print(f"label_map={r.get('label_map','?')}")
    print(f"ID acc={r['id_acc']:.4f} OOD acc={r['ood_acc']:.4f}")
    for m, d in r['methods'].items():
        id_d = d.get('id', {}).get('deltaECE', 0)
        ood_d = d.get('ood', {}).get('deltaECE', 0)
        decay = d.get('decay', 0)
        print(f"  {m:12s} ID={id_d:+.4f} OOD={ood_d:+.4f} decay={decay:+.4f}")