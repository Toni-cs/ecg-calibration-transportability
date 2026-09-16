"""生成 OSF 预注册存档清单（本地时间戳 + 文件哈希）。

无 OSF token 时生成本地存档，证明协议和代码在实验前已固定。
有 OSF token 时可上传到 OSF（需设置 OSF_TOKEN 环境变量）。
"""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ARCHIVE_FILES = [
    "docs/EXPERIMENT_PROTOCOL.md",
    "paper/main_bspc.tex",
    "scripts/eval_transfer.py",
    "scripts/eval_l2_shift.py",
    "scripts/step2_predictability.py",
    "scripts/step3_deployment.py",
    "scripts/summarize_l2_shifts.py",
    "src/data/l2_shifts.py",
    "src/data/mapping.py",
    "src/utils/calibration.py",
    "src/utils/calibration_methods.py",
    "src/utils/prior_shift.py",
    "src/models/ecg_classifier.py",
    "src/models/baselines.py",
]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = {
        "timestamp_utc": timestamp,
        "project": "DECAL: ECG Calibration Repair ID→OOD Decay Decomposition",
        "target_venue": "BSPC (中科院二区)",
        "files": {},
    }
    for rel in ARCHIVE_FILES:
        p = ROOT / rel
        if p.exists():
            manifest["files"][rel] = {
                "sha256": file_hash(p),
                "size_bytes": p.stat().st_size,
                "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
            }
        else:
            manifest["files"][rel] = {"error": "not found"}

    out = ROOT / "docs" / "osf_archive_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"存档清单已生成: {out}")
    print(f"时间戳: {timestamp}")
    print(f"文件数: {sum(1 for v in manifest['files'].values() if 'sha256' in v)}/{len(ARCHIVE_FILES)}")
    print(f"\n文件哈希:")
    for rel, info in manifest["files"].items():
        if "sha256" in info:
            print(f"  {rel}: {info['sha256'][:16]}... ({info['size_bytes']} bytes)")

    osf_token = os.environ.get("OSF_TOKEN")
    if osf_token:
        print("\n[OSF token 检测到，可上传到 OSF]")
    else:
        print("\n[无 OSF token，本地存档已生成。设置 OSF_TOKEN 环境变量后可上传。]")
        print("[注：当前为实验中存档，非预注册。预注册应在实验前完成。]")


if __name__ == "__main__":
    main()