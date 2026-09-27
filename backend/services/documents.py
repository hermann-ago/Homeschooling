"""PDF inspection and document records for books in the synced Homeschooling folder."""
from __future__ import annotations

import hashlib
import io

from pypdf import PdfReader

from storage import layout

MAX_PDF_BYTES = 262_144_000


def inspect_pdf(data: bytes) -> tuple[int, str]:
    """Page count and the text of the first 15 pages (usually the contents)."""
    if not data.startswith(b"%PDF"):
        raise ValueError("That file is not a PDF")
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:15]:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return len(reader.pages), "\n\n".join(parts).strip()


def find_by_checksum(db, sha256: str) -> dict | None:
    return next((d for d in db.all("documents") if d["sha256"] == sha256), None)


def add_uploaded_document(tx, data: bytes, filename: str, page_count: int, subject_id: int) -> dict:
    """Save the book into the subject's Books folder (Drive for desktop uploads it).

    An identical book already in the app is reused where it is, even if another
    child's subject added it first.
    """
    sha = hashlib.sha256(data).hexdigest()
    existing = find_by_checksum(tx, sha)
    if existing:
        return existing
    path, sha = tx.add_blob(data, layout.for_subject(tx, subject_id, layout.BOOKS), filename, "application/pdf")
    return tx.insert("documents", {"file_path": path, "original_filename": filename, "size_bytes": len(data),
                                   "page_count": page_count, "sha256": sha, "source": "uploaded"})


def add_drive_document(tx, path: str, name: str, size: int, page_count: int, sha256: str) -> dict:
    """Reference a book already in the Homeschooling folder by its relative path (no copy)."""
    existing = next((d for d in tx.all("documents") if d["file_path"] == path), None) \
        or find_by_checksum(tx, sha256)
    if existing:
        return existing
    return tx.insert("documents", {"file_path": path, "original_filename": name, "size_bytes": size,
                                   "page_count": page_count, "sha256": sha256, "source": "drive"})
