"""Health, the tutor credential, storage status, backups and host controls."""
from __future__ import annotations

import signal
import threading
import math
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from dependencies import context, current_device, require_host, require_family, live_context
from security.devices import Device
from security.network import is_loopback
from services.ai_budget import micros

router = APIRouter()


class LearnerNarrator(BaseModel):
    child_id: int = Field(ge=1)
    english_voice: str = Field(pattern=r'^[A-Za-z0-9_-]{10,100}$')
    portuguese_voice: str = Field(pattern=r'^[A-Za-z0-9_-]{10,100}$')


class InworldLearnerNarrator(BaseModel):
    child_id: int = Field(ge=1)
    english_voice: str | None = Field(None, min_length=1, max_length=100)
    portuguese_voice: str | None = Field(None, min_length=1, max_length=100)


class AISettingsRequest(BaseModel):
    provider: str = "openai"
    teaching_usd: float = Field(3, ge=0, le=100)
    books_usd: float = Field(2, ge=0, le=100)
    voice_usd: float = Field(2, ge=0, le=100)
    google_voice_enabled: bool = False
    voice_provider: Literal["google-gemini", "kokoro-local", "elevenlabs", "inworld"] | None = None
    inworld_enabled: bool | None = None
    inworld_voice_en: str | None = Field(None, min_length=1, max_length=100)
    inworld_voice_pt: str | None = Field(None, min_length=1, max_length=100)
    inworld_learner_voices: list[InworldLearnerNarrator] | None = Field(None, max_length=20)
    elevenlabs_enabled: bool | None = None
    elevenlabs_voice_en: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{10,100}$')
    elevenlabs_voice_pt: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{10,100}$')
    elevenlabs_learner_voices: list[LearnerNarrator] | None = Field(default=None, max_length=20)
    aligned_voice_blocks: bool | None = None
    local_voice_en: Literal["am_michael", "af_heart"] | None = None
    local_voice_pt: Literal["pf_dora", "pm_alex"] | None = None
    pilot_passed: bool = False
    monthly_generation_enabled: bool | None = None


class AIKeyRequest(BaseModel):
    provider: str
    key: str = Field(min_length=15, max_length=500)


class InworldNarratorSettings(BaseModel):
    model_config = {'extra': 'forbid'}
    english_voice: str = Field(min_length=1, max_length=100)
    portuguese_voice: str = Field(min_length=1, max_length=100)
    learners: list[InworldLearnerNarrator] = Field(max_length=20)


