# OSF upload checklist

Do these in order. Steps 1 to 4 are the upload; steps 5 to 7 close the loop in
the manuscript. Nothing here requires re-running any analysis.

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
- [ ] Title: `Preregistered protocol and amendments: temperature-scaling calibration transfer across ECG corpora (v2.1-A1)`
- [ ] Category: *Project*. Add the tags listed in `OSF_PROJECT_DESCRIPTION.md`.
- [ ] Paste the description block from `OSF_PROJECT_DESCRIPTION.md` into the
      project description field.

## 2. Add contributors and license

- [ ] Add **Toni Guan** as a bibliographic contributor (add an ORCID if you have
      one; it strengthens the record).
- [ ] Set the license to **CC-BY-4.0**. If OSF insists on CC0-1.0 for a
      registration, accept CC0 and note the change here: ______________

## 3. Upload the bundle

- [ ] Upload every file in this folder, including `SHA256SUMS.txt`.
- [ ] Add `OSF_PROJECT_DESCRIPTION.md` and `OSF_UPLOAD_CHECKLIST.md` only if you
      want the working notes public; they are not part of the record itself.

## 4. Make it public and record the DOI

- [ ] Make the project **public**. OSF assigns a DOI of the form
      `10.17605/OSF.IO/XXXXX`.
- [ ] Write the DOI here: `https://doi.org/____________________`
- [ ] Optional but stronger: **Register** the project with the *OSF
      Preregistration* template, answering the timeline questions honestly as
      described at the end of `OSF_PROJECT_DESCRIPTION.md`. A registration gets a
      second, immutable timestamp.

## 5. Update the manuscript

Three edits in `D:\A1\ecg-lab-v2\paper\main.tex`.

- [ ] **Data availability**, the sentence beginning "Pre-registration archival
      status." Replace:

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

- [ ] **Bibliography note** (the `\bibitem` for the protocol, around line 2044).
      Replace the parenthetical:

      ```
      (local snapshot; public OSF archival pending)
      ```

      with:

      ```
      (local snapshot; archived at \url{https://doi.org/XXXXX})
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
that it is not recoverable, and that the deposited v2.1-A1 is the earliest
complete version that still exists. `README_ARCHIVAL_STATUS.md` says this in
writing, which is better than being asked and having no answer.
