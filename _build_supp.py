"""Assemble the BSPC submission supplementary package.

Everything the manuscript promises to submit exists locally but had never been
assembled. This builds paper/submission/supplementary/ plus an index README and
a SHA-256 checksum file, writes nothing outside paper/submission/, and deletes
nothing.
"""
import glob
import hashlib
import os
import shutil

SRC = os.path.abspath(".")
OUT = os.path.join("paper", "submission", "supplementary")
created = []


def put(src, subdir, name=None):
    dst = os.path.join(OUT, subdir)
    os.makedirs(dst, exist_ok=True)
    target = os.path.join(dst, name or os.path.basename(src))
    shutil.copy2(src, target)
    created.append(target)
    return target


# S1 -- protocol documents and the hash manifest
for f in [
    "docs/EXPERIMENT_PROTOCOL.md",
    "docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md",
    "docs/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md",
    "docs/osf_archive_manifest.json",
]:
    if os.path.exists(f):
        put(f, "S1_protocol")

# S2 -- aggregate result tables
for f in sorted(glob.glob("results/*.csv")):
    put(f, "S2_result_tables")

# S3 -- per-experiment result files, kept in their transfer/<pair>/<arch>/seed layout
for f in sorted(glob.glob("checkpoints/transfer/**/transfer_result.json", recursive=True)):
    rel = os.path.relpath(f, "checkpoints/transfer")
    parts = rel.split(os.sep)
    put(f, os.path.join("S3_per_experiment", *parts[:-1]), name="transfer_result.json")

# S4 -- the 60 per-seed reliability diagrams referenced by the paper
for f in sorted(glob.glob("paper/figures/fig_reliability_supp_*.pdf")):
    put(f, "S4_reliability_diagrams")

# index + checksums
lines = [
    "# Supplementary material",
    "",
    "Manuscript: *When Does Temperature Scaling Pay Off in Cross-Corpus ECG",
    "Transfer? A Multi-Seed Calibration Boundary Study*",
    "",
    "Target journal: Biomedical Signal Processing and Control (Elsevier).",
    "",
    "## Contents",
    "",
    "| Folder | Contents | Files |",
    "|---|---|---|",
]
folders = sorted({os.path.dirname(p) for p in created})
for folder in folders:
    n = sum(1 for p in created if os.path.dirname(p) == folder)
    rel = os.path.relpath(folder, OUT).replace(os.sep, "/")
    lines.append(f"| `{rel}/` | see below | {n} |")
lines += [
    "",
    "### S1_protocol",
    "`EXPERIMENT_PROTOCOL.md` (protocol v2.1-A1), the A1 endpoint re-location",
    "amendment, the A2 family-reduction amendment, and",
    "`osf_archive_manifest.json` -- the file-level SHA-256 manifest taken on",
    "2026-09-05. See `docs/` in the public repository for the same documents.",
    "",
    "### S2_result_tables",
    "Aggregate result tables underlying every number in the main text.",
    "",
    "### S3_per_experiment",
    "`transfer_result.json` for each cell of the 60-experiment transfer grid,",
    "kept in the `transfer/<pair>/<architecture>/seed<42-46>/` layout of the",
    "public repository.",
    "",
    "### S4_reliability_diagrams",
    "The 60 per-seed reliability diagrams catalogued in the Supplementary",
    "Materials section of the manuscript, named",
    "`fig_reliability_supp_{pair}_{arch}_seed{s}.pdf`.",
    "",
    "## Verification",
    "",
    "`SHA256SUMS.txt` lists the SHA-256 of every file in this package. Verify",
    "with `sha256sum -c SHA256SUMS.txt`.",
    "",
]

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))

sums = []
for p in sorted(created):
    digest = hashlib.sha256(open(p, "rb").read()).hexdigest()
    sums.append(f"{digest}  {os.path.relpath(p, OUT).replace(os.sep, '/')}")
with open(os.path.join(OUT, "SHA256SUMS.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(sums) + "\n")

total = sum(os.path.getsize(p) for p in created)
print(f"assembled {len(created)} files into {OUT}")
print(f"total payload {total/1e6:.2f} MB")
for folder in folders:
    n = sum(1 for p in created if os.path.dirname(p) == folder)
    print(f"  {os.path.relpath(folder, OUT):32s} {n} files")