@router.get("/ai/status", dependencies=[Depends(require_family)])
def ai_status():
    ctx = context()
    provider, model = ctx.ai.selection()
    from tutoring import local_audio, narration_alignment, elevenlabs_audio, inworld_audio
    from tutoring.inworld_voices import learner_choices
    from services.ai_provider import PREPARATION_MODEL, PREPARATION_REASONING
    tts = ctx.config.get("tts", {})
    local = tts.get("provider", "google-gemini") == local_audio.PROVIDER
    eleven = tts.get('provider') == elevenlabs_audio.PROVIDER
    inworld = tts.get('provider') == 'inworld'
    jobs = [{"id": j["id"], "done": j["done"], "total": j["total"], "stage": j["stage"],
             "status": j["status"], "error": j["error"]} for j in ctx.store.all("book_imports")
            if j["status"] in ("failed", "waiting", "queued", "running")]
    return {"provider": provider, "model": model, "spending_policy": "tracking_only",
            "preparation_model": PREPARATION_MODEL if provider == 'openai' else model,
            "preparation_reasoning": PREPARATION_REASONING if provider == 'openai' else None,
            "keys": {p: bool(ctx.ai.key(p)) for p in ("openai", "google", "elevenlabs", "inworld")},
            "voice": {"provider": tts.get("provider", "google-gemini"),
                      "model": inworld_audio.MODEL if inworld else elevenlabs_audio.MODEL if eleven else local_audio.MODEL if local else "gemini-3.8-flash-lite-tts",
                      "voice": inworld_audio.narrator(ctx, 'en-US') if inworld else elevenlabs_audio.narrator(ctx, 'en-US') if eleven else local_audio.narrator(ctx, "en-US") if local else "Achird",
                      "enabled": tts.get('inworld_enabled', False) if inworld else tts.get('elevenlabs_enabled', False) if eleven else local_audio.available(ctx) if local else tts.get("enabled", False),
                      "inworld_enabled": bool(tts.get('inworld_enabled')),
                      "inworld_model": inworld_audio.MODEL,
                      "inworld_voice_en": inworld_audio.narrator(ctx, 'en-US'),
                      "inworld_voice_pt": inworld_audio.narrator(ctx, 'pt-BR'),
                      "inworld_learner_voices": learner_choices(ctx),
                      "elevenlabs_enabled": tts.get('elevenlabs_enabled', False),
                      "elevenlabs_voice_en": elevenlabs_audio.narrator(ctx, 'en-US'),
                      "elevenlabs_voice_pt": elevenlabs_audio.narrator(ctx, 'pt-BR'),
                      "elevenlabs_model": elevenlabs_audio.MODEL,
                      "elevenlabs_learner_voices": [{**row, 'name': (ctx.store.get('children', row['child_id']) or {}).get('name', 'Learner')}
                          for row in tts.get('elevenlabs_learner_voices', [])],
                      "google_enabled": tts.get("enabled", False), "local_available": local_audio.available(ctx),
                      "aligned_blocks": bool(tts.get('aligned_blocks')),
                      "alignment_languages": [lang for lang in narration_alignment.ASSETS if narration_alignment.available(ctx, lang)],
                      "local_voice_en": local_audio.narrator(ctx, "en-US"),
                      "local_voice_pt": local_audio.narrator(ctx, "pt-BR")},
            "pilot_passed": ctx.ai.settings.get("pilot_passed", False),
            "monthly_generation_enabled": ctx.ai.settings.get("monthly_generation_enabled", False),
            "usage": ctx.ai.ledger.summary(ctx.ai.limits), "book_jobs": jobs,
            "voice_jobs": [j for j in ctx.ai.ledger.jobs() if j["status"] not in ("ready", "ready_with_fallback")],
            "uncertain_requests": ctx.ai.ledger.requests(uncertain_only=True),
            "provider_balances": ctx.config.get("provider_balances", {})}


class ProviderBalanceCheck(BaseModel):
    balance: float = Field(ge=-1000000, le=1000000, allow_inf_nan=False)
    currency: Literal["USD", "BRL"]
    auto_reload: bool
    note: str = Field("", max_length=500)


@router.put("/ai/balances/{provider}", dependencies=[Depends(require_family), Depends(require_host)])
def save_provider_balance(provider: Literal["openai", "google"], payload: ProviderBalanceCheck):
    """Dated portal observations; never alter allowances, usage or provider billing."""
    if payload.currency != ("USD" if provider == "openai" else "BRL"):
        raise HTTPException(400, "Keep each provider balance in its original billing currency")
    ctx = context()
    checks = {**ctx.config.get("provider_balances", {}), provider: {
        **payload.model_dump(), "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": "billing_page_check"}}
    ctx.config.update(provider_balances=checks)
    return {"provider": provider, **checks[provider]}


class AIReconcileRequest(BaseModel):
    charged_usd: float = Field(ge=0, le=100)
    verified_provider_bill: bool = False


@router.put("/ai/requests/{request_id}/reconcile", dependencies=[Depends(require_family), Depends(require_host)])
def ai_reconcile(request_id: str, payload: AIReconcileRequest):
    if not payload.verified_provider_bill or not math.isfinite(payload.charged_usd):
        raise HTTPException(400, "Verify this request's actual charge in the provider bill first")
    try:
        context().ai.ledger.reconcile(request_id, micros(payload.charged_usd))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ai_status()


