# Student flow verification — 17 October 2026

**Story:** A supervised learner opens a prepared lesson from Curriculum, reads with the book visible, asks for clarification, answers, receives help, corrects a captured transcript, resumes after interruptions, and finishes. A parent can inspect the evidence and repeat the topic without overwriting the completed session.

## Environment and evidence

Used the built app in the in-app browser at a disposable loopback server. All learners, books and responses were synthetic. Entered the app's actual Test Mode through Settings. Planner, feedback and transcription were deterministic offline mocks; no family records or credentials were opened. The synthetic AI ledger contained zero provider requests and zero charges after the walkthrough.

Compared all rows in 15 base learning-record tables before and after the student session, guide regeneration, another session, and leaving Test Mode: unchanged. Test answers appeared in the test records UI and were absent after leaving Test Mode. Compatible prepared guide versions remain deliberately reusable between modes.

| Boundary/flow | Result | Observed evidence |
|---|---|---|
| Settings → Test Mode | Passed | Persistent TEST MODE banner and test-only storage path. |
| Curriculum → lesson | Passed | Original PDF alongside the green Figtree introduction; only the current tutor activity rendered. |
| Reading → clarification → return | Passed | Asked “What does tribe mean?”; reply saved beneath reading, then returned to reading. No learner attempt created for the free question. |
| Narration → break → refresh → return | Passed for UI/checkpoint | Play changed to Pause; a break stopped the reading UI. Saved checkpoint retained device sentence 3, activity and interaction. Refresh restored the break. |
| Typed draft → refresh | Passed | “He kept the tribes apart.” remained in the response field. |
| Submit → feedback → refresh | Passed | Original response/feedback recovered with one response and one assessed attempt. Keyboard activation of Send answer worked. |
| Wrong answer → hint → revision | Passed | Original answer, feedback, hint and revision stayed ordered and inspectable. Revised success remained `with_help`. |
| Spoken transcript → correction → refresh → confirmation | Passed after fix | Original “trides” remained separate from corrected “tribes.” The correction draft survived refresh, and assessment stayed unavailable until confirmation. Input was simulated, not spoken into an OS microphone. |
| Continue → recap → Finish | Passed | Explicit controls required; completed session retained reading reached and understanding “With help” separately. |
| Parent records | Passed | Both attempts, assistance, original transcript and confirmed interpretation were inspectable. |
| Completed topic → Write again → Start lesson | Passed | New guide version and separate session `…-02`; completed `…-01` remained attached to its original guide and retained all evidence. |
| Leave Test Mode → normal records | Passed | Zero synthetic practice answers in the base records view; all 15 checked base tables unchanged. |

## Issues found and repaired

1. **Return orientation repeated after refresh or later steps.** A break snapshot stayed active indefinitely, while dismissal lived only in component state. Added a durable `acknowledge_return` event, limited orientation to the returned activity, and cleared the snapshot on advancement. Verified acknowledgement → refresh and advancement in the browser and integration tests.
2. **Unconfirmed transcript edits were lost on refresh.** The confirmation form held edits only in React state. Added a browser draft scoped to mode, session and response. Confirming clears that draft only after a successful result. The original capture remains immutable, and the draft never triggers assessment. Reproduced the loss, then verified the corrected text survived refresh in the browser.

The offline rehearsal assessor was also corrected to use the request-selected test context, so Test Mode receives feedback for its own synthetic responses. Its planner is mocked to permit UI regeneration without a paid request.

## Regression checks

- Frontend: **144 tests passed** across 32 files with two workers; lint and production build passed.
- Backend: **25 focused tests passed** for activity integration/API and Test Mode; the engine/return regression subset also passed.
- An initial fully parallel frontend run timed out in an existing recorded-audio seek test. That file passed separately, and the complete suite passed with two workers. No recorded-audio code was changed in this verification.
- Existing simulated-browser media and query-fixture warnings remain; these are not proof of physical device behavior.

## Limits

This verifies the desktop interface, commands, persistence, recovery and projections with controlled responses. It does not validate real AI teaching quality, OS microphone dictation, physical speaker output, recorded-audio seeking on family devices, phone/tablet layouts, camera/photo capture, or the family's actual Math exercise mappings. Those still need device/content-specific checks.

Local screenshots are saved in the ignored `.tmp-data` folder: `student-introduction-2026-10-17.png`, `student-transcript-recovery-2026-10-17.png`, `student-completed-2026-10-17.png`, and `student-test-mode-exit-2026-10-17.png`.


## Shared screen, full thread and repeat follow-up (2026-10-17)

