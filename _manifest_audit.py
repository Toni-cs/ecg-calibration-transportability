"""Recover the frozen protocol snapshot recorded in the OSF hash manifest.

For every entry, walk the git history of that path and look for a blob whose
sha256 equals the recorded value. If found, the pre-registration anchor is
independently verifiable; if not, the manifest points at content that no
longer exists anywhere and the anchor is broken.
"""
import hashlib
import json
import os
import subprocess

d = json.load(open("docs/osf_archive_manifest.json", encoding="utf-8"))
print("manifest frozen at", d["timestamp_utc"])
print()

found = notfound = 0
for path, rec in d["files"].items():
    want = rec["sha256"]
    # commits that touched this path, newest first
    log = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", path],
        capture_output=True,
    ).stdout.decode().split()
    hit = None
    for c in log:
        blob = subprocess.run(
            ["git", "show", f"{c}:{path}"], capture_output=True
        ).stdout
        if hashlib.sha256(blob).hexdigest() == want:
            hit = (c[:10], len(blob))
            break
    if hit:
        found += 1
        print(f"RECOVERABLE  {path:38s} blob at commit {hit[0]} ({hit[1]} B)")
    else:
        notfound += 1
        print(f"LOST         {path:38s} no git blob matches the recorded sha256 "
              f"(searched {len(log)} commits)")

print()
print(f"--- recoverable={found}  lost={notfound} ---")
