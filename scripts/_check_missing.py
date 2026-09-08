import json
from pathlib import Path
root = Path('D:/A1/ecg-lab-v2')
MISSING = [
    ('chapman', 'ptbxl', 45),
    ('chapman', 'ptbxl', 46),
    ('cpsc', 'chapman', 45),
    ('cpsc', 'chapman', 46),
    ('cpsc', 'ptbxl', 45),
    ('cpsc', 'ptbxl', 46),
    ('ptbxl', 'chapman', 44),
    ('ptbxl', 'chapman', 45),
    ('ptbxl', 'chapman', 46),
]
for src, tgt, seed in MISSING:
    p = root / 'checkpoints' / 'transfer' / f'{src}_{tgt}' / 'resnet1d' / f'seed{seed}' / 'transfer_result.json'
    bm = root / 'checkpoints' / 'transfer' / f'{src}_{tgt}' / 'resnet1d' / f'seed{seed}' / 'best_model.pt'
    exists = False
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            exists = 'methods' in d and isinstance(d['methods'], dict) and len(d['methods']) > 0
        except Exception:
            pass
    status = "DONE" if exists else "MISSING"
    print(f'{src}_{tgt}_seed{seed}: result={status} best_model={bm.exists()}')