The follow-up keeps all options in the shared lesson screen; there is no separate parent interface. Voice preparation is an expandable lesson tool. The latest teacher feedback and current question stay with the answer input; older exchanges collapse beneath them. A whole-thread control expands reached teaching, original prompts, follow-ups, answers, hints and feedback. Learning records and learning notes link to that session. Typed answers save and assess through one durable command, without bypassing dictated/photo confirmation or prediction reveal. Draft indicators distinguish local storage from an acknowledged server save.

Browser verification used the built UI on port 8770 and a fresh disposable synthetic database (`homeschooling-activity-rehearsal-es5ulloc`). Paid generation was mocked; the rehearsal AI request ledger remained empty. The family database was not used for testing.

Verified in the browser:

- Welcome → reading → question with automatic answer focus; optional voice preparation remained collapsed below tutoring.
- Typed wrong answer: device-save indicator became home-server-save only after acknowledgement. Reload restored the exact draft.
- One **Check my answer** click saved and assessed; a wrong answer opened a distinct follow-up. The latest feedback stayed visible, and the answer area received focus.
- Requested hint → typed revision → one-click check → explicit Continue → recap → Finish.
- **Show full lesson thread** displayed the welcome, complete reached reading, original question, original answer, follow-up, hint, revised answer and teacher feedback.
- **Repeat this lesson** opened new session `2026-10-17-c1-02` at the introduction with the same saved guide. The original `…-01` remained completed. All six compared original record groups (sessions, attempts, responses, interactions, dialogue and actions) were unchanged.
- Records → saved answer → **Open full lesson thread** navigated back to the original `…-01`, independently of the active repeat. Assisted success stayed labeled **With help**.

Regression checks: **149 frontend tests across 32 files passed** (two workers, 15-second test timeout); **47 focused backend tests passed**, followed by the additional **Test Mode repeat-isolation test**. Lint, production build and whitespace checks passed. The Records link test also passed after its final assertion was added. Earlier validation caught a duplicate import, stateful test mocks and a missing-root-history edge case; these were repaired before final checks. Existing media simulation warnings and the build's chunk-size advisory remain.

Screenshots: `.tmp-data/repeat-and-thread-2026-10-17.png` and `.tmp-data/full-lesson-exchanges-2026-10-17.png`. Physical-device dictation/audio and phone/tablet layouts were not revalidated in this follow-up.

After verification, the recorded home server was stopped gracefully (writing its normal backup) and restarted with the built interface. Health returned `ok` and the running server exposed all 23 activity definitions. No learner answers were submitted to the home server. The disposable browser tab and rehearsal server were closed.


## Closing overview, attempts, position and help (2026-10-18)

**Story:** A student sees their current lesson position, requests targeted help, returns to skipped work from a factual recap, and navigates between the original session, its repeats and the next assigned lesson. All controls remain in the same shared interface.

| Boundary | Result | Evidence |
|---|---|---|
| UI renders | Passed | Generic step labels, three help choices, observed recap and attempt links rendered in the built browser UI. |
| Client to API | Passed | Each help kind (`explain`, `example`, `hint`) produced its own saved event; the recap return used `revisit_activity`. |
| API to data | Passed | Revisit created a new interaction. Three help records survived and the assessed answer retained their text with `with_help` independence. |
| Data to response | Passed | A skipped unanswered task showed no saved/checked answer; successful return updated the recap to one checked answer and zero unfinished activities. |
| Response to UI | Passed | Recap received keyboard focus; Next lesson opened the correct following chapter; original/repeat links navigated to their exact saved sessions. |

The browser rehearsal used disposable invented records at `homeschooling-activity-rehearsal-yq6pike2`, served on port 8771. It never opened the family records. The rehearsal AI request ledger contained **zero requests**. No learner response was submitted to the main home server.

Verified journey: welcome → reached reading → simpler explanation → separate imaginary example → hint → leave unanswered work to revisit → recap (no assessed answer) → Return to this activity → new interaction → typed assisted answer → explicit Continue → recap (one checked answer) → Finish → Open next lesson → original → Repeat → Original lesson link → Resume your repeat. The repeat was a distinct session; original responses remained available. Cross-day IDs were `2026-10-17-c1-01` and `2026-10-18-c1-01`.

Recovery verification found that the older HTTP response cache could replay a failed help response indefinitely or reject a refreshed revision before reaching the engine. Canonical activity events now use their durable engine receipts instead. A real HTTP integration test verifies failed example → same operation with current revision → recovered result, one job and one delivered message; changed content under that identity is rejected. A failed help request can be deferred without inventing evidence, and later recovery retains its original operation identity.

