# Lesson preparation from home devices

Family devices use relative API addresses on the home network. Preparation does
not require HTTPS. In particular, HTTP phones do not provide crypto.randomUUID:
use the shared operationId fallback and guard browser storage. Keep one operation
identity after an ambiguous submission; never leave busy set after a local error.

The preparation button first checks cost, then queues a durable server job. Save
the accepted job in the local query cache immediately. The home computer does the
work after the phone closes the dialog. Poll queued/running jobs and show script,
review and voice phases separately, including synchronized voice sections. Keep
the progress button available while working. A failed status refresh is not proof
that generation failed: show the connection error and offer a status refresh.

On failure, show the actual sanitized provider/review reason alongside which
materials were saved. A saved script is different from an approved review and
ready audio. Reopen Script review to retry that saved review without regenerating
the lesson. Do not report generic success when review prevented narration.

Classify both the provider's allowlisted error code and error type. OpenAI can
return code `credit_balance_exhausted` with type `insufficient_quota`; this is
exhausted API credit, not a temporary request limit. Preserve that classification
through the guide writer, HTTP error and durable job. Explain that script-provider
API credit is separate from Inworld narration credit. Never expose raw upstream
messages, account identifiers or keys. A Codex-authored import can prepare the
script without a lesson-writing API purchase.

Known quota/billing failures, refusals and uncertain purchases require attention;
never silently switch providers or repurchase an unknown outcome. A review
explicitly rejected with rate_limit_exceeded may wait the provider's bounded
Retry-After interval and retry once with the same request identity. Report that
wait in progress. A failed second attempt is saved and shown to the family.

Verification should use the current LAN address with an HTTP browser, phone-size
viewport and randomUUID absent. Exercise both generation and recovery. Select
next sections whose previous work is complete; leave unfinished classes alone.
Check saved reviews and full audio coverage, and compare learner records before
and after: preparation must not create answers, sessions or completion.

Regression coverage lives in CurriculumLessonPrep, LessonPreparationBar,
test_curriculum_preparation, test_script_review and test_preparation_provider_errors.

Inworld character timings can contain multi-character fragments, particularly in
URLs. Validate the complete original text and timing arrays, then map sentence
starts only to exact measured fragment boundaries. Never interpolate times inside
a fragment or change the source text to fit it. Resume from the saved paid reply
and existing clips; do not buy replacement audio for a timestamp-reader failure.
