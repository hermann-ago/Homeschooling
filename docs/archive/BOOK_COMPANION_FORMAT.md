# Portable book companions

Each exact PDF can have a `homeschooling.book-companion` version 1 JSON alongside
it in the subject's Books folder. `backend/tutoring/book_companion.py` defines the
canonical Pydantic schema; `GET /api/book-companion-schema` exposes the same schema.
The envelope contains `content_sha256` of sorted UTF-8 JSON `contents` (Python's
default JSON separators), not the file's pretty-printed bytes. The source PDF has
its own independent SHA-256. No learner records are part of this format.

## Contents and trust

- `source`: exact PDF hash, original filename, page count, role, edition, language.
- `pages`: every PDF page, once and in order; dimensions in PDF points, optional
  printed label, unchanged native extraction, faithful transcription, review
  method/status/issues, student/teacher classification, literal reading blocks
  and headings, ordered visual elements.
- `elements`: stable IDs; kind text, illustration, diagram, table, formula,
  answer_space or decoration. Visible text and interpretation are separate;
  tables retain rows, math retains expressions, and optional normalized boxes
  use `[left, top, right, bottom]` with top-left origin. Links refer to existing
  element/exercise IDs.
- `exercises`: stable IDs plus original reference, chapter/section, source pages,
  printed page, instructions, kind, optional status and uncertainty. The answer
  field must be null.
- Visually confirmed unnumbered exercises use `unnumbered: true` and a unique
  internal ID while retaining an empty printed reference. This does not license
  guessing missing numbers from an incomplete extraction.
- `teacher_only.answers`: private key entries with exact source pages and quoted
  evidence. Key pages stay private; entries never join student narration or the
  general records export. Visual keys also carry `evidence_element_ids`, checked
  against the description or table row of an element on those exact key pages.
  This preserves answers conveyed by connecting lines, colors or diagrams.
- Private compound answers can use `evidence_quotes`, each with its actual key
  page and literal quote. Page `notes` hold informational observations separately
  from blocking `issues`. Native analysis can select page-local `reading_spans`
  by first/last line; the server inserts the original literal text.

`native_draft` is never evidence of successful visual extraction. `checked`
requires a review method and no unresolved page/element issue. Uncertainty stays
`needs_review`. Structural validation checks references and boundaries, not the
factual correctness or fidelity of a claimed transcription.

## Interface and API

Curriculum > subject > Books > **Book JSON files** provides local draft creation,
download, page inspection and JSON import. **Understand these books together**
continues the existing provider-neutral, checkpointed analysis with cost preview,
job limit and monthly allowance. Source scans now record visual structure and
automatically refresh opted-in companions. The existing worker and spending
reservations provide error recovery; there is no new paid queue.
Opted-in collections scan at most three page groups concurrently under the same
job budget. Pause/failure stops new scheduling and checkpoints already-sent
results before releasing the job. Failed or uncertain purchases are not retried.

Completed provider proposals are checkpointed before source validation in the
teacher-only book cache. Rejected references can be revalidated locally without
repurchasing or overwriting the original scan. Formatting-equivalent quotes map
back to exact original text spans, including drop caps, ligatures and word
wrapping. A key's mistaken student-book page number is relocated only when its
evidence uniquely identifies an actual key page; otherwise the entry stays
explicitly unresolved within the inspected range.
Numeric visual references are resolved only to a unique exercise on that page.
Imported exercise IDs survive cache promotion and export. Missing or repeated
printed question identities retain distinct source positions in the integrated
map and remain unavailable for automatic key matching until reviewed.

- `GET /api/subjects/{subject}/book-companions`: coverage, paths and revisions.
- `POST .../book-companions/{document}`: local extraction + saved source scans;
  no provider request. Saves JSON atomically with its database reference.
- `GET .../{document}/export`: complete family-owned JSON, including private keys.
- `GET .../{document}/pages/{page}`: inspect one page representation.
- `POST .../{document}/import`: multipart `file` and `expected_revision`.
- Explicit reviewed corrections add `source_review=true` and a required `note`.
  They create an immutable correction layer without deleting original scans.
- `GET .../{document}/history`: source-correction versions and review notes.

All endpoints require the family role. Imports verify checksum, schema, exact
PDF, role, edition, page inventory, IDs, citations, private material and ownership.
Complete checked eight-page groups (including a shorter final group) join the
existing `book_units` cache. Unfinished groups do not. Conflicting immutable scans
are rejected. In-progress or paused analysis must finish before importing a
different representation. Historical learner evidence and lessons are unaffected.

`book_companions` is teacher-only and participates in SQLite backup/restore and
test-mode's normal database/file isolation. Each changed snapshot has an immutable
hash-named file. Ordinary Excel/records projections omit its contents.
`book_source_reviews` retains each explicit correction. Source maps pin their
review IDs so an old map does not silently change when a new JSON is imported.

The UI also exposes two editable, versioned **Skills dos materiais**. See
`docs/MATERIAL_ANALYSIS_SKILLS.md` for source rules, history and the free local
source-map refresh. Personalized lesson scripts are prepared later.

## Codex route

The installed `homeschooling-book-companion` skill uses this schema and the local
`backend/tools/book_companion.py` CLI. `draft`, `schema` and `seal` need no app
credentials, API purchases or learner database writes. Codex inspects bounded
page groups; `seal` validates and hashes without certifying pages automatically.
JSON upload uses the same app interface.

## Collection integration

Each student book and key retains its own companion. The existing subject
collection records reading order, editions and the exact target of each key.
The subject-knowledge archive remains the integrated map. Source summaries and
exercise links reuse imported scan units. Only assigned, checked, student-safe
visual structure enters lesson preparation; partial-page lessons omit visual
context until region-to-passage mapping exists. Original PDF attachments remain
available for visually structured books.
