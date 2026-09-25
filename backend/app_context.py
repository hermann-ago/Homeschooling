"""Wires configuration, Google clients, the store, devices and the sync worker."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path

import request_context
from config import APP_FOLDERS, HostConfig
from google_io.drive import DriveClient
from google_io.oauth import GoogleAuth
from google_io.rest import GoogleRest
from google_io.sheets import SheetsClient
from security.devices import DeviceRegistry
from storage import PENDING, RECONCILE, SAVED, Store
from storage.gateway import AuthorizationRequired, GoogleUnavailable, OutsideBoundary
from storage.workbook import WORKBOOK_NAME, bootstrap, write_overview

logger = logging.getLogger(__name__)
FLUSH_WAIT_SECONDS = float(os.getenv("HOMESCHOOLING_FLUSH_WAIT", "6"))


class SyncWorker(threading.Thread):
    """Flushes pending operations in the background with backoff while offline."""

    def __init__(self, context: "AppContext"):
        super().__init__(name="sheets-sync", daemon=True)
        self.context = context
        self.event = threading.Event()
        self.stopping = threading.Event()
        self._last_overview = 0.0
        self._overview_saved_at = None

    def nudge(self):
        self.event.set()

    def run(self):
        delay = 15
        while not self.stopping.is_set():
            self.event.wait(delay)
            self.event.clear()
            store = self.context.store
            try:
                status = store.flush()
            except Exception:  # never let the worker die; the error is visible in status
                logger.exception("Sync failed")
                status = store.status()
            if status["pending"] and not status.get("online"):
                delay = min(300, max(15, delay * 2))
            else:
                delay = 15
            if (status.get("last_saved_at") != self._overview_saved_at and time.time() - self._last_overview > 600
                    and status.get("online") and not status["maintenance"]):
                try:
                    write_overview(store)
                    self._overview_saved_at = status.get("last_saved_at")
                    self._last_overview = time.time()
                except (GoogleUnavailable, AuthorizationRequired, PermissionError, ValueError) as error:
                    logger.info("Overview not refreshed: %s", error)

    def stop(self):
        self.stopping.set()
        self.event.set()


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
    def __init__(self, config: HostConfig | None = None, *, sheets=None, drive=None, auth=None,
                 start_worker: bool = True):
        self.config = config or HostConfig()
        self.devices = DeviceRegistry(self.config.secrets_dir)
        self.auth = auth or GoogleAuth(self.config.secrets_dir)
        self.responses = ResponseCache(self.config.dir / "responses")
        self.instance_token = uuid.uuid4().hex
        run = self.config.dir / "run"
        run.mkdir(parents=True, exist_ok=True)
        instance = run / "instance.json"
        fd = os.open(instance, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"pid": os.getpid(), "token": self.instance_token}, stream)
        self.sheets, self.drive = sheets, drive
        if sheets is None and drive is None:
            self._build_google_clients()
        self.store = Store(self.config.store_dir, self.sheets, self.drive).load()
        self.worker = SyncWorker(self) if start_worker else None
        if self.worker:
            self.worker.start()
        from tutoring.service import TutorService
        self.tutor = TutorService(self)

    # ── Google ───────────────────────────────────────────────────────────────
    def _build_google_clients(self):
        if not (self.auth.configured and self.auth.connected):
            return
        rest = GoogleRest(self.auth)
        self.drive = DriveClient(rest, self.config.get("root_folder_id"), self.config.get("folders"))
        spreadsheet_id = self.config.get("spreadsheet_id")
        self.sheets = SheetsClient(rest, spreadsheet_id) if spreadsheet_id else None

    def google_status(self) -> dict:
        status = self.store.status()
        return {
            "client_configured": self.auth.configured, "connected": self.auth.connected,
            "authorization_required": bool(status.get("auth_required")) or (self.auth.configured and not self.auth.connected),
            "root_folder_id": self.config.get("root_folder_id"),
            "spreadsheet_id": self.config.get("spreadsheet_id"),
            "folders": self.config.get("folders"),
        }

    def setup_google(self) -> dict:
        """Create the app folders and the workbook under the root (after authorization)."""
        self._build_google_clients()
        if self.drive is None:
            raise AuthorizationRequired("Connect Google first")
        root = self.drive._raw_metadata(self.config.get("root_folder_id"))
        if root.get("mimeType") != "application/vnd.google-apps.folder":
            raise ValueError("The configured Homeschooling root is not a folder")
        folders = {}
        for name in APP_FOLDERS:
            try:
                folders[name] = self.drive.ensure_folder(name)
            except PermissionError as error:
                raise PermissionError(
                    "Google allowed reading the Homeschooling folder but not adding app folders to it. "
                    "Make sure this Google account can edit the folder, then reconnect.") from error
        self.config.update(folders=folders)
        spreadsheet_id = self.config.get("spreadsheet_id") or self.drive.find_workbook(WORKBOOK_NAME) \
            or self.drive.create_workbook(WORKBOOK_NAME)
        self.config.update(spreadsheet_id=spreadsheet_id)
        self._build_google_clients()
        added = bootstrap(self.sheets)
        self.store.sheets, self.store.drive = self.sheets, self.drive
        self.store.load()
        self.nudge()
        return {"folders": folders, "spreadsheet_id": spreadsheet_id, "tabs_added": added}

    def disconnect_google(self):
        self.auth.disconnect()
        self.store.info["auth_required"] = True

    # ── sync helpers ─────────────────────────────────────────────────────────
    def nudge(self):
        if self.worker:
            self.worker.nudge()

    def settle(self, operation_ids: list[str], wait: float = FLUSH_WAIT_SECONDS) -> str:
        """Try to reach Google now; report the least-settled state among operations."""
        if not operation_ids:
            return SAVED
        if self.worker:
            self.worker.nudge()
            states = [self.store.wait_for(op, wait) for op in operation_ids]
        else:
            self.store.flush()
            states = [self.store.operation_state(op) for op in operation_ids]
        states = [s for s in states if s]
        if RECONCILE in states:
            return RECONCILE
        if PENDING in states:
            return PENDING
        return SAVED

    # ── Drive files ──────────────────────────────────────────────────────────
    def file_bytes(self, file_id: str | None, sha256: str | None = None) -> bytes:
        """Return a Drive file, preferring the verified local copy."""
        store = self.store
        cached_sha = sha256 or (store.known_sha(file_id) if file_id else None)
        if cached_sha:
            data = store.blobs.get(cached_sha)
            if data is not None:
                return data
        if not file_id:
            raise FileNotFoundError("This file has no Drive copy yet")
        if file_id.startswith("pending:"):
            data = store.blobs.get(file_id.split(":", 1)[1])
            if data is None:
                raise FileNotFoundError("The local copy of this file is missing")
            return data
        if self.drive is None:
            raise GoogleUnavailable("Google Drive is not connected and this file is not cached")
        data = self.drive.download(file_id)
        digest = hashlib.sha256(data).hexdigest()
        if sha256 and digest != sha256:
            raise ValueError("The Drive copy does not match its recorded checksum")
        store.blobs.put(data)
        store.remember_file(digest, file_id)
        return data

    def shutdown(self):
        if self.worker:
            self.worker.stop()


def request_operation(kind: str, summary: str | None = None):
    """Shortcut used by routes: a store transaction bound to this request."""
    from dependencies import context
    return context().store.transaction(operation_id=request_context.operation_id(), kind=kind,
                                       device=request_context.device_label(), summary=summary)


__all__ = ["AppContext", "request_operation", "OutsideBoundary"]
