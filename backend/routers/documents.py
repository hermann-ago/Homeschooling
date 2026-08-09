from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_family_user
from database import get_db
from models import Document
from schemas.documents import DocumentResponse, StorageUsageResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/usage", response_model=StorageUsageResponse)
def storage_usage(db: Session = Depends(get_db), user_id: str = Depends(require_family_user)):
    used = db.query(func.coalesce(func.sum(Document.size_bytes), 0)).filter(
        Document.owner_id == user_id
    ).scalar()
    return StorageUsageResponse(bytes_used=int(used or 0))


@router.get("/{document_id:int}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db), user_id: str = Depends(require_family_user)):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == user_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/by-path/lookup", response_model=DocumentResponse)
def get_document_by_path(
    blob_path: str = Query(..., min_length=5, max_length=600),
    db: Session = Depends(get_db),
    user_id: str = Depends(require_family_user),
):
    document = db.query(Document).filter(
        Document.blob_path == blob_path,
        Document.owner_id == user_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