Checks: **157 frontend tests across 33 files passed**; the final help-location component check also passed. **57 focused backend/security/synchronization tests passed**, followed by one additional unreached-question recap guard test (**58 checks**). The eight overview tests also passed after final projection updates. Lint, production build and whitespace checks passed. One earlier backend fixture setup raced with the frontend build replacing its assets folder; the affected test passed when rerun after the build. Builds and backend fixtures should run sequentially. Existing simulated media warnings and the production bundle-size advisory remain.

Screenshot: `.tmp-data/lesson-summary-2026-10-18.png`. The browser walkthrough verifies desktop behavior with mocked teaching. Actual device dictation, physical audio and phone/tablet layouts were not revalidated here. The recorded home server was restarted with its normal backup after verification; the disposable browser/server were closed afterward.

## Development Test Mode switch (2026-10-18)

The Vite string proxy rewrote Host to the API address while retaining the browser's Origin, causing Test Mode changes to fail the API's same-origin check. Both the normal development configuration and the disposable practice configuration now explicitly preserve Host (`changeOrigin: false`); backend protection is unchanged.

Verified through the visible browser on port 5173, forwarding only to the synthetic rehearsal on port 8772: switching Test Mode on succeeded, the switch became checked, and the practice lesson opened with the Test Mode banner and Start lesson control. A mutation through the same proxy with Origin `http://evil.example` still returned 403. The rehearsal uses temporary sample records and mocked teaching; no family learner records or paid AI calls were used.

## Chat-style lesson workspace (2026-10-18)

The tutor now separates a chronological, independently scrolling conversation from a bottom answer/action area. Reached history opens in order above the current activity; future teaching stays absent. Typing, choices, transcript confirmation, assessment, reading completion, breaks and Finish retain the same engine commands. The lesson menu at the top contains listening replay, narration preparation, session permissions, position details and attempt links. The lesson header is compact, source boundaries and extraction notes live in Book details, and PDF page navigation floats over the viewer instead of consuming a bottom strip. The wider tutor panel uses about 41% of an ordinary wide screen, capped at 46rem. Fit page uses the actual PDF aspect ratio and both viewport dimensions; Fit width and zoom remain available.

Browser verification used only the existing disposable rehearsal and its Test Mode copy. The original completed practice thread remained available; a new repeat was used for welcome → reading → question → saved wrong-answer draft → reload → feedback/follow-up → hint → revised draft → break → resume and acknowledgement. The exact revision draft returned, and remained pending for the user to try. Scrolling up showed Back to latest; the composer bounds stayed identical before and after scrolling (top 554.48px, bottom 884px). The visible PDF was 593 × 767px inside an 830 × 792px viewport, with no horizontal or vertical overflow in Fit page. The top options menu opened in the browser and closed with Escape. Screenshot: `.tmp-data/lesson-chat-layout-2026-10-18.png`.

Focused regression coverage checks history order, the separate answer area, preserving scroll position when replies arrive, keyboard menu dismissal, portrait fitting and width fitting, plus the existing capture/recovery/confirmation and activity transitions. Verification is desktop-only; mobile devices, virtual keyboards, real dictation and physical audio were not manually revalidated. No family learner records or paid teaching requests were used.

Final checks: **160 frontend tests across 33 files passed**; lint, production build and whitespace checks passed. Existing simulated-media warnings and the production bundle-size advisory remain. The development frontend and disposable practice backend remain running for the user's walkthrough.

## Invalid feedback reply recovery (2026-10-19)

A live lesson exposed a complete, charged Assessment reply with trailing corrupt material and a conflicting second assessment. Strict validation correctly rejected it, but the generic Retry control repeatedly retrieved the same invalid cache entry. No fragment was selected or used to grade the learner.

Complete schema failures now have a distinct failure type. The canonical engine exposes a safe recovery status on the saved response. An explicit Generate replacement feedback action records permission in the existing assessment job, retains the frozen response/context, and requests at most one replacement of that exact invalid reply under existing spending limits. Both raw replies and charges remain saved. Replacement identity survives network retries and restart; invalid replacements stop for review, and uncertain replacement outcomes retain reservations without another purchase. Ordinary retries still reuse the invalid original without a paid request. Workbook assessment uses the same recovery path.

Regression verification used invented records and mocked provider responses: valid replacement, invalid replacement, uncertain transport outcome, restart/replay, unchanged capture, one assessed attempt, original cache retention, legacy invalid-cache behavior and guide duplicate recovery. **42 distinct backend checks** passed across the focused runs; **31 activity UI tests**, lint, production build and whitespace checks passed. The first frontend run could not start a fork worker; the thread-worker rerun passed.

