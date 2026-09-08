import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
pairs = ["cpsc_ptbxl", "cpsc_chapman", "ptbxl_cpsc", "chapman_cpsc"]
for pair in pairs:
    for seed in ["seed42", "seed43"]:
        p = root / f"checkpoints/transfer/{pair}/inceptiontime/{seed}/transfer_result.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        print(f"\n=== {r['source']}->{r['target']} {seed} (nc={r['num_classes']}) ===")
        print(f"  ID={r['id_acc']:.4f} OOD={r['ood_acc']:.4f}")
        for m, d in r['methods'].items():
            if m.endswith("_pi"):
                continue
            id_d = d.get('id', {}).get('deltaECE', 0)
            ood_d = d.get('ood', {}).get('deltaECE', 0)
            decay = d.get('decay', 0)
            print(f"  {m:12s} ID={id_d:+.4f} OOD={ood_d:+.4f} decay={decay:+.4f}")