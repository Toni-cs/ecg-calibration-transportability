# Revision log

Chronology of the protocol record. Only dates documented in the source
documents are asserted here; nothing is back-dated.

| Date (UTC) | Event | Evidence |
|---|---|---|
| before 2026-09-05 | Protocol v2.0 authored after cross-validation by five independent adversarial reviews (experimental design, statistical methodology, engineering reproducibility, literature novelty, Reviewer-2 simulation) | `01_PROTOCOL_EN.md`, Revision history |
| 2026-09-05 | Amendment 1 merged: primary endpoint relocated from the ID-to-OOD decay contrast to the OOD calibration benefit `ΔECE_OOD`; the §6 symbol typo corrected; the contribution statement relocated | `03_AMENDMENT_1_EN.md`, header |
| 2026-09-05T04:19:46Z | Baseline hash manifest taken over 14 files (protocol, manuscript, analysis scripts, model and utility modules) | `07_HASH_MANIFEST_baseline_2026-09-05.json` |
| 2026-09-10 | Amendment 2: the confirmatory family is reduced from 156 to 12 hypotheses; the 13 L2 shift levels are re-designated as exploratory dose-response; the 60 seed experiments are designated robustness evidence rather than a confirmatory family | `05_AMENDMENT_2_EN.md`, header |
| 2026-09-13 | Archival audit: 10 of the 14 fingerprinted files have changed since the freeze, and for 7 of them the frozen content is recoverable from neither repository's version control | `README_ARCHIVAL_STATUS.md`, `08_HASH_MANIFEST_as_uploaded.json` |
| (this deposit) | Public archival of the protocol, both amendments, and the archival-status report under an OSF timestamp | this record |

## What this record does and does not establish

**It establishes**: the content of the protocol and both amendments as
deposited here, and the internal timeline that those documents record in their
own headers.

**It does not establish**: that the protocol was publicly registered before the
data were collected. Both amendment documents carry the status "draft pending
OSF timestamping", and the internal manifest cannot be re-verified for 7 of its
14 entries because the frozen file contents no longer exist in any repository.
The manuscript discloses this under "Pre-registration archival status".

Readers evaluating the study's pre-registration claim should weigh it
accordingly: the design decisions are documented and dated, but the public
timestamp begins with this deposit rather than preceding the analysis.
