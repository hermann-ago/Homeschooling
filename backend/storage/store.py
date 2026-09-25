"""The Homeschooling database: SQLite on the home server.

Reads are served from an in-memory copy loaded at start-up. A transaction
stages changes, validates them (required fields, relationships, uniqueness,
expected revisions) and commits them in one SQLite transaction together with
an Operation Receipts row, then updates the in-memory copy. The home server is
the only writer, so a committed change is saved; there is no sync queue.

Operation IDs make retries safe: a repeated operation ID is recognised from
its receipt instead of being applied twice.

The database file lives under %LOCALAPPDATA%\\Homeschooling (never in a synced
folder, where syncing a live SQLite file can corrupt it). Verified backups are
copied into the Drive folder's Backups folder.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .schema import SCHEMA_VERSION, TABLES, Table, coerce, column_kind, normalise, to_cell

logger = logging.getLogger(__name__)

SAVED = "saved"


class StoreError(Exception):
    status_code = 400


class NotFound(StoreError):
    status_code = 404


class IntegrityViolation(StoreError):
    status_code = 409


class RevisionConflict(StoreError):
    status_code = 409

    def __init__(self, message: str, current: dict | None):
        super().__init__(message)
        self.current = current


class DuplicateOperation(StoreError):
    status_code = 409

    def __init__(self, operation_id: str, state: str, same_request: bool):
        super().__init__(f"Operation {operation_id} was already recorded ({state})")
        self.operation_id = operation_id
        self.state = state
        self.same_request = same_request


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


SQL_TYPES = {"int": "INTEGER", "float": "REAL", "bool": "INTEGER"}


def _to_db(kind: str, value):
    if value is None:
        return None
    if kind in ("int", "float"):
        return value
    if kind == "bool":
        return 1 if value else 0
    return to_cell(kind, value)


def _from_db(kind: str, value):
    if value is None:
        return None
    if kind == "bool":
        return bool(value)
    if kind in ("int", "float"):
        return value
    return coerce(kind, value, from_cell=True)


class Transaction:
    def __init__(self, store: "Store", operation_id: str | None, kind: str, device: str | None,
                 summary: str | None, request_sha256: str | None):
        self.store = store
        self.operation_id = operation_id or f"op-{uuid.uuid4().hex}"
        self.kind = kind
        self.device = device
        self.summary = summary
        self.request_sha256 = request_sha256
        self._staged: dict[tuple[str, object], dict | None] = {}
        self._order: list[tuple[str, object]] = []
        self._touched: set[tuple[str, object]] = set()
        self._preserved: dict[tuple[str, object], tuple[int | None, datetime | None]] = {}
        self.result = None
        self.created_files: list[str] = []

    # ── reads that see staged changes ────────────────────────────────────────
    def get(self, table: str, record_id) -> dict | None:
        key = (table, record_id)
        if key in self._staged:
            value = self._staged[key]
            return dict(value) if value is not None else None
        return self.store.get(table, record_id)

    def all(self, table: str) -> list[dict]:
        rows = {r["id"]: r for r in self.store.all(table)}
        for (name, record_id), value in self._staged.items():
            if name != table:
                continue
            if value is None:
                rows.pop(record_id, None)
            else:
                rows[record_id] = dict(value)
        return list(rows.values())

    def find(self, table: str, **equals) -> list[dict]:
        return [r for r in self.all(table) if all(r.get(k) == v for k, v in equals.items())]

    # ── writes ────────────────────────────────────────────────────────────────
    def _stage(self, table: str, record_id, value):
        key = (table, record_id)
        if key not in self._staged:
            self._order.append(key)
        self._staged[key] = value

    def insert(self, table: str, values: dict, *, revision: int | None = None,
               updated_at: datetime | None = None) -> dict:
        """Insert a row. Migration may keep the source revision and update time."""
        spec = TABLES[table]
        record = {c: None for c in spec.header}
        record.update(normalise(spec, values))
        if record.get("id") is None:
            if spec.id_type != "int":
                raise StoreError(f"{table} records need an explicit id")
            record["id"] = self.store._allocate_id(table)
        if self.get(table, record["id"]) is not None:
            raise IntegrityViolation(f"{table} {record['id']} already exists")
        if "created_at" in spec.columns and record.get("created_at") is None:
            record["created_at"] = utcnow()
        self._check_required(spec, record)
        self._check_foreign_keys(spec, record)
        self._stage(table, record["id"], record)
        if revision is not None or updated_at is not None:
            self._preserved[(table, record["id"])] = (revision, updated_at)
        return dict(record)

    def update(self, table: str, record_id, changes: dict, expected_revision: int | None = None) -> dict:
        spec = TABLES[table]
        current = self.get(table, record_id)
        if current is None:
            raise NotFound(f"{table} {record_id} not found")
        self._check_revision(table, current, expected_revision)
        values = normalise(spec, {k: v for k, v in changes.items() if k != "id"}, partial=True)
        record = {**current, **values}
        self._check_required(spec, record)
        self._check_foreign_keys(spec, record)
        self._stage(table, record_id, record)
        return dict(record)

    def delete(self, table: str, record_id, expected_revision: int | None = None):
        current = self.get(table, record_id)
        if current is None:
            raise NotFound(f"{table} {record_id} not found")
        self._check_revision(table, current, expected_revision)
        self._stage(table, record_id, None)
        for child in TABLES.values():
            for fk in child.foreign_keys:
                if fk.table != table:
                    continue
                dependants = [r for r in self.all(child.name) if r.get(fk.column) == record_id]
                for dependant in dependants:
                    if fk.on_delete == "restrict":
                        raise IntegrityViolation(
                            f"{table} {record_id} is referenced by {child.name} {dependant['id']}; "
                            "tutoring evidence is preserved, so remove it deliberately first")
                    if fk.on_delete == "set_null":
                        self._stage(child.name, dependant["id"], {**dependant, fk.column: None})
                    elif self.get(child.name, dependant["id"]) is not None:
                        self.delete(child.name, dependant["id"])

    def touch(self, table: str, record_id):
        """Record a new revision for an unchanged row (used by imports that preserve revisions)."""
        current = self.get(table, record_id)
        if current is None:
            raise NotFound(f"{table} {record_id} not found")
        self._stage(table, record_id, current)
        self._touched.add((table, record_id))

    def add_blob(self, data: bytes, folder: str, name: str, mime_type: str | None = None) -> tuple[str, str]:
        """Write the file into the Homeschooling folder now, before any row refers to it."""
        if self.store.files is None:
            raise StoreError("The Homeschooling folder is not configured")
        relative, sha, created = self.store.files.write_new(folder, name, data)
        if created:
            self.created_files.append(relative)
        return relative, sha

    # ── validation ───────────────────────────────────────────────────────────
    @staticmethod
    def _check_revision(table, current, expected_revision):
        if expected_revision is not None and current["revision"] != expected_revision:
            raise RevisionConflict(f"{table} {current['id']} changed on another device", current)

    @staticmethod
    def _check_required(spec: Table, record: dict):
        missing = [c for c in spec.required if record.get(c) is None]
        if missing:
            raise StoreError(f"{spec.name} requires {', '.join(missing)}")

    def _check_foreign_keys(self, spec: Table, record: dict):
        for fk in spec.foreign_keys:
            value = record.get(fk.column)
            if value is not None and self.get(fk.table, value) is None:
                raise NotFound(f"{fk.table} {value} not found")

    def _check_unique(self):
        touched = {table for table, _ in self._order}
        for table in touched:
            spec = TABLES[table]
            for columns in spec.unique:
                seen = {}
                for row in self.all(table):
                    key = tuple(row.get(c) for c in columns)
                    if key in seen:
                        raise IntegrityViolation(f"{table} already has {dict(zip(columns, key))}")
                    seen[key] = row["id"]

    def changes(self) -> list[dict]:
        self._check_unique()
        now = utcnow()
        result = []
        for table, record_id in self._order:
            original = self.store.get(table, record_id)
            new = self._staged[(table, record_id)]
            if original is None and new is None:
                continue
            if original is None:
                revision, updated_at = self._preserved.get((table, record_id), (None, None))
                row = {**new, "revision": revision or 1, "updated_at": updated_at or now}
                result.append({"table": table, "action": "insert", "id": record_id, "base_revision": None,
                               "row": row})
            elif new is None:
                result.append({"table": table, "action": "delete", "id": record_id,
                               "base_revision": original["revision"], "row": None})
            else:
                comparable = {k: v for k, v in new.items() if k not in ("revision", "updated_at")}
                unchanged = comparable == {k: v for k, v in original.items() if k not in ("revision", "updated_at")}
                if unchanged and (table, record_id) not in self._touched:
                    continue
                row = {**new, "revision": original["revision"] + 1, "updated_at": now}
                result.append({"table": table, "action": "update", "id": record_id,
                               "base_revision": original["revision"], "row": row})
        return result


class Store:
    def __init__(self, path, files=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.files = files
        self._lock = threading.RLock()
        self._data: dict[str, dict] = {name: {} for name in TABLES}
        self._next_ids: dict[str, int] = {}

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def load(self):
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
                version = connection.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
                if version and int(version[0]) > SCHEMA_VERSION:
                    raise StoreError("This database was written by a newer version of the app")
                for spec in TABLES.values():
                    self._ensure_table(connection, spec)
                connection.execute("INSERT OR REPLACE INTO _meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
                for spec in TABLES.values():
                    columns = spec.header
                    rows = connection.execute(f'SELECT {", ".join(_q(c) for c in columns)} FROM {_q(spec.name)}')
                    table = {}
                    for values in rows:
                        record = {c: _from_db(column_kind(spec, c), v) for c, v in zip(columns, values)}
                        table[record["id"]] = record
                    self._data[spec.name] = table
                    if spec.id_type == "int" and table:
                        self._next_ids[spec.name] = max(table) + 1
            finally:
                connection.close()
        return self

    @staticmethod
    def _ensure_table(connection, spec: Table):
        columns = [f'{_q(c)} {SQL_TYPES.get(column_kind(spec, c), "TEXT")}' for c in spec.header]
        connection.execute(f"CREATE TABLE IF NOT EXISTS {_q(spec.name)} ({', '.join(columns)}, PRIMARY KEY (id))")
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({_q(spec.name)})")}
        for column in spec.header:
            if column not in existing:  # additive schema changes
                kind = SQL_TYPES.get(column_kind(spec, column), "TEXT")
                connection.execute(f"ALTER TABLE {_q(spec.name)} ADD COLUMN {_q(column)} {kind}")

    # ── reads ────────────────────────────────────────────────────────────────
    def all(self, table: str) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._data[table].values()]

    def get(self, table: str, record_id) -> dict | None:
        with self._lock:
            record = self._data[table].get(record_id)
            return dict(record) if record is not None else None

    def find(self, table: str, **equals) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._data[table].values()
                    if all(r.get(k) == v for k, v in equals.items())]

    def first(self, table: str, **equals) -> dict | None:
        rows = self.find(table, **equals)
        return rows[0] if rows else None

    def _allocate_id(self, table: str) -> int:
        with self._lock:
            current = max([self._next_ids.get(table, 1), *(i + 1 for i in self._data[table])])
            self._next_ids[table] = current + 1
            return current

    # ── writes ───────────────────────────────────────────────────────────────
    @contextmanager
    def transaction(self, operation_id: str | None = None, kind: str = "app", device: str | None = None,
                    summary: str | None = None, request_sha256: str | None = None):
        with self._lock:
            if operation_id:
                receipt = self._data["operation_receipts"].get(operation_id)
                if receipt is not None:
                    same = request_sha256 is not None and request_sha256 == receipt["payload_sha256"]
                    raise DuplicateOperation(operation_id, SAVED, same)
            tx = Transaction(self, operation_id, kind, device, summary, request_sha256)
            try:
                yield tx
                tx.result = self._commit(tx)
            except BaseException:
                for relative in tx.created_files:  # nothing will refer to them
                    try:
                        self.files.remove(relative)
                    except OSError:
                        pass
                raise

    def _commit(self, tx: "Transaction") -> dict:
        changes = tx.changes()
        if not changes:
            return {"operation_id": tx.operation_id, "sync": SAVED, "changes": 0}
        now = utcnow()
        receipt = {"id": tx.operation_id, "revision": 1, "updated_at": now,
                   "payload_sha256": tx.request_sha256 or sha256_text([[c["table"], c["action"], str(c["id"])]
                                                                       for c in changes]),
                   "kind": tx.kind, "device": tx.device, "summary": (tx.summary or tx.kind)[:300], "created_at": now}
        changes.append({"table": "operation_receipts", "action": "insert", "id": tx.operation_id,
                        "base_revision": None, "row": receipt})
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for change in changes:
                self._write(connection, change)
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        for change in changes:  # the database committed; mirror it in memory
            rows = self._data[change["table"]]
            if change["action"] == "delete":
                rows.pop(change["id"], None)
            else:
                rows[change["id"]] = dict(change["row"])
        return {"operation_id": tx.operation_id, "sync": SAVED, "changes": len(changes) - 1}

    @staticmethod
    def _write(connection, change):
        spec = TABLES[change["table"]]
        name = _q(spec.name)
        if change["action"] == "delete":
            cursor = connection.execute(f"DELETE FROM {name} WHERE id=? AND revision=?",
                                        (_to_db(spec.id_type, change["id"]), change["base_revision"]))
        elif change["action"] == "insert":
            columns = spec.header
            values = [_to_db(column_kind(spec, c), change["row"].get(c)) for c in columns]
            try:
                connection.execute(f"INSERT INTO {name} ({', '.join(_q(c) for c in columns)}) "
                                   f"VALUES ({', '.join('?' for _ in columns)})", values)
            except sqlite3.IntegrityError as error:
                raise IntegrityViolation(f"{spec.name} {change['id']} already exists") from error
            return
        else:
            columns = [c for c in spec.header if c != "id"]
            values = [_to_db(column_kind(spec, c), change["row"].get(c)) for c in columns]
            cursor = connection.execute(
                f"UPDATE {name} SET {', '.join(f'{_q(c)}=?' for c in columns)} WHERE id=? AND revision=?",
                [*values, _to_db(spec.id_type, change["id"]), change["base_revision"]])
        if cursor.rowcount != 1:
            raise RevisionConflict(f"{spec.name} {change['id']} changed while saving", None)

    def operation_state(self, operation_id: str) -> str | None:
        with self._lock:
            return SAVED if operation_id in self._data["operation_receipts"] else None

    def status(self) -> dict:
        return {"state": SAVED, "database": str(self.path),
                "drive_folder": str(self.files.root) if self.files and self.files.root else None,
                "drive_folder_available": bool(self.files and self.files.available)}

    # ── backups ──────────────────────────────────────────────────────────────
    def backup_to(self, destination: Path) -> dict:
        """A consistent, integrity-checked copy of the database."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.part")
        temporary.unlink(missing_ok=True)
        with self._lock:
            source = self._connect()
            target = sqlite3.connect(temporary)
            try:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise StoreError("The backup copy failed its integrity check")
                counts = {spec.name: target.execute(f"SELECT COUNT(*) FROM {_q(spec.name)}").fetchone()[0]
                          for spec in TABLES.values()}
            finally:
                target.close()
                source.close()
        os.replace(temporary, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return {"path": str(destination), "sha256": digest, "counts": counts}


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
