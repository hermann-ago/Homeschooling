# Family book library

Books is the shared repository for the family. The initial catalog preserves
30 titles, their seven stages, order, author/year metadata and supplied links.
Files can be added later. Availability notes are catalog data; only recorded
source checks establish the edition actually downloaded.

## Prepare and read

1. Open Books, choose a child, and add a title to their curriculum. It appears as
   that child's separate subject in Curriculum and Progress. Other children are
   not enrolled automatically. Removing it retains progress for re-adding later.
2. Upload the original readable, unencrypted PDF (up to 250 MiB). The app stores
   its bytes and checksum once in Family Library/Books. Upload makes no AI call.
3. Choose Prepare chapter map. The app reads PDF bookmarks or local contents
   pages, retaining chapter titles and original PDF ranges. It does not scan or
   transcribe the entire book through AI. If contents are unavailable, enter
   ranges in the chapter editor or select lesson pages directly.
4. Open a chapter in the normal reader. Prepare its tutor script from the actual
   assigned PDF pages. The writer supplies natural teaching and faithful reading
   words directly from those pages, without a precomputed exercise inventory or
   required list of reading/task IDs. A separate review checks the original pages.
5. Use read-along, the live companion and Practice tools. Generated explanations,
   questions and recordings are shared book preparation. Answers, help, revisions,
   conversations and progress belong to the individual child.

New reading scripts use schema-constrained JSON directly. Generated comprehension
checks offer yes/no, true/false or two to four choices, with no typed explanation.
This also applies to printed brainstorming/discussion questions: they never
become mandatory written or cursive work. The original story and commentary stay.
They follow coherent reading sections and normally use two or three quick checks.
Live feedback retains the same selection interaction. Existing saved sessions
keep their original script; preparing a new version applies the new policy.
See [How a lesson is made](LESSON_PIPELINE.md) for the shared writing,
validation, review and grading path used across subjects.
For preparation with Codex without a paid lesson-writing API, follow
[Codex lesson workflow](CODEX_LESSON_WORKFLOW.md).

For workbooks and other related sources, use Books and pages for this lesson in
preparation options to add original PDF ranges from the subject collection.
Answer-key pages are found automatically and stay teacher-only. The same workflow
is the default across textbooks, workbooks, combined books, tests and references.
See [How a lesson is made](LESSON_PIPELINE.md).

## Shared preparation and independent learning

- library_books stores the catalog and exact document reference; library_readings
  binds each child to an ordinary subject with purpose=library.
  Paused membership uses purpose=library_paused and retains the same child,
  subject, topics and records. Active books track real progress without imposing
  a school-year deadline or silently adding scheduled study slots.
- book_navigation stores edition-bound chapter maps, with portable map files in
  Family Library/Chapter Maps/Lesson Content. A map is reusable across children.
- Shared instructions live in library_book_skills. library_materials stores
  compatible source reviews, guided teaching, Practice material, editorial
  reviews and narration. The original reader can be deleted without losing them.
- Shared teaching receives source context and common family guidance, without
  child names, ages, preferences, answers, memory or progress. The live companion
  still adapts to the current child, and its personal feedback stays separate.
- Shared book lessons live in Family Library/<book id>/Lesson Content, recordings
  in Family Library/<book id>/Audio and instructions in Teaching Skill.
- Reuse checks the exact edition, boundaries, selected pages, source/instruction
  versions, language and preparation policy. Voice identity also includes the
  provider, narrator and rate. Older variants and active sessions keep their files.
- Source-page changes affect future preparation; they never rewrite an active
  lesson or its answers. A failed review remains failed when reused.
- Active book subjects appear in that child's curriculum and progress totals.
  They are not inserted into the automatic school timetable. Paused book
  subjects stay off the curriculum; their evidence remains available in Records.

Stages describe the supplied reading sequence, not age suitability. The parent
chooses the books. Tutoring distinguishes an author's arguments from established
facts and assesses comprehension and reasoning without requiring agreement.

## Voices

Settings -> Teaching and voice offers account narrators and existing samples,
with family and per-child defaults. Lesson options and preparation dialogs also
let a parent audition voices and select one narrator for a lesson. Selecting a
voice makes no speech-generation request. Create its recording separately under
the connected provider's subscription credits; earlier recordings remain available.

## Storage and historical material

The standard SQLite transactions, operation receipts, file-first persistence,
optimistic revisions, backups and exports apply. The SQLite database stays local,
while ordinary book and preparation files use the existing Drive-synced folder.
Different PDFs do not replace an attached edition behind saved learning records.

Whole-book scanning, companion authoring and collection-wide AI analysis are
retired. Their authoring endpoints cannot start provider calls. Historical source
reports, scripts, recordings and evidence remain readable. An old refused page
batch is no longer a prerequisite for chapter navigation or lesson preparation.

## Verification

Backend checks cover local chapter maps without scanner/provider calls, shared
materials, child isolation, source and key-page selection, edition/range checks,
voice selection without generation, retired authoring endpoints, and the normal
interactive activity flow. Frontend checks cover books, source-page controls,
narrator previews, defaults and preparation dialogs.

The Jonathan Gullible pilot read four contents pages locally and mapped 40
chapters plus six back-matter entries. Its new opening lesson uses original PDF
pages 13-16, includes three comprehension prompts, passed editorial review, and
has a five-question Practice quiz and George narration. The guide, quiz and audio
were checked for reuse with Mila. A real companion exchange and sample answer
were exercised in disposable Test Mode without changing live learner records.
