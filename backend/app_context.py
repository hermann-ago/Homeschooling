"""Wires configuration, the SQLite database, the Drive folder, devices and housekeeping."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import request_context
from config import HostConfig
from security.devices import DeviceRegistry
from storage import DriveFolder, Store
from storage.backups import create_backup, export_excel, latest_backup

logger = logging.getLogger(__name__)


class Housekeeping(threading.Thread):
    """Daily verified backup into the Drive folder plus the read-only Excel copy."""

    def __init__(self, context: "AppContext", interval: float = 3600):
        super().__init__(name="housekeeping", daemon=True)
        self.context = context
        self.interval = interval
        self.stopping = threading.Event()

    def run(self):
        while not self.stopping.is_set():
            try:
                self.context.daily()
            except Exception:  # never stop the server over housekeeping
                logger.exception("Daily backup or export failed")
            self.stopping.wait(self.interval)

    def stop(self):
        self.stopping.set()


class ResponseCache:
    """Stored responses for Idempotency-Key retries (per device, 7 days)."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, device_hash: str, key: str) -> Path:
        return self.dir / (hashlib.sha256(f"{device_hash}:{key}".encode()).hexdigest() + ".json")

    def get(self, device_hash: str, key: str) -> dict | None:
        path = self._path(device_hash, key)
        if not path.exists():
            return None
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry["stored_at"] < time.time() - 7 * 86400:
            path.unlink(missing_ok=True)
            return None
        return entry

    def put(self, device_hash: str, key: str, entry: dict):
        path = self._path(device_hash, key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({**entry, "stored_at": time.time()}), encoding="utf-8")
        os.replace(temporary, path)


class AppContext:
    def __init__(self, config: HostConfig | None = None, *, drive_folder=None, start_worker: bool = True):
        self.config = config or HostConfig()
        self.devices = DeviceRegistry(self.config.secrets_dir)
        self.responses = ResponseCache(self.config.dir / "responses")
        self.instance_token = uuid.uuid4().hex
        self.files = DriveFolder(drive_folder or self.config.get("drive_folder"))
        if self.files.available and start_worker:  # tools (e.g. the dry run) leave the Drive folder untouched
            self.files.ensure_folders()
        self.store = Store(self.config.database_path, self.files).load()
        self._assign_subject_folders()
        self.last_export = None
        self.worker = Housekeeping(self) if start_worker else None
        if self.worker:
            self.worker.start()
        from tutoring.service import TutorService
        self.tutor = TutorService(self)

    def _assign_subject_folders(self):
        """Record the Kid/Grade/Subject folder of subjects created before folders were recorded, and the grade
        of subjects created before each subject had its own (read from its folder)."""
        from storage import layout
        missing = [s for s in self.store.all("subjects") if not s.get("folder") or s.get("grade") is None]
        if missing:
            with self.store.transaction(kind="subjects.folders", summary="Recorded subject folders and grades") as tx:
                for subject in missing:
                    folder = layout.subject_base(tx, subject)
                    grade = layout.grade_of_folder(folder)
                    tx.update("subjects", subject["id"], {"folder": folder, "grade": layout.stored_grade(grade)})

    def announce(self):
        """Record this server instance for the launcher (only the server process calls this)."""
        run = self.config.dir / "run"
        run.mkdir(parents=True, exist_ok=True)
        fd = os.open(run / "instance.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"pid": os.getpid(), "token": self.instance_token}, stream)

    # ── Drive folder ─────────────────────────────────────────────────────────
    def set_drive_folder(self, path: str) -> dict:
        folder = DriveFolder(path)
        if not folder.available:
            raise ValueError(f"{path} is not a folder on this computer")
        lowered = str(Path(path)).lower()
        if not any(marker in lowered for marker in ("drive", "g:")):
            logger.warning("The chosen folder does not look like a Google Drive folder: %s", path)
        folder.ensure_folders()
        self.config.update(drive_folder=str(Path(path)))
        self.files.root = folder.root
        return self.status()

    def status(self) -> dict:
        from storage.backups import EXPORT_NAME
        export = self.last_export or (EXPORT_NAME if self.files.available and (self.files.root / EXPORT_NAME).exists()
                                      else None)
        return {**self.store.status(),
                "last_backup": latest_backup(self.store, self.config.backup_dir),
                "last_export": export}

    # ── housekeeping ─────────────────────────────────────────────────────────
    def daily(self):
        latest = latest_backup(self.store, self.config.backup_dir)
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        if not latest or today not in latest:
            self.backup_now()
            self.export_now()
        self.move_unfinished_forward()

    def move_unfinished_forward(self, now: datetime | None = None) -> list[int]:
        """With the family's "move unfinished lessons forward" setting on, re-plan every learner who has
        unfinished lessons from earlier days, once a day, before that day's first lesson starts (so a school
        day in progress is never reshuffled). Returns the learners re-planned."""
        from services.scheduler_engine import recalculate_schedule
        from utils import get_setting, set_setting
        now = now or datetime.now()
        today = now.date()
        if get_setting(self.store, "AUTO_REPLAN") != "on" or get_setting(self.store, "AUTO_REPLAN_LAST") == today.isoformat():
            return []
        slots = self.store.all("scheduled_slots")
        starts = [s["time_start"] for s in slots if s["date"] == today and s["time_start"]]
        if starts and now.strftime("%H:%M") >= min(starts):
            return []  # lessons have started today; try again tomorrow morning
        done = {c["slot_id"] for c in self.store.all("completions")}
        behind = sorted({s["child_id"] for s in slots if s["date"] < today and s["id"] not in done})
        with self.store.transaction(kind="schedule.auto_replan",
                                    summary=f"Moved unfinished lessons forward for {len(behind)} learners") as tx:
            for child_id in behind:
                recalculate_schedule(child_id, tx, today)
            set_setting(tx, "AUTO_REPLAN_LAST", today.isoformat())
        if behind:
            logger.info("Moved unfinished lessons forward for learners %s", behind)
        return behind

    def backup_now(self) -> dict:
        return create_backup(self.store, self.config.backup_dir)

    def export_now(self) -> str | None:
        self.last_export = export_excel(self.store)
        return self.last_export

    def file_bytes(self, path: str | None, sha256: str | None = None) -> bytes:
        if not path:
            raise FileNotFoundError("This record has no file")
        return self.files.read(path, sha256)

    def shutdown(self):
        if self.worker:
            self.worker.stop()
        try:
            if self.files.available:
                self.backup_now()
        except Exception:
            logger.exception("Backup at shutdown failed")


def request_operation(kind: str, summary: str | None = None):
    """Shortcut used by routes: a database transaction bound to this request."""
    from dependencies import context
    return context().store.transaction(operation_id=request_context.operation_id(), kind=kind,
                                       device=request_context.device_label(), summary=summary)
