# Chapter maps and original lesson pages

The default for **all** books, including workbooks, tests and answer keys, is a
small edition-bound chapter map plus original pages selected for each lesson.
Full-book transcription, exercise extraction and collection-wide AI analysis
are retired. Their authoring endpoints return 410, and no analysis worker runs.
Historical scripts, recordings, source reports and learner records remain readable.

## Book preparation

`book_navigation` stores PDF checksum, contents-page references and ordered chapter
titles with original PDF page ranges. Maps are shared by edition across children.
Preparation reads bookmarks or locally extracted contents; it makes no AI request.
PDF/printed-page offsets are established from actual page labels, not estimated.
If contents cannot be read reliably, the parent enters ranges in **Chapter maps**,
or selects lesson pages directly. No full-book scan is purchased as a fallback.

## Lesson preparation

**Books and pages for this lesson**, available in preparation options, lets a
parent add inclusive PDF ranges from any book in the subject collection. Chapter
choices are shortcuts to those ranges. The main assigned pages are automatic.
Relationships and exact editions stay in the existing book collection.

`lesson_page_selections` freezes the chosen documents and checksums. Existing
explicit exercise/key associations migrate once to page pointers, without using
their transcriptions, task obligations or child completion to write new scripts.

The writer receives original student pages, a page map, normal teaching guidance
and relevant learner context. For family-library books the prepared teaching stays
neutral and reusable. The compact `page_script` format describes spoken sections,
faithful reading text with page references, questions and book-work pauses. It has no
precomputed reading/task-ID list or whole-book coverage schema. It does not require
the script to narrate every worksheet word or create a separate stop per blank.
The writer reads directly from the PDF, keeping ordinary typography natural and
omitting running headers. Native text is a fallback for explicit text-only inputs.

The local compiler retains the existing activity engine, capture controls and
learner evidence. Source references must belong to attached student pages. The
independent review checks the actual pages for substantive omissions, changed
questions/options, contradictions, missing answer pauses and answer leakage.
Style/pacing preferences remain advice. Review and generation keep their normal
budgets, durable requests and refusal handling.

Answer-key PDFs are excluded from the writer and student page views. Selected
key pages join the private review bundle and the pinned original-page assessment
input. A running session keeps its immutable preparation files. Later source-page
changes invalidate new reuse without changing that session or its answers.

## Narrators

The ElevenLabs account voice catalog supplies names, accent/style labels and
existing preview samples. **Settings → Teaching and voice** lets parents audition
voices and save family/child defaults. Lesson options and curriculum preparation
also expose **Choose a narrator** for a lesson-specific selection.

Selecting or previewing a narrator does not generate speech. Create the recorded
voice separately, using the normal estimate and voice allowance. New recordings
have their own voice identity; earlier recordings remain playable. The provider
catalog follows [ElevenLabs List voices](https://elevenlabs.io/docs/api-reference/voices/search).

## Verification

`test_page_preparation.py` checks local shared maps without scanner/provider calls,
unconstrained page-based compilation, private key attachments, edition/range
validation, source-change invalidation, voice discovery/selection and retired API
guards. Library-reuse tests continue to protect child isolation and reusable
scripts, Practice content, reviews and audio.
