"""Health, the tutor credential, storage status, backups and host controls."""
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
            "host": is_loopback(client) or client == "testclient"}


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
