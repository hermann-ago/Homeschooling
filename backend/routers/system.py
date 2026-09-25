"""Pairing, Google connection, synchronisation and host controls."""
from __future__ import annotations

import json
import os
import signal
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from dependencies import context, current_device, require_host, require_member, require_parent
from security.devices import Device
from security.network import is_loopback
from storage.gateway import AuthorizationRequired, GoogleUnavailable

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


# ── Pairing ──────────────────────────────────────────────────────────────────

class PairingRequest(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=60)
    role: str = Field(..., pattern="^(parent|learner)$")


class PairingPoll(BaseModel):
    request_id: str
    poll_secret: str


class PairingApproval(BaseModel):
    request_id: str
    code: str = Field(..., pattern=r"^\d{6}$")
    role: str | None = Field(None, pattern="^(parent|learner)$")


@router.post("/pairing/request")
def pairing_request(payload: PairingRequest):
    try:
        return context().devices.request(payload.device_name, payload.role)
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/pairing/poll")
def pairing_poll(payload: PairingPoll):
    return context().devices.poll(payload.request_id, payload.poll_secret)


@router.get("/pairing/waiting", dependencies=[Depends(require_host)])
def pairing_waiting():
    """Codes waiting for approval, visible only on the host computer."""
    return context().devices.waiting()


@router.post("/pairing/approve", dependencies=[Depends(require_host)])
def pairing_approve(payload: PairingApproval):
    try:
        return context().devices.approve(payload.request_id, payload.code, payload.role)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/pairing/deny/{request_id}", dependencies=[Depends(require_host)])
def pairing_deny(request_id: str):
    context().devices.deny(request_id)
    return {"status": "denied"}


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
            "host": is_loopback(client) or client == "testclient"}


@router.get("/devices", dependencies=[Depends(require_parent)])
def devices():
    return context().devices.list()


@router.delete("/devices/{device_id}", status_code=204, dependencies=[Depends(require_parent)])
def revoke_device(device_id: str):
    try:
        context().devices.revoke(device_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Google connection (host computer only) ──────────────────────────────────

@router.get("/google/status", dependencies=[Depends(require_member)])
def google_status():
    return context().google_status()


@router.post("/google/client", dependencies=[Depends(require_parent), Depends(require_host)])
async def google_client(file: UploadFile):
    try:
        context().auth.save_client(json.loads(await file.read(65_536)))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return context().google_status()


@router.post("/google/connect", dependencies=[Depends(require_parent), Depends(require_host)])
def google_connect(request: Request):
    """Begin Google authorization in the host computer's browser (loopback redirect)."""
    port = request.url.port or context().config.get("port")
    try:
        url = context().auth.start(f"http://127.0.0.1:{port}/api/google/oauth/callback")
    except AuthorizationRequired as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"authorization_url": url}


@router.get("/google/oauth/callback", dependencies=[Depends(require_host)], response_class=HTMLResponse)
def google_callback(state: str = Query(...), code: str | None = Query(None), error: str | None = Query(None)):
    if error or not code:
        return HTMLResponse(f"<p>Google authorization was not completed ({error or 'no code'}).</p>", status_code=400)
    try:
        context().auth.finish(state, code)
        context().setup_google()
    except (AuthorizationRequired, GoogleUnavailable, PermissionError, ValueError) as exc:
        return HTMLResponse(f"<p>Google authorization failed: {exc}</p><p><a href='/settings'>Back</a></p>",
                            status_code=400)
    return RedirectResponse("/settings?google=connected")


@router.post("/google/setup", dependencies=[Depends(require_parent), Depends(require_host)])
def google_setup():
    try:
        return context().setup_google()
    except AuthorizationRequired as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/google/disconnect", dependencies=[Depends(require_parent), Depends(require_host)])
def google_disconnect():
    context().disconnect_google()
    return context().google_status()


# ── Synchronisation and maintenance ─────────────────────────────────────────

@router.get("/sync/status", dependencies=[Depends(require_member)])
def sync_status():
    status = context().store.status()
    return {k: status[k] for k in ("state", "pending", "needs_reconciliation", "maintenance", "online",
                                   "auth_required", "last_saved_at", "last_error", "connected")}


@router.get("/sync/operations/{operation_id}", dependencies=[Depends(require_member)])
def operation(operation_id: str):
    return {"operation_id": operation_id, "state": context().store.operation_state(operation_id) or "unknown"}


@router.post("/sync/now", dependencies=[Depends(require_member)])
def sync_now():
    return context().store.flush()


@router.get("/sync/unsettled", dependencies=[Depends(require_parent)])
def unsettled():
    return context().store.unsettled()


@router.post("/sync/reconcile/{operation_id}/retry", dependencies=[Depends(require_parent)])
def reconcile_retry(operation_id: str):
    return context().store.retry(operation_id)


@router.post("/sync/reconcile/{operation_id}/discard", dependencies=[Depends(require_parent)])
def reconcile_discard(operation_id: str):
    """Set aside a conflicting change. It stays on disk under queue/discarded for review."""
    return context().store.discard(operation_id)


@router.post("/maintenance/begin", dependencies=[Depends(require_parent)])
def maintenance_begin():
    return context().store.begin_maintenance()


@router.post("/maintenance/end", dependencies=[Depends(require_parent)])
def maintenance_end():
    return context().store.end_maintenance()


# ── Host process control ────────────────────────────────────────────────────

class ShutdownRequest(BaseModel):
    instance_token: str


@router.post("/host/shutdown", dependencies=[Depends(require_host)])
def shutdown(payload: ShutdownRequest):
    """Graceful stop requested by the launcher that recorded this exact instance."""
    if payload.instance_token != context().instance_token:
        raise HTTPException(status_code=403, detail="Not this server instance")
    context().store.flush(max_ops=10_000)
    # raise_signal runs uvicorn's own handler, so shutdown is graceful on Windows too.
    threading.Timer(0.5, lambda: signal.raise_signal(signal.SIGINT)).start()
    return {"stopping": True, "sync": context().store.status()["state"]}
