# Paste-ready values for the OSF Create Project dialog

Copy each block straight into the matching field. Nothing here needs editing.

---

## Title

```
Protocol and amendments v2.1-A1: temperature-scaling calibration transfer across ECG corpora
```

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
Protocol, both amendments, and an archival-status report for a multi-seed study
of temperature-scaling calibration transfer across three public ECG corpora
(PTB-XL, Chapman-Shaoxing, CPSC2018+2019).

STATUS, STATED PLAINLY
This is a public archival of the protocol record, not a prospective
registration made before data collection. The protocol and both amendments were
authored during the study and are dated in their own headers (A1: 2026-09-05;
A2: 2026-09-10); both carry the status "draft pending OSF timestamping". An
internal SHA-256 manifest of the working tree was taken on 2026-09-05, but of
its 14 entries, 10 files have changed since that freeze and for 7 the frozen
content can no longer be recovered from version control, including the protocol
document itself. This is documented file by file in README_ARCHIVAL_STATUS.md
and disclosed in the manuscript under "Pre-registration archival status". The
public timestamp of this record begins here.

CONTENTS
- 01_PROTOCOL_v2.1-A1_EN.md          protocol v2.1-A1, English, with amendment A1 as Appendix A1
- 02_PROTOCOL_v2.1-A1_ZH_original.md the same protocol in the original Chinese, the record of authority
- 03/04_AMENDMENT_A1_*.md            amendment A1: primary endpoint relocation (decay to dECE_OOD)
- 05/06_AMENDMENT_A2_*.md            amendment A2: confirmatory family reduction (156 to 12)
- 07_HASH_MANIFEST_baseline_*.json   the internal manifest as taken, preserved byte-for-byte
- 08_HASH_MANIFEST_as_uploaded.json  per-file before/after hashes with a recoverability verdict
- 09_REVISION_LOG.md                 chronology, with the evidence for each date
- README_ARCHIVAL_STATUS.md          which frozen files are no longer recoverable
- SHA256SUMS.txt                     SHA-256 of every file in this deposit

RELATED MATERIAL
Analysis code, patient-level split indices, per-experiment result artifacts, and
trained model checkpoints:
https://github.com/gt17641001169-design/ecg-calibration-transportability

LICENSE
Documentation in this deposit: CC-BY-4.0.
```

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
2. Go to **Files**, then **OSF Storage**, and upload all 14 files from
   `D:\A1\ecg-lab-v2\paper\osf_upload\`. You can drag the whole folder.
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
