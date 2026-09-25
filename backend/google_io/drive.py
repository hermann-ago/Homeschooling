"""Google Drive REST client implementing ``storage.gateway.DriveGateway``.

The Homeschooling folder is the application boundary. ``drive.readonly`` can
see the whole Drive, so every read walks the file's parents and refuses files
outside the configured root.
"""
from __future__ import annotations

import json
import threading
import uuid

from storage.gateway import OutsideBoundary

FILES = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
FIELDS = "id,name,mimeType,size,sha256Checksum,md5Checksum,modifiedTime,parents,appProperties,trashed"


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class DriveClient:
    def __init__(self, rest, root_folder_id: str, folders: dict[str, str] | None = None):
        self.rest = rest
        self.root = root_folder_id
        self.folders = dict(folders or {})
        self._inside: dict[str, bool] = {root_folder_id: True}
        self._lock = threading.Lock()

    # ── boundary ─────────────────────────────────────────────────────────────
    def _raw_metadata(self, file_id: str) -> dict:
        return self.rest.request("GET", f"{FILES}/{file_id}", params={"fields": FIELDS,
                                                                      "supportsAllDrives": "true"}).json()

    def inside_root(self, file_id: str, _depth: int = 0) -> bool:
        with self._lock:
            if file_id in self._inside:
                return self._inside[file_id]
        if _depth > 40:
            return False
        parents = self._raw_metadata(file_id).get("parents") or []
        result = any(self.inside_root(parent, _depth + 1) for parent in parents)
        with self._lock:
            self._inside[file_id] = result
        return result

    def _require_inside(self, file_id: str) -> None:
        if not self.inside_root(file_id):
            raise OutsideBoundary("That file is outside the Homeschooling folder")

    def metadata(self, file_id: str) -> dict:
        self._require_inside(file_id)
        return self._raw_metadata(file_id)

    def download(self, file_id: str) -> bytes:
        self._require_inside(file_id)
        return self.rest.request("GET", f"{FILES}/{file_id}", params={"alt": "media"}).content

    # ── app folders and files ────────────────────────────────────────────────
    def list_children(self, folder_id: str, query: str = "") -> list[dict]:
        items, token = [], None
        while True:
            params = {"q": f"'{_q(folder_id)}' in parents and trashed=false" + (f" and {query}" if query else ""),
                      "fields": f"nextPageToken,files({FIELDS})", "pageSize": 1000,
                      "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
            if token:
                params["pageToken"] = token
            body = self.rest.request("GET", FILES, params=params).json()
            items += body.get("files", [])
            token = body.get("nextPageToken")
            if not token:
                return items

    def ensure_folder(self, name: str) -> str:
        existing = self.list_children(self.root, f"mimeType='{FOLDER_MIME}' and name='{_q(name)}'")
        if existing:
            folder_id = existing[0]["id"]
        else:
            folder_id = self.rest.request("POST", FILES, params={"fields": "id"}, idempotent=False, json={
                "name": name, "mimeType": FOLDER_MIME, "parents": [self.root],
                "appProperties": {"app": "homeschooling", "role": name}}).json()["id"]
        self.folders[name] = folder_id
        with self._lock:
            self._inside[folder_id] = True
        return folder_id

    def find_workbook(self, name: str) -> str | None:
        found = self.list_children(self.root, f"mimeType='{SHEET_MIME}' and name='{_q(name)}'")
        return found[0]["id"] if found else None

    def create_workbook(self, name: str) -> str:
        return self.rest.request("POST", FILES, params={"fields": "id"}, idempotent=False, json={
            "name": name, "mimeType": SHEET_MIME, "parents": [self.root],
            "appProperties": {"app": "homeschooling", "role": "database"}}).json()["id"]

    def find_by_property(self, folder: str, key: str, value: str) -> str | None:
        folder_id = self.folders.get(folder) or self.ensure_folder(folder)
        found = self.list_children(folder_id, f"appProperties has {{ key='{_q(key)}' and value='{_q(value)}' }}")
        return found[0]["id"] if found else None

    def upload(self, data: bytes, name: str, mime_type: str, folder: str, app_properties: dict) -> str:
        folder_id = self.folders.get(folder) or self.ensure_folder(folder)
        metadata = {"name": name, "parents": [folder_id], "appProperties": app_properties, "mimeType": mime_type}
        if len(data) <= 5 * 1024 * 1024:
            boundary = uuid.uuid4().hex
            body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n").encode() \
                + data + f"\r\n--{boundary}--".encode()
            response = self.rest.request("POST", UPLOAD, params={"uploadType": "multipart", "fields": "id"},
                                         content=body, idempotent=False,
                                         headers={"Content-Type": f"multipart/related; boundary={boundary}"})
            file_id = response.json()["id"]
        else:
            session = self.rest.request("POST", UPLOAD, params={"uploadType": "resumable", "fields": "id"},
                                        json=metadata, idempotent=False,
                                        headers={"X-Upload-Content-Type": mime_type,
                                                 "X-Upload-Content-Length": str(len(data))})
            response = self.rest.request("PUT", session.headers["Location"], content=data, idempotent=True,
                                         headers={"Content-Type": mime_type})
            file_id = response.json()["id"]
        with self._lock:
            self._inside[file_id] = True
        return file_id

    def list_pdfs(self) -> list[dict]:
        """Every PDF beneath the root (breadth first), for linking existing books by file ID."""
        result, queue, seen = [], [self.root], set()
        while queue:
            folder = queue.pop(0)
            if folder in seen:
                continue
            seen.add(folder)
            for item in self.list_children(folder):
                with self._lock:
                    self._inside[item["id"]] = True
                if item["mimeType"] == FOLDER_MIME:
                    queue.append(item["id"])
                elif item["mimeType"] == "application/pdf":
                    result.append(item)
        return result
