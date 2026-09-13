# Archival status of the protocol hash manifest

Two repositories were searched for each frozen file: the working repository
and the public release repository. Where either still holds a commit whose
blob matches the recorded SHA-256 (in raw, LF-normalised, or CRLF-normalised
form), the entry is marked recoverable and the commit is named. Line-ending
normalisation matters on Windows checkouts and would otherwise produce false
'unrecoverable' verdicts.

Baseline manifest: `07_HASH_MANIFEST_baseline_2026-09-05.json`, taken 2026-09-05T04:19:46.851339+00:00, covering 14 files.

## Disclosure

Of the 14 files fingerprinted in the baseline manifest,
**10 have changed since the freeze** and the frozen content of
**7 can no longer be recovered from the project's version control**.
The baseline manifest therefore documents intent and timing, but for those
files it cannot be independently re-verified by a third party. This is
disclosed in the manuscript, and it is the reason this OSF record is an
archival of the current state rather than a substitute for it.

## Per-file status

| File | Frozen 2026-09-05 | As uploaded | Changed | Frozen content recoverable |
|---|---|---|---|---|
| `docs/EXPERIMENT_PROTOCOL.md` | 25048 B | 52641 B | yes | **no** |
| `paper/main.tex` | 27943 B | 115855 B | yes | **no** |
| `scripts/eval_transfer.py` | 17846 B | 19312 B | yes | **no** |
| `scripts/eval_l2_shift.py` | 8295 B | 10585 B | yes | **no** |
| `scripts/step2_predictability.py` | 5421 B | 11431 B | yes | **no** |
| `scripts/step3_deployment.py` | 5911 B | 21760 B | yes | **no** |
| `scripts/summarize_l2_shifts.py` | 5235 B | 5235 B | no | yes (commit dd9664742b) |
| `src/data/l2_shifts.py` | 3609 B | 8789 B | yes | **no** |
| `src/data/mapping.py` | 29751 B | 30018 B | yes | yes (commit dd9664742b) |
| `src/utils/calibration.py` | 30076 B | 32237 B | yes | yes (commit dd9664742b) |
| `src/utils/calibration_methods.py` | 16973 B | 16973 B | no | yes (commit df9c914307) |
| `src/utils/prior_shift.py` | 9852 B | 9852 B | no | yes (commit dd9664742b) |
| `src/models/ecg_classifier.py` | 5706 B | 5706 B | no | yes (commit dd9664742b) |
| `src/models/baselines.py` | 10780 B | 11568 B | yes | yes (commit dd9664742b) |

## Files whose frozen content is not recoverable

- `docs/EXPERIMENT_PROTOCOL.md` (25048 B -> 52641 B)
- `paper/main.tex` (27943 B -> 115855 B)
- `scripts/eval_transfer.py` (17846 B -> 19312 B)
- `scripts/eval_l2_shift.py` (8295 B -> 10585 B)
- `scripts/step2_predictability.py` (5421 B -> 11431 B)
- `scripts/step3_deployment.py` (5911 B -> 21760 B)
- `src/data/l2_shifts.py` (3609 B -> 8789 B)

## Verification

`SHA256SUMS.txt` lists the SHA-256 of every file in this bundle as uploaded.
