"""Pairing, storage status, backups and host controls."""
from __future__ import annotations

import signal
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dependencies import context, current_device, require_host, require_member, require_parent
from security.devices import Device
from security.network import is_loopback

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


# ── Storage: database, Drive folder, backups ────────────────────────────────

@router.get("/storage/status", dependencies=[Depends(require_member)])
def storage_status():
    """Where data lives and whether the synced Drive folder is reachable."""
    return context().status()


@router.get("/sync/operations/{operation_id}", dependencies=[Depends(require_member)])
def operation(operation_id: str):
    return {"operation_id": operation_id, "state": context().store.operation_state(operation_id) or "unknown"}


class DriveFolderRequest(BaseModel):
    path: str = Field(..., min_length=3, max_length=400)


@router.post("/storage/drive-folder", dependencies=[Depends(require_parent), Depends(require_host)])
def set_drive_folder(payload: DriveFolderRequest):
    """Point the server at the synced Homeschooling folder (host computer only)."""
    try:
        return context().set_drive_folder(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/storage/backup", dependencies=[Depends(require_parent)])
def backup_now():
    return context().backup_now()


@router.post("/storage/export", dependencies=[Depends(require_parent)])
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
