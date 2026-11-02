"""Saved source collections; assembling a collection never starts AI preparation.

A subject's books with their roles, order and editions. Saving a collection
sets up any new book (chapter map and lessons); prepared books and started
lessons keep their current roles and versions.
"""
from __future__ import annotations

import hashlib
import io
import uuid

from pypdf import PdfReader

from services.documents import MAX_PDF_BYTES, add_drive_document
from storage import RevisionConflict
from storage.store import sha256_text
from .books import READING_ROLES, PRACTICE_ROLES, book_name


def binding(db, subject_id):
    return next(iter(db.find("subject_collections", subject_id=subject_id)), None)


def key_targets(book):
    return list(dict.fromkeys([*(book.get('answer_for_ids') or []), *([book['answer_for_id']] if book.get('answer_for_id') else [])]))


def view(db, subject_id):
    subject = db.get("subjects", subject_id)
    linked = binding(db, subject_id)
    collection = db.get("book_collections", linked["collection_id"]) if linked else None
    prepared = {b["document_id"]: b for b in db.find("subject_books", subject_id=subject_id) if not b["archived"]}
    if collection:
        members = [b for b in db.find("collection_books", collection_id=collection["id"]) if not b["archived"]]
    else:
        members = []
        ordered = sorted(prepared.values(), key=lambda b: (b["role"] not in READING_ROLES, b["document_id"]))
        main = next((b["id"] for b in ordered if b["role"] in READING_ROLES and any(
            t["is_core"] and not t["archived"] for t in db.find("topics", subject_id=subject_id, document_id=b["document_id"]))), None)
        main = main or next((b["id"] for b in ordered if b["role"] in READING_ROLES), None)
        for position, b in enumerate(ordered):
            members.append({"id": b["id"], "document_id": b["document_id"], "role": b["role"], "edition": "",
                            "position": position, "is_main": b["id"] == main,
                            "companion_id": b["companion_id"] if b["role"] in ("workbook", "test") else None,
                            "answer_for_id": b.get("answer_for_id") if b["role"] == "answer_key" else None,
                            "answer_for_ids": key_targets(b) if b['role']=='answer_key' else []})
    books = []
    for member in sorted(members, key=lambda b: b["position"]):
        doc = db.get("documents", member["document_id"])
        old = prepared.get(doc["id"])
        books.append({"key": member["id"], "document_id": doc["id"], "role": member["role"],
                      "edition": member["edition"] or "", "position": member["position"], "is_main": member["is_main"],
                      "companion_key": member["companion_id"], "answer_for_key": member["answer_for_id"],
                      "answer_for_keys": key_targets(member),
                      "name": book_name(doc["original_filename"]), "path": doc["file_path"],
                      "page_count": doc["page_count"], "sha256": doc["sha256"],
                      "prepared_status": old["status"] if old else "not_prepared"})
    version = db.get("collection_versions", collection["active_version"]) if collection and collection["active_version"] else None
    return {"id": collection["id"] if collection else None, "shared": bool(collection and len(db.find("subject_collections", collection_id=collection["id"])) > 1), "name": collection["name"] if collection else f"{subject['name']} books",
            "revision": collection["revision"] if collection else 0, "version": version["number"] if version else 0,
            "version_id": version["id"] if version else None, "books": books}


def inspect_sources(ctx, books):
    """Inspect new PDFs outside the database transaction, with no provider call."""
    inspected = []
    for item in books:
        row = dict(item)
        if row.get("document_id") is not None:
            doc = ctx.store.get("documents", row["document_id"])
            if not doc:
                raise ValueError("Choose an existing book or upload its PDF")
            row["document"] = doc
        else:
            path = row["path"]
            # Resolve first to enforce the Drive boundary and bound the read.
            source = ctx.files.resolve(path)
            if source.stat().st_size > MAX_PDF_BYTES:
                raise ValueError("Choose a PDF smaller than 250 MiB")
            with source.open("rb") as stream:
                data = stream.read(MAX_PDF_BYTES + 1)
            if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
                raise ValueError("Choose a PDF smaller than 250 MiB")
            try:
                pages = len(PdfReader(io.BytesIO(data)).pages)
            except Exception as exc:
                raise ValueError("This PDF could not be read") from exc
            if pages < 1:
                raise ValueError("Choose a PDF with at least one page")
            sha = hashlib.sha256(data).hexdigest()
            existing = next((d for d in ctx.store.all("documents") if d["file_path"] == path), None)
            if existing and existing["sha256"] != sha:
                raise ValueError("This PDF changed since it was saved. Upload the new edition under a new filename.")
            row["new_document"] = {"path": path, "name": path.rsplit("/", 1)[-1], "size": len(data), "pages": pages, "sha": sha}
        inspected.append(row)
    return inspected


