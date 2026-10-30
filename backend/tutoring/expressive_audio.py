"""Cached Gemini WAV passages. Passage boundaries are known; sentence timings are never fabricated."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import threading
import time
import wave
from datetime import datetime, timezone

from services.ai_budget import BudgetError, token_cost
from services.ai_provider import ContentRejectedError, RateLimitError
from storage import layout

MODEL = "gemini-3.8-flash-lite-tts"
PROVIDER = "google-gemini"
STYLE = "A friendly, patient teacher. Speak clearly at a calm, measured pace with natural expression."
MAX_AUDIO_TOKENS = 6000
_lock = threading.RLock()


def chunks(sentences, boundaries=()):
    """Preserve sentence text and stop at paragraphs, voice-role boundaries and activities."""
    result, current, first = [], [], 0
    for i, sentence in enumerate(sentences):
        previous = sentences[i - 1] if i else None
        # Old guides label every sentence as a paragraph; keep their same-role runs smooth.
        paragraph_changed = previous and sentence.get("paragraphIndex") != previous.get("paragraphIndex")
        if sentence.get("kind") is not None:
            paragraph_changed = previous and (sentence.get("kind") != previous.get("kind") or (
                sentence.get("paragraphBoundary") and previous.get("paragraphBoundary") and paragraph_changed))
        if current and (i in boundaries or paragraph_changed or len(" ".join(current)) + len(sentence["text"]) > 1500):
            result.append((first, i - first, " ".join(current)))
            current, first = [], i
        current.append(sentence["text"])
        if sentence.get("pause_after"):
            result.append((first, i - first + 1, " ".join(current)))
            current, first = [], i + 1
    if current:
        result.append((first, len(sentences) - first, " ".join(current)))
    return result


def rates(moment=None):
    return (0.5, 6) if (moment or datetime.now(timezone.utc)).date().isoformat() < "2027-01-01" else (1, 12)


def body(text, voice, language, rate):
    style = STYLE + f" Use {'Brazilian Portuguese' if language == 'pt-BR' else 'American English'}. Pace factor: {rate}."
    return {"model": MODEL, "input": [{"type": "user_input", "content": [
        {"type": "text", "text": text, "annotations": [{"type": "speech_metadata", "style": style}]}]}],
        "response_format": {"type": "audio", "mime_type": "audio/wav"},
        "generation_config": {"speech_config": [{"voice": voice}], "max_output_tokens": min(MAX_AUDIO_TOKENS, max(1500, len(text.encode()) * 6))},
        "store": False}


def maximum_cost(payload):
    # UTF-8 bytes plus an overhead allowance are a conservative text token bound.
    count = len(json.dumps(payload, ensure_ascii=False).encode()) + 256
    if count > 8192:
        raise ValueError("A narration passage is too long. Split it before generating audio.")
    return token_cost(count, payload["generation_config"]["max_output_tokens"], *rates())


def part_key(text, voice, language, rate):
    return "voice:content:" + hashlib.sha256(json.dumps(
        [text, PROVIDER, MODEL, voice, language, rate, STYLE], ensure_ascii=False).encode()).hexdigest()


def older_recordings(ctx, voice, language, rate):
    """Read legacy completed manifests; identical saved passages remain reusable."""
    sources = {}
    for row in ctx.store.all("guides"):
        try:
            sources[row["guide_sha256"]] = json.loads(ctx.file_bytes(row["guide_path"]))["sentences"]
        except (ValueError, OSError):
            continue
    for row in ctx.store.all("passages"):
        try:
            from .passages import split_sentences
            sources[row["passage_sha256"]] = split_sentences(json.loads(ctx.file_bytes(row["passage_path"]))["passage"])
        except (ValueError, OSError, KeyError):
            continue
    attempts = {}
    for source_hash, sentences in sources.items():
        sections = chunks(sentences)
        old_key = hashlib.sha256(json.dumps([source_hash, "lesson", PROVIDER, MODEL, voice, language, rate, STYLE,
                                            [(first, count) for first, count, _ in sections], 3]).encode()).hexdigest()
        for i, (_, _, text) in enumerate(sections):
            rid = f"voice:{old_key}:{i}"
            if ctx.ai.ledger.request_state(rid) not in (None, "rejected"):
                attempts[part_key(text, voice, language, rate)] = rid
    found = {}
    for row in ctx.store.all("audio_tracks"):
        if row["provider"] != PROVIDER or row["voice"] != voice or row["speaking_rate"] != rate or row["status"] != "ready":
            continue
        try:
            manifest = json.loads(ctx.file_bytes(row["manifest_path"]))
            sentences = sources.get(row["passage_sha256"])
            if not sentences or any(manifest.get(k) != v for k, v in {"model": MODEL, "language": language, "style": STYLE}.items()):
                continue
            for track in manifest["tracks"]:
                first, count = track["startSentence"], track["sentenceCount"]
                text = " ".join(s["text"] for s in sentences[first:first + count])
                found[part_key(text, voice, language, rate)] = track
        except (ValueError, OSError, KeyError):
            continue
    return found, attempts


def generate(ctx, topic, passage, *, voice="Achird", rate=0.9, language="en-US", dry_run=False, purpose="lesson", maximum_usd=None):
    if dry_run:
        return _generate(ctx, topic, passage, voice=voice, rate=rate, language=language, dry_run=True, purpose=purpose, maximum_usd=maximum_usd)
    with _lock:  # same passage requested by two devices is generated once
        try:
            return _generate(ctx, topic, passage, voice=voice, rate=rate, language=language, dry_run=dry_run, purpose=purpose, maximum_usd=maximum_usd)
        except Exception as exc:
            for job in ctx.ai.ledger.jobs():
                if job.get("status") == "running" and job.get("provider") == PROVIDER:
                    job.update(status="paused", error=str(exc), cost_usd=ctx.ai.ledger.voice_cost(job["id"]))
                    ctx.ai.ledger.save_job(job["id"], job)
            raise


def _generate(ctx, topic, passage, *, voice, rate, language, dry_run, purpose, maximum_usd):
    sentences = passage["sentences"]
    if not sentences:
        raise ValueError("This lesson has no text to narrate")
    sections = chunks(sentences, {a["start_sentence"] for a in passage.get("activities", []) if a.get("start_sentence") is not None})
    key = hashlib.sha256(json.dumps([passage["passage_sha256"], purpose, PROVIDER, MODEL, voice, language, rate, STYLE,
                                    [(first, count) for first, count, _ in sections], 3]).encode()).hexdigest()
    existing = ctx.store.get("audio_tracks", key)
    if existing and existing["status"] == "ready":
        from .audio import validate_manifest
        manifest = json.loads(ctx.file_bytes(existing["manifest_path"]))
        valid, _ = validate_manifest(manifest, passage["passage_sha256"], len(sentences))
        if valid:
            for part in manifest["tracks"]:
                if not part.get("fallback"):
                    ctx.file_bytes(part["path"], part["sha256"])
            return {"track_id": key, "reused": True, "characters": 0, "estimated_cost_usd": 0,
                    "parts": len(manifest["tracks"]), "completed_parts": len(manifest["tracks"]),
                    "allowed": True, "job_status": manifest.get("job_status", "ready"), "fallback_parts": sum(bool(p.get("fallback")) for p in manifest["tracks"]), "provider": PROVIDER, "model": MODEL}
    ledger = ctx.ai.ledger
    payloads = [body(text, voice, language, rate) for _, _, text in sections]
    legacy, previous_attempts = older_recordings(ctx, voice, language, rate)
    ids = [part_key(text, voice, language, rate) for _, _, text in sections]
    # Keep an old in-flight identity so introducing content caching cannot retry it.
    ids = [f"voice:{key}:{i}" if ledger.request_state(f"voice:{key}:{i}") else rid for i, rid in enumerate(ids)]
    ids = [previous_attempts.get(rid, rid) if not ledger.part(rid) else rid for rid in ids]
    saved_parts = [ledger.part(rid) or legacy.get(part_key(text, voice, language, rate)) for rid, (_, _, text) in zip(ids, sections)]
    missing = [i for i, saved in enumerate(saved_parts) if not saved]
    unique_missing = {ids[i]: i for i in missing}
    upper = sum(maximum_cost(payloads[i]) for i in unique_missing.values()) / 1_000_000
    budget = ledger.summary(ctx.ai.limits)["categories"]["voice"]
    previous = next((j for j in ledger.jobs() if j["id"] == key), {})
    scope_id = previous.get("generation_scope_id")
    scope = ledger.scope_summary(scope_id) if scope_id else None
    if maximum_usd is not None and not scope_id:
        scope_id = "narration-" + key
        scope = {"maximum_usd": None, "remaining_usd": None, "used_usd": 0}
    remaining = None
    enabled = ctx.config.get("tts", {}).get("enabled", False)
    estimate = {"track_id": key, "reused": False, "characters": sum(len(t) for _, _, t in sections),
                "parts": len(sections), "completed_parts": len(sections) - len(missing),
                "passage_ranges": [{"first": first, "count": count} for first, count, _ in sections],
                "estimated_cost_usd": upper, "remaining_usd": remaining, "job_limit_usd": scope["maximum_usd"] if scope else None,
                "monthly_limit_usd": budget["limit_usd"], "voice": voice, "rate": rate, "language": language, "provider": PROVIDER, "model": MODEL,
                "tracking_only": True, "allowed": not missing or enabled,
                "job_status": "cached_parts" if not missing else "paused" if not enabled else "partial" if len(missing) < len(sections) else "waiting"}
    if dry_run:
        return {**estimate, "dry_run": True, "reason": None if enabled or not missing else "A parent must confirm Google billing is restored in Settings."}
    if not enabled and missing:
        raise BudgetError("Google voice is paused. Restore its prepaid balance and spending cap, then enable voice in host Settings. Saved recordings and device voice still work.")
    key_secret = ctx.ai.key("google")
    if not key_secret and missing:
        raise ValueError("The Google API key is missing on the home server")
    if scope_id and not previous.get("generation_scope_id"):
        ledger.configure_scope(scope_id, round(maximum_usd * 1_000_000), category="voice")
    requests = previous.get("request_ids", [f"voice:{key}:{i}" for i in range(len(sections)) if ledger.request_state(f"voice:{key}:{i}")])
    job = {"topic_id": topic["id"], "purpose": purpose, "provider": PROVIDER, "model": MODEL,
           "passage_sha256": passage["passage_sha256"], "voice": voice, "rate": rate,
           "status": "running", "parts": len(sections), "completed_parts": len(sections) - len(missing),
           "ranges": estimate["passage_ranges"], "cost_usd": ledger.voice_cost(key), "error": None, "request_ids": requests,
           "generation_scope_id": scope_id}
    ledger.save_job(key, job)
    folder = layout.for_topic(ctx.store, topic["id"], layout.AUDIO)
    tracks = []
    for i, ((first, count, text), payload) in enumerate(zip(sections, payloads)):
        part_id = ids[i]
        saved = ledger.part(part_id) or saved_parts[i]
        if saved:
            if not saved.get("fallback"):
                ctx.file_bytes(saved["path"], saved["sha256"])
            tracks.append({**saved, "startSentence": first, "sentenceCount": count})
            continue
        if ledger.request_state(part_id) in (None, "rejected") and part_id not in requests:
            requests.append(part_id)
            ledger.save_job(key, job)
        try:
            for attempt in range(3):
                ledger.reserve(part_id, "voice", maximum_cost(payload), ctx.ai.limits,
                               provider=PROVIDER, model=MODEL, operation="narration", scope_id=scope_id)
                try:
                    result = ctx.ai._post("https://generativelanguage.googleapis.com/v1beta/interactions",
                                          {"x-goog-api-key": key_secret}, payload, part_id)
                    break
                except RateLimitError as exc:
                    if attempt == 2:
                        raise
                    # Only an explicit refusal releases the reservation. Unknown
                    # outcomes never enter this retry path. No lesson lock is held.
                    job.update(error="Google rate limit: waiting before resuming saved passages.")
                    ledger.save_job(key, job)
                    time.sleep(exc.retry_after)
            job.update(error=None)
            usage = result.get("usage") or {}
            inp, out = usage.get("total_input_tokens"), usage.get("total_output_tokens")
            if isinstance(inp, int) and isinstance(out, int) and min(inp, out) >= 0:
                ledger.settle(part_id, token_cost(inp, out, *rates()), usage)
            else:
                ledger.mark(part_id, "uncertain")
            if result.get("status") != "completed":
                raise ValueError("The voice response was incomplete; completed passages remain saved.")
            output = result.get("output_audio")
            if not output:
                output = next((c for step in result.get("steps", []) if step.get("type") == "model_output"
                               for c in step.get("content", []) if c.get("type") == "audio"), None)
            if not output or output.get("mime_type", "audio/wav") != "audio/wav":
                raise ValueError("Google did not return a WAV recording")
            data = base64.b64decode(output["data"], validate=True)
            with wave.open(io.BytesIO(data)) as wav:
                duration = wav.getnframes() / wav.getframerate()
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not 0 < duration <= MAX_AUDIO_TOKENS / 25 + 1:
                    raise ValueError("The recording format or duration is invalid")
            with ctx.store.transaction(kind="tutor.audio_part") as tx:
                path, sha = tx.add_blob(data, folder, f"narration-{hashlib.sha256(part_id.encode()).hexdigest()[:24]}.wav", "audio/wav")
            saved = {"path": path, "sha256": sha, "mime": "audio/wav", "startSentence": first,
                     "sentenceCount": count, "duration": duration, "timing": "passage"}
            ledger.save_part(part_id, saved)
            job.update(completed_parts=sum(bool(ledger.part(rid) or saved_parts[j]) for j, rid in enumerate(ids)), cost_usd=ledger.voice_cost(key))
            ledger.save_job(key, job)
            tracks.append(saved)
        except ContentRejectedError as exc:
            # A definite content refusal is saved. Do not resend it or alter the
            # book wording to evade the provider; device speech reads it locally.
            saved = {"fallback": True, "reason": str(exc), "startSentence": first,
                     "sentenceCount": count, "duration": 0, "timing": "device"}
            ledger.save_part(part_id, saved)
            tracks.append(saved)
            job.update(completed_parts=len(tracks), cost_usd=ledger.voice_cost(key))
            ledger.save_job(key, job)
        except Exception:
            # _post records rejected/uncertain requests. A successful but unusable audio
            # response stays counted and is not regenerated automatically.
            raise
    fallback_parts = sum(bool(t.get("fallback")) for t in tracks)
    ready_status = "ready_with_fallback" if fallback_parts else "ready"
    manifest = {"version": 3, "cacheKey": key, "provider": PROVIDER, "model": MODEL, "voice": voice,
                "language": language, "style": STYLE, "speakingRate": rate,
                "passageHash": passage["passage_sha256"], "sentenceCount": len(sentences),
                "characterCount": estimate["characters"], "timing": "passage", "tracks": tracks,
                "cost_usd": ledger.voice_cost(key), "job_status": ready_status, "part_cache": "exact-text-v1", "fallback_parts": fallback_parts}
    with ctx.store.transaction(kind="tutor.audio_manifest") as tx:
        path, _ = tx.add_blob(json.dumps(manifest).encode(), folder, f"narration-{key[:24]}-manifest.json", "application/json")
        values = {"topic_id": topic["id"], "passage_sha256": passage["passage_sha256"], "provider": PROVIDER,
                  "voice": voice, "speaking_rate": rate, "manifest_path": path, "status": "ready",
                  "characters": estimate["characters"], "sentence_count": len(sentences), "timing": "passage",
                  "note": "feedback:audio" if purpose == "feedback" else None}
        if existing:
            tx.update("audio_tracks", key, values)
        else:
            tx.insert("audio_tracks", {"id": key, **values})
    job.update(status=ready_status, completed_parts=len(sections), fallback_parts=fallback_parts, cost_usd=ledger.voice_cost(key))
    ledger.save_job(key, job)
    return {**estimate, "completed_parts": len(tracks), "allowed": True, "job_status": ready_status, "fallback_parts": fallback_parts, "cost_usd": job["cost_usd"]}
