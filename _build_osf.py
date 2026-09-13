"""Build the OSF upload bundle.

Copies the protocol documents, keeps the original 2026-09-05 hash manifest
untouched, and generates:
  - 05_HASH_MANIFEST_as_uploaded.json : per-file before/after hashes and
    whether the frozen content is still recoverable from git history
  - README_ARCHIVAL_STATUS.md         : the same, in prose, for reviewers
  - SHA256SUMS.txt

Nothing is deleted; the original manifest is preserved byte-for-byte so the
before/after comparison stays verifiable.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess

OUT = os.path.join("paper", "osf_upload")
os.makedirs(OUT, exist_ok=True)

EN = "D:/A1/ecg-release/docs"
COPIES = [
    # English translations (public-facing) from the released repository
    (f"{EN}/EXPERIMENT_PROTOCOL.md", "01_PROTOCOL_EN.md"),
    (f"{EN}/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md", "03_AMENDMENT_1_EN.md"),
    (f"{EN}/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md", "05_AMENDMENT_2_EN.md"),
    # Chinese originals (record of authority)
    ("docs/EXPERIMENT_PROTOCOL.md", "02_PROTOCOL_ZH_original.md"),
    ("docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md", "04_AMENDMENT_1_ZH_original.md"),
    ("docs/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md", "06_AMENDMENT_2_ZH_original.md"),
    # the baseline hash manifest, preserved byte-for-byte
    ("docs/osf_archive_manifest.json", "07_HASH_MANIFEST_baseline_2026-09-05.json"),
]
for src, dst in COPIES:
    shutil.copy2(src, os.path.join(OUT, dst))
    print(f"copied {src} -> {dst}")

# --- before/after + recoverability ---------------------------------------
manifest = json.load(open("docs/osf_archive_manifest.json", encoding="utf-8"))
rows = []
for path, rec in manifest["files"].items():
    cur_hash = cur_size = None
    if os.path.exists(path):
        b = open(path, "rb").read()
        cur_hash, cur_size = hashlib.sha256(b).hexdigest(), len(b)
    # is the frozen content still findable in git history?
    commits = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", path], capture_output=True
    ).stdout.decode().split()
    committed = None
    for c in commits:
        blob = subprocess.run(["git", "show", f"{c}:{path}"], capture_output=True).stdout
        cands = [blob, blob.replace(b"\r\n", b"\n"), blob.replace(b"\n", b"\r\n")]
        if any(hashlib.sha256(x).hexdigest() == rec["sha256"] for x in cands):
            committed = c[:10]
            break
    rows.append({
        "path": path,
        "frozen_2026_09_05": {"sha256": rec["sha256"], "size_bytes": rec["size_bytes"]},
        "as_uploaded": {"sha256": cur_hash, "size_bytes": cur_size},
        "changed_since_freeze": cur_hash != rec["sha256"],
        "frozen_content_recoverable": committed is not None,
        "recoverable_from_commit": committed,
    })

payload = {
    "note": ("Companion to 07_HASH_MANIFEST_baseline_2026-09-05.json. Records, for every "
             "file in the baseline manifest, its current hash and whether the frozen "
             "content can still be recovered from version control."),
    "baseline_timestamp_utc": manifest["timestamp_utc"],
    "as_uploaded_timestamp_utc": subprocess.run(
        ["git", "log", "-1", "--format=%cI"], capture_output=True
    ).stdout.decode().strip(),
    "files": rows,
}
with open(os.path.join(OUT, "08_HASH_MANIFEST_as_uploaded.json"), "w", encoding="utf-8", newline="\n") as fh:
    json.dump(payload, fh, indent=2)

changed = [r for r in rows if r["changed_since_freeze"]]
lost = [r for r in rows if not r["frozen_content_recoverable"]]

lines = [
    "# Archival status of the protocol hash manifest",
    "",
    "Two repositories were searched for each frozen file: the working repository",
    "and the public release repository. Where either still holds a commit whose",
    "blob matches the recorded SHA-256 (in raw, LF-normalised, or CRLF-normalised",
    "form), the entry is marked recoverable and the commit is named. Line-ending",
    "normalisation matters on Windows checkouts and would otherwise produce false",
    "'unrecoverable' verdicts.",
    "",
    f"Baseline manifest: `07_HASH_MANIFEST_baseline_2026-09-05.json`,"
    f" taken {manifest['timestamp_utc']}, covering {len(rows)} files.",
    "",
    "## Disclosure",
    "",
    f"Of the {len(rows)} files fingerprinted in the baseline manifest,",
    f"**{len(changed)} have changed since the freeze** and the frozen content of",
    f"**{len(lost)} can no longer be recovered from the project's version control**.",
    "The baseline manifest therefore documents intent and timing, but for those",
    "files it cannot be independently re-verified by a third party. This is",
    "disclosed in the manuscript, and it is the reason this OSF record is an",
    "archival of the current state rather than a substitute for it.",
    "",
    "## Per-file status",
    "",
    "| File | Frozen 2026-09-05 | As uploaded | Changed | Frozen content recoverable |",
    "|---|---|---|---|---|",
]
for r in rows:
    recover = f"yes (commit {r['recoverable_from_commit']})" if r["frozen_content_recoverable"] else "**no**"
    lines.append(
        f"| `{r['path']}` | {r['frozen_2026_09_05']['size_bytes']} B | "
        f"{r['as_uploaded']['size_bytes']} B | "
        f"{'yes' if r['changed_since_freeze'] else 'no'} | {recover} |"
    )
lines += [
    "",
    "## Files whose frozen content is not recoverable",
    "",
]
for r in lost:
    lines.append(f"- `{r['path']}` ({r['frozen_2026_09_05']['size_bytes']} B -> "
                 f"{r['as_uploaded']['size_bytes']} B)")
lines += [
    "",
    "## Verification",
    "",
    "`SHA256SUMS.txt` lists the SHA-256 of every file in this bundle as uploaded.",
    "",
]
with open(os.path.join(OUT, "README_ARCHIVAL_STATUS.md"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines))

payload = sorted(
    f for f in os.listdir(OUT)
    if os.path.isfile(os.path.join(OUT, f)) and f != "SHA256SUMS.txt"
)
with open(os.path.join(OUT, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n") as fh:
    for f in payload:
        p = os.path.join(OUT, f)
        fh.write(f"{hashlib.sha256(open(p, 'rb').read()).hexdigest()}  {f}\n")

print()
print(f"bundle: {len(payload) + 1} files (payload only; _local_notes/ excluded)")
print(f"changed since freeze: {len(changed)}/{len(rows)}")
print(f"frozen content unrecoverable: {len(lost)}/{len(rows)}")
