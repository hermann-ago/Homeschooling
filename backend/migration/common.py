"""Shared pieces for the one-time migration tools.

Imports are staged: they write through the same store (and the same Sheets
verification) as the app, with deterministic operation IDs, so re-running a
step after an interruption never duplicates rows. Conflicting evidence is
reported, never overwritten.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from storage import DuplicateOperation


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