@router.put("/ai/settings", dependencies=[Depends(require_family), Depends(require_host)])
def ai_settings(payload: AISettingsRequest):
    if payload.provider not in ("openai", "google") or not all(math.isfinite(v) for v in
            (payload.teaching_usd, payload.books_usd, payload.voice_usd)):
        raise HTTPException(status_code=400, detail="Choose a supported provider and finite spending allowances")
    ctx = context()
    voice_settings = {**ctx.config.get("tts", {}), "enabled": payload.google_voice_enabled}
    if any(getattr(payload, k) is not None for k in ('inworld_voice_en', 'inworld_voice_pt', 'inworld_learner_voices')):
        from tutoring.inworld_voices import catalog
        try:
            voices = {v['id']: v['language'] for v in catalog(ctx)}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        pairs = [(payload.inworld_voice_en, 'en-US'), (payload.inworld_voice_pt, 'pt-BR')]
        rows = payload.inworld_learner_voices
        if rows is not None:
            if len({r.child_id for r in rows}) != len(rows) or any(not ctx.store.get('children', r.child_id) for r in rows):
                raise HTTPException(400, 'Choose each existing learner once for Inworld narrators')
            pairs += [(getattr(r, field), language) for r in rows for field, language in
                (('english_voice', 'en-US'), ('portuguese_voice', 'pt-BR'))]
            voice_settings['inworld_learner_voices'] = [r.model_dump() for r in rows]
        if any(voice and voices.get(voice) != language for voice, language in pairs):
            raise HTTPException(400, 'Choose an available Inworld narrator in the selected language')
    for field in ('inworld_enabled', 'inworld_voice_en', 'inworld_voice_pt'):
        if getattr(payload, field) is not None:
            voice_settings[field] = getattr(payload, field)
    voice_settings['inworld_model'] = 'inworld-tts-2-flash'
    if payload.elevenlabs_learner_voices is not None:
        rows = payload.elevenlabs_learner_voices
        if len({r.child_id for r in rows}) != len(rows) or any(not ctx.store.get('children', r.child_id) for r in rows):
            raise HTTPException(400, 'Choose each existing learner once for narrator settings')
        voice_settings['elevenlabs_learner_voices'] = [r.model_dump() for r in rows]
    if payload.voice_provider is not None:
        voice_settings["provider"] = payload.voice_provider
    if payload.aligned_voice_blocks is not None:
        voice_settings['aligned_blocks'] = payload.aligned_voice_blocks
    for key in ("local_voice_en", "local_voice_pt", "elevenlabs_enabled", "elevenlabs_voice_en", "elevenlabs_voice_pt"):
        if getattr(payload, key) is not None:
            voice_settings[key] = getattr(payload, key)
    ctx.config.update(ai={**ctx.ai.settings, "provider": payload.provider, "spending_policy": "tracking_only"},
                      tts=voice_settings)
    return ai_status()


@router.get('/ai/inworld/narrators', dependencies=[Depends(require_family)])
def inworld_narrators():
    from tutoring.inworld_voices import MODEL, narrator, learner_choices
    ctx = context()
    return {'provider': ctx.config.get('tts', {}).get('provider'), 'model': MODEL,
        'connected': bool(ctx.ai.key('inworld')), 'english_voice': narrator(ctx, 'en-US'),
        'portuguese_voice': narrator(ctx, 'pt-BR'), 'learners': learner_choices(ctx)}


