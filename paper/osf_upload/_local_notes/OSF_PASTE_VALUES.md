# Paste-ready values for the OSF Create Project dialog

Copy each block straight into the matching field. Nothing here needs editing.

> **This file is a working note. It is NOT part of the deposit.**
> Do not upload it, and do not drag the parent folder into OSF. Upload only the
> 11 files listed in step 3 of `OSF_UPLOAD_CHECKLIST.md`. The four files in
> `_local_notes/` are instructions for you, not records of the study.

---

## Title

```
Protocol and amendments: temperature-scaling calibration transfer across ECG corpora
```

The title names the content, not the versioning trail. Amendment numbers and
protocol revision history live inside the documents, where a reader needs them
to follow the record; they are deliberately kept out of the public record name.

Why not "Preregistered": the analysis is complete and the public timestamp
starts with this record. A title that says "Preregistered" would claim a status
the deposit itself documents as not established.

---

## Storage Location

```
United States
```

Leave the default. This field only chooses which OSF storage region holds the
files; it has no bearing on the record's validity. Change it only if you have an
institutional storage add-on you specifically want to use.

---

## Description (Optional)

```
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
```

**Pasting over an earlier draft?** If the box already holds text that mentions
`v2.1-A1`, or lists file names such as `01_PROTOCOL_v2.1-A1_EN.md`, that is the
earlier draft — the file names carried version labels then. Clear the box and
paste the block above instead. The current text names no version, and groups the
contents by kind rather than enumerating file names.

---

## Template (Optional)

```
```

**Leave this empty.** Do not select a template here.

Two reasons. First, a project template scaffolds a wiki and component structure
that will sit alongside the files you upload and add nothing. Second, the
preregistration questions belong to the *registration* form, which you fill at
registration time (via Registrations, then New registration, then "OSF
Preregistration"). Picking a template now only creates a second, redundant
skeleton. Fill the registration form later using
`OSF_REGISTRATION_ANSWERS.md`.

---

## After you click Create Project

1. It lands you on the project page. Use **Add a DOI or ARK** if you want the
   public identifier minted immediately; otherwise it is assigned when you make
   the project public.
2. Go to **Files**, then **OSF Storage**, and upload the **11 files** listed in
   step 3 of `OSF_UPLOAD_CHECKLIST.md`. Select those files individually — do
   **not** drag the folder, because that would also publish the four working
   notes in `_local_notes/`.
3. Set the license under **Settings** to CC-BY-4.0.
4. Add tags: ECG, calibration, temperature scaling, domain shift, preregistration, reproducibility
5. Make the project **public** (Settings, then Public). Confirm the DOI resolves.
6. Send me the DOI and I will run the backfill over the manuscript and cover
   letter in one command.

## URL to verify before you publish

The RELATED MATERIAL link in the description is:

```
https://github.com/gt17641001169-design/ecg-calibration-transportability
```

Open it once to confirm it resolves, since this record will be public.
