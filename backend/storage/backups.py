"""Database backups in the Drive folder and a daily read-only Excel copy.

A backup is an integrity-checked SQLite copy written to the Homeschooling
folder's ``Backups`` folder, so Google Drive keeps it off the computer. The
Excel copy (``Homeschooling Database (read-only copy).xlsx`` in the
Homeschooling folder) is for reading only; changes are made in the app. It
leaves out teacher-only tables (answer keys).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .schema import TABLES, to_cell, column_kind

KEEP_BACKUPS = 30
EXPORT_NAME = "Homeschooling Database (read-only copy).xlsx"


def create_backup(store, local_dir: Path | None = None) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"homeschooling-{stamp}.sqlite3"
    with tempfile.TemporaryDirectory() as scratch:
        result = store.backup_to(Path(scratch) / name)
        data_path = Path(result["path"])
        copies = []
        if store.files is not None and store.files.available:
            target = store.files.root / "Backups"
            target.mkdir(exist_ok=True)
            shutil.copy2(data_path, target / name)
            copies.append(store.files.relative(target / name))
            _prune(target)
        if local_dir is not None:
            Path(local_dir).mkdir(parents=True, exist_ok=True)
            shutil.copy2(data_path, Path(local_dir) / name)
            copies.append(str(Path(local_dir) / name))
            _prune(Path(local_dir))
    return {"name": name, "sha256": result["sha256"], "counts": result["counts"], "copies": copies,
            "created_at": stamp}


def _prune(folder: Path):
    backups = sorted(folder.glob("homeschooling-*.sqlite3"))
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)


def latest_backup(store, local_dir: Path | None = None) -> str | None:
    folders = []
    if store.files is not None and store.files.available:
        folders.append(store.files.root / "Backups")
    if local_dir is not None:
        folders.append(Path(local_dir))
    names = sorted({p.name for folder in folders if folder.exists() for p in folder.glob("homeschooling-*.sqlite3")})
    return names[-1] if names else None


def verify_restore(backup_file: Path) -> dict:
    """Open a backup copy on its own and confirm every table can be read."""
    from .store import Store
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "restore-check.sqlite3"
        shutil.copy2(backup_file, copy)
        connection = sqlite3.connect(copy)
        try:
            ok = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            connection.close()
        restored = Store(copy).load()
        return {"integrity": ok, "counts": {name: len(restored.all(name)) for name in TABLES}}


def export_excel(store) -> str | None:
    """Write the read-only Excel copy into the Homeschooling folder."""
    if store.files is None or not store.files.available:
        return None
    import openpyxl
    workbook = openpyxl.Workbook()
    overview = workbook.active
    overview.title = "Overview"
    overview.append(["Homeschooling Database — read-only copy"])
    overview.append(["Written", datetime.now(timezone.utc).isoformat(timespec="seconds")])
    overview.append(["Make changes in the Homeschooling app; edits here are not read back."])
    overview.append([])
    overview.append(["Table", "Rows"])
    for spec in TABLES.values():
        if spec.teacher_only:  # answer keys never leave the app
            continue
        overview.append([spec.tab, len(store.all(spec.name))])
        sheet = workbook.create_sheet(spec.tab[:31])
        sheet.append(spec.header)
        for record in sorted(store.all(spec.name), key=lambda r: str(r["id"])):
            sheet.append([to_cell(column_kind(spec, c), record.get(c)) for c in spec.header])
        sheet.freeze_panes = "A2"
    target = store.files.root / EXPORT_NAME
    temporary = target.with_name(f".{target.name}.part")
    workbook.save(temporary)
    os.replace(temporary, target)
    return store.files.relative(target)
