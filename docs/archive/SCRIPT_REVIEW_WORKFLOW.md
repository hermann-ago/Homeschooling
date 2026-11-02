# Reusable teaching, source notes and script review

The app owns the preparation and review workflow. Real lesson quality still needs
representative pilots; structural/provider tests do not establish teaching quality.
See [PDF-first preparation and cleanup ledger](PDF_FIRST_PREPARATION.md).
New script preparation runs a separate structured editorial/source-consistency
review before requesting narration. The app tracks teaching and voice usage;
the provider controls subscription credits and billing. There is no automatic rewrite,
provider switch or replacement purchase after a review problem.

## Reusable layers

1. Family tutoring style: age-aware voice and interaction, with the selected learner profile.
2. Subject teaching skill: pedagogy and pacing, reusable across that subject's books.
3. Original assigned PDF pages and material relationships; JSON companions are optional supporting indexes.
4. Source notes: explicit corrections/uncertainties bound to PDF SHA-256 and inclusive PDF pages.
5. Script-review skill: shared editorial rules, editable under **Skills dos materiais → Revisão do roteiro**.
6. Engine: contracts, structural checks, waiting, capture, evidence and narration.

Source notes are under **Curriculum → subject → Teaching skill → Book source notes**.
The same PDF edition reuses its notes in other subjects or learner collections.
A different edition or non-overlapping page range does not. Saving or archiving
a note appends a version and writes a JSON archive beside the subject teaching
skill. It never changes the PDF, answer key, historical answer or running session.
The separate assessment guidance is kept out of child-facing guide payloads and
planner input; it is frozen in new lesson context for response assessment.

## Review behavior

Deterministic source coverage remains mandatory and separate from AI review.
For new PDF-first guides the reviewer receives the same original student pages as
the writer, plus explicitly mapped private key pages where available. Exact PDFs,
page maps, edition hashes and partial-page boundaries are frozen with the guide.
Legacy guides retain their original review identity. Explicit text-only and mixed
teacher/student sources retain their safe text path.
The reviewer also receives exact saved activities, assigned text, relevant source notes,
frozen subject/family style, and the versioned review skill. It checks age-appropriate
wording, duplication, pacing, waiting interactions, answer leakage, unsupported
teacher assertions and unresolved source conflicts. Findings target existing activity IDs.
The engine derives the decision from blocking findings; the reviewer cannot advance
a lesson or record understanding.

The review compares supplied evidence. It does not browse reference links, independently
verify every factual assertion, or certify a book. Uncertain/conflicting facts require
source clarification. A reviewed source note records a human/source decision, not a
claim that its URL was automatically fact-checked. A human-reviewed plan import is
recorded distinctly as `family_review`, not an AI review.

Curriculum shows **Reviewing script…**, the saved review result and audio status.
Open **Preparation options → Script review** for findings. A failed review can be
explicitly retried within its displayed limit; saved exact-input AI replies and
uncertain spending reservations are reused. An explicit rewrite receives the saved
editorial/task findings and earlier corrections from that same source/topic,
including optional advice on an approved draft. This prevents a rewrite from
forgetting an earlier repair. Source/key disputes still require checking the
relevant source/skill/note; private key findings are not forwarded as public teaching
instructions. No paid rewrite happens automatically. Existing sessions retain
their pinned version. No separate parent interface was introduced.

Reviews are private append-only reports bound to exact activities, source snapshot,
scoped notes, frozen teaching style and current review policy. Changes invalidate
approval for new audio purchases. Existing playback is retained. Legacy guides show
no editorial review recorded and are not silently rewritten or charged; they may be
reviewed explicitly. New guides require approval before narration generation.

## Interfaces and storage

- `GET/PUT /api/subjects/{subject}/source-notes`: edition/page-bound notes with expected edition/version.
- `GET /api/tutor/guides/{guide}/review`: private findings and current input hash.
- `POST /api/tutor/guides/{guide}/review`: explicit retry with expected input hash and teaching cap.
- `source_annotations`: versioned shared source records, no learner evidence.
- `lesson_script_reviews`: private reports, separate from attempts and completion.

Both tables use normal schema/backup machinery and test-mode isolation. Preparation
artifacts can be copied into compatible test workspaces; learner work never merges
back. Public guide/curriculum status exposes only review status and generic summary,
not findings or assessment exceptions.

## History cleanup

The Forbidden City corrections originally stored in the History subject skill are
migrated into a note for that exact Story of the World edition and PDF pages 219–222.
The Q11 source-conflict exception is assessment guidance. General connected-reading
and exercise strategies remain in History. Re-importing the already reviewed script
keeps its spoken text/audio identity; no new script or voice purchase is needed.

## Source disagreements during a lesson

For a question checking the book's wording, feedback can accept that wording while
briefly qualifying a disputed factual claim. A minor clarification does not require
another question or a parent inspection.

If an assessment still returns `Source disputed`, the shared activity UI shows a
source note and **Continue lesson**, with manual review optional. The
`acknowledge_source_issue` command validates the exact saved response and interaction,
records the acknowledgment, and advances once. The original answer, assessment,
attempts and assistance remain unchanged. The activity is addressed, while learning
stays unassessed; it does not become a wrong answer or a practice gap. This applies
across books and subjects, including already-started sessions. Missing written
evidence cannot use this command to bypass its separate capture requirements.

## Continue remaining work versus repeat

`repeat` with `unfinished_only: true` creates a continuation scoped to the original
completion summary's deferred activities. It retains exact source/assignment links
and leaves unrelated reading and questions `not_assigned`, rather than claiming
they were repeated or completed. A full repeat uses `from_beginning: true`.

Older repeats opened from unfinished work can use `focus_unfinished` to recover
that same scope. The app identifies the original completed session and its actual
remaining items. Once those items are addressed, Continue opens the recap, not the
first reading. Answers, attempts, assistance and original completion records are
preserved; the learner still chooses Finish lesson explicitly.

The current activity's reading/continue/finish buttons live below its scroll area.
The activity panel shrinks to the available height after session notices, so a
long passage or voice status cannot push those controls below the viewport.
