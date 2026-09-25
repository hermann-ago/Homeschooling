"""Paired household devices and their Homeschooling credentials.

A browser asks to pair and shows a short code. A parent approves the matching
code on the host computer. The device then receives a random token; only its
SHA-256 is stored here. Roles:

* ``parent`` – everything, including Google connection, pairing and maintenance.
* ``learner`` – lessons, reading, annotations and checklists; no teacher-only data.
* ``tutor`` – an AI agent's MCP bridge: tutoring context, including teacher-only
  evidence, and tutoring records; no Google, pairing or maintenance controls.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROLES = ("parent", "learner", "tutor")
PAIRING_SECONDS = 300
MAX_OPEN_REQUESTS = 5


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    role: str
    token_hash: str

    @property
    def is_parent(self) -> bool:
        return self.role == "parent"

    @property
    def sees_teacher_content(self) -> bool:
        return self.role in ("parent", "tutor")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceRegistry:
    def __init__(self, directory: Path, clock=time.time):
        self.path = Path(directory) / "devices.json"
        self.clock = clock
        self._lock = threading.Lock()
        self._requests: dict[str, dict] = {}
        self._devices: dict[str, dict] = {}
        if self.path.exists():
            self._devices = json.loads(self.path.read_text(encoding="utf-8")).get("devices", {})

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"devices": self._devices}, stream, indent=2)
        os.replace(temporary, self.path)

    def _expire(self):
        now = self.clock()
        self._requests = {k: v for k, v in self._requests.items() if v["expires"] > now or v.get("token")}

    # ── pairing ──────────────────────────────────────────────────────────────
    def request(self, name: str, role: str) -> dict:
        if role not in ("parent", "learner"):
            raise ValueError("Choose parent or learner")
        with self._lock:
            self._expire()
            if sum(1 for r in self._requests.values() if r["status"] == "waiting") >= MAX_OPEN_REQUESTS:
                raise PermissionError("Too many pairing requests are waiting; approve or wait a few minutes")
            request_id = secrets.token_urlsafe(12)
            poll_secret = secrets.token_urlsafe(24)
            code = f"{secrets.randbelow(1_000_000):06d}"
            self._requests[request_id] = {
                "id": request_id, "name": name.strip()[:60] or "Browser", "role": role, "code": code,
                "poll_hash": _hash(poll_secret), "status": "waiting", "expires": self.clock() + PAIRING_SECONDS,
            }
            return {"request_id": request_id, "poll_secret": poll_secret, "code": code,
                    "expires_in": PAIRING_SECONDS}

    def waiting(self) -> list[dict]:
        with self._lock:
            self._expire()
            return [{k: r[k] for k in ("id", "name", "role", "code")} | {"expires_in": int(r["expires"] - self.clock())}
                    for r in self._requests.values() if r["status"] == "waiting"]

    def approve(self, request_id: str, code: str, role: str | None = None) -> dict:
        with self._lock:
            self._expire()
            request = self._requests.get(request_id)
            if not request or request["status"] != "waiting":
                raise LookupError("That pairing request expired")
            if not hmac.compare_digest(request["code"], code.strip()):
                raise PermissionError("The code does not match the device")
            role = role or request["role"]
            if role not in ("parent", "learner"):
                raise ValueError("Choose parent or learner")
            token = self._issue(request["name"], role)
            request.update(status="approved", token=token, role=role)
            return {"name": request["name"], "role": role}

    def deny(self, request_id: str) -> None:
        with self._lock:
            request = self._requests.get(request_id)
            if request:
                request["status"] = "denied"

    def poll(self, request_id: str, poll_secret: str) -> dict:
        with self._lock:
            self._expire()
            request = self._requests.get(request_id)
            if not request or not hmac.compare_digest(request["poll_hash"], _hash(poll_secret)):
                return {"status": "expired"}
            if request["status"] == "approved":
                token = request.pop("token")
                del self._requests[request_id]
                return {"status": "approved", "token": token, "role": request["role"], "name": request["name"]}
            return {"status": request["status"]}

    # ── devices ──────────────────────────────────────────────────────────────
    def _issue(self, name: str, role: str) -> str:
        if role not in ROLES:
            raise ValueError("Unknown role")
        token = "hs_" + secrets.token_urlsafe(32)
        device_id = secrets.token_hex(6)
        self._devices[device_id] = {"id": device_id, "name": name, "role": role, "token_hash": _hash(token),
                                    "created_at": int(self.clock()), "last_seen": None}
        self._save()
        return token

    def issue(self, name: str, role: str) -> str:
        """Direct issue on the host (the agent bridge credential, or the host browser)."""
        with self._lock:
            return self._issue(name, role)

    def authenticate(self, token: str | None) -> Device | None:
        if not token:
            return None
        digest = _hash(token)
        with self._lock:
            for device in self._devices.values():
                if hmac.compare_digest(device["token_hash"], digest):
                    now = int(self.clock())
                    if not device["last_seen"] or now - device["last_seen"] > 300:
                        device["last_seen"] = now
                        self._save()
                    return Device(device["id"], device["name"], device["role"], device["token_hash"])
        return None

    def list(self) -> list[dict]:
        with self._lock:
            return [{k: d[k] for k in ("id", "name", "role", "created_at", "last_seen")} for d in self._devices.values()]

    def revoke(self, device_id: str) -> None:
        with self._lock:
            if self._devices.pop(device_id, None) is None:
                raise LookupError("Unknown device")
            self._save()