def save(tx, subject_id, name, expected_revision, inspected):
    linked = binding(tx, subject_id)
    collection = tx.get("book_collections", linked["collection_id"]) if linked else None
    if expected_revision != (collection["revision"] if collection else 0):
        raise RevisionConflict("This collection changed on another device. Reopen it before saving.", collection)
    keys = [b["key"] for b in inspected]
    if len(set(keys)) != len(keys):
        raise ValueError("Each book must appear once in the collection")
    if len({b["position"] for b in inspected}) != len(inspected):
        raise ValueError("Choose a distinct position for each book")
    by_key = {b["key"]: b for b in inspected}
    prior_members={b['id']:b for b in tx.find('collection_books',collection_id=collection['id'])} if collection else {}
    reading = [b for b in inspected if b["role"] in READING_ROLES]
    if any(b["is_main"] and b["role"] not in READING_ROLES for b in inspected) or sum(b["is_main"] for b in reading) != bool(reading):
        raise ValueError("Choose one main textbook or combined book")
    for b in inspected:
        companion = by_key.get(b.get("companion_key"))
        prior=prior_members.get(b['key'])
        if 'answer_for_keys' not in b and prior and b.get('answer_for_key')==prior.get('answer_for_id'):
            b['answer_for_keys']=key_targets(prior)
        targets = list(dict.fromkeys([*(b.get('answer_for_keys') or []), *([b['answer_for_key']] if b.get('answer_for_key') else [])]))
        b['answer_for_keys']=targets
        if b.get("companion_key") and (not companion or companion["role"] not in READING_ROLES or companion is b):
            raise ValueError("Choose a companion textbook in this collection")
        if b.get("companion_key") and b["role"] not in ("workbook", "test"):
            raise ValueError("Only workbooks and tests need a companion textbook")
        if b["role"] == "answer_key":
            if not targets or any((target:=by_key.get(k)) is None or target['role'] not in PRACTICE_ROLES or target is b for k in targets):
                raise ValueError("Choose the exact workbooks or combined books this answer key belongs to")
            b['answer_for_key']=targets[0]
        elif targets:
            raise ValueError("Only answer keys can have a matching workbook")
        if b["role"] in ("workbook", "test") and not b.get("companion_key") and len(reading) == 1:
            b["companion_key"] = reading[0]["key"]
    if not collection:
        cid = "collection-" + uuid.uuid4().hex
        collection = tx.insert("book_collections", {"id": cid, "name": name})
        tx.insert("subject_collections", {"id": f"subject-collection-{subject_id}", "subject_id": subject_id, "collection_id": cid})
    cid = collection["id"]
    members = {b["document_id"]: b for b in tx.find("collection_books", collection_id=cid)}
    resolved = []
    for b in sorted(inspected, key=lambda b: b["position"]):
        doc = b.get("document")
        if not doc:
            n = b["new_document"]
            doc = add_drive_document(tx, n["path"], n["name"], n["size"], n["pages"], n["sha"])
            if doc["sha256"] != n["sha"]:
                raise ValueError("This PDF changed while the collection was being saved")
        member = members.get(doc["id"])
        resolved.append({"input": b, "document": doc, "id": member["id"] if member else "collection-book-" + uuid.uuid4().hex})
    if len({r["document"]["id"] for r in resolved}) != len(resolved):
        raise ValueError("This PDF is already selected. Keep one copy of each book in the collection.")
    ids = {r["input"]["key"]: r["id"] for r in resolved}
    manifest_books = []
    for r in resolved:
        b, doc = r["input"], r["document"]
        manifest_books.append({"id": r["id"], "document_id": doc["id"], "sha256": doc["sha256"], "role": b["role"],
            "edition": b["edition"].strip(), "position": b["position"], "is_main": b["is_main"],
            "companion_id": ids.get(b.get("companion_key")), "answer_for_id": ids.get(b.get("answer_for_key")),
            "answer_for_ids":[ids[k] for k in b['answer_for_keys']]})
    manifest = {"name": name, "books": manifest_books}
    fingerprint = sha256_text(manifest)
    prior = tx.get("collection_versions", collection["active_version"]) if collection.get("active_version") else None
    if prior and prior["fingerprint"] == fingerprint:
        return
    # A sibling's source collection must not change because this subject edits
    # its books. Fork on an actual edit; content caches remain reusable.
    if linked and len(tx.find("subject_collections", collection_id=cid)) > 1:
        cid = "collection-" + uuid.uuid4().hex
        collection = tx.insert("book_collections", {"id": cid, "name": name})
        tx.update("subject_collections", linked["id"], {"collection_id": cid})
        remap = {b["id"]: "collection-book-" + uuid.uuid4().hex for b in manifest_books}
        manifest_books = [{**b, "id": remap[b["id"]], "companion_id": remap.get(b["companion_id"]), "answer_for_id": remap.get(b["answer_for_id"]),
                           'answer_for_ids':[remap[k] for k in b['answer_for_ids']]} for b in manifest_books]
        manifest = {"name": name, "books": manifest_books}
        fingerprint = sha256_text(manifest)
        prior, members = None, {}
    # Insert members before setting links, so references can point forward.
    for b in manifest_books:
        if not tx.get("collection_books", b["id"]):
            tx.insert("collection_books", {k: v for k, v in {**b, "collection_id": cid}.items()
                                          if k not in ("sha256", "companion_id", "answer_for_id")})
    for b in manifest_books:
        tx.update("collection_books", b["id"], {k: v for k, v in {**b, "archived": False}.items() if k not in ("id", "sha256")})
    selected = {b["id"] for b in manifest_books}
    for member in members.values():
        if member["id"] not in selected and not member["archived"]:
            tx.update("collection_books", member["id"], {"archived": True})
    vid = "collection-version-" + uuid.uuid4().hex
    tx.insert("collection_versions", {"id": vid, "collection_id": cid, "number": prior["number"] + 1 if prior else 1,
                                      "fingerprint": fingerprint, "manifest": manifest})
    tx.update("book_collections", cid, {"name": name, "active_version": vid}, expected_revision=expected_revision if linked and cid == linked["collection_id"] else None)
