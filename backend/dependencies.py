"""FastAPI dependencies: the app context, paired-device roles and idempotent writes."""
from __future__ import annotations

import hashlib
import json
import uuid

from fastapi import Depends, HTTPException, Request, status

import request_context
from security.devices import Device
from security.network import is_loopback

_context = None

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def set_context(value):
    global _context
    _context = value


def context():
    if _context is None:
        raise RuntimeError("The app context has not started")
    return _context


def store():
    return context().store


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return None


def current_device(request: Request) -> Device:
    device = context().devices.authenticate(_bearer(request))
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Pair this device first")
    return device


def require_member(device: Device = Depends(current_device)) -> Device:
    return device


def require_parent(device: Device = Depends(current_device)) -> Device:
    if not device.is_parent:
        raise HTTPException(status_code=403, detail="A parent device is required")
    return device


def require_teacher(device: Device = Depends(current_device)) -> Device:
    if not device.sees_teacher_content:
        raise HTTPException(status_code=403, detail="Teacher-only content is not available on learner devices")
    return device


def require_host(request: Request):
    client = request.client.host if request.client else None
    if not (is_loopback(client) or client == "testclient"):
        raise HTTPException(status_code=403, detail="Use the host computer for this step")


class IdempotencyMiddleware:
    """Replay retried writes and report their Google Sheets sync state.

    Mutating ``/api`` requests carry an ``Idempotency-Key``. Every store
    operation created by the request uses that key as its operation ID, so a
    retry after a timeout returns the original response rather than creating a
    duplicate. Responses carry ``X-Sync-State``: ``saved`` (verified in Google
    Sheets), ``pending`` (safe on the home server, not yet in Google) or
    ``needs_reconciliation``.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in MUTATING or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        key = headers.get("idempotency-key")
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        token = headers.get("authorization", "")
        device_hash = hashlib.sha256(token.encode()).hexdigest()
        request_hash = hashlib.sha256(scope["method"].encode() + b" " + scope["path"].encode() + b"?"
                                      + scope.get("query_string", b"") + b"\n" + body).hexdigest()
        ctx = context()
        if key:
            if len(key) > 120 or not all(c.isalnum() or c in "-_:." for c in key):
                return await _json(send, 400, {"detail": "Invalid Idempotency-Key"})
            prior = ctx.responses.get(device_hash, key)
            if prior:
                if prior["request_hash"] != request_hash:
                    return await _json(send, 409, {"detail": "This Idempotency-Key was used for a different request"})
                state = ctx.settle(prior["operation_ids"], wait=0)
                return await _replay(send, prior, state)
        device = ctx.devices.authenticate(token.split(" ", 1)[1] if " " in token else None)
        request = request_context.RequestContext(key=key or f"req-{uuid.uuid4().hex}",
                                                 device_label=f"{device.name} ({device.role})" if device else None)
        marker = request_context.begin(request)

        async def replay_receive():
            nonlocal body
            chunk, body = body, b""
            return {"type": "http.request", "body": chunk, "more_body": False}

        started, chunks = {}, []

        async def capture(message):
            if message["type"] == "http.response.start":
                started.update(message)
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        try:
            await self.app(scope, replay_receive, capture)
        finally:
            request_context.end(marker)
        response_body = b"".join(chunks)
        state = None
        if request.operation_ids:
            import anyio
            state = await anyio.to_thread.run_sync(ctx.settle, request.operation_ids)
        response_headers = [(k, v) for k, v in started.get("headers", []) if k.lower() != b"content-length"]
        if state:
            response_headers += [(b"x-sync-state", state.encode()),
                                 (b"x-operation-id", ",".join(request.operation_ids).encode())]
        if key and started.get("status", 500) < 500:
            ctx.responses.put(device_hash, key, {
                "request_hash": request_hash, "status": started["status"], "operation_ids": request.operation_ids,
                "headers": [(k.decode("latin-1"), v.decode("latin-1")) for k, v in response_headers
                            if k.lower() in (b"content-type",)],
                "body": response_body.decode("latin-1"),
            })
        response_headers.append((b"content-length", str(len(response_body)).encode()))
        await send({"type": "http.response.start", "status": started.get("status", 500), "headers": response_headers})
        await send({"type": "http.response.body", "body": response_body})


async def _replay(send, prior, state):
    body = prior["body"].encode("latin-1")
    headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in prior["headers"]]
    headers += [(b"x-idempotent-replay", b"true"), (b"content-length", str(len(body)).encode())]
    if prior["operation_ids"]:
        headers += [(b"x-sync-state", state.encode()), (b"x-operation-id", ",".join(prior["operation_ids"]).encode())]
    await send({"type": "http.response.start", "status": prior["status"], "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _json(send, status_code, payload):
    body = json.dumps(payload).encode()
    await send({"type": "http.response.start", "status": status_code,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