After a graceful home-server restart/backup, recovery was applied through the real browser to the family's pending response. The saved response count stayed at four; its original text hash and response identity were unchanged. Assessed attempts rose from three to four as the one previously pending answer received feedback. The replacement request completed once (US$0.001270), and Continue lesson became available. No learner answer was typed, replaced, skipped or advanced by the recovery. Screenshot: `.tmp-data/lucas-feedback-recovered-2026-10-19.png`.

## Reviewed-key grading and assessment correction (2026-10-19)

Investigation of an incorrectly rejected workbook response confirmed that retrieval had succeeded: both the exact original question and the reviewed answer key were in the frozen teacher-only assessment context. The model confused the subject of the statement with the subject of its supporting passage and contradicted the key. Original question/key PDF pages were extracted and visually checked locally; no paid generation was used for investigation or correction.

Unambiguous true/false responses can now be checked directly against the exact pinned exercise's reviewed key. This path requires matched source provenance, a key reference, no source issue or key exception, and an ordinary answer objective. Reasoning, written methods, photos, ambiguous wording and uncertain keys stay on their existing assessment path. The original provider prompt/cache identity remains unchanged for work that uses that path.

A family-only `recheck_key` activity event can correct a previously rejected first response that demonstrably matches that reviewed key. It retains the immutable original attempt, creates an assessment amendment (not a learner revision), preserves real assistance, appends a visible teacher correction, and marks only that assignment/activity addressed. A review whose sole recorded basis was the teacher error is withdrawn; a real assistance-based review remains open. Learning memory uses the amendment while retaining the audit history. Keys remain absent from child payloads. Follow-ups for completed physical writing now resume capture instead of requiring another declaration of writing completion.

Synthetic verification: **58 focused backend checks passed** for workbooks, activity transitions, learning memory and keyed assessment. The final **16 key-specific cases** passed again after the review-withdrawal guard was refined; these include source exceptions, ambiguous answers, HTTP replay/restart, immutable evidence, assistance preservation, public-key exclusion and derived-memory amendments. **32 activity UI tests**, lint, production build and whitespace checks passed.

After a normal backup/restart, the existing rejected response was corrected through the app's inline key-recheck control. Its capture stayed unchanged, an amendment marked it correct, the erroneous review became Withdrawn with no due date, and Continue lesson was visible. No answer was entered or lesson advanced during the correction. Screenshot: `.tmp-data/history-key-correction-2026-10-19.png`.

## Current activity box and Enter submission (2026-10-19)

Current questions, source reading, demonstrations, teacher feedback, capture, confirmation, recovery, breaks and recap controls now share the bottom activity box. The upper conversation contains reached history and processed exchanges, including earlier responses within the current activity. A follow-up keeps its own prompt in the activity box and its original question/answer in reference history. Future activities remain excluded. Reading opens expanded; the size toggle changes presentation without advancing work or remounting narration. New prompts reset the activity scroll without moving a learner who is reviewing earlier history.

Enter uses the same validated submission path as the answer button; Shift+Enter inserts a new line. Empty answers, required reasoning, busy submissions and IME composition cannot bypass validation. A synchronous in-flight guard prevents repeated key presses from submitting twice, and retries retain the durable response identity. Dictated answers still require confirmation before assessment.

The focused activity, capture and guided-lesson suites passed **48 tests**, covering history placement, reading expansion, follow-up transitions, durable drafts, keyboard submission and capture confirmation. Browser verification used only the isolated mocked practice server on port 8772 through the practice frontend: resumed draft → Shift+Enter newline → Enter submission → processed exchange in history → feedback and Continue in the activity box → recap → finish → distinct repeat → expanded reading → smaller reading → question. Lucas's production page was reloaded for read-only verification of the rebuilt interface and preserved completed lesson. No production answer or progression event was submitted. Screenshot: `.tmp-data/current-activity-box-2026-10-19.png`.

Lint, production build and tracked whitespace checks passed. A broader frontend run was stopped after unusually slow execution and two failures in the activity suite; both affected checks (ambiguous transport recovery and prediction gating) passed unchanged when rerun in isolation. The complete frontend suite was not established as passing by this run. Existing simulated-media notices and the bundle-size advisory remain.

## Minimized activity and visible recording preparation (2026-10-19)

The activity box now minimizes to its bottom header, giving the reference history the remaining height. Narration pauses through the shared controller. The reading/capture subtree remains mounted and hidden, retaining its cursor, scroll and drafts; Show activity restores it without advancing. A new interaction or break automatically exposes its current work. Browser geometry confirmed a minimized height of about 48 pixels and hidden content. No learner answer or completion event was sent during verification. Screenshot: `.tmp-data/minimized-activity-2026-10-19.png`.

