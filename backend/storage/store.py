"""Sheets-authoritative store with a local cache and a durable pending queue.

Reads are served from memory. A committed transaction becomes an *operation*:
it is written to ``queue/`` on disk before it is applied in memory, then sent
to Google Sheets in one atomic ``spreadsheets.batchUpdate`` together with an
Operation Receipts row. After the batch the affected rows are read back; only
then is the operation reported as ``saved``.

* ``pending`` – durable on this computer, not yet confirmed in Google Sheets.
* ``saved`` – the receipt and every row were verified in Google Sheets.
* ``needs_reconciliation`` – Sheets disagreed (edited elsewhere, row missing,
  verification failed). The operation is preserved and excluded from the live
  view until a parent retries or discards it.

A response lost after Google applied a batch is safe: the next flush finds the
receipt and marks the operation saved instead of writing it twice.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .gateway import AuthorizationRequired, GoogleUnavailable, quote_tab
from .schema import (
    META_TAB, OVERVIEW_TAB, SCHEMA_VERSION, TABLES, Table, cells_to_row, column_kind, normalise, row_to_cells,
)

logger = logging.getLogger(__name__)

SAVED = "saved"
PENDING = "pending"
RECONCILE = "needs_reconciliation"
PLACEHOLDER = "pending:"


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


class MaintenancePaused(StoreError):
    status_code = 423


class DuplicateOperation(StoreError):
    status_code = 409

    def __init__(self, operation_id: str, state: str, same_request: bool):
        super().__init__(f"Operation {operation_id} was already recorded ({state})")
        self.operation_id = operation_id
        self.state = state
        self.same_request = same_request


class _FlushConflict(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(temporary, "w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class BlobStore:
    """Content-addressed local copies of Drive files (outbox and read cache)."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, sha: str) -> Path:
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("Invalid blob digest")
        return self.root / sha[:2] / sha

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        path = self.path(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            with open(temporary, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        return sha

    def get(self, sha: str) -> bytes | None:
        path = self.path(sha)
        if not path.exists():
            return None
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            path.unlink(missing_ok=True)  # corrupted cache entry; refetch from Drive
            return None
        return data


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
        self._blobs: dict[str, dict] = {}
        self._touched: set[tuple[str, object]] = set()
        self._preserved: dict[tuple[str, object], tuple[int | None, datetime | None]] = {}
        self.result = None

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
        """Record a new revision for an unchanged row (used after direct spreadsheet edits)."""
        current = self.get(table, record_id)
        if current is None:
            raise NotFound(f"{table} {record_id} not found")
        self._stage(table, record_id, current)
        self._touched.add((table, record_id))

    def add_blob(self, data: bytes, folder: str, name: str, mime_type: str) -> tuple[str, str]:
        """Keep bytes locally now; upload to Drive before the reference reaches Sheets."""
        sha = self.store.blobs.put(data)
        self._blobs[sha] = {"sha": sha, "folder": folder, "name": name, "mime": mime_type, "file_id": None}
        existing = self.store.known_file_id(sha)
        return (existing or PLACEHOLDER + sha), sha

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
            spec = TABLES[table]
            original = self.store.get(table, record_id)
            new = self._staged[(table, record_id)]
            if original is None and new is None:
                continue
            if original is None:
                revision, updated_at = self._preserved.get((table, record_id), (None, None))
                row = {**new, "revision": revision or 1, "updated_at": updated_at or now}
                result.append({"table": table, "action": "insert", "id": record_id, "base_revision": None,
                               "row": row_to_cells(spec, row)})
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
                               "base_revision": original["revision"], "row": row_to_cells(spec, row)})
        return result


