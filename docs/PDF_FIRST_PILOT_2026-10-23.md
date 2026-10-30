# PDF-first preparation pilot — October 23, 2026

Prepared the next incomplete, non-archived lessons using the normal app preparation
API and existing caps (US$0.30 script/review, US$0.75 audio). Did not start student
sessions, submit answers, grade pretend work, or mark chapters complete.

## Delivered lessons

| Learner | Lesson | Saved guide | Result |
| --- | --- | --- | --- |
| Lucas | The Rus Come to Constantinople, book 208–211 / PDF 223–226 | `guide-376-1b8c358aac` | 23 steps, all 56 assigned source sentences once/in order, 5 reading stretches, 2 discussion questions, 10 exact linked exercises |
| Mila | Consoantes - Letra S, PDF/book 47–60 | `guide-978-f0622121b0` | 22 steps, both complete literary excerpts, all 13 numbered tasks, opening letter models, writing capture, correct listen-before-work sequence |

The scripts were written by the app's API planner. Lucas passed automated review.
Mila required six paid planner drafts while the workflow was hardened. One cached
draft was recovered after a serializer fix without repurchasing it. The final API
draft was approved by direct visual review through the existing reviewed-plan
import. **Its spoken-script hash is identical to the API-generated draft**
`guide-978-d7d537f7c1`; Codex did not rewrite the final teaching text by hand.
The import records `family_review` distinctly from AI approval.

Both previews were traversed in the browser, including all 23 Lucas steps and all
22 Mila steps. Preview paused at each step and created no learner attempts. This
does not establish real-device dictation or every possible adaptive feedback path.

## Findings and reusable changes

1. A complete provider reply could still omit the actual poems. The source-bound
   validator correctly rejected it before saving or buying narration. The planner
   now receives a compact example of the exact required read segments and source
   IDs alongside the output contract.
2. Duplicate JSON visual descriptions competed with original page images. PDF-first
   planner context now omits those descriptions, retaining exact readings/tasks,
   source relationships, skills and learner context. Stored companions are intact.
3. A valid provider union serialized empty reading-only fields into an introduction.
   Parsing now resolves content to the declared registry model. The saved reply
   became usable without another paid script request; nonempty incompatible fields
   remain errors.
4. A work pause could precede the poem it referred to. Explicit listen-then-work
   instructions now carry a same-page reading dependency, enforced in provider-plan
   validation and final emitted activity validation.
5. Full rewrites forgot earlier corrections. Explicit rewrites now receive current
   editorial advice plus bounded prior corrections from the same topic/source
   lineage. This includes advice on approved drafts and legacy revision chains.
   There is no automatic paid rewrite loop.
6. Some drafts read a direction and repeated it as another activity. The output
   contract now states that the activity already narrates its prompt; ordinary
   work directions belong in one waiting activity.

## Automated-review limitation

Mila's reviewer first correctly identified a missing opening page and later the
omission of the middle picture column on page 59. On the final, corrected draft,
it falsely claimed that page 59 contained no middle pictures. The exact frozen PDF
attachment sent to both models was rendered and visually checked: those pictures
are present. The correct script was preserved, a versioned edition/page-bound
source clarification was saved through the app, and visual approval was recorded.

An earlier advisory also misdescribed the page 47 letter forms. Neither advisory
was treated as authoritative over the original page. The test therefore does
**not** establish unattended reliable preparation. Direct pages help, source guards
catch real omissions, and explicit rewrites can use findings; visual review is
still fallible and benefited from Codex supervision in this pilot.

## Narration

- Lucas: Google Achird accepted one of four generation blocks and declined three.
  The saved manifest validates and contains 5 recorded sections and 20 text-only
  sections. No refusal-retry purchase or source rewording was performed. His
  script is prepared, but advanced narration is incomplete.
- Mila's final script: Google Achird completed both generation blocks. All 22
  sections have saved audio, with zero text-only sections. Manifest validation
  passed and all referenced media files exist.
- Audio for a superseded Mila draft remains saved for audit/reuse. It is not
  substituted for the final script's recording.

## Actual app charges

| Work during this pilot | Charges |
| --- | --- |
| Lucas script | US$0.003580 |
| Six Mila planner drafts | US$0.054840 |
| Six automatic reviews | US$0.038953 |
| All narration, including superseded draft audio | US$0.095243 |
| **Total** | **US$0.192616** |

The app ledger recorded 13 teaching requests and 8 narration requests, including
three declined narration requests charged at zero. This excludes Codex subscription
usage and makes no claim about provider taxes or external account activity.

## Record isolation and verification

Before/after sorted-row hashes match for attempts (109), activity responses (63),
dialogue (153), tutor sessions (15), playback (12), assignment items (46), reviews
(12), and topics (796). Only preparation/review/source-note/media artifacts were
added. Neither child's answers, understanding, saved place or completion changed.

Focused regressions covered source contracts, activity unions, cached reply
recovery, review feedback, task ordering and canonical preparation. The final
engine/interaction/curriculum/source/voice compatibility run passed 79 tests;
the source/registry/review/planning run passed 69, with two additional lineage
tests passing after the history adapter was added. These runs overlap.

Evidence and intermediate renders are under
`.tmp-data/pdf-first-pilot-20261023/`, including exact API draft JSON, the actual
sent page 59 rendering, preview screenshot, media checks, ledger totals and
before/after evidence hashes. No live learner records were copied into test fixtures.

See [the cleanup ledger](PDF_FIRST_PREPARATION.md) before removing companions,
legacy adapters or superseded preparation/media artifacts. Preserve anything
referenced by a started session.

## Original PDFs inspected

- [History reading](</G:/My Drive/Casa, Família e Vida Prática/Homeschooling/Lucas/3rd Grade/History/Books/Story of the World V.2.pdf>): book 208–211 / PDF 223–226.
- [History exercises and private key](</G:/My Drive/Casa, Família e Vida Prática/Homeschooling/Lucas/3rd Grade/History/Books/SOTW2_Tests.pdf>): PDF 90–92 and 173.
- [Mila worksheet book](</G:/My Drive/Casa, Família e Vida Prática/Homeschooling/Mila/1st Grade/Português/Books/No mundo das consoantes - Volume 2 - Família de Trigo.pdf>): PDF/book 47–60.
