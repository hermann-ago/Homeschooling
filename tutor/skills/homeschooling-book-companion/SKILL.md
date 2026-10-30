---
name: homeschooling-book-companion
description: Prepare source-bound JSON companions for PDF textbooks, workbooks and answer keys used by the Homeschooling app, preserving original text, page structure and visual exercises. Use for book conversion and source review, not for grading learner responses.
---

# Homeschooling book companions

Produce `homeschooling.book-companion` version 1 JSON accepted by the app. The PDF is the original; a description is an interpretation, never a substitute for checking an ambiguous figure. Use Codex's own reading capabilities without calling a paid provider API unless the user requests that route.

## Canonical tools

Locate the Homeschooling repository (on this host `C:/CodingLocal/Homeschooling`). Read `docs/BOOK_COMPANION_FORMAT.md` there. The source of truth is `backend/tutoring/book_companion.py`; generate its JSON schema rather than inventing fields:

```powershell
.\backend\venv\Scripts\python.exe backend/tools/book_companion.py schema --output tmp/pdfs/book-companion.schema.json
.\backend\venv\Scripts\python.exe backend/tools/book_companion.py draft 'book.pdf' --role combined --edition '2024' --output 'book.book.json'
```

Or download the existing JSON from Curriculum > subject > Books > Book JSON files. Keep the source PDF SHA-256, page count, role and edition unchanged. A teacher key uses `answer_key` and is linked to its exact student book in the app collection.

For large native PDFs, `backend/tools/book_source_review.py draft` preserves text-block geometry and inventories displayed images using optional PyMuPDF/Pillow (`backend/requirements-source-tools.txt`). It is faster than whole-book pypdf extraction. Its output is deliberately unreviewed. Use `sheets` for bounded complete-page renders and `checkpoint` to apply explicit page decisions pinned to the original SHA. Keep extraction, visual inspection and certification as distinct stages; file/image counts are not review coverage.

Use the standalone CLI or the running app's API. Do not instantiate another `AppContext` against the live database for inspection: startup recovery can pause active jobs. Keep offline validation independent of the learner database.

Read the current `book-json` instructions from `GET /api/material-skills` when the server is available. The starter is `tutor/materials/book-json/GUIDE.md`; family edits and history appear under Curriculum > subject > Skills dos materiais. Keep source-conversion rules separate from the material-links skill and personalized teaching skills.

## Inspect and represent

- Inspect rendered, complete PDF pages. Native extraction is a starting point; cursive fonts, math, tables, blanks, diagrams and reading order require visual checking. Work in bounded batches and checkpoint the file so a long book can resume.
- Include every PDF page once, even covers and blank pages. Keep PDF numbering distinct from visible printed labels. Preserve `native_text` unchanged; put faithful corrected transcription in `text`.
- Verify volume boundaries: a table of contents may list multiple books and restart printed page numbers. Use source `sections` for exact lesson/chapter navigation, with part, original PDF pages and printed labels. Compare chapter openings; do not extrapolate a single offset across volumes. Hidden template layers and overlapping fill/stroke text can look plausible in extraction; inspect the visible page before correcting them.
- Preserve exercise numbers/letters, section names, instructions, choices and referenced figures. Use stable unique exercise and element IDs. Keep meaningful labels, arrows, colors, table cells, formulas and spatial relationships in elements. Descriptions use the book's language. Bboxes are normalized and optional; do not guess them.
- For visually confirmed unnumbered questions, keep `reference` empty, set `unnumbered: true`, and preserve a unique internal ID. Do not treat incomplete extraction as proof that numbering is absent.
- `reading_blocks` and `headings` are verbatim excerpts from transcription. For combined books, reading blocks contain teaching/reading paragraphs only, excluding exercise instructions and private keys. Do not solve questions while transcribing.
- Native-text analysis can select page-local `reading_spans` by numbered lines so the app inserts the original text. Never relocate a neighboring page's heading or continuation merely because it completes a thought. Formatting differences must resolve back to exact source spans without dropping numeric or mathematical signs.
- Mark a page `checked` only after inspecting it, with `review_method` and no unresolved issues; `student_safe` requires checking for teacher solutions. Use `needs_review` for uncertainty; leave uninspected pages `native_draft`. Never fill unreadable details or silently correct the book's own errors.
- Separate image interpretation (`description`) from visible source wording (`text`). Decorative artwork gets a brief decoration entry. Answer spaces and handwriting requirements are pedagogical structure, not decoration.
- Answers belong exclusively in `teacher_only.answers`, with original references and evidence quoted from the actual key page. For graphical keys, preserve observed pairings in a table or description and include `evidence_element_ids`; evidence must quote that description or a row's cells joined with spaces. Key pages are always teacher material. Do not infer a missing answer or map keys by shared topic alone.
- A two-up key page has its own PDF/printed number and separate embedded student-page numbers. Match lesson, exact part, section and edition, not a reused footer number. A publisher's example answer remains an example. Parent read-aloud text is not automatically a private answer key; preserve the source's speaker/turn labels.
- For answers spanning pages or separate excerpts, use `evidence_quotes` with a page and literal quote for each part. Keep informational review observations in page `notes`, separate from blocking `issues`. A faithfully transcribed typo remains visible with a note; an absent official answer remains unresolved.

## Validate and deliver

After edits, validate against the exact PDF and recompute the envelope checksum:

```powershell
.\backend\venv\Scripts\python.exe backend/tools/book_companion.py seal 'edited.book.json' --pdf 'book.pdf' --output 'checked.book.json'
```

This does not certify pages automatically. Report checked versus pending coverage. The app reuses complete checked groups of eight pages; partial reviewed groups are retained in JSON but not promoted prematurely.

Deliver the JSON for Curriculum > subject > Books > Book JSON files > Import JSON. Importing into the app is a separate authorized write: preserve existing immutable scans; a conflicting scan requires the app's source-review flow, not deletion. Do not put child names, answers, attempts, credentials, personalized guides or fabricated mastery in companions. Never overwrite the PDF.

For an authorized correction to an existing scan, use **Importar correção revisada**, with its observed revision and a note explaining the visual checks. The app saves an immutable correction layer and preserves earlier JSON/scans. Inspect the resulting source history and refresh only dependent material, without rerunning paid generation automatically.
