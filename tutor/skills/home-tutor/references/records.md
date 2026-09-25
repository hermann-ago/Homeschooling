# Record payloads

All saves take `operation_id` (stable, reused on retry) and, for session records, `expected_revision` (the `revision` from the previous response).

## `record_attempts.attempts[]`
| Field | Meaning |
|---|---|
| `question_ref` (required) | e.g. `Q4 / book 71 (PDF 74)` or the question text for tutor-created items |
| `first_result` (required) | `Correct`, `Partly correct`, `Not yet`, `Unanswered`, `Unreadable`, `Source disputed` |
| `first_answer` | the learner's first answer, verbatim (spelling as written) |
| `reading_certainty` | how clearly the handwriting could be read (`Clear`, `Uncertain`, …) |
| `help_given` | the actual prompt, clue, pointer or explanation given |
| `revised_answer`, `after_help_result` | the answer after help and its result (`With help`, …) |
| `independence` | optional; `independent`, `with_help`, `not_assessed`. Defaults: help → `with_help`; correct without help → `independent`. Assisted work cannot be `independent`. |
| `topic_id`, `chapter` | when the question belongs to another topic of the same chapter |
| `question_text`, `tutor_created` | identify tutor-created questions |
| `source_note` | source/key references and known key conflicts |
| `recheck_date` | YYYY-MM-DD |
| `amends_attempt_id` | for a correction of an earlier record (the original stays) |

## `save_checkpoint`
`phase`, exact `next_prompt`, `observations[]` of `{prompt, first_response, help?, revision?, explanation_supplied?, note?}`. Earlier observations must be repeated unchanged at the start of the list; add corrections as `note`. Optional `minutes` only when actually known.

## `update_reviews.reviews[]`
New: `concept`, `evidence` (observed), optional `topic_id`, `next_prompt`. Update: `id` plus `outcome` (`Independent`, `With help`, `Not yet`), optional `evidence` (appended), `next_prompt`, `status` (`Closed` only with outcome `Independent` in a later lesson). Intervals default to 2 → 7 → 21 days.

## `finish_lesson`
`next_topic_id` (required, different from the current topic), `learner_explained` (required), `difficulty`, `help_that_worked`, `next_action`, `parent_observation`, `understanding` (`Independent`, `With help`, `Needs help`, `Not assessed`), `next_step`, `complete_topic` (true only when the topic is truly complete), `minutes`, `session_type`, `chapter_updates[]` of `{chapter, test_status, test_date, items_to_revisit, note}`. A subsection's questions never make a chapter test complete.

## `save_preference`
Only preferences the learner or parent confirmed, e.g. `key: "narrator"`, `value: {"voice": "en-US-Neural2-J", "rate": 0.9}`, `confirmed_by: "parent"`.