class Store:
    def __init__(self, data_dir, sheets=None, drive=None, *, verify_writes: bool = True):
        self.dir = Path(data_dir)
        self.sheets = sheets
        self.drive = drive
        self.verify_writes = verify_writes
        self.blobs = BlobStore(self.dir / "blobs")
        self.queue_dir = self.dir / "queue"
        for sub in ("", "saved", "discarded"):
            (self.queue_dir / sub).mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._flush_lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._base: dict[str, dict] = {name: {} for name in TABLES}
        self._data: dict[str, dict] = {name: {} for name in TABLES}
        self._headers: dict[str, list[str]] = {}
        self._next_ids: dict[str, int] = {}
        self._ops: list[dict] = []
        self._seq = 0
        self._file_ids: dict[str, str] = {}
        self.maintenance = False
        self.info = {"online": None, "auth_required": False, "last_error": None, "last_saved_at": None,
                     "last_loaded_at": None, "schema_problems": []}
        self._load_flags()

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def load(self):
        with self._lock:
            self._load_queue()
            snapshot = self._snapshot_path()
            if snapshot.exists():  # local cache index survives even when Sheets is reachable
                self._file_ids.update(json.loads(snapshot.read_text(encoding="utf-8")).get("file_ids", {}))
            loaded = False
            if self.sheets is not None:
                try:
                    problems = self._pull()
                    loaded = not problems
                    if problems:
                        self.info["schema_problems"] = problems
                        self.maintenance = True
                        self._save_flags()
                except (GoogleUnavailable, AuthorizationRequired) as error:
                    self._record_error(error)
            if not loaded and not self._base_loaded_from_sheets:
                self._load_snapshot()
            self._rebuild()
            return self

    _base_loaded_from_sheets = False

    def _flags_path(self):
        return self.dir / "state" / "flags.json"

    def _load_flags(self):
        path = self._flags_path()
        if path.exists():
            flags = json.loads(path.read_text(encoding="utf-8"))
            self.maintenance = bool(flags.get("maintenance"))

    def _save_flags(self):
        _atomic_write(self._flags_path(), json.dumps({"maintenance": self.maintenance}))

    def _snapshot_path(self):
        return self.dir / "state" / "snapshot.json"

    def _load_snapshot(self):
        path = self._snapshot_path()
        if not path.exists():
            return
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        self._next_ids.update(snapshot.get("next_ids", {}))
        self._file_ids.update(snapshot.get("file_ids", {}))
        for name, rows in snapshot["tables"].items():
            spec = TABLES.get(name)
            if spec is None:
                continue
            self._base[name] = {}
            for cells in rows:
                record = cells_to_row(spec, spec.header, cells)
                self._base[name][record["id"]] = record
        self.info["last_loaded_at"] = snapshot.get("loaded_at")

    def _save_snapshot(self):
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "loaded_at": self.info.get("last_loaded_at"),
            "next_ids": self._next_ids,
            "file_ids": self._file_ids,
            "tables": {name: [row_to_cells(TABLES[name], r) for r in rows.values()]
                       for name, rows in self._base.items()},
        }
        _atomic_write(self._snapshot_path(), json.dumps(snapshot, ensure_ascii=False))

    def _load_queue(self):
        self._ops = []
        for path in sorted(self.queue_dir.glob("*.json")):
            op = json.loads(path.read_text(encoding="utf-8"))
            self._ops.append(op)
            self._seq = max(self._seq, op["seq"])
        for path in self.queue_dir.glob("saved/*.json"):
            self._seq = max(self._seq, int(path.name.split("-", 1)[0]))

    def _op_path(self, op, folder: str = "") -> Path:
        base = self.queue_dir / folder if folder else self.queue_dir
        return base / f"{op['seq']:010d}-{op['id']}.json"

    def _persist_op(self, op):
        _atomic_write(self._op_path(op), json.dumps(op, ensure_ascii=False))

    def _read_tabs(self, titles: list[str]) -> dict[str, list[list[str]]]:
        ranges = [quote_tab(t) for t in titles]
        values = self.sheets.get_values(ranges)
        return dict(zip(titles, values))

    def _pull(self) -> list[str]:
        """Replace the base with Google Sheets. Returns validation problems."""
        titles = self.sheets.metadata()
        missing = [t.tab for t in TABLES.values() if t.tab not in titles]
        if missing:
            return [f"Missing tab: {tab}" for tab in missing]
        raw = self._read_tabs([t.tab for t in TABLES.values()])
        base, headers, problems = self._parse_workbook(raw)
        if problems:
            return problems
        self._base = base
        self._headers = headers
        for name, rows in base.items():
            if TABLES[name].id_type == "int" and rows:
                self._next_ids[name] = max(self._next_ids.get(name, 1), max(rows) + 1)
        self.info["online"] = True
        self.info["auth_required"] = False
        self.info["last_loaded_at"] = utcnow().isoformat()
        self.info["schema_problems"] = []
        self._base_loaded_from_sheets = True
        self._save_snapshot()
        return []

    @staticmethod
    def _parse_workbook(raw) -> tuple[dict, dict, list[str]]:
        base, headers, problems = {}, {}, []
        for spec in TABLES.values():
            rows = raw.get(spec.tab) or []
            header = rows[0] if rows else []
            if header[:len(spec.header)] != spec.header:
                problems.append(f"{spec.tab}: header must start with {', '.join(spec.header)}")
                continue
            headers[spec.tab] = header
            table = {}
            for index, cells in enumerate(rows[1:], start=2):
                if not any(cells):
                    continue
                try:
                    record = cells_to_row(spec, header, cells)
                except (ValueError, TypeError) as error:
                    problems.append(f"{spec.tab} row {index}: {error}")
                    continue
                if record["id"] is None or record["revision"] is None:
                    problems.append(f"{spec.tab} row {index}: id and revision are required")
                    continue
                if record["id"] in table:
                    problems.append(f"{spec.tab} row {index}: duplicate id {record['id']}")
                    continue
                table[record["id"]] = record
            base[spec.name] = table
        if not problems:
            for spec in TABLES.values():
                for record in base[spec.name].values():
                    for fk in spec.foreign_keys:
                        value = record.get(fk.column)
                        if value is not None and value not in base[fk.table]:
                            problems.append(f"{spec.tab} {record['id']}: {fk.column} {value} does not exist")
                    missing = [c for c in spec.required if record.get(c) is None]
                    if missing:
                        problems.append(f"{spec.tab} {record['id']}: missing {', '.join(missing)}")
                for columns in spec.unique:
                    seen = set()
                    for record in base[spec.name].values():
                        key = tuple(record.get(c) for c in columns)
                        if key in seen:
                            problems.append(f"{spec.tab}: duplicate {', '.join(columns)} {key}")
                        seen.add(key)
        return base, headers, problems

    def _rebuild(self):
        """Live view = verified base + replay of every pending operation."""
        data = copy.deepcopy(self._base)
        receipts = self._base["operation_receipts"]
        for op in list(self._ops):
            if op["status"] != PENDING:
                continue
            if op["id"] in receipts:
                self._mark_saved(op, apply_to_base=False)
                continue
            try:
                self._apply(data, op, check=True)
            except _FlushConflict as conflict:
                op["status"] = RECONCILE
                op["last_error"] = str(conflict)
                self._persist_op(op)
        self._data = data
        for name, rows in data.items():
            if TABLES[name].id_type == "int" and rows:
                self._next_ids[name] = max(self._next_ids.get(name, 1), max(rows) + 1)

    @staticmethod
    def _apply(tables: dict, op: dict, check: bool):
        for change in op["changes"]:
            spec = TABLES[change["table"]]
            rows = tables[change["table"]]
            current = rows.get(change["id"])
            if check:
                if change["action"] == "insert" and current is not None:
                    raise _FlushConflict(f"{spec.tab} {change['id']} already exists")
                if change["action"] != "insert":
                    if current is None:
                        raise _FlushConflict(f"{spec.tab} {change['id']} no longer exists")
                    if current["revision"] != change["base_revision"]:
                        raise _FlushConflict(f"{spec.tab} {change['id']} was changed elsewhere "
                                             f"(revision {current['revision']}, expected {change['base_revision']})")
            if change["action"] == "delete":
                rows.pop(change["id"], None)
            else:
                rows[change["id"]] = cells_to_row(spec, spec.header, change["row"])

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

    def known_file_id(self, sha: str) -> str | None:
        with self._lock:
            return self._file_ids.get(sha)

    def known_sha(self, file_id: str) -> str | None:
        with self._lock:
            return next((sha for sha, known in self._file_ids.items() if known == file_id), None)

    def remember_file(self, sha: str, file_id: str):
        """Index a downloaded Drive file so it can be served from the local cache while offline."""
        with self._lock:
            if self._file_ids.get(sha) != file_id:
                self._file_ids[sha] = file_id
                self._save_snapshot()

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
            if self.maintenance:
                raise MaintenancePaused("The parent is maintaining the spreadsheet; changes are paused")
            if operation_id:
                state = self.operation_state(operation_id)
                if state is not None:
                    same = request_sha256 is not None and request_sha256 == self._request_hash(operation_id)
                    raise DuplicateOperation(operation_id, state, same)
            tx = Transaction(self, operation_id, kind, device, summary, request_sha256)
            yield tx
            tx.result = self._commit(tx)

    def _request_hash(self, operation_id: str) -> str | None:
        for op in self._ops:
            if op["id"] == operation_id:
                return op.get("request_sha256")
        receipt = self._data["operation_receipts"].get(operation_id)
        return receipt.get("payload_sha256") if receipt else None

    def _commit(self, tx: Transaction) -> dict:
        changes = tx.changes()
        if not changes:
            return {"operation_id": tx.operation_id, "sync": SAVED, "changes": 0}
        self._seq += 1
        op = {
            "id": tx.operation_id, "seq": self._seq, "kind": tx.kind, "device": tx.device,
            "summary": (tx.summary or tx.kind)[:300], "created_at": utcnow().isoformat(),
            "request_sha256": tx.request_sha256, "payload_sha256": sha256_text(changes),
            "status": PENDING, "attempts": 0, "last_error": None,
            "blobs": list(tx._blobs.values()), "changes": changes,
        }
        self._persist_op(op)  # durable before it becomes visible
        self._apply(self._data, op, check=False)
        self._ops.append(op)
        self._changed.notify_all()
        return {"operation_id": op["id"], "sync": PENDING, "changes": len(changes)}

    def operation_state(self, operation_id: str) -> str | None:
        with self._lock:
            for op in self._ops:
                if op["id"] == operation_id:
                    return op["status"]
            if operation_id in self._data["operation_receipts"] or operation_id in self._base["operation_receipts"]:
                return SAVED
            if list(self.queue_dir.glob(f"saved/*-{operation_id}.json")):
                return SAVED
            return None

    def wait_for(self, operation_id: str, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        with self._lock:
            while True:
                state = self.operation_state(operation_id)
                remaining = deadline - time.monotonic()
                if state != PENDING or remaining <= 0:
                    return state
                self._changed.wait(remaining)

    # ── synchronisation ──────────────────────────────────────────────────────
    def _record_error(self, error: Exception):
        if isinstance(error, AuthorizationRequired):
            self.info["auth_required"] = True
            self.info["online"] = True
        else:
            self.info["online"] = False
        self.info["last_error"] = str(error)

    def flush(self, max_ops: int = 25) -> dict:
        """Send pending operations to Sheets. Safe to call at any time."""
        if self.sheets is None:
            return self.status()
        with self._flush_lock:
            with self._lock:
                if self.maintenance:
                    return self.status()
                ops = [op for op in self._ops if op["status"] == PENDING][:max_ops]
            if not ops:
                return self.status()
            try:
                self._flush(ops)
                self.info["online"] = True
                self.info["auth_required"] = False
                self.info["last_error"] = None
            except (GoogleUnavailable, AuthorizationRequired) as error:
                with self._lock:
                    for op in ops:
                        if op["status"] == PENDING:
                            op["attempts"] += 1
                            op["last_error"] = str(error)
                            self._persist_op(op)
                    self._record_error(error)
            with self._lock:
                self._changed.notify_all()
        return self.status()

    def _upload_blobs(self, ops):
        for op in ops:
            pending_blobs = [b for b in op.get("blobs", []) if not b.get("file_id")]
            for blob in pending_blobs:
                if self.drive is None:
                    raise GoogleUnavailable("Google Drive is not connected")
                file_id = self._file_ids.get(blob["sha"]) or self.drive.find_by_property(
                    blob["folder"], "sha256", blob["sha"])
                if not file_id:
                    data = self.blobs.get(blob["sha"])
                    if data is None:
                        raise GoogleUnavailable(f"Local copy of {blob['name']} is missing")
                    file_id = self.drive.upload(data, blob["name"], blob["mime"], blob["folder"],
                                                {"sha256": blob["sha"], "app": "homeschooling"})
                blob["file_id"] = file_id
                with self._lock:
                    self._file_ids[blob["sha"]] = file_id
                    self._substitute(op, PLACEHOLDER + blob["sha"], file_id)
                    self._persist_op(op)
                    self._save_snapshot()

    def _substitute(self, op, placeholder, file_id):
        for change in op["changes"]:
            if change["row"]:
                change["row"] = [file_id if cell == placeholder else cell for cell in change["row"]]
        for rows in self._data.values():
            for record in rows.values():
                for key, value in record.items():
                    if value == placeholder:
                        record[key] = file_id
        for other in self._ops:
            if other is op:
                continue
            for change in other["changes"]:
                if change["row"] and placeholder in change["row"]:
                    change["row"] = [file_id if cell == placeholder else cell for cell in change["row"]]
                    self._persist_op(other)

    def _layout(self, tabs: list[str]) -> dict:
        ranges = []
        for tab in tabs:
            ranges += [f"{quote_tab(tab)}!1:1", f"{quote_tab(tab)}!A:B"]
        values = self.sheets.get_values(ranges)
        layout = {}
        by_tab = {spec.tab: spec for spec in TABLES.values()}
        for index, tab in enumerate(tabs):
            header = (values[2 * index] or [[]])[0]
            spec = by_tab[tab]
            if header[:len(spec.header)] != spec.header:
                raise _FlushConflict(f"{tab} columns were rearranged; use maintenance mode to repair them")
            ids, revisions = [], []
            for cells in values[2 * index + 1][1:]:
                if not cells or not cells[0]:
                    ids.append(None)
                    revisions.append(None)
                    continue
                ids.append(int(cells[0]) if column_kind(spec, "id") == "int" else cells[0])
                revisions.append(int(cells[1]) if len(cells) > 1 and cells[1] else None)
            layout[tab] = {"ids": ids, "revisions": revisions}
        return layout

    @staticmethod
    def _cells(values: list[str]) -> dict:
        return {"values": [{"userEnteredValue": {"stringValue": v}} for v in values]}

    def _requests(self, op, layout, sheet_ids) -> list[dict]:
        requests = []
        for change in op["changes"]:
            spec = TABLES[change["table"]]
            tab = layout[spec.tab]
            ids = tab["ids"]
            if change["action"] == "insert":
                if change["id"] in ids:
                    raise _FlushConflict(f"{spec.tab} already contains id {change['id']}")
                while ids and ids[-1] is None:
                    ids.pop()
                    tab["revisions"].pop()
                ids.append(change["id"])
                tab["revisions"].append(int(change["row"][1]))
                requests.append({"appendCells": {"sheetId": sheet_ids[spec.tab], "fields": "userEnteredValue",
                                                 "rows": [self._cells(change["row"])]}})
                continue
            matches = [i for i, value in enumerate(ids) if value == change["id"]]
            if len(matches) != 1:
                raise _FlushConflict(f"{spec.tab} id {change['id']} is missing or duplicated in Google Sheets")
            index = matches[0]
            if tab["revisions"][index] != change["base_revision"]:
                raise _FlushConflict(f"{spec.tab} {change['id']} was edited in Google Sheets "
                                     f"(revision {tab['revisions'][index]}, expected {change['base_revision']})")
            if change["action"] == "delete":
                requests.append({"deleteDimension": {"range": {
                    "sheetId": sheet_ids[spec.tab], "dimension": "ROWS",
                    "startIndex": index + 1, "endIndex": index + 2}}})
                del ids[index]
                del tab["revisions"][index]
            else:
                requests.append({"updateCells": {
                    "start": {"sheetId": sheet_ids[spec.tab], "rowIndex": index + 1, "columnIndex": 0},
                    "fields": "userEnteredValue", "rows": [self._cells(change["row"])]}})
                tab["revisions"][index] = change["base_revision"] + 1
        receipt = self._receipt(op)
        receipts = layout[TABLES["operation_receipts"].tab]
        receipts["ids"].append(op["id"])
        receipts["revisions"].append(1)
        requests.append({"appendCells": {"sheetId": sheet_ids[TABLES["operation_receipts"].tab],
                                         "fields": "userEnteredValue",
                                         "rows": [self._cells(row_to_cells(TABLES["operation_receipts"], receipt))]}})
        return requests

    @staticmethod
    def _receipt(op) -> dict:
        return {"id": op["id"], "revision": 1, "updated_at": utcnow(), "payload_sha256": op.get("request_sha256") or op["payload_sha256"],
                "kind": op["kind"], "device": op.get("device"), "summary": op.get("summary"),
                "created_at": datetime.fromisoformat(op["created_at"])}

    def _flush(self, ops):
        self._upload_blobs(ops)
        tabs = sorted({TABLES[c["table"]].tab for op in ops for c in op["changes"]} | {TABLES["operation_receipts"].tab})
        sheet_ids = self.sheets.metadata()
        try:
            layout = self._layout(tabs)
        except _FlushConflict as conflict:
            with self._lock:
                for op in ops:
                    self._mark_reconcile(op, str(conflict), rebuild=False)
                self._rebuild()
            return
        present = set(layout[TABLES["operation_receipts"].tab]["ids"])
        batch, requests = [], []
        for op in ops:
            if op["id"] in present:
                with self._lock:
                    self._mark_saved(op)  # an earlier response was lost after Google applied it
                continue
            snapshot = copy.deepcopy(layout)
            try:
                requests += self._requests(op, layout, sheet_ids)
                batch.append(op)
            except _FlushConflict as conflict:
                layout = snapshot
                with self._lock:
                    self._mark_reconcile(op, str(conflict))
                break
        if not requests:
            return
        with self._lock:
            for op in batch:
                op["attempts"] += 1
                self._persist_op(op)
        self.sheets.batch_update(requests)
        if not self.verify_writes:
            with self._lock:
                for op in batch:
                    self._mark_saved(op)
            return
        verified = self._layout(tabs)
        expected: dict[tuple[str, object], int | None] = {}
        for op in batch:
            for change in op["changes"]:
                tab = TABLES[change["table"]].tab
                expected[(tab, change["id"])] = None if change["action"] == "delete" else int(change["row"][1])
        problems = []
        for (tab, record_id), revision in expected.items():
            ids = verified[tab]["ids"]
            positions = [i for i, value in enumerate(ids) if value == record_id]
            if revision is None and positions:
                problems.append(f"{tab} {record_id} was not deleted")
            elif revision is not None and (len(positions) != 1 or verified[tab]["revisions"][positions[0]] != revision):
                problems.append(f"{tab} {record_id} did not verify")
        receipt_ids = verified[TABLES["operation_receipts"].tab]["ids"]
        with self._lock:
            for op in batch:
                if problems or receipt_ids.count(op["id"]) != 1:
                    self._mark_reconcile(op, "Verification failed: " + "; ".join(problems or ["receipt missing"]))
                else:
                    self._mark_saved(op)

    def _mark_saved(self, op, apply_to_base: bool = True):
        if apply_to_base:
            try:
                self._apply(self._base, op, check=False)
            except _FlushConflict:
                pass
        receipt = self._receipt(op)
        self._base["operation_receipts"][op["id"]] = receipt
        self._data["operation_receipts"][op["id"]] = dict(receipt)
        op["status"] = SAVED
        source = self._op_path(op)
        _atomic_write(self._op_path(op, "saved"), json.dumps(op, ensure_ascii=False))
        source.unlink(missing_ok=True)
        if op in self._ops:
            self._ops.remove(op)
        self.info["last_saved_at"] = utcnow().isoformat()
        self._save_snapshot()
        self._changed.notify_all()

    def _mark_reconcile(self, op, reason: str, rebuild: bool = True):
        op["status"] = RECONCILE
        op["last_error"] = reason
        self._persist_op(op)
        logger.warning("Operation %s needs reconciliation: %s", op["id"], reason)
        if rebuild:
            self._rebuild()
        self._changed.notify_all()

    # ── parent tools ─────────────────────────────────────────────────────────
    def status(self) -> dict:
        with self._lock:
            pending = [op for op in self._ops if op["status"] == PENDING]
            reconcile = [op for op in self._ops if op["status"] == RECONCILE]
            if reconcile:
                state = RECONCILE
            elif pending:
                state = PENDING
            else:
                state = SAVED
            return {
                "state": state, "pending": len(pending), "needs_reconciliation": len(reconcile),
                "maintenance": self.maintenance, "connected": self.sheets is not None, **self.info,
            }

    def unsettled(self) -> list[dict]:
        with self._lock:
            return [{k: op[k] for k in ("id", "seq", "kind", "summary", "status", "created_at", "attempts", "last_error")}
                    | {"changes": [{k: c[k] for k in ("table", "action", "id", "base_revision")} for c in op["changes"]]}
                    for op in self._ops]

    def retry(self, operation_id: str) -> dict:
        with self._flush_lock, self._lock:
            op = self._find_op(operation_id)
            if self.sheets is not None:
                problems = self._pull()
                if problems:
                    raise StoreError("; ".join(problems))
            op["status"] = PENDING
            op["last_error"] = None
            self._persist_op(op)
            self._rebuild()
        return self.flush()

    def discard(self, operation_id: str) -> dict:
        """Remove an operation from the live view while keeping its evidence on disk."""
        with self._flush_lock, self._lock:
            op = self._find_op(operation_id)
            op["status"] = "discarded"
            op["discarded_at"] = utcnow().isoformat()
            _atomic_write(self._op_path(op, "discarded"), json.dumps(op, ensure_ascii=False))
            self._op_path(op).unlink(missing_ok=True)
            self._ops.remove(op)
            self._rebuild()
        return self.status()

    def _find_op(self, operation_id):
        for op in self._ops:
            if op["id"] == operation_id:
                return op
        raise NotFound(f"Operation {operation_id} is not waiting")

    def begin_maintenance(self) -> dict:
        self.flush(max_ops=10_000)
        with self._flush_lock, self._lock:
            self.maintenance = True
            self._save_flags()
        return self.status()

    def end_maintenance(self) -> dict:
        """Reload Sheets, validate every tab and resume writes only when valid."""
        with self._flush_lock, self._lock:
            if self.sheets is None:
                raise StoreError("Google Sheets is not connected")
            previous = copy.deepcopy(self._base)
            problems = self._pull()
            if problems:
                self.info["schema_problems"] = problems
                return {**self.status(), "resumed": False, "problems": problems}
            edited = self._external_edits(previous)
            self.maintenance = False
            self._save_flags()
            self._rebuild()
        if edited:
            # Unmarked parent edits must invalidate earlier queued changes to those rows.
            with self.transaction(kind="maintenance", summary=f"Recorded {len(edited)} spreadsheet edits") as tx:
                for table, record_id in edited:
                    tx.touch(table, record_id)
        self.flush(max_ops=10_000)
        return {**self.status(), "resumed": True, "problems": [], "edited_rows": len(edited)}

    def _external_edits(self, previous) -> list[tuple[str, object]]:
        edited = []
        for name, rows in self._base.items():
            if name == "operation_receipts":
                continue
            for record_id, record in rows.items():
                before = previous.get(name, {}).get(record_id)
                if before is not None and before["revision"] == record["revision"]:
                    strip = lambda r: {k: v for k, v in r.items() if k not in ("updated_at",)}
                    if strip(before) != strip(record):
                        edited.append((name, record_id))
        return edited
