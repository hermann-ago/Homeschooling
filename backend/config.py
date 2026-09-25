"""Host configuration and local data locations.

Everything the server keeps locally lives under ``%LOCALAPPDATA%\\Homeschooling``
(outside Google Drive and OneDrive): the SQLite database, local backup copies,
extraction caches and paired devices. Files live in the synced Drive folder.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

DEFAULT_PORT = 8000
# The Homeschooling folder as Google Drive for desktop syncs it on the host.
DRIVE_FOLDER_CANDIDATES = (
    r"G:\My Drive\Casa, Família e Vida Prática\Homeschooling",
    r"G:\Meu Drive\Casa, Família e Vida Prática\Homeschooling",
)


def data_dir() -> Path:
    override = os.getenv("HOMESCHOOLING_DATA")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Homeschooling"


def home_tutor_dir() -> Path:
    """Shared HomeTutor data (the narration usage ledger used by every subject)."""
    base = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "HomeTutor"


def _refuse_synced(path: Path) -> None:
    lowered = str(path.resolve()).lower()
    if any(marker in lowered for marker in ("google drive", "my drive", "onedrive", "dropbox")) or (
            sys.platform == "win32" and lowered.startswith("g:")):
        raise RuntimeError(f"Local data must not live in a synced folder: {path}")


class HostConfig:
    """Small JSON settings file; never contains credentials.

    ``drive_folder`` is the synced Homeschooling folder. It is detected on the
    host when unset and can be changed in parent settings.
    """

    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory or data_dir())
        _refuse_synced(self.dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "config.json"
        self._lock = threading.Lock()
        self.values = {"drive_folder": None, "port": DEFAULT_PORT, "allowed_hosts": [],
                       "tts": {"voice": "en-US-Neural2-J", "rate": 0.9, "project": "gen-lang-client-0088393168"}}
        if self.path.exists():
            self.values.update(json.loads(self.path.read_text(encoding="utf-8")))
        if os.getenv("HOMESCHOOLING_DRIVE_FOLDER"):
            self.values["drive_folder"] = os.environ["HOMESCHOOLING_DRIVE_FOLDER"]
        elif not self.values.get("drive_folder"):
            found = next((c for c in DRIVE_FOLDER_CANDIDATES if Path(c).is_dir()), None)
            if found:
                self.values["drive_folder"] = found

    def get(self, key, default=None):
        return self.values.get(key, default)

    def update(self, **changes):
        with self._lock:
            self.values.update(changes)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)

    @property
    def secrets_dir(self) -> Path:
        return self.dir / "secrets"

    @property
    def database_path(self) -> Path:
        return self.dir / "homeschooling.sqlite3"

    @property
    def cache_dir(self) -> Path:
        return self.dir / "cache"

    @property
    def backup_dir(self) -> Path:
        return self.dir / "backups"
