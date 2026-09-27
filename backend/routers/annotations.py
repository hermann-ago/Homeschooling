"""Per-page PDF handwriting. Strokes live in the Drive folder's ``Annotations`` as
JSON files; the annotations table holds the file path, checksum and revision."""
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from app_context import request_operation as write
from dependencies import context, require_member, store
from schemas.annotations import AnnotationPageResponse, AnnotationPageUpdate
from storage import RevisionConflict, layout
from storage import FileUnavailable

router = APIRouter(prefix="/annotations", tags=["PDF Annotations"], dependencies=[Depends(require_member)])
MAX_REQUEST_BYTES = 1_048_576


def _context_check(child_id: int, document_id: int, page_number: int) -> None:
    child = store().get("children", child_id)
    document = store().get("documents", document_id)
    if not child or not document:
        raise HTTPException(status_code=404, detail="Annotation page not found")
    if page_number < 1 or page_number > document["page_count"]:
        raise HTTPException(status_code=422, detail="PDF page is outside this document")


def _row(child_id, document_id, page_number):
    return store().first("annotations", child_id=child_id, document_id=document_id, page_number=page_number)


def _response(row: dict | None, child_id, document_id, page_number) -> AnnotationPageResponse:
    if row is None:
        return AnnotationPageResponse(child_id=child_id, document_id=document_id, page_number=page_number,
                                      strokes=[], revision=0, updated_at=None)
    try:
        strokes = json.loads(context().file_bytes(row["file_path"], row["sha256"]))["strokes"]
    except FileUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Handwriting for this page cannot be opened: {exc}") from exc
    return AnnotationPageResponse(child_id=child_id, document_id=document_id, page_number=page_number,
                                  strokes=strokes, revision=row["revision"], updated_at=row["updated_at"])


def _conflict(row):
    raise HTTPException(status_code=409, detail={
        "message": "Annotations changed on another device",
        "current": _response(row, row["child_id"], row["document_id"], row["page_number"]).model_dump(mode="json"),
    })


@router.get("/children/{child_id}/documents/{document_id}/pages/{page_number}", response_model=AnnotationPageResponse)
def get_page_annotations(child_id: int, document_id: int, page_number: int):
    _context_check(child_id, document_id, page_number)
    return _response(_row(child_id, document_id, page_number), child_id, document_id, page_number)


@router.put("/children/{child_id}/documents/{document_id}/pages/{page_number}", response_model=AnnotationPageResponse)
def save_page_annotations(child_id: int, document_id: int, page_number: int, payload: AnnotationPageUpdate,
                          request: Request):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="Annotation payload cannot exceed 1 MiB")
    _context_check(child_id, document_id, page_number)
    strokes = [stroke.model_dump(mode="json") for stroke in payload.strokes]
    body = json.dumps({"child_id": child_id, "document_id": document_id, "page_number": page_number,
                       "strokes": strokes}, separators=(",", ":"), sort_keys=True).encode()
    existing = _row(child_id, document_id, page_number)
    if payload.base_revision == 0 and existing:
        _conflict(existing)
    if payload.base_revision and not existing:
        raise HTTPException(status_code=409, detail="Annotation revision is no longer available")
    try:
        with write("annotations.save", f"Handwriting on page {page_number}") as tx:
            # Each saved version is its own content-addressed file, so earlier revisions remain.
            name = f"annotations-child{child_id}-doc{document_id}-p{page_number}-{hashlib.sha256(body).hexdigest()[:12]}.json"
            folder = layout.for_child_document(tx, child_id, document_id, layout.HANDWRITING)
            path, sha = tx.add_blob(body, folder, name, "application/json")
            values = {"file_path": path, "sha256": sha, "stroke_count": len(strokes)}
            if existing:
                tx.update("annotations", existing["id"], values, expected_revision=payload.base_revision)
            else:
                tx.insert("annotations", {"child_id": child_id, "document_id": document_id,
                                          "page_number": page_number, **values})
    except RevisionConflict:
        _conflict(_row(child_id, document_id, page_number))
    return _response(_row(child_id, document_id, page_number), child_id, document_id, page_number)
