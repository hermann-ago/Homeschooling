"""PDF inspection and document records for books kept in Google Drive."""
from __future__ import annotations

import hashlib
import io

from pypdf import PdfReader

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


def add_uploaded_document(tx, data: bytes, filename: str, page_count: int) -> dict:
    """Keep the bytes locally and queue the Drive upload; reuse an identical book."""
    sha = hashlib.sha256(data).hexdigest()
    existing = find_by_checksum(tx, sha)
    if existing:
        return existing
    file_id, sha = tx.add_blob(data, "Books", filename, "application/pdf")
    return tx.insert("documents", {"drive_file_id": file_id, "original_filename": filename, "size_bytes": len(data),
                                   "page_count": page_count, "sha256": sha, "source": "uploaded"})


def add_drive_document(tx, metadata: dict, page_count: int, sha256: str) -> dict:
    """Reference an existing book beneath the Homeschooling folder by file ID (no copy)."""
    existing = next((d for d in tx.all("documents") if d["drive_file_id"] == metadata["id"]), None) \
        or find_by_checksum(tx, sha256)
    if existing:
        return existing
    return tx.insert("documents", {"drive_file_id": metadata["id"], "original_filename": metadata["name"],
                                   "size_bytes": int(metadata.get("size") or 0), "page_count": page_count,
                                   "sha256": sha256, "source": "drive"})
