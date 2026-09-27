"""Shared pieces for the one-time migration tools.

Imports are staged: they write through the same store as the app, each batch
in one SQLite transaction with a deterministic operation ID, so re-running a
step after an interruption never duplicates rows. Conflicting evidence is
reported, never overwritten.

A dry run works on a copy of the database and a scratch folder: files the
import would add to the Drive folder go to a temporary directory instead, so
neither the database nor Google Drive changes.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from storage import DriveFolder, DuplicateOperation, FileUnavailable, Store
from storage.files import OutsideBoundary, safe_name, sha256_bytes
from storage.layout import check_folder


class ScratchFolder(DriveFolder):
    """The real Drive folder for reading; new files go to a temporary directory."""

    def __init__(self, root, scratch: Path):
        super().__init__(root)
        self.scratch = Path(scratch)
        self.written: dict[str, Path] = {}

    @property
    def available(self) -> bool:
        return True

    def require(self):
        if self.root is None or not self.root.is_dir():
            raise FileUnavailable("The Homeschooling Drive folder is not available on this computer")

    def write_new(self, folder: str, name: str, data: bytes) -> tuple[str, str, bool]:
        try:
            folder = check_folder(folder)
        except ValueError as error:
            raise OutsideBoundary(str(error)) from error
        relative = f"{folder}/{safe_name(name)}"
        path = self.scratch / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.written[relative] = path
        return relative, sha256_bytes(data), False

    def read(self, relative: str, sha256: str | None = None) -> bytes:
        if relative in self.written:
            return self.written[relative].read_bytes()
        return super().read(relative, sha256)


def dry_run_store(context) -> Store:
    """A throwaway copy of the live database whose file writes go to a scratch folder."""
    scratch = Path(tempfile.mkdtemp(prefix="homeschooling-dry-run-"))
    database = scratch / "dry-run.sqlite3"
    if Path(context.config.database_path).exists():
        source = sqlite3.connect(context.config.database_path)
        target = sqlite3.connect(database)
        with target:
            source.backup(target)
        source.close()
        target.close()
    return Store(database, ScratchFolder(context.files.root, scratch / "files")).load()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class Report:
    def __init__(self, name: str):
        self.name = name
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.counts: dict[str, dict] = {}
        self.conflicts: list[dict] = []
        self.warnings: list[str] = []
        self.skipped: list[str] = []
        self.notes: list[str] = []

    def count(self, table: str, **values):
        self.counts.setdefault(table, {}).update(values)

    def conflict(self, kind: str, detail: str, **evidence):
        self.conflicts.append({"kind": kind, "detail": detail, **evidence})

    def as_dict(self) -> dict:
        return {"name": self.name, "started_at": self.started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
                "counts": self.counts, "conflicts": self.conflicts, "warnings": self.warnings,
                "skipped": self.skipped, "notes": self.notes, "clean": not self.conflicts}

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.name}-{self.started_at[:19].replace(':', '')}.json"
        path.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return path


def staged(store, operation_id: str, summary: str, work, report: Report):
    """Run one import batch once. A repeated run finds the earlier operation and skips it."""
    try:
        with store.transaction(operation_id=operation_id, kind="migration", device="migration",
                               summary=summary) as tx:
            work(tx)
        return True
    except DuplicateOperation as duplicate:
        report.skipped.append(f"{operation_id} already imported ({duplicate.state})")
        return False


def chunks(rows: list, size: int = 400):
    for start in range(0, len(rows), size):
        yield start // size, rows[start:start + size]


def parse_time(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
