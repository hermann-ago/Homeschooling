"""Prepare pinned lesson recordings outside lesson locks, using the existing ledger."""
import hashlib
import threading

from . import audio, narration
from .preparation_limits import DEFAULT_AUDIO_CAP_USD

_lock = threading.Lock()
_scheduled = set()


def status(ctx, guide_id, *, all_jobs=None,provider=None):
    provider = provider or ctx.config.get("tts", {}).get("provider", "google-gemini")
    all_jobs = ctx.ai.ledger.jobs() if all_jobs is None else all_jobs
    jobs = [j for j in all_jobs if j.get("automatic_guide_id") == guide_id and j.get("provider") == provider]
    guide = ctx.store.get("guides", guide_id)
    recordings = [j for j in all_jobs if guide and j.get("passage_sha256") == guide["guide_sha256"] and j.get("provider") == provider]
    if guide and provider in ('elevenlabs', 'inworld'):
        if provider == 'inworld':
            from .inworld_voices import selected, narrator
        else:
            from .voice_choices import selected
            from .elevenlabs_audio import narrator
        topic = ctx.store.get('topics', guide['topic_id'])
        subject = ctx.store.get('subjects', topic['subject_id'])
        voice = selected(ctx.store, topic['id']) or narrator(ctx, audio.language_for(subject['name']), subject['child_id'])
        jobs = [j for j in jobs if j.get('voice') == voice]
        recordings = [j for j in recordings if j.get('voice') == voice]
    if not jobs and not recordings:
        return None
    job = jobs[-1] if jobs else {**recordings[-1], 'track_id':recordings[-1]['id']}
    if recordings and recordings[-1]["status"] in ("running", "aligning", "ready", "ready_with_fallback", "alignment_review", "paused"):
        job = {**recordings[-1], "track_id": recordings[-1]["id"]}
    result={k: job.get(k) for k in ("status", "error", "provider", "track_id", "completed_parts", "parts")}
    result['alignment']='local' if job.get('strategy') else None
    result['missing_retry_used']=bool(job.get('retry_requests'))
    # Raw recordings survive a timing failure. Distinguish them from blocks
    # already synchronized; zero synchronized does not mean nothing was saved.
    result['recorded_parts']=sum(bool(p) and not p.get('fallback') for rid in job.get('request_ids',[])
        for p in [ctx.ai.ledger.part(rid)]) if job.get('strategy') else None
    return result


def schedule(ctx, topic, guide, voice, rate, tasks):
    """A saved guide is the identity. Re-entry never blindly retries failed purchases."""
    tts = ctx.config.get("tts", {})
    enabled = tts.get('inworld_enabled', False) if tts.get('provider') == 'inworld' else tts.get('elevenlabs_enabled', False) if tts.get('provider') == 'elevenlabs' else tts.get('enabled')
    if not enabled or tts.get("provider", "google-gemini") not in ("google-gemini", "kokoro-local", "elevenlabs", "inworld"):
        return
    from .script_review import require_audio
    try:require_audio(ctx,guide)
    except ValueError:return
    key = "automatic-voice-" + hashlib.sha256(str((guide["guide_id"], tts.get("provider"), voice, rate)).encode()).hexdigest()
    marker = (id(ctx), key)
    with _lock:
        previous = next((j for j in ctx.ai.ledger.jobs() if j["id"] == key), None)
        if marker in _scheduled or previous and previous["status"] in ("ready", "ready_with_fallback", "paused", "failed"):
            return
        job = {"automatic_guide_id": guide["guide_id"], "topic_id": topic["id"], "voice": voice, "provider": tts.get("provider", "google-gemini"),
               "status": "queued", "error": None, "track_id": None}
        ctx.ai.ledger.save_job(key, job)
        _scheduled.add(marker)
    def run():
        try:
            job.update(status="running")
            ctx.ai.ledger.save_job(key, job)
            subject = ctx.store.get("subjects", topic["subject_id"])
            result = narration.generate(ctx, topic, guide, voice=voice, rate=rate, language=audio.language_for(subject["name"]),maximum_usd=DEFAULT_AUDIO_CAP_USD)
            job.update(status=result.get("job_status", "ready"), track_id=result["track_id"])
        except Exception as exc:
            # The original recording job retains reservations and completed parts.
            job.update(status="paused", error=str(exc))
        finally:
            ctx.ai.ledger.save_job(key, job)
            with _lock:
                _scheduled.discard(marker)
    def launch():
        # FastAPI waits for BackgroundTasks before our response receipt is sent.
        # A provider's quota backoff must not hold lesson creation/start open.
        try:
            threading.Thread(target=run, name="lesson-voice-" + guide["guide_id"], daemon=True).start()
        except Exception as exc:
            job.update(status="paused", error=str(exc))
            ctx.ai.ledger.save_job(key, job)
            with _lock:
                _scheduled.discard(marker)
    tasks.add_task(launch)
