"""Offline, exact-text Kokoro recordings. No provider request or spending reservation."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import threading
import wave

from storage import layout
from .expressive_audio import chunks

PROVIDER = "kokoro-local"
MODEL = "kokoro-v1.0"
ASSETS = {
    "kokoro-v1.0.onnx": "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}
VOICES = {"en-US": ("am_michael", "af_heart"), "pt-BR": ("pf_dora", "pm_alex")}
STYLE = "kokoro-onnx-0.6.1;espeakng-loader-0.2.4;trim;sentence-pause=0.25;clause-pause=0.1;pcm16-v1"
_lock = threading.RLock()
_engines = {}


def folder(ctx):
    host = getattr(ctx, "live", None) or ctx
    return host.config.dir / "models" / MODEL


def available(ctx):
    return (importlib.util.find_spec("kokoro_onnx") is not None
            and all((folder(ctx) / name).is_file() for name in ASSETS))


def narrator(ctx, language):
    if language not in VOICES:
        raise ValueError("Local narration supports English and Brazilian Portuguese")
    return ctx.config.get("tts", {}).get("local_voice_pt" if language == "pt-BR" else "local_voice_en", VOICES[language][0])


def _engine(ctx):
    root = folder(ctx).resolve()
    if root not in _engines:
        if not available(ctx):
            raise ValueError("Local voice needs its model installed on the home computer. Saved recordings still play.")
        for name, expected in ASSETS.items():
            with (root / name).open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                    raise ValueError("The local voice model failed its integrity check. Reinstall the original model.")
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(root / "kokoro-v1.0.onnx"), sess_options=options,
                                       providers=["CPUExecutionProvider"])
        _engines[root] = Kokoro.from_session(session, str(root / "voices-v1.0.bin"))
    return _engines[root]


def render(ctx, text, voice, language, rate):
    import numpy as np
    samples, sample_rate = _engine(ctx).create(text, voice=voice, speed=rate,
        lang="pt-br" if language == "pt-BR" else "en-us", trim=True, sentence_pause=.25, clause_pause=.1)
    if sample_rate != 24000 or not len(samples) or not np.isfinite(samples).all():
        raise ValueError("The local narrator returned an invalid recording")
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
        wav.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return data.getvalue()


def part_key(text, voice, language, rate):
    identity = [text, PROVIDER, MODEL, ASSETS, voice, language, rate, STYLE]
    return "voice:local:" + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def generate(ctx, topic, passage, *, voice=None, rate=.9, language="en-US", dry_run=False,
             purpose="lesson", maximum_usd=None):
    voice = voice or narrator(ctx, language)
    if voice not in VOICES.get(language, ()) or not math.isfinite(rate) or not .5 <= rate <= 2:
        raise ValueError("Choose a local voice in the lesson language and a speed between 0.5 and 2")
    if not passage["sentences"]:
        raise ValueError("This lesson has no text to narrate")
    with _lock:  # Multiple devices share one CPU worker and immutable part identities.
        return _generate(ctx, topic, passage, voice, rate, language, dry_run, purpose)


def _generate(ctx, topic, passage, voice, rate, language, dry_run, purpose):
    from .audio import validate_manifest
    sections = chunks(passage["sentences"])
    ids = [part_key(text, voice, language, rate) for _, _, text in sections]
    key = hashlib.sha256(json.dumps([passage["passage_sha256"], purpose, ids,
                                    [(first, count) for first, count, _ in sections], 3]).encode()).hexdigest()
    existing = ctx.store.get("audio_tracks", key)
    estimate = {"track_id": key, "provider": PROVIDER, "model": MODEL, "voice": voice,
                "rate": rate, "language": language, "estimated_cost_usd": 0, "cost_usd": 0,
                "characters": sum(len(text) for _, _, text in sections), "parts": len(sections),
                "passage_ranges": [{"first": first, "count": count} for first, count, _ in sections],
                "job_limit_usd": None, "fallback_parts": 0}
    if existing and existing["status"] == "ready":
        manifest = json.loads(ctx.file_bytes(existing["manifest_path"]))
        valid, _ = validate_manifest(manifest, passage["passage_sha256"], len(passage["sentences"]))
        if valid:
            for part in manifest["tracks"]:
                ctx.file_bytes(part["path"], part["sha256"])
            return {**estimate, "reused": True, "allowed": True, "job_status": "ready",
                    "completed_parts": len(sections), "dry_run": dry_run}
    ledger = ctx.ai.ledger
    saved = [ledger.part(identity) for identity in ids]
    missing = sum(part is None for part in saved)
    reason = None if not missing or available(ctx) else "Install the local voice on the home computer first. Saved recordings still play."
    estimate.update(reused=False, completed_parts=len(sections) - missing, allowed=reason is None,
                    reason=reason, job_status="cached_parts" if not missing else "waiting" if reason is None else "paused")
    if dry_run:
        return {**estimate, "dry_run": True}
    if reason:
        raise ValueError(reason)
    job = {"topic_id": topic["id"], "purpose": purpose, "provider": PROVIDER, "model": MODEL,
           "status": "running", "parts": len(sections), "completed_parts": len(sections) - missing,
           "ranges": estimate["passage_ranges"], "cost_usd": 0, "error": None, "request_ids": []}
    ledger.save_job(key, job)
    target = layout.for_topic(ctx.store, topic["id"], layout.AUDIO)
    tracks = []
    try:
        for (first, count, text), identity in zip(sections, ids):
            part = ledger.part(identity)
            if part:
                ctx.file_bytes(part["path"], part["sha256"])
            else:
                # Inference is outside the database transaction. Each finished part is durable.
                data = render(ctx, text, voice, language, rate)
                with wave.open(io.BytesIO(data)) as wav:
                    duration = wav.getnframes() / wav.getframerate()
                    if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not 0 < duration <= 600:
                        raise ValueError("The local recording format or duration is invalid")
                with ctx.store.transaction(kind="tutor.audio_part") as tx:
                    path, sha = tx.add_blob(data, target, f"narration-{hashlib.sha256(identity.encode()).hexdigest()[:24]}.wav", "audio/wav")
                part = {"path": path, "sha256": sha, "mime": "audio/wav", "duration": duration, "timing": "passage"}
                ledger.save_part(identity, part)
            tracks.append({**part, "startSentence": first, "sentenceCount": count})
            job.update(completed_parts=sum(ledger.part(identity) is not None for identity in ids))
            ledger.save_job(key, job)
        manifest = {"version": 3, "cacheKey": key, "provider": PROVIDER, "model": MODEL,
                    "voice": voice, "language": language, "speakingRate": rate, "style": STYLE,
                    "passageHash": passage["passage_sha256"], "sentenceCount": len(passage["sentences"]),
                    "characterCount": estimate["characters"], "timing": "passage", "tracks": tracks,
                    "cost_usd": 0, "job_status": "ready", "fallback_parts": 0, "part_cache": "exact-text-v1"}
        with ctx.store.transaction(kind="tutor.audio_manifest") as tx:
            path, _ = tx.add_blob(json.dumps(manifest).encode(), target, f"narration-{key[:24]}-manifest.json", "application/json")
            values = {"topic_id": topic["id"], "passage_sha256": passage["passage_sha256"], "provider": PROVIDER,
                      "voice": voice, "speaking_rate": rate, "manifest_path": path, "status": "ready",
                      "characters": estimate["characters"], "sentence_count": len(passage["sentences"]),
                      "timing": "passage", "note": "feedback:audio" if purpose == "feedback" else None}
            if existing:
                tx.update("audio_tracks", key, values)
            else:
                tx.insert("audio_tracks", {"id": key, **values})
        job.update(status="ready", completed_parts=len(sections))
        ledger.save_job(key, job)
        return {**estimate, "allowed": True, "completed_parts": len(sections), "job_status": "ready"}
    except Exception as exc:
        job.update(status="paused", error="Local voice stopped. Completed passages are saved; retry from this lesson.")
        ledger.save_job(key, job)
        raise ValueError(job["error"]) from exc
