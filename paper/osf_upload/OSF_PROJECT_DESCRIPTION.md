# Text to paste into the OSF project description

Copy the block below verbatim into the OSF project description field. It is
written so that the record is accurate whether or not the registration form is
also completed.

---

**Protocol and amendments for**: *When Does Temperature Scaling Pay Off in
Cross-Corpus ECG Transfer? A Multi-Seed Calibration Boundary Study* (Toni Guan,
College of Information Technology, Shenyang Institute of Technology).

**What this deposit is.** The preregistered experiment protocol v2.1-A1 and its
two amendments for a multi-seed study of temperature-scaling calibration
transfer across three public ECG corpora (PTB-XL, Chapman-Shaoxing,
CPSC2018+2019), together with an archival-status report.

**Status, stated plainly.** This is a **public archival of the protocol record**,
not a prospective registration made before data collection. The protocol and
both amendments were authored during the study and are dated in their own
headers (A1: 2026-09-05; A2: 2026-09-10); both carry the status "draft pending
OSF timestamping". An internal SHA-256 manifest of the working tree was taken on
2026-09-05, but of its 14 entries, 10 files have changed since that freeze and
for 7 the frozen content can no longer be recovered from version control —
including the protocol document itself. This is documented file by file in
`README_ARCHIVAL_STATUS.md`, and it is disclosed in the manuscript under
"Pre-registration archival status". The public timestamp of this record begins
here.

**Contents.**

| File | Role |
|---|---|
| `01_PROTOCOL_v2.1-A1_EN.md` | Protocol v2.1-A1, English translation, including amendment A1 as Appendix A1 |
| `02_PROTOCOL_v2.1-A1_ZH_original.md` | The same protocol in the original Chinese, the record of authority |
| `03_AMENDMENT_A1_EN.md`, `04_AMENDMENT_A1_ZH_original.md` | Amendment A1: primary endpoint relocation (decay to `ΔECE_OOD`) |
| `05_AMENDMENT_A2_EN.md`, `06_AMENDMENT_A2_ZH_original.md` | Amendment A2: confirmatory family reduction (156 to 12) and designation of the L2 shift levels as exploratory |
| `07_HASH_MANIFEST_baseline_2026-09-05.json` | The internal manifest as taken, preserved byte-for-byte |
| `08_HASH_MANIFEST_as_uploaded.json` | Per-file before/after hashes with a recoverability verdict for each |
| `09_REVISION_LOG.md` | Chronology, with the evidence for each date |
| `README_ARCHIVAL_STATUS.md` | Human-readable archival status, including the files whose frozen content is unrecoverable |
| `SHA256SUMS.txt` | SHA-256 of every file in this deposit |

**Related material.** Analysis code, patient-level split indices, per-experiment
result artifacts, and trained model checkpoints:
https://github.com/gt17641001169-design/ecg-calibration-transportability

**License.** Documentation in this deposit: CC-BY-4.0. The deposited files may
be redistributed with attribution.

---

## OSF field values

| Field | Value |
|---|---|
| Title | Protocol and amendments v2.1-A1: temperature-scaling calibration transfer across ECG corpora |
| Category | Project (or "Data" if a dataset-style record is preferred) |
| Contributors | Toni Guan (Shenyang Institute of Technology) — bibliographic contributor |
| License | CC-BY-4.0 for the documents; CC0-1.0 if OSF requires it for a registration |
| Description | the block above |
| Tags | ECG, calibration, temperature scaling, domain shift, preregistration, reproducibility |

## Registration form, if you complete one

Choose the **OSF Preregistration** template. On the "Study information" step, in
the free-text fields, state: the registration is being made after data
collection, the protocol was authored during the study, and the internal
manifest does not fully verify. Do **not** answer that the analysis plan was
registered before data collection — that would be false, and `09_REVISION_LOG.md`
in the same deposit contradicts it.