When a guided reading has no saved recording, its voice controls now explain that state and offer inline recording preparation, using the exact pinned session and the existing estimate/creation flow. The reported lesson had an empty saved-audio list; the host was also configured for Kokoro. Following the user's explicit choice, the canonical settings endpoint switched new recordings to Google/Achird while preserving all allowance amounts and other settings. The estimate was checked in the app (maximum US$0.423, US$1.93 remaining); no paid audio generation was requested. Creating guided text remains separate from recording it.

Activity, guided-lesson and read-along suites passed **58 tests**, including mounted-state preservation, draft retention, pause behavior, inline missing-recording controls and pinned-session preparation. Lint, production build and tracked whitespace checks passed. Production was reloaded and minimize/restore plus the inline Google estimate were verified; the learner remained on the same reading step.

## Automatic recordings and step playback (2026-10-19)

Preparing a guide, starting a guided session and repeating a lesson now schedule the selected narrator automatically. Jobs are saved in the existing narration ledger and run after lesson transactions and locks are released. Identical recordings and passages reuse their existing identities and budget reservations. Disabled voice, exhausted allowance, provider failure and uncertain outcomes preserve the text lesson; unknown purchases are not blindly repeated. Queued/running jobs interrupted by a server restart are marked paused. Practice sessions receive reusable recordings after compatible live preparation finishes, without copying or modifying learner evidence.

Recordings now split at all semantic activity boundaries. Explicit Start/Continue/stage transitions request playback once for that current step; refresh and polling do not request autoplay. Playback requires an exact planned source range and prompt. Revised warm-ups, live follow-ups, feedback and hints without their own matching recording remain text-only. Question audio ending never submits an answer or advances the activity. The shared play/pause button stays at the bottom-right outside the activity's scrolling content. Minimize, help, submission and break interruptions stop narration; recorded playback retains its saved media position. Device speech remains an explicit manual option and is not an automatic substitute for missing saved narration.

The synthetic browser rehearsal on port 8773 uses mocked 12-second WAV files and disposable learners only. Verified: session creation automatically prepares recordings → welcome autoplay → Continue autoplays reading → bottom-right pause and resume preserve offset → reading completion waits for Continue → question autoplay waits for an actual typed answer → wrong answer produces a separately identified follow-up with no media element or borrowed question recording. No production answer or lesson advancement was submitted during verification.

Focused checks passed for automatic job identity, budget/cache reuse, bounded provider rate-limit recovery, unknown outcomes, practice isolation, exact activity matching and transport behavior. The five frontend suites covered 69 cases, followed by the added recording-upgrade case and updated transport checks. Backend generation/cache/budget checks passed 26 cases; mode/automatic checks passed 15 cases plus the new targeted recording-sync case. Lint, production build and tracked whitespace checks passed. Existing simulated-media notices and bundle-size advice remain.

For the family's open lesson, nine recorded passages were saved before a definite Google 429 refusal. Recovery reused those passages and finished all 37 entries: 36 recordings and one text-only fallback after a provider content refusal. The final generation charge was US$0.097724. Only explicit 429 refusals receive at most two delayed retries for a passage, honoring a bounded Retry-After delay; each retry re-establishes the same spending reservation. Unknown or ambiguous outcomes retain their reservation and remain paused. Preparation progress is exposed without future teaching content. Production was restarted with normal backups; the completed recording validates as synchronized and is selected in the unchanged pending reading step. Playback availability and its bottom-right placement were verified without advancing or answering for the learner. The final fallback/transport pair of suites passed 21 checks.

## Session narration toolbar (2026-10-19)

Voice selection, reading speed, current-passage replay and voice information now live in the tutor's top bar. The activity box retains the current teaching content and bottom-right play/pause control. The information menu holds recording notes and the existing missing-recording preparation flow. Voice and speed are stored per session and app mode on this device, carry across activity transitions and survive refresh. Changing voice pauses narration; changing speed does not start playback. Replay remains scoped to the exact current activity, so a follow-up cannot replay an unrelated original question.

The four focused frontend suites passed **72 tests** covering toolbar placement, minimized activities, controlled reading settings, durable session preferences and the existing autoplay/transport flow. Lint and production build passed; existing simulated-media notices and the bundle-size advisory remain. The rebuilt production UI was reloaded on the family's existing reading step. The toolbar fit on one line, remained accessible while minimized, restored a changed speed after refresh, and opened/closed its information menu with Escape. Speed was restored to 1x. No answer, advancement or paid generation was submitted. Screenshot: `.tmp-data/session-narration-topbar-2026-10-19.png`.

## Missing recorded passage recovery (2026-10-19)

The family's first reading contained a 2.92-second recorded title followed by a five-sentence passage that Google declined under its content filters. The remaining two sentences in that reading had their own recording. The existing intentional stop at an unrecorded part exposed only a disabled transport and a generic text-only label, leaving the reason unclear.

