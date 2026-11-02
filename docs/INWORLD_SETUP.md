# Connect an Inworld credential

Create the credential yourself in https://platform.inworld.ai:
Manage → API Keys → Generate new key → Standard → Generate.
Copy the complete Basic (Base64) credential as supplied, without the word Basic.
Do not encode it a second time. Standard credentials support direct TTS;
voice-management and Router write permissions are not needed for synthesis.
See https://docs.inworld.ai/quickstart-tts for the current provider instructions.

On the home server computer, open
http://localhost:8000/settings#ai-voice and find Teaching and voice.
Under Save a key on this home server, choose Inworld, paste the credential into
the password field, and click Save key securely. The value clears after saving.
Only the home computer can save it; family/tutor devices cannot retrieve it.
Windows protects it with the existing user-bound DPAPI secret store. It is
not saved in config.json or returned by the status API. INWORLD_API_KEY is also
supported for an explicitly configured server environment.

Choose Check Inworld connection to verify it with a read-only voice-catalog
request. This checks authentication and Voices Read access without generating
speech, exposing the key, or changing the narrator. No Router/Voices write
permission is required. The same host-only check is GET /api/ai/inworld/check.

Saving a credential does not request speech or change the current narrator.
Never paste credentials into chat or put them in client code or lesson files.

Select **Inworld Flash** as the narration provider, enable it, and save settings.
The app fixes the synthesis model to `inworld-tts-2-flash`; it never upgrades to
the more expensive model. Flash speech is charged by characters, not LLM tokens.
The app tracks the On-Demand list-price equivalent ($15 per million characters),
without enforcing a local allowance. Inworld credits and the actual bill apply.

Open **Settings → Narrator voices** near the top of the page, or go directly to
`/settings#narrator-voices`. This section and its sample players are available on
family phones and tablets as well as the home computer. Choose the family
narrators, optionally expand **Separate voices for each child**, and save with
**Save narrator choices**. Sample buttons select the family narrator; a child
with an explicit choice retains that separate narrator. Saving preferences
does not generate recordings or change the provider/account connection.

During a lesson, **Narrator & samples** beside lesson preparation opens voices
in the lesson's language. **Use narrator for this lesson** saves an override
for that lesson. **Family & child narrators** opens the family Settings section.

The voice picker includes five curated male and five female American-English
voices, plus all three currently available native Brazilian male voices and
five Brazilian female voices. Inworld supplies no popularity ranking, so the
shortlist is labeled curated. Built-in Flash previews use the unbilled preview
endpoint and are cached; listening does not generate a paid lesson recording.
Family choices apply to both children unless a child has a separate selection.
Individual lessons can also select a narrator in Lesson & voice.

Family devices may read/update `/api/ai/inworld/narrators`. This narrowly scoped
endpoint accepts narrator IDs and child overrides only, validates ownership and
language, and cannot change keys, models, provider selection or billing settings.
Tutor credentials cannot use it. Test mode can browse samples but cannot save
real family preferences. Provider/key settings remain host-only.

After the final script is approved, prepare voice from Lesson & voice or the
curriculum preparation controls. Existing exact speech blocks are reused.
Replies are saved before synchronization, and unknown purchases are never
resent automatically. Inworld's empty timestamp markers, including markers
between synthesis chunks and at the audio tail, are removed from all three timing
arrays together. Real character timestamps and the script remain unchanged.
Invalid timings use installed local alignment;
the paid reply remains saved if alignment needs repair.

Official references: https://docs.inworld.ai/tts/tts-models,
https://docs.inworld.ai/api-reference/voiceAPI/voiceservice/get-voice-preview,
https://inworld.ai/pricing.
