"""Files in the Homeschooling folder of the synced Google Drive (Drive for desktop).

Books, handwriting, audio, student work, tutor content and backups are ordinary
files in that folder; Drive for desktop uploads them. The database stores paths
relative to the folder, plus SHA-256 checksums so a moved or renamed book can be
found again. Nothing outside the folder can be read or written.

With Drive's default "stream files" mode, a file is downloaded the first time it
is opened; mark the Homeschooling folder "Available offline" so books open
without internet.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
from pathlib import Path, PurePosixPath

APP_FOLDERS = ("Books", "Student Work", "Audio", "Annotations", "Tutor Content", "Backups")


class OutsideBoundary(PermissionError):
    """A path is outside the Homeschooling folder."""


class FileUnavailable(OSError):
    """The folder or file cannot be read right now (not synced, offline or missing)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .")
    return cleaned[:150] or "file"


class DriveFolder:
    def __init__(self, root):
        self.root = Path(root) if root else None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.root) and self.root.is_dir()

    def require(self):
        if not self.available:
            raise FileUnavailable(f"The Homeschooling folder is not available ({self.root}). "
                                  "Check that Google Drive for desktop is running and signed in.")

    def ensure_folders(self) -> list[str]:
        self.require()
        created = []
        for name in APP_FOLDERS:
            folder = self.root / name
            if not folder.exists():
                folder.mkdir()
                created.append(name)
        return created

    def resolve(self, relative: str) -> Path:
        """The absolute path for a stored reference, refusing anything outside the folder."""
        self.require()
        if not relative:
            raise OutsideBoundary("Empty file reference")
        pure = PurePosixPath(relative.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts or re.match(r"^[A-Za-z]:", relative):
            raise OutsideBoundary("File references must stay inside the Homeschooling folder")
        path = (self.root / Path(*pure.parts)).resolve()
        if path != self.root.resolve() and self.root.resolve() not in path.parents:
            raise OutsideBoundary("File references must stay inside the Homeschooling folder")
        return path

    def relative(self, path: Path) -> str:
        path = Path(path).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise OutsideBoundary(f"{path} is outside the Homeschooling folder")
        return path.relative_to(root).as_posix()

    def read(self, relative: str, sha256: str | None = None) -> bytes:
        path = self.resolve(relative)
        try:
            data = path.read_bytes()
        except FileNotFoundError as error:
            raise FileUnavailable(f"{relative} is missing from the Homeschooling folder") from error
        except OSError as error:  # e.g. a streamed file while offline
            raise FileUnavailable(f"{relative} cannot be opened now ({error}). If the internet is down, "
                                  "mark the Homeschooling folder 'Available offline' in Google Drive.") from error
        if sha256 and sha256_bytes(data) != sha256:
            raise FileUnavailable(f"{relative} does not match its recorded checksum")
        return data

    def write(self, folder: str, name: str, data: bytes) -> tuple[str, str]:
        """Write a new file atomically; identical content under the same name is reused."""
        relative, sha, _ = self.write_new(folder, name, data)
        return relative, sha

    def write_new(self, folder: str, name: str, data: bytes) -> tuple[str, str, bool]:
        """Like ``write``; also says whether a new file was created (False when reused)."""
        self.require()
        if folder not in APP_FOLDERS:
            raise OutsideBoundary(f"Unknown app folder {folder}")
        sha = sha256_bytes(data)
        directory = self.root / folder
        directory.mkdir(exist_ok=True)
        stem, suffix = os.path.splitext(safe_name(name))
        with self._lock:
            candidate, number = directory / f"{stem}{suffix}", 1
            while candidate.exists():
                if candidate.stat().st_size == len(data) and sha256_path(candidate) == sha:
                    return self.relative(candidate), sha, False
                number += 1
                candidate = directory / f"{stem}-{number}{suffix}"
            temporary = directory / f".{candidate.name}.{os.getpid()}.part"
            with open(temporary, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, candidate)
        return self.relative(candidate), sha, True

    def remove(self, relative: str):
        """Delete a file this server just created (used when its transaction fails)."""
        self.resolve(relative).unlink(missing_ok=True)

    def list_pdfs(self) -> list[dict]:
        self.require()
        result = []
        for directory, folders, files in os.walk(self.root):
            folders[:] = [f for f in folders if not f.startswith(".")]
            for name in files:
                if name.lower().endswith(".pdf") and not name.startswith("."):
                    path = Path(directory) / name
                    try:
                        size = path.stat().st_size
                    except OSError:
                        continue
                    result.append({"path": self.relative(path), "name": name, "size": size})
        return sorted(result, key=lambda f: f["path"].lower())

    def find_by_checksum(self, sha256: str, size: int | None = None, suffix: str = ".pdf") -> str | None:
        """Locate a file by content (only files of the same size are hashed)."""
        self.require()
        for directory, folders, files in os.walk(self.root):
            folders[:] = [f for f in folders if not f.startswith(".")]
            for name in files:
                if suffix and not name.lower().endswith(suffix):
                    continue
                path = Path(directory) / name
                try:
                    if size is not None and path.stat().st_size != size:
                        continue
                    if sha256_path(path) == sha256:
                        return self.relative(path)
                except OSError:
                    continue
        return None
