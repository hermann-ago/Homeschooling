"""Who is calling the home server.

Every device on the home network is a family device with full access: the
network guard (security/network.py) already keeps everyone else out. The only
credential left is the AI tutor's MCP bridge token, issued on the host by
``launcher pair-agent``, so tutoring records show they came from the tutor. Only
its SHA-256 is stored here.
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

ROLES = ("tutor",)


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    role: str
    token_hash: str

    @property
    def is_parent(self) -> bool:
        return self.role == "family"

    @property
    def sees_teacher_content(self) -> bool:
        return self.role in ("family", "tutor")


FAMILY = Device("family", "Home network device", "family", "")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceRegistry:
    def __init__(self, directory: Path, clock=time.time):
        self.path = Path(directory) / "devices.json"
        self.clock = clock
        self._lock = threading.Lock()
        self._devices: dict[str, dict] = {}
        if self.path.exists():
            stored = json.loads(self.path.read_text(encoding="utf-8")).get("devices", {})
            # Browsers paired before pairing was removed held learner or parent tokens; forget them.
            self._devices = {k: d for k, d in stored.items() if d["role"] in ROLES}
            if len(self._devices) != len(stored):
                self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"devices": self._devices}, stream, indent=2)
        os.replace(temporary, self.path)

    def issue(self, name: str, role: str) -> str:
        """Issue a credential on the host (the tutor bridge's, via launcher pair-agent)."""
        if role not in ROLES:
            raise ValueError("Unknown role")
        token = "hs_" + secrets.token_urlsafe(32)
        device_id = secrets.token_hex(6)
        with self._lock:
            self._devices[device_id] = {"id": device_id, "name": name, "role": role, "token_hash": _hash(token),
                                        "created_at": int(self.clock()), "last_seen": None}
            self._save()
        return token

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
