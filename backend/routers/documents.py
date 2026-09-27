from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from dependencies import context, require_family, store
from schemas.documents import DocumentResponse, StorageUsageResponse
from storage import FileUnavailable, OutsideBoundary, layout
from utils import get_or_404

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/usage", response_model=StorageUsageResponse)
def storage_usage():
    return StorageUsageResponse(bytes_used=sum(d["size_bytes"] or 0 for d in store().all("documents")))


@router.get("/{document_id:int}", response_model=DocumentResponse)
def get_document(document_id: int):
    return get_or_404(store(), "documents", document_id, "Document")


def document_bytes(document: dict) -> bytes:
    try:
        data = context().file_bytes(document["file_path"], document["sha256"])
    except OutsideBoundary as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=502, detail="The stored document is not a PDF")
    return data


@router.get("/{document_id:int}/content")
def document_content(document_id: int, request: Request):
    """PDF bytes read from the synced Homeschooling folder.

    The book's checksum is its ETag, so a device that already has the book gets
    a quick 304 without the file being read (or re-checked) again.
    """
    document = get_or_404(store(), "documents", document_id, "Document")
    etag = f'"{document["sha256"]}"' if document.get("sha256") else None
    headers = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
               "Content-Disposition": "inline", **({"ETag": etag} if etag else {})}
    if etag and etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return Response(content=document_bytes(document), media_type="application/pdf", headers=headers)


@router.get("/drive/books", dependencies=[Depends(require_family)])
def drive_books():
    """PDFs beneath the Homeschooling folder, with whether each is already linked."""
    try:
        pdfs = context().files.list_pdfs()
    except FileUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    linked = {d["file_path"] for d in store().all("documents")}
    return [{**f, "linked": f["path"] in linked} for f in pdfs if not f["path"].startswith(layout.BACKUPS + "/")]