The footer now identifies a missing passage and offers explicit Use device voice for this passage. It never starts device speech automatically. This temporary choice preserves the selected session narrator and returns to the next saved recording within the same reading. Device cursors preserve the original track/part and unfinished sentence through interruption or refresh. Continuation between audio parts is retained independently of source-loading pause events, while an explicit interruption cancels it. Reading boundaries still stop before the next activity.

The four focused suites passed **76 tests**, including missing-part recovery, restoration, media source changes, interruption cancellation, session voice preservation and no automatic progression. Lint and production build passed. The family lesson was reloaded, its missing-part button started device narration, and playback was immediately paused. The activity stayed on Step 3; no answer or advancement was submitted and no new paid recording was requested. Screenshot: `.tmp-data/missing-recording-playback-2026-10-19.png`. Simulated-media notices and the existing bundle-size advisory remain; automated media tests do not establish sound quality on every family device.

## Workbook feedback identity recovery (2026-10-19)

The saved reply for a reported workbook failure marked the submitted answer correct but transposed characters in the assignment item ID. Exact ownership validation correctly rejected it; the generic TutorError classification then offered Retry, which repeatedly reused the same invalid saved reply. The answer remained captured and unassessed when the learner left the activity to revisit.

Workbook validation now checks the exact expected item set inside the AI provider's cached-response validation boundary. Omitted, duplicate and changed IDs are classified as invalid replies and use the existing explicitly requested, bounded replacement flow. Scoped schemas retain the original JSON schema, name and output budget, preserving cache/purchase identities. The complete workbook prompt, including appended exercise context, is frozen before generation so serialization order after restart cannot create a different request. No mismatched reply is attached by guessing an exercise ID.

Synthetic verification passed 50 workbook/key/activity checks and 19 focused recovery/budget checks (overlapping suites). Coverage includes cached retries without another purchase, restart, independent request scopes, one explicit replacement, and one resulting attempt despite duplicate commands. Whitespace checks passed. The home server was restarted through its normal backup/launcher after feedback work finished; health and the same pending activity were confirmed. No family answer, assessment, skipped-work status or progression was changed by the repair, and no live replacement generation was requested.

## Mila Portuguese book reconnection (2026-10-19)

The supplied 142-page PDF was checked against the missing document record and visually inspected before recovery. With the home server stopped through its normal backup flow, the original document 15 was reconnected using a canonical Store transaction and durable file reference in Mila's Portuguese Books folder. All 11 linked topics, annotations, progress and every other database table were compared before/after and remained unchanged; other document records were also unchanged. The new file checksum was verified after writing. No curriculum analysis or paid AI generation was requested.

The existing Letra Q topic still assigns pages 16-29; the supplied PDF's page 16 is labeled Letra P. This source-range issue was observed but the stored page assignments were preserved during file repair.

After restart, the original document content endpoint returned HTTP 200 with application/pdf, the missing-file warning disappeared, and the PDF rendered in the family's existing lesson tab. Screenshot: `.tmp-data/mila-portuguese-restored-2026-10-19.png`. The app's existing page ranges and progress were retained.

## Portuguese section range correction (2026-10-19)

The family authorized correcting the book's complete lesson mapping. An earlier question incorrectly described W/Y as absent before the full scan finished; this was corrected, and the family explicitly chose to retain both. Actual page headings and section dividers were checked across all 142 pages. Printed and PDF page numbers agree, so offset remains zero. Corrected ranges: introduction 1-4; P 5-18; Q 19-32; R 33-46; S 47-60; T 61-74; V 75-88; X 89-102; Z 103-116; K 117-124; W 125-132; Y 133-140. The missing K topic was added, and existing topics were reordered to source order. Closing blank/publisher pages 141-142 were not turned into teaching tasks.

Changes used a revision-checked canonical Store transaction after a normal server backup/stop. All existing topic fields apart from ranges, order, offset and revision metadata were compared unchanged; every other database table, including completion evidence, annotations and the existing guide, was unchanged. Unrelated topics were unchanged. The source check required no started sessions, frozen passage records or assignments for these topics. No AI generation was requested. The server restarted normally and the live reader returned printed/PDF range 19-32 with zero offset.

Browser verification opened the Q divider on book/PDF page 19 and displayed assignment 19-32. W/Y remained in the topic list, 12 topics were present including K, and the two previously completed topics remained complete. The earlier saved Q guide is now marked noncurrent by the existing passage fingerprint check and requires regeneration before reuse. Screenshot: `.tmp-data/mila-portuguese-correct-pages-2026-10-19.png`.

