# Structured lesson authoring

## Decision

Use schema-constrained JSON as the AI writer's output across the app. Keep natural
teaching language inside typed turns. Validate that object locally, compile it
deterministically into the existing activity contract, review those exact saved
activities against the original source, and render them with registered components.
Do not purchase a prose script and ask another model to infer its structure.

Investigation on 2026-10-29 found that this is already the common preparation path:

- `backend/tutoring/page_script.py` defines the compact authoring schema and source
  checks. `welcome`, ordered `turns` and `closing` distinguish `say`, `read`, `ask`
  and original `book_work` explicitly.
- `backend/services/ai_provider.py` sends OpenAI a strict JSON Schema and Google
  a JSON response schema, then validates the reply with Pydantic. Complete invalid
  responses remain cached for the existing explicit recovery flow.
- `backend/routers/tutor.py` passes that schema to the writer, saves the original
  structured script in the guide context and performs local compilation. No AI
  conversion is involved. The original JSON is private preparation data.
- `backend/tutoring/script_review.py` reviews the exact compiled activities,
  original pages and frozen guidance. Review identity includes those inputs;
  changing the questions or policy changes the review identity. Audio generation
  requires approval. The existing bounded editorial repair prepares a complete
  new structured script under the same spending cap, with another review.
- The reader consumes the saved, versioned activity JSON. Engine-generated IDs,
  source checks, learner responses, progression and evidence stay server-owned.

Compilation is useful: an AI author should specify teaching and answer controls,
without authoring database IDs, mutable session state, evidence records or UI code.
This is a deterministic adapter between two explicit schemas, not inference from
prose. Keep that boundary rather than making the model emit arbitrary engine state.

## Books interaction policy

New family reading preparation freezes `book_question_policy: book-choice-2`.
Its provider schema and local validation restrict generated `ask` turns to
discussion with `single_choice` (two to four distinct labels) or `true_false`.
Yes/no uses two localized single-choice labels. The compiler emits the ordinary
`ask_question` activity with `response_modes: ["choice"]`, answer evidence and
no required reasoning. Reasoning may be tested by choosing between possible reasons.

The writing and review guidance asks for a coherent reading followed by normally
two or three brief checks, one at a time. Question count, good distractors, source
fidelity and pacing still need editorial judgment; the schema alone cannot prove
those qualities. Printed brainstorming and discussion questions also use only
selection checks or are omitted; they do not require writing. Local compilation,
canonical reviewed imports and pre-voice validation enforce this rule.
Curriculum subjects keep the same structured pipeline with their appropriate
text, spelling, handwriting and other controls.

The live reading feedback schema disallows free-text `follow_up` and permits only
a selection question as an extra activity. Brief feedback can return a child to
the same choices for a retry. The UI hides the answer-method selector and optional
explanation field for choice-only controls. Hints must return to the existing
reading/choices; old review prompts without choices are not injected as warmups.
Choice captures retain the existing recognition-versus-explained-mastery distinction.

The shared preparation version and cache key include the policy. Old materials
remain available, while new preparation uses the new contract and a fresh review.
Active sessions retain their pinned guide. This change does not purchase scripts,
regenerate recordings, rewrite saved lessons or alter learner answers automatically.

## Provider guidance checked

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs):
  use a strict schema, closed objects and required properties; supported schemas
  are a subset of JSON Schema.
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output):
  schema-constrained JSON still needs application validation and handling of
  semantically incorrect content.

Schema correctness is separate from teaching quality. Retain source review and
representative family reading pilots before claiming that a lesson teaches well.

## Verification

The book-policy tests cover schema rejection, both provider schema adapters,
live selection follow-ups, original structured-script persistence, source review,
cross-child reuse, an incorrect choice, retry after restart and unchanged learner
isolation. Preparation and the activity engine are exercised directly against
disposable data with deterministic provider replies. The UI regression verifies
selection, refresh and submission without a method picker or text field.

The initial sandbox could not create TestClient's local socket pair. Verification
in the host runtime subsequently passed the 60 focused backend checks, including HTTP
preparation, review, shared reuse and script replacement. The reading/activity UI
checks passed 136 tests; the production build and lint on the edited components
also passed. The additional blank-page regression passed with the related 19 checks.
Synthetic checks establish behavior, not teaching effectiveness.

## Paragraphs in the reader

Original paragraph breaks remain blank lines in each JSON reading's `text` field.
The compiler retains them while normalizing printed line wraps, and assigns each
sentence its paragraph within the current turn. The reader groups those sentences
into paragraphs and uses inline keyboard-accessible text controls, so highlighting
and sentence replay remain available without making every sentence a separate box.
Headings and attributions remain separate when the source identifies them that way.

For older scripts, the API can recover saved author paragraphs only when every
sentence matches exactly. It changes display metadata without rewriting the saved
guide, audio identity, timing, answers or progress. Unmatched older scripts retain
their existing metadata; preparing a new version uses the current paragraph policy.

Source maps explicitly mark a page `blank: true` only when its PDF content stream
is empty and it has no annotations. Lack of selectable text is insufficient:
scanned pages, illustrations and graphical exercises remain visual source work.
Writers and reviewers treat marked blank pages as present, with no reading task,
so a trailing empty page cannot turn a complete chapter into a missing-source stop.

The 2026-10-29 A Great Storm pilot uses original PDF pages 13–16 (page 16 is
structurally blank), eight paragraph groups in each of its two readings, and
three single-choice checks. It passed AI source review with no findings. The
selected Adam narrator was recorded with ElevenLabs Flash v2.5 and verified
ready with synchronization. A fresh script session preserves the earlier thread;
the opened listening preview does not submit answers or complete reading work.
