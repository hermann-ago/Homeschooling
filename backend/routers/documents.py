from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from dependencies import context, require_member, require_parent, store
from schemas.documents import DocumentResponse, StorageUsageResponse
from storage.gateway import AuthorizationRequired, GoogleUnavailable, OutsideBoundary
from utils import get_or_404

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/usage", response_model=StorageUsageResponse, dependencies=[Depends(require_member)])
def storage_usage():
    return StorageUsageResponse(bytes_used=sum(d["size_bytes"] or 0 for d in store().all("documents")))


@router.get("/{document_id:int}", response_model=DocumentResponse, dependencies=[Depends(require_member)])
def get_document(document_id: int):
    return get_or_404(store(), "documents", document_id, "Document")


def document_bytes(document: dict) -> bytes:
    try:
        data = context().file_bytes(document["drive_file_id"], document["sha256"])
    except OutsideBoundary as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthorizationRequired as exc:
        raise HTTPException(status_code=503, detail="This book is not cached yet and Google needs a parent to "
                                                    "reconnect on the host computer") from exc
    except GoogleUnavailable as exc:
        raise HTTPException(status_code=503, detail="This book is not cached on the home server and Google "
                                                    "Drive is unreachable") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=502, detail="The stored document is not a PDF")
    return data


@router.get("/{document_id:int}/content", dependencies=[Depends(require_member)])
def document_content(document_id: int):
    """PDF bytes proxied from Drive through the home server and cached locally."""
    document = get_or_404(store(), "documents", document_id, "Document")
    data = document_bytes(document)
    return Response(content=data, media_type="application/pdf", headers={
        "Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline"})


@router.get("/drive/books", dependencies=[Depends(require_parent)])
def drive_books():
    """PDFs beneath the Homeschooling folder, with whether each is already linked."""
    ctx = context()
    if ctx.drive is None:
        raise HTTPException(status_code=503, detail="Connect Google Drive first")
    linked_ids = {d["drive_file_id"] for d in store().all("documents")}
    linked_sha = {d["sha256"] for d in store().all("documents") if d["sha256"]}
    return [{"id": f["id"], "name": f["name"], "size": int(f.get("size") or 0),
             "linked": f["id"] in linked_ids or f.get("sha256Checksum") in linked_sha}
            for f in ctx.drive.list_pdfs()]
