"""Apply an OSF DOI everywhere the manuscript and cover letter reference it.

Usage:
    python _apply_osf_doi.py 10.17605/OSF.IO/XXXXX

Does four replacements (three in main.tex, one in cover_letter.tex), then
recompiles both documents. Every replacement is verified after writing; a
pattern that no longer matches is reported rather than silently skipped.
"""
import os
import re
import subprocess
import sys

if len(sys.argv) < 2 or not sys.argv[1].startswith("10."):
    print("usage: python _apply_osf_doi.py 10.17605/OSF.IO/XXXXX")
    raise SystemExit(2)

DOI = sys.argv[1].strip()
URL = f"https://doi.org/{DOI}"
MAIN = "paper/main.tex"
LETTER = "paper/cover_letter.tex"

EDITS = [
    (
        MAIN,
        "\\textbf{Pre-registration archival status.} The protocol and both amendments\n"
        "(A1, A2), together with an archival-status report, are being deposited under\n"
        "a public OSF timestamp before publication. Until that record is live,\n"
        "\\texttt{docs/osf\\_archive\\_manifest.json} is a local snapshot taken on\n"
        "2026-09-05 and is not a substitute for public registration.",
        "\\textbf{Pre-registration archival status.} The protocol, both amendments\n"
        "(A1, A2), and a per-file archival-status report are publicly archived at\n"
        f"\\url{{{URL}}}. \\texttt{{docs/osf\\_archive\\_manifest.json}} is the internal\n"
        "snapshot taken on 2026-09-05; it is not a substitute for the public record.",
    ),
    (
        MAIN,
        "\\texttt{docs/osf\\_archive\\_manifest.json} (local snapshot; public OSF\n"
        "archival pending); revision A1 full text in",
        "\\texttt{docs/osf\\_archive\\_manifest.json} (local snapshot; archived at\n"
        f"\\url{{{URL}}}); revision A1 full text in",
    ),
    (
        LETTER,
        "\\textbf{Public OSF archival is not yet complete} and is\n"
        "declared as pending in the manuscript; we will register the protocol and\n"
        "both amendments, together with an archival-status report, under a public\n"
        "OSF timestamp before publication.",
        "The protocol, both amendments, and a per-file\n"
        f"archival-status report are publicly archived at \\url{{{URL}}}.",
    ),
]


def apply(path, old, new):
    text = open(path, encoding="utf-8").read()
    if new in text:
        print(f"  [already applied] {path}")
        return True
    if old not in text:
        print(f"  [NOT FOUND] {path}: the source text has changed, edit by hand:")
        print("              " + old.replace("\n", "\\n")[:100])
        return False
    open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
    after = open(path, encoding="utf-8").read()
    ok = new in after
    print(f"  [{'OK' if ok else 'FAILED'}] {path}")
    return ok


print(f"applying DOI {DOI}")
results = [apply(p, o, n) for p, o, n in EDITS]

# recompile; a PDF held open by a viewer will refuse to be written
for job, passes in (("main", 2), ("cover_letter", 2)):
    for _ in range(passes):
        r = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", f"{job}.tex"],
            cwd="paper", capture_output=True,
        )
    out = r.stdout.decode("utf-8", "ignore")
    m = re.search(r"Output written on .*\((\d+) pages", out)
    err = "Emergency stop" in out or "Fatal error" in out
    print(f"  {job}: {'ERROR (PDF locked or LaTeX error)' if err else (m.group(0) if m else 'compiled')}")

print()
print("verified DOI occurrences:")
for path in (MAIN, LETTER):
    t = open(path, encoding="utf-8").read()
    print(f"  {path}: {t.count(URL)}")
print()
print("next: git add paper/main.tex paper/main.pdf paper/cover_letter.tex paper/cover_letter.pdf && git commit")
