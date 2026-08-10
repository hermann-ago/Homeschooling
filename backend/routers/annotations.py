from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import require_family_user
from database import get_db
from models import Child, Document, PdfPageAnnotation
from schemas.annotations import AnnotationPageResponse, AnnotationPageUpdate


router = APIRouter(prefix="/annotations", tags=["PDF Annotations"])
MAX_REQUEST_BYTES = 1_048_576


def _owned_context(
    db: Session,
    child_id: int,
    document_id: int,
    page_number: int,
    user_id: str,
) -> tuple[Child, Document]:
    child = db.query(Child).filter(Child.id == child_id, Child.owner_id == user_id).first()
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == user_id,
    ).first()
    if not child or not document:
        raise HTTPException(status_code=404, detail="Annotation page not found")
    if page_number < 1 or page_number > document.page_count:
        raise HTTPException(status_code=422, detail="PDF page is outside this document")
    return child, document


def _empty_page(child_id: int, document_id: int, page_number: int) -> AnnotationPageResponse:
    return AnnotationPageResponse(
        child_id=child_id,
        document_id=document_id,
        page_number=page_number,
        strokes=[],
        revision=0,
        updated_at=None,
    )


def _annotation_response(annotation: PdfPageAnnotation) -> AnnotationPageResponse:
    return AnnotationPageResponse.model_validate(annotation)


def _conflict(annotation: PdfPageAnnotation):
    raise HTTPException(
        status_code=409,
        detail={
            "message": "Annotations changed on another device",
            "current": _annotation_response(annotation).model_dump(mode="json"),
        },
    )


@router.get(
    "/children/{child_id}/documents/{document_id}/pages/{page_number}",
    response_model=AnnotationPageResponse,
)
def get_page_annotations(
    child_id: int,
    document_id: int,
    page_number: int,
    user_id: str = Depends(require_family_user),
    db: Session = Depends(get_db),
):
    _owned_context(db, child_id, document_id, page_number, user_id)
    annotation = db.query(PdfPageAnnotation).filter(
        PdfPageAnnotation.owner_id == user_id,
        PdfPageAnnotation.child_id == child_id,
        PdfPageAnnotation.document_id == document_id,
        PdfPageAnnotation.page_number == page_number,
    ).first()
    return _annotation_response(annotation) if annotation else _empty_page(
        child_id, document_id, page_number
    )


@router.put(
    "/children/{child_id}/documents/{document_id}/pages/{page_number}",
    response_model=AnnotationPageResponse,
)
def save_page_annotations(
    child_id: int,
    document_id: int,
    page_number: int,
    payload: AnnotationPageUpdate,
    request: Request,
    user_id: str = Depends(require_family_user),
    db: Session = Depends(get_db),
):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="Annotation payload cannot exceed 1 MiB")

    _owned_context(db, child_id, document_id, page_number, user_id)
    filters = (
        PdfPageAnnotation.owner_id == user_id,
        PdfPageAnnotation.child_id == child_id,
        PdfPageAnnotation.document_id == document_id,
        PdfPageAnnotation.page_number == page_number,
    )
    stroke_data = [stroke.model_dump(mode="json") for stroke in payload.strokes]
    now = datetime.now(timezone.utc)

    if payload.base_revision == 0:
        existing = db.query(PdfPageAnnotation).filter(*filters).first()
        if existing:
            _conflict(existing)
        annotation = PdfPageAnnotation(
            owner_id=user_id,
            child_id=child_id,
            document_id=document_id,
            page_number=page_number,
            strokes=stroke_data,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        db.add(annotation)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.query(PdfPageAnnotation).filter(*filters).first()
            if existing:
                _conflict(existing)
            raise
        db.refresh(annotation)
        return _annotation_response(annotation)

    updated = db.query(PdfPageAnnotation).filter(
        *filters,
        PdfPageAnnotation.revision == payload.base_revision,
    ).update(
        {
            PdfPageAnnotation.strokes: stroke_data,
            PdfPageAnnotation.revision: payload.base_revision + 1,
            PdfPageAnnotation.updated_at: now,
        },
        synchronize_session=False,
    )
    if updated != 1:
        db.rollback()
        existing = db.query(PdfPageAnnotation).filter(*filters).first()
        if existing:
            _conflict(existing)
        raise HTTPException(status_code=409, detail="Annotation revision is no longer available")

    db.commit()
    annotation = db.query(PdfPageAnnotation).filter(*filters).one()
    return _annotation_response(annotation)
