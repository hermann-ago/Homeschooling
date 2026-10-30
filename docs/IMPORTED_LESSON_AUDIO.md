# Importing checked lesson recordings

The host-only family route `POST /api/tutor/reader/narration/import` attaches
externally generated Inworld TTS-2 WAV recordings to an existing pinned lesson.
It does not generate a script, make a provider request, require an API key,
change the family-wide narrator, or advance learner progress.

Multipart fields identify the learner, topic, optional session, guide, exact passage
hash, voice (`Clive` / English or `Maitê` / Brazilian Portuguese), speed, and
ordered blocks. Each block supplies a starting sentence, count, and SHA-256 of
the exact joined script text. Uploads must be bounded mono 16-bit WAVs at 16 or
24 kHz. Gaps, overlaps, text changes, mismatched ownership, and incomplete
coverage are rejected.

Before a student session starts, imports must target the current, reviewed guide
for that learner/topic. When a session is supplied, its ownership and exact pinned
guide remain mandatory. Preparing audio never needs to create student progress.
Curriculum reports complete imported Inworld audio as ready and identifies the
provider; a preferred import takes priority over older provider failures.

The existing local acoustic checker verifies the actual speech outside database
transactions. Saved blocks survive retries, deterministic recording identities
avoid duplicate tracks, and the existing version-4 publisher produces the normal
activity clips and sentence timings. Original blocks and clips use ordinary
durable storage and backups. External credit consumption is not fabricated as an
app API charge: the published `cost_usd` is null.

A successfully imported recording becomes preferred only for that exact guide
text. Existing Google recordings remain available. A complete preferred recording
takes precedence over an older provider's failed-preparation notice. Previously
chosen playback voices remain user-controlled in the lesson selector.

This is an import workflow, not automatic Inworld API integration. Future
automatic preparation still uses the configured provider until a separate
provider adapter and account connection are added.

The acoustic checker accepts an English `sea` decoded as letter `C` only as a
one-word homophone at the exact independently recognized position. Source text
is unchanged; missing words and changed options continue to fail validation.

English Kiev can be decoded as KIIV/KYIV or split into KI/KEI OF. These exact
pronunciation spellings are accepted only at an existing Kiev word independently
located by the recognizer, and are recorded in alignment metadata. Source spelling,
answer choices and assessment are unchanged. Other cities, missing names and
changed option labels still fail the ordinary coverage/confidence checks.
