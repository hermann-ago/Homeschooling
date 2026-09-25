"""Interfaces to Google Sheets and Drive, plus faithful in-memory fakes.

The store only needs three Sheets capabilities (read ranges, list tabs and an
atomic ``spreadsheets.batchUpdate``) and a handful of Drive calls. The fakes
interpret the same request bodies the real API receives, so tests exercise the
exact requests sent to Google.
"""
from __future__ import annotations

import hashlib
import re
import threading
from typing import Protocol


class GoogleUnavailable(Exception):
    """Google could not be reached; the request certainly or possibly failed."""

    def __init__(self, message: str = "Google is unreachable", uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


class AuthorizationRequired(Exception):
    """Stored Google authorization is missing, expired or revoked."""


class OutsideBoundary(PermissionError):
    """A Drive file is outside the configured Homeschooling folder."""


class SheetsGateway(Protocol):
    def metadata(self) -> dict[str, int]: ...
    def get_values(self, ranges: list[str]) -> list[list[list[str]]]: ...
    def batch_update(self, requests: list[dict]) -> None: ...


class DriveGateway(Protocol):
    def upload(self, data: bytes, name: str, mime_type: str, folder: str, app_properties: dict) -> str: ...
    def find_by_property(self, folder: str, key: str, value: str) -> str | None: ...
    def download(self, file_id: str) -> bytes: ...
    def metadata(self, file_id: str) -> dict: ...


_RANGE = re.compile(r"^'?(?P<tab>.+?)'?(?:!(?P<cells>.+))?$")


def _column_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def quote_tab(tab: str) -> str:
    return "'" + tab.replace("'", "''") + "'"


class FakeSheets:
    """In-memory spreadsheet honouring batchUpdate atomicity and fault injection."""

    def __init__(self):
        self.tabs: dict[str, dict] = {}
        self._next_sheet_id = 100
        self.lock = threading.Lock()
        self.calls: list[str] = []
        self.faults: list[str] = []  # offline | auth | lost_response | offline_after_read

    def fail_next(self, *kinds: str):
        self.faults.extend(kinds)

    def _fault(self, applied: bool = False):
        if not self.faults:
            return
        kind = self.faults[0]
        if kind == "lost_response" and applied:
            self.faults.pop(0)
            raise GoogleUnavailable("Timed out waiting for Sheets", uncertain=True)
        if kind in ("offline", "auth") and not applied:
            self.faults.pop(0)
            if kind == "auth":
                raise AuthorizationRequired("Google authorization was revoked")
            raise GoogleUnavailable("Network unreachable")

    def metadata(self) -> dict[str, int]:
        self.calls.append("metadata")
        self._fault()
        return {title: tab["sheet_id"] for title, tab in self.tabs.items()}

    def get_values(self, ranges: list[str]) -> list[list[list[str]]]:
        self.calls.append("get_values")
        self._fault()
        with self.lock:
            return [self._read(r) for r in ranges]

    def _read(self, range_: str) -> list[list[str]]:
        match = _RANGE.match(range_)
        tab = match["tab"].replace("''", "'")
        rows = self.tabs[tab]["rows"]
        cells = match["cells"]
        if not cells:
            selected = rows
            columns = None
        elif re.fullmatch(r"\d+:\d+", cells):
            start, end = (int(x) for x in cells.split(":"))
            selected = rows[start - 1:end]
            columns = None
        else:
            first, last = cells.split(":")
            columns = (_column_index(first), _column_index(last))
            selected = rows
        result = []
        for row in selected:
            values = row if columns is None else row[columns[0]:columns[1] + 1]
            result.append(list(values))
        while result and not any(result[-1]):
            result.pop()
        # Sheets trims trailing empty cells in each row.
        return [self._trim(r) for r in result]

    @staticmethod
    def _trim(row):
        row = list(row)
        while row and row[-1] == "":
            row.pop()
        return row

    def batch_update(self, requests: list[dict]) -> None:
        self.calls.append("batch_update")
        self._fault()
        with self.lock:
            staged = {title: {"sheet_id": tab["sheet_id"], "rows": [list(r) for r in tab["rows"]]}
                      for title, tab in self.tabs.items()}
            by_id = {tab["sheet_id"]: title for title, tab in staged.items()}
            next_id = self._next_sheet_id
            for request in requests:  # any error aborts the whole batch
                (kind, body), = request.items()
                if kind == "addSheet":
                    title = body["properties"]["title"]
                    if title in staged:
                        raise ValueError(f"Duplicate sheet {title}")
                    staged[title] = {"sheet_id": next_id, "rows": []}
                    by_id[next_id] = title
                    next_id += 1
                elif kind == "updateCells":
                    rows = staged[by_id[body["start"]["sheetId"]]]["rows"]
                    start = body["start"]["rowIndex"]
                    col = body["start"].get("columnIndex", 0)
                    for offset, row in enumerate(body["rows"]):
                        while len(rows) <= start + offset:
                            rows.append([])
                        target = rows[start + offset]
                        values = [v.get("userEnteredValue", {}).get("stringValue", "") for v in row["values"]]
                        while len(target) < col + len(values):
                            target.append("")
                        target[col:col + len(values)] = values
                elif kind == "appendCells":
                    rows = staged[by_id[body["sheetId"]]]["rows"]
                    while rows and not any(rows[-1]):
                        rows.pop()
                    for row in body["rows"]:
                        rows.append([v.get("userEnteredValue", {}).get("stringValue", "") for v in row["values"]])
                elif kind == "deleteDimension":
                    rng = body["range"]
                    rows = staged[by_id[rng["sheetId"]]]["rows"]
                    if rng["endIndex"] > len(rows):
                        raise ValueError("Delete range is outside the sheet")
                    del rows[rng["startIndex"]:rng["endIndex"]]
                elif kind in ("updateSheetProperties", "repeatCell", "updateSpreadsheetProperties", "autoResizeDimensions"):
                    continue
                elif kind == "updateCellsClear":
                    continue
                else:
                    raise ValueError(f"Unsupported request {kind}")
            self.tabs = staged
            self._next_sheet_id = next_id
        self._fault(applied=True)

    # Helpers for tests and parent-maintenance scenarios.
    def rows(self, tab: str) -> list[list[str]]:
        return [self._trim(r) for r in self.tabs[tab]["rows"]]

    def edit_cell(self, tab: str, row: int, column: int, value: str):
        rows = self.tabs[tab]["rows"]
        while len(rows[row]) <= column:
            rows[row].append("")
        rows[row][column] = value


class FakeDrive:
    """Minimal Drive with folders keyed by role and an enforced root boundary."""

    def __init__(self):
        self.files: dict[str, dict] = {}
        self.faults: list[str] = []
        self._counter = 0

    def _fault(self):
        if self.faults:
            kind = self.faults.pop(0)
            if kind == "auth":
                raise AuthorizationRequired("Google authorization was revoked")
            raise GoogleUnavailable("Network unreachable")

    def add_file(self, data: bytes, name: str, folder: str = "Books", mime_type: str = "application/pdf",
                 app_properties: dict | None = None, file_id: str | None = None) -> str:
        self._counter += 1
        file_id = file_id or f"file{self._counter:04d}"
        self.files[file_id] = {
            "id": file_id, "name": name, "folder": folder, "mimeType": mime_type, "data": data,
            "appProperties": dict(app_properties or {}), "size": str(len(data)),
            "sha256Checksum": hashlib.sha256(data).hexdigest(), "inside_root": True,
        }
        return file_id

    def upload(self, data, name, mime_type, folder, app_properties):
        self._fault()
        return self.add_file(data, name, folder, mime_type, app_properties)

    def find_by_property(self, folder, key, value):
        self._fault()
        for item in self.files.values():
            if item["folder"] == folder and item["appProperties"].get(key) == value:
                return item["id"]
        return None

    def download(self, file_id):
        self._fault()
        item = self.files.get(file_id)
        if not item:
            raise FileNotFoundError(file_id)
        if not item["inside_root"]:
            raise OutsideBoundary("File is outside the Homeschooling folder")
        return item["data"]

    def metadata(self, file_id):
        self._fault()
        item = self.files.get(file_id)
        if not item:
            raise FileNotFoundError(file_id)
        if not item["inside_root"]:
            raise OutsideBoundary("File is outside the Homeschooling folder")
        return {k: v for k, v in item.items() if k != "data"}

    def list_pdfs(self):
        self._fault()
        return [{k: v for k, v in item.items() if k != "data"} for item in self.files.values()
                if item["mimeType"] == "application/pdf" and item["inside_root"]]