@router.put('/ai/inworld/narrators', dependencies=[Depends(require_family)])
def save_inworld_narrators(payload: InworldNarratorSettings):
    """Family-device preferences only; no credentials, provider changes or speech."""
    from tutoring.inworld_voices import catalog
    ctx = context()
    if len({r.child_id for r in payload.learners}) != len(payload.learners) or any(
            not ctx.store.get('children', r.child_id) for r in payload.learners):
        raise HTTPException(400, 'Choose each existing learner once for narrator voices')
    try:
        voices = {v['id']: v['language'] for v in catalog(ctx)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    pairs = [(payload.english_voice, 'en-US'), (payload.portuguese_voice, 'pt-BR')]
    pairs += [(getattr(row, field), language) for row in payload.learners
        for field, language in (('english_voice', 'en-US'), ('portuguese_voice', 'pt-BR'))]
    if any(voice and voices.get(voice) != language for voice, language in pairs):
        raise HTTPException(400, 'Choose an available narrator in the selected language')
    overrides = {row['child_id']: row for row in ctx.config.get('tts', {}).get('inworld_learner_voices', [])}
    overrides.update({row.child_id: row.model_dump() for row in payload.learners})
    ctx.config.update(tts={**ctx.config.get('tts', {}), 'inworld_voice_en': payload.english_voice,
        'inworld_voice_pt': payload.portuguese_voice,
        'inworld_learner_voices': list(overrides.values())})
    return inworld_narrators()


@router.get('/ai/inworld/voices', dependencies=[Depends(require_family)])
def inworld_voices():
    from tutoring.inworld_voices import packet
    try:
        return packet(context())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/ai/voices', dependencies=[Depends(require_family)])
def configured_voices():
    if context().config.get('tts', {}).get('provider') == 'inworld':
        return inworld_voices()
    from tutoring.voice_choices import catalog
    try:
        return {'provider': 'elevenlabs', 'voices': catalog(context())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/ai/inworld/voices/{voice_id}/preview', dependencies=[Depends(require_family)])
def inworld_preview(voice_id: str):
    from tutoring.inworld_voices import preview
    try:
        return Response(preview(context(), voice_id), media_type='audio/mpeg', headers={'Cache-Control': 'private, max-age=86400'})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/ai/key", dependencies=[Depends(require_family), Depends(require_host)])
def ai_key(payload: AIKeyRequest):
    try:
        context().ai.save_key(payload.provider, payload.key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"provider": payload.provider, "configured": True}


@router.get('/ai/elevenlabs/check', dependencies=[Depends(require_family), Depends(require_host)])
def check_elevenlabs():
    """Read-only key/permission check. Never return account details or the key."""
    ctx = context()
    key = ctx.ai.key('elevenlabs')
    if not key:
        raise HTTPException(400, 'Save an ElevenLabs API key on the home server first')
    try:
        reply = ctx.ai.http.get('https://api.elevenlabs.io/v1/user', headers={'xi-api-key': key})
    except Exception:
        raise HTTPException(502, 'Could not reach ElevenLabs; no speech was requested') from None
    if not reply.is_success:
        raise HTTPException(400, f'ElevenLabs returned {reply.status_code}. Check the key and its Read User permission.')
    return {'configured': True, 'verified': True, 'speech_requested': False}


@router.get('/ai/inworld/check', dependencies=[Depends(require_family), Depends(require_host)])
def check_inworld():
    """Read-only authentication check; never synthesize audio or expose credentials."""
    ctx = context()
    key = ctx.ai.key('inworld')
    if not key:
        raise HTTPException(400, 'Save an Inworld API key on the home server first')
    try:
        reply = ctx.ai.http.get('https://api.inworld.ai/voices/v1/voices',
            params={'pageSize': 1}, headers={'Authorization': f'Basic {key}'})
    except Exception:
        raise HTTPException(502, 'Could not reach Inworld; no speech was requested') from None
    if not reply.is_success:
        raise HTTPException(400, f'Inworld returned {reply.status_code}. Check the Standard key and Voices Read permission.')
    try:
        value = reply.json()
        if not isinstance(value, dict) or not isinstance(value.get('voices'), list):
            raise ValueError('Invalid voice catalog')
    except (ValueError, TypeError):
        raise HTTPException(502, 'Inworld returned an unreadable voice catalog; no speech was requested') from None
    return {'configured': True, 'verified': True, 'speech_requested': False}


@router.get('/ai/elevenlabs/voices', dependencies=[Depends(require_family)])
def elevenlabs_voices():
    from tutoring.voice_choices import catalog
    try:
        return {'voices': catalog(context()), 'speech_requested': False}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/health")
def health():
    return {"status": "ok"}


# ── The tutor's credential ────────────────────────────────────────────────────

class AgentPairing(BaseModel):
    name: str = Field("Desktop tutor", min_length=1, max_length=60)


@router.post("/pairing/agent", dependencies=[Depends(require_host)])
def pairing_agent(payload: AgentPairing):
    """Issue the MCP bridge credential; callable only on the host computer (see launcher pair-agent)."""
    return {"token": context().devices.issue(payload.name, "tutor"), "role": "tutor"}


@router.get("/session")
def session(request: Request, device: Device = Depends(current_device)):
    client = request.client.host if request.client else None
    return {"device": {"id": device.id, "name": device.name, "role": device.role},
            "host": is_loopback(client) or client == "testclient",
            "environment": "test" if context().is_test else "live",
            "test_mode": context().is_test}


class TestModeRequest(BaseModel):
    enabled: bool
    token: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


@router.post("/test-mode", dependencies=[Depends(require_family)])
def test_mode(payload: TestModeRequest, request: Request, response: Response):
    from services.test_mode import manager, COOKIE, mode_token
    modes = manager(live_context())
    old = mode_token(request.scope)
    try:
        if payload.enabled:
            if payload.token:
                modes.get(payload.token)
                token = payload.token
            elif old != "live":
                modes.get(old)  # Never silently substitute real records for an expired test.
                token = old
            else:
                token = modes.create()
            response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/api")
        else:
            if old != "live":
                modes.end(old)
            token = None
            response.delete_cookie(COOKIE, path="/api")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"test_mode": payload.enabled, "token": token}


# ── Storage: database, Drive folder, backups ────────────────────────────────


@router.get('/network/camera', dependencies=[Depends(require_family)])
def camera_connection(request: Request):
    from security.https import certificate_info, local_names, manager, DEFAULT_PORT
    ctx = live_context()
    listener = manager(request.app, ctx)
    certificate = certificate_info(ctx.config)
    names = certificate['names'] if certificate else local_names()
    hostname = request.url.hostname
    if hostname not in names:
        hostname = next((name for name in names if name[0].isdigit() and not name.startswith('127.')), 'localhost')
    port = ctx.config.get('https', {}).get('port', DEFAULT_PORT)
    return {'enabled': bool(ctx.config.get('https', {}).get('enabled')), 'running': listener.running,
        'secure_url': f'https://{hostname}:{port}/',
        'certificate_download': '/api/network/camera/certificate' if certificate else None,
        'certificate_sha256': certificate['fingerprint'] if certificate else None,
        'certificate_expires': certificate['expires'] if certificate else None,
        'error': listener.error}


@router.post('/network/camera/enable', dependencies=[Depends(require_family), Depends(require_host)])
async def enable_camera_connection(request: Request):
    from security.https import manager, DEFAULT_PORT
    if context().is_test:
        raise HTTPException(400, 'Leave test mode to change the home server connection.')
    ctx = live_context()
    listener = manager(request.app, ctx)
    try:
        await listener.start()
        ctx.config.update(https={**ctx.config.get('https', {}), 'enabled': True,
            'port': ctx.config.get('https', {}).get('port', DEFAULT_PORT)})
    except (ValueError, OSError, RuntimeError) as exc:
        listener.error = str(exc)
        raise HTTPException(400, str(exc)) from None
    return camera_connection(request)


@router.get('/network/camera/certificate', dependencies=[Depends(require_family)])
def download_home_certificate():
    from security.https import files
    path = files(live_context().config)['download']
    if not path.exists():
        raise HTTPException(404, 'Enable the secure camera connection on the home computer first.')
    return FileResponse(path, media_type='application/pkix-cert', filename=path.name,
        headers={'Cache-Control': 'no-store'})

@router.get("/storage/status")
def storage_status():
    """Where data lives and whether the synced Drive folder is reachable."""
    return context().status()


@router.get("/sync/operations/{operation_id}")
def operation(operation_id: str):
    return {"operation_id": operation_id, "state": context().store.operation_state(operation_id) or "unknown"}


class DriveFolderRequest(BaseModel):
    path: str = Field(..., min_length=3, max_length=400)


@router.post("/storage/drive-folder", dependencies=[Depends(require_family), Depends(require_host)])
def set_drive_folder(payload: DriveFolderRequest):
    """Point the server at the synced Homeschooling folder (host computer only)."""
    try:
        return context().set_drive_folder(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/storage/backup", dependencies=[Depends(require_family)])
def backup_now():
    return context().backup_now()


@router.post("/storage/export", dependencies=[Depends(require_family)])
def export_now():
    return {"path": context().export_now()}


# ── Host process control ────────────────────────────────────────────────────

class ShutdownRequest(BaseModel):
    instance_token: str


@router.post("/host/shutdown", dependencies=[Depends(require_host)])
def shutdown(payload: ShutdownRequest):
    """Graceful stop requested by the launcher that recorded this exact instance."""
    if payload.instance_token != context().instance_token:
        raise HTTPException(status_code=403, detail="Not this server instance")
    # raise_signal runs uvicorn's own handler, so shutdown is graceful on Windows too.
    threading.Timer(0.5, lambda: signal.raise_signal(signal.SIGINT)).start()
    return {"stopping": True}
