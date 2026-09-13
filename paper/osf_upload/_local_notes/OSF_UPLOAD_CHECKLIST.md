# OSF upload checklist

Do these in order. Steps 1 to 4 are the upload; steps 5 to 7 close the loop in
the manuscript. Nothing here requires re-running any analysis.

> **Working note — not part of the deposit.** Do not upload this file to OSF.

## Before you start

- [ ] Read `README_ARCHIVAL_STATUS.md`. You are about to publish a record that
      says, in writing, which parts of the internal manifest no longer verify.
      That is the point: the alternative is a record that claims more than the
      evidence supports, and a reviewer can check the hashes themselves.
- [ ] Confirm you are comfortable with the sentence in `09_REVISION_LOG.md`
      that the public timestamp begins with this deposit. If you are not, do not
      post the record — instead, say so and the manuscript's pre-registration
      language will be softened to match.

## 1. Create the OSF project

- [ ] Sign in at osf.io, then **Create new project**.
- [ ] Title: `Protocol and amendments: temperature-scaling calibration transfer across ECG corpora`
      (no version or amendment label in the record name — those live inside the
      documents; and deliberately no "Preregistered", since this record is a
      public archival made after analysis and the title should not claim
      otherwise)
- [ ] Category: *Project*. Add the tags listed in `OSF_PROJECT_DESCRIPTION.md`.
- [ ] Paste the description block from `OSF_PROJECT_DESCRIPTION.md` into the
      project description field.

## 2. Add contributors and license

- [ ] Add **Toni Guan** as a bibliographic contributor, affiliation
      *College of Information Technology, Shenyang Institute of Technology*
      (add an ORCID if you have one; it strengthens the record).
- [ ] Set the license to **CC-BY-4.0**. If OSF insists on CC0-1.0 for a
      registration, accept CC0 and note the change here: ______________

## 3. Upload the bundle

The deposit is exactly **11 files**, all of them sitting directly beside this
note (`_local_notes/` is not part of it):

```
01_PROTOCOL_EN.md
02_PROTOCOL_ZH_original.md
03_AMENDMENT_1_EN.md
04_AMENDMENT_1_ZH_original.md
05_AMENDMENT_2_EN.md
06_AMENDMENT_2_ZH_original.md
07_HASH_MANIFEST_baseline_2026-09-05.json
08_HASH_MANIFEST_as_uploaded.json
09_REVISION_LOG.md
README_ARCHIVAL_STATUS.md
SHA256SUMS.txt
```

- [ ] Upload those 11 files. Select them individually.
- [ ] Do **not** drag the folder, and do **not** upload anything from
      `_local_notes/` — those four files are instructions to you, and publishing
      them would put a checklist inside the record that the checklist itself
      describes.

## 4. Make it public and record the DOI

- [ ] Make the project **public**. OSF assigns a DOI of the form
      `10.17605/OSF.IO/XXXXX`.
- [ ] Write the DOI here: `https://doi.org/____________________`
- [ ] Optional but stronger: **Register** the project with the *OSF
      Preregistration* template. Use `OSF_REGISTRATION_ANSWERS.md`, which gives
      the answer for every field. The decisive one is **Existing data →
      "Registration following analysis of existing data"**; pick that and every
      other answer stays consistent. A registration gets a second, immutable
      timestamp and a separate DOI.

## 5. Update the manuscript

Edits in `D:\A1\ecg-lab-v2\paper\main.tex`.

- [ ] **Data availability**, the sentence beginning "Pre-registration archival
      status." (around line 1676). Replace:

      ```
      \textbf{Pre-registration archival status.} The protocol and both amendments
      (A1, A2), together with an archival-status report, are being deposited under
      a public OSF timestamp before publication. Until that record is live,
      \texttt{docs/osf\_archive\_manifest.json} is a local snapshot taken on
      2026-09-05 and is not a substitute for public registration.
      ```

      with:

      ```
      \textbf{Pre-registration archival status.} The protocol, both amendments
      (A1, A2), and a per-file archival-status report are publicly archived at
      \url{https://doi.org/XXXXX}. \texttt{docs/osf\_archive\_manifest.json} is
      the internal snapshot taken on 2026-09-05; it is not a substitute for the
      public record.
      ```

- [ ] **Bibliography note** (the `\bibitem` for the protocol, around line 2046).
      Replace the parenthetical:

      ```
      (local snapshot; public OSF archival pending)
      ```

      with:

      ```
      (local snapshot; archived at \url{https://doi.org/XXXXX})
      ```

- [ ] **Bibliography title**: the same `\bibitem` still reads
      ``...pre-registered experiment protocol v2.1-A1,''``. The deposited record
      name now carries no version label, so drop the trailing version from the
      cited title to keep the citation and the deposit consistent:

      ```
      ``ECG calibration boundary study -- experiment protocol,''
      ```

- [ ] **Header comment**: no change needed; the archive only affects bodies of
      text.

## 6. Update the cover letter

- [ ] In `paper\cover_letter.tex`, replace:

      ```
      \textbf{Public OSF archival is not yet complete} and is
      declared as pending in the manuscript; we will register the protocol and
      both amendments, together with an archival-status report, under a public
      OSF timestamp before publication.
      ```

      with:

      ```
      The protocol, both amendments, and a per-file
      archival-status report are publicly archived at
      \url{https://doi.org/XXXXX}.
      ```

## 7. Rebuild and verify

- [ ] Compile both documents:

      ```
      cd /d/A1/ecg-lab-v2/paper
      pdflatex -interaction=nonstopmode main.tex
      pdflatex -interaction=nonstopmode main.tex
      pdflatex -interaction=nonstopmode cover_letter.tex
      pdflatex -interaction=nonstopmode cover_letter.tex
      ```

- [ ] Confirm zero `!` errors in the output and that both PDFs regenerate.
- [ ] Check the DOI resolves in a browser before submitting.

## Known limitation to keep in mind

The upload cannot repair the 7 files whose frozen content is gone. If a reviewer
asks for the protocol exactly as it stood on 2026-09-05, the honest answer is
that it is not recoverable, and that the deposited protocol is the earliest
complete version that still exists. `README_ARCHIVAL_STATUS.md` says this in
writing, which is better than being asked and having no answer.