## Mila's age-six Portuguese teaching skill (2026-10-19)

Updated only subject 13 through the versioned teaching-skill endpoint, saving version 2 and its normal Drive Markdown export. The existing general evidence/record rules were preserved. The new subject guidance requests a fuller 70-120-word welcome in short sentences, playful sound/letter discovery, concrete directions for workbook verbs, short attention cycles, optional movement, brief supported answers, and gentle bounded correction. It distinguishes letter names from sounds, avoids unverified picture claims and inaccurate Q/U generalizations, keeps handwriting inspection separate from spoken answers, and directs tidy preparation for instructional worksheets without turning repeated purchase/footer text into teaching content. It includes an adaptable Portuguese welcome example and does not require a separate adult interface.

The shared preparation prompt now treats 2-4 introduction sentences as a default and respects fuller introductions requested by a subject skill. Its prose-length ratio no longer restricts scaffolding for sparse workbooks. Introduction storage is bounded separately at 1800 characters; the existing 700-character explanation bound remains. Existing saved lesson files are not rewritten by this change.

Sixteen synthetic guide/skill checks passed, including preservation of an introduction beyond 700 characters through the activity projection, bounded output, unchanged book order, version isolation, and saved-session guide/skill pinning. The live skill endpoint returned version 2; the current session retained its original guide and skill version 1, while future preparation correctly identified the older guide as noncurrent. No new lesson or recording was generated for this skill update. The current Google recording separately paused on a provider 429 after previously saving 41 of 45 parts; saved material was retained.

## Opt-in visual preparation and fresh Q lesson (2026-10-19)

Kept extracted-text preparation as the default; added explicit skill-frontmatter selection of assigned-page PDF context. The subset checks book version, ownership, source safety, whole-page boundaries, page/byte limits and source mapping before provider invocation. Saved context includes original/attachment hashes and page identities. Existing provider PDF handling supplies images/layout; teaching PDF requests use the same low reasoning setting as other visual teaching requests. Registry questions no longer receive a redundant legacy fallback question; the no-question Portuguese fallback is localized.

Synthetic verification: 36 visual/guide/preparation/test-mode checks passed; 17 visual/planning checks passed; 25 visual/cost/automatic-voice checks passed before the final asynchronous dispatch adjustment, and 13 focused visual/voice checks passed afterward. Suites overlap. Coverage includes default text without PDF access, selected-page-only transmission, private-page/ownership/version rejection, free previews, saved provenance, cached reuse, unchanged attempts, registered question preservation, durable voice jobs, duplicate scheduling and a blocked mock voice request that does not block creation or session start. Whitespace checks passed.

Saved Portuguese skill versions 3 and 4 with explicit visual context and workbook pacing/capture guidance. Two bounded AI preparations used Q pages 19–32. Inspection found missing poem/cantiga narration and grouped paper tasks in the second draft. A source-reviewed guide restored both readings from the checked PDF, split the worksheet tasks and used two registered handwriting captures rather than text questions for tracing. The intro remains the generated fuller welcome. The reviewed plan has 38 activities covering all 14 pages; observation/coloring/matching acknowledgments do not claim assessed correctness.

The family explicitly authorized a fresh session without retaining the existing session's progress. The old session was verified unused at the introduction with no responses, dialogue or attempts, then marked replaced with its pending actions not assigned using a canonical revision-checked transaction after a normal backup/stop. Forty-eight protected tables and unrelated sessions were compared unchanged. No learner response, assessment or completion was invented. New guide: `guide-976-87754608ac`; new session: `2026-10-19-c2-02`, active at the introduction. Google repeatedly returned 429 during earlier narration jobs. The obsolete generation request was stopped during a known rejected-request backoff; saved parts and ledger states were retained. Automatic narration was moved to a daemon worker launched from the durable background-task queue so provider backoff cannot withhold HTTP creation/start responses. The reviewed lesson starts immediately while its recording prepares.

The proposed reusable Codex skill and importable, page-structured book companion are a future extension; this change does not implement companion import or bulk description of all book images.

Production browser verification displayed the new session at Welcome, the fuller Portuguese introduction in the green card, the correct Q divider on page 19, and assignment 19–32. No student activity was advanced or answered. Saved narration was visibly preparing with 2 of 39 passages available; the lesson controls were usable immediately. Screenshot: `.tmp-data/mila-q-fresh-visual-2026-10-19.png`.
# Fresh Google recording verification · 20 October 2026

