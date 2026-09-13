"""Same audit as _manifest_audit.py, but with line-ending normalisation.

Git may store LF while the working tree holds CRLF (core.autocrlf on Windows),
so a byte-exact sha256 comparison produces false 'LOST' verdicts. For each
historical blob we test: raw bytes, LF-normalised, and CRLF-normalised.
"""
import hashlib
import json
import subprocess

d = json.load(open("docs/osf_archive_manifest.json", encoding="utf-8"))


def variants(b: bytes):
    out = {"raw": b}
    if b"\r\n" in b:
        out["lf"] = b.replace(b"\r\n", b"\n")
    if b"\n" in b and b"\r\n" not in b:
        out["crlf"] = b.replace(b"\n", b"\r\n")
    return out


found = lost = 0
for path, rec in d["files"].items():
    want = rec["sha256"]
    log = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", path], capture_output=True
    ).stdout.decode().split()
    hit = None
    for c in log:
        blob = subprocess.run(["git", "show", f"{c}:{path}"], capture_output=True).stdout
        for name, v in variants(blob).items():
            if hashlib.sha256(v).hexdigest() == want:
                hit = (c[:10], len(blob), name)
                break
        if hit:
            break
    if hit:
        found += 1
        print(f"RECOVERABLE  {path:38s} commit {hit[0]} ({hit[1]} B, {hit[2]} form)")
    else:
        lost += 1
        print(f"LOST         {path:38s} searched {len(log)} commit(s), no normalised match")

print()
print(f"--- recoverable={found}  lost={lost} ---")
