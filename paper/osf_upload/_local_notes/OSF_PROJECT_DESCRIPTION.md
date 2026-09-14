# Text to paste into the OSF project description

This file is the description of record — the authoritative wording for the
deposit. The copy you actually paste into the OSF project description field
lives in `OSF_PASTE_VALUES.md`, so that there is only ever one file to edit; the
block below is byte-identical to it. It is written so that the record is
accurate whether or not the registration form is also completed.

> **Working note — not part of the deposit.** Do not upload this file to OSF.

---

**Protocol and amendments for**: *When Does Temperature Scaling Pay Off in
Cross-Corpus ECG Transfer? A Multi-Seed Calibration Boundary Study* (Toni Guan,
College of Information Technology, Shenyang Institute of Technology).

**What this deposit is.** The experiment protocol and its two amendments for a
multi-seed study of temperature-scaling calibration transfer across three public
ECG corpora (PTB-XL, Chapman-Shaoxing, CPSC2018+2019), together with an
archival-status report.

**Status, stated plainly.** This is a **public archival of the protocol record**,
not a prospective registration made before data collection. The protocol and
both amendments were authored during the study and are dated in their own
headers (2026-09-05 and 2026-09-10); both carry the status "draft pending OSF
timestamping". An internal SHA-256 manifest of the working tree was taken on
2026-09-05, but of its 14 entries, 10 files have changed since that freeze and
for 7 the frozen content can no longer be recovered from version control —
including the protocol document itself. This is documented file by file in
`README_ARCHIVAL_STATUS.md`, and it is disclosed in the manuscript under
"Pre-registration archival status". The public timestamp of this record begins
here.

**Contents.**

| Group | Files | Role |
|---|---|---|
| Protocol | 2 | The protocol in English, and the same protocol in the original Chinese, which is the record of authority |
| Amendments | 4 | Amendment 1 (primary endpoint relocation) and Amendment 2 (confirmatory family reduction), each in English and in the original Chinese |
| Manifest | 2 | The internal hash manifest as taken, preserved byte-for-byte, and a per-file before/after audit with a recoverability verdict for every entry |
| Chronology | 1 | `09_REVISION_LOG.md` — the dates, each with its evidence |
| Status report | 1 | `README_ARCHIVAL_STATUS.md` — the files whose frozen content is no longer recoverable |
| Checksums | 1 | `SHA256SUMS.txt` — SHA-256 of every file in this deposit |

**Related material.** Analysis code, patient-level split indices, per-experiment
result artifacts, and trained model checkpoints:
https://github.com/gt17641001169-design/ecg-calibration-transportability

**License.** Documentation in this deposit: CC-BY-4.0. The deposited files may
be redistributed with attribution.

---

## OSF field values

| Field | Value |
|---|---|
| Title | Protocol and amendments: temperature-scaling calibration transfer across ECG corpora |
| Category | Project (or "Data" if a dataset-style record is preferred) |
| Contributors | Toni Guan (College of Information Technology, Shenyang Institute of Technology) — bibliographic contributor |
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
