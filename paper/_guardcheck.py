"""Compare pre-compression vs current main text for lost hedges, qualifiers,
and provenance tokens.

Whitespace is normalised before phrase counting so that LaTeX line breaks do
not create false negatives. Counts are also reported against the expected
proportional shrinkage, because a 27% word reduction must reduce every token
count somewhat.
"""
import re
import subprocess
from collections import Counter

BS = chr(92)
ESC = re.escape(BS)  # a literal backslash, escaped for regex use

OLD = subprocess.run(
    ["git", "show", "HEAD~1:paper/main.tex"], capture_output=True
).stdout.decode("utf-8")
NEW = open("main.tex", encoding="utf-8").read()


def main_text(t):
    b = t.split(BS + "begin{document}", 1)[1]
    return b.split(BS + "section*{Supplementary Materials}")[0]


def flat(s):
    """Collapse all whitespace to single spaces."""
    return re.sub(r"\s+", " ", s)


OB, NB = main_text(OLD), main_text(NEW)
OF, NF = flat(OB), flat(NB)

# --- word counts -----------------------------------------------------------
def wc(s):
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = re.sub(
        ESC + r"begin\{(?:table|figure|tabular)\}.*?" + ESC + r"end\{(?:table|figure|tabular)\}",
        " ",
        s,
        flags=re.S,
    )
    s = re.sub(r"\$\$?.*?\$\$?", " X ", s, flags=re.S)          # math -> placeholder
    s = re.sub(ESC + r"[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", s)     # commands
    s = re.sub(r"[{}$&~^_]", " ", s)
    return len([w for w in s.split() if any(c.isalpha() for c in w)])


WO, WN = wc(OB), wc(NB)
ratio = WN / WO
print(f"=== word count: old={WO}  new={WN}  ratio={ratio:.3f} ===")

# --- provenance tokens -----------------------------------------------------
pat_tt = re.compile(ESC + r"texttt\{([^}]*)\}")
ot, nt = Counter(flat(x) for x in pat_tt.findall(OF)), Counter(flat(x) for x in pat_tt.findall(NF))
print()
print("=== \\texttt tokens (filenames/fields) ===")
lost = {k: (ot[k], nt.get(k, 0)) for k in ot if nt.get(k, 0) < ot[k]}
print(lost if lost else "NONE")
print("total: %d -> %d" % (sum(ot.values()), sum(nt.values())))

pat_s = re.compile(ESC + r"S" + ESC + r"ref\{([^}]*)\}")
os_, ns_ = Counter(pat_s.findall(OF)), Counter(pat_s.findall(NF))
print()
print("=== \\S\\ref targets ===")
lost = {k: (os_[k], ns_.get(k, 0)) for k in os_ if ns_.get(k, 0) < os_[k]}
print(lost if lost else "NONE")

# --- qualifier lexicon -----------------------------------------------------
LEX = [
    "not a predictive", "cannot be extrapolated", "not asserted", "exploratory",
    "not confirmatory", "post-hoc", "in-sample", "implemented but not enabled",
    "historical provenance", "fully balanced", "pre-registered",
    "registered as future work", "unavailable", "not excluded",
    "not interpretable", "conditional on", "limited to", "do not affect",
    "should be read jointly", "plausibly", "toy experiment", "heuristic",
    "tendency rather", "no label-free gate is claimed", "no post-hoc exclusion",
    "systematic", "successful", "disclosed", "transparently", "without a threshold",
    "not universally safe", "held-out dose", "Noise Stress Test",
    "under PhysioNet licensing", "pair, seed, shift", "the two CI methods",
    "not enabled", "were not used", "not claimed", "exploratory + robustness",
]
print()
print("=== qualifier lexicon (whitespace-normalised) ===")
print(f"{'phrase':44s} {'old':>4s} {'new':>4s} {'exp':>5s}  verdict")
for phrase in LEX:
    co, cn = OF.count(phrase), NF.count(phrase)
    if not (co or cn):
        continue
    exp = co * ratio
    if cn < co and cn < exp - 0.75:
        verdict = "DISPROPORTIONATE LOSS"
    elif cn < co:
        verdict = "proportional"
    else:
        verdict = "ok"
    print(f"{phrase!r:44s} {co:4d} {cn:4d} {exp:5.1f}  {verdict}")