After the daily quota reset, the existing Q guide `guide-976-87754608ac` was voiced through the production narration endpoint, without regenerating the guide or advancing its session. All three Google requests completed. Actual usage recorded US$0.064199 within a US$0.23 job maximum and the unchanged monthly voice allowance. The output contains 423.16 seconds of speech: blocks of 168.12, 174.24 and 80.80 seconds. Checked local CTC similarities were 0.9655, 0.9758 and 0.9752 respectively. The new manifest covers all 94 sentences with 39 locally cut clips; every activity boundary is a playback boundary, and every file hash matched. Three generation requests are separate from the number of local playback files.

A second production invocation returned `reused: true` with no additional voice spend. Read-only before/after hashes of attempts, reviews, sessions, checkpoints, dialogue, lesson actions, playback, activity interactions, responses and events were unchanged. No real learner answer, assistance, completion or reading progress was recorded. The interaction-table baseline was collected after generation started and before browser rehearsal; the seven legacy learning-table baselines preceded the generation request.

Browser verification used a disposable synthetic learner, an invented one-page book, and the newly generated real introduction, reading and question clips. It never opened a family database or provider credential. Start/Continue autoplay, manual pause/resume, measured sentence highlighting, stopping after reading until Continue, and waiting for an actual question response were checked. Refresh restored the same unanswered question without autoplay. No answer was submitted. The production reader returned the new track as synchronized, preferred and ready, with automatic voice preparation also ready. This establishes fresh continuous Google generation and playback with the actual local timing/cutting path, replacing the prior pilot's concatenated-recording limitation. Subjective pronunciation and teaching quality still benefit from family listening.

# Longer-recording pilot · 19 October 2026

Implemented `aligned-blocks-v1`: larger Gemini requests, durable raw WAV reuse, local checked CTC sentence alignment and activity-bounded playback clips. The host's expressive voice/model and allowances stay unchanged. Settings exposes the option and installed language availability. Google quota refusals pause, retaining saved audio and reservations.

Offline actual-voice checks used existing narrator recordings, never learner microphone audio: Portuguese 12 sentences / 93.24 seconds, similarity 0.9673; English 4 sentences / 21.40 seconds, similarity 0.9690. Processing took approximately 46 and 4.5 seconds respectively on this host. Isolated Q letter names needed an acoustic spelling normalization for alignment only. An older script containing a watermark/email was rejected rather than given invented timings. Originals and live learning records were not modified. These checks concatenate existing parts: they do **not** establish the quality or timing of a freshly generated continuous Google block. The project's daily Google quota was already exhausted; no new paid request was made for this implementation.

Automated checks cover one mock purchase producing several clips, duplicate/restart reuse, retained raw audio after alignment failure, changed sentence layout reusing the purchase, unsupported scripts, exhausted quota, frozen spending limits, unknown provider outcomes, invalid timings, and durable quota windows. Frontend tests cover measured highlighting, activity-stop behavior and refresh restoring offset without autoplay. A separate disposable browser rehearsal uses synthetic WAVs and timings, with no family database or provider access. A supervised fresh Google block still needs a listening check after quota resets.

Verification completed: 50 focused frontend checks passed; the final backend run covering alignment purchases, automatic voice and Test Mode passed 30 checks. An earlier broader voice/budget/local-voice run passed 43 checks before the additional edge cases were added. The Test Mode integration now waits for its asynchronous voice worker and exercises both narration strategies, asserting no live attempts, reviews, sessions, checkpoints or dialogue changes. Browser rehearsal confirmed Continue starts saved narration, reading end stays at the completed reading until Continue, refresh does not autoplay, and the next question waits for actual input. Corrected the finished-reading footer to say the reading is saved. Production was backed up and restarted; longer recordings were enabled with Google/Achird and existing dollar allowances preserved. The real Q script passed local preflight and its free preview returned three blocks, blocked by the existing daily quota until 20 October at 04:00 São Paulo. No fresh Google request was sent.

# Lesson navigation menu · 20 October 2026

Added Go back one step and Start lesson over to the existing lesson options menu. Synthetic engine/API tests cover repeated back to the beginning, stale revisions, lost-response retries, break navigation, restart persistence, pending draft/recording-offset recovery, frozen completed answers/feedback, unconfirmed capture preservation, assistance retention, family-only commands, and starting a completed lesson from its introduction without changing the original session. Frontend tests cover the menu events, fresh response areas with old exchanges in history, cached narration on an exact replay, and isolation from old audio offsets. Focused runs passed 58 frontend checks and 19 backend navigation/Test Mode checks; the broader existing engine/API/overview run passed 28 checks before the completed-lesson extension.

The disposable browser rehearsal went from a question back to reading and introduction, returned forward to recover the unchanged typed draft, and restarted from a break. No real student answers or paid AI calls were used. Production was backed up before the additive schema upgrade. The live Q session is left paused at its existing activity; the new controls were only exercised in the disposable rehearsal.
