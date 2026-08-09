import logging
import os
import secrets
import traceback

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auth import SetupRequest, create_first_family_account, require_family_user
from database import get_db
from models import (AppSetting, BlockedDay, CanvasAIContent, CanvasInsert, Child,
                    Completion, CurriculumTopic, Document, ScheduledSlot, Subject,
                    TimeWindow)
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from routers import calendar, canvas, checklist, children, documents, progress, scheduler, subjects, time_windows

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Homeschool Scheduler",
    description="Private hosted scheduling app for one homeschool family",
    version="2.0.0",
    docs_url=None if os.getenv("VERCEL") else "/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

protected = [Depends(require_family_user)]
app.include_router(children.router, prefix="/api/children", tags=["Children"], dependencies=protected)
app.include_router(subjects.router, prefix="/api/subjects", tags=["Subjects"], dependencies=protected)
app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendar"], dependencies=protected)
app.include_router(scheduler.router, prefix="/api/schedule", tags=["Scheduler"], dependencies=protected)
app.include_router(checklist.router, prefix="/api/checklist", tags=["Checklist"], dependencies=protected)
app.include_router(progress.router, prefix="/api/progress", tags=["Progress"], dependencies=protected)
app.include_router(time_windows.router, prefix="/api/time-windows", tags=["Time Windows"], dependencies=protected)
app.include_router(canvas.router, prefix="/api/canvas", tags=["Canvas"], dependencies=protected)
app.include_router(documents.router, prefix="/api", dependencies=protected)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url, exc)
    logger.error(traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": "An internal server error occurred. Please try again."})


@app.get("/api")
def root():
    return {"message": "Homeschool Scheduler API"}


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/setup")
def setup_family(payload: SetupRequest, db=Depends(get_db)):
    """One-time, code-protected creation of the shared family account."""
    return create_first_family_account(payload, db)


@app.post("/api/internal/import-legacy", include_in_schema=False)
def import_legacy_snapshot(
    payload: dict,
    x_migration_code: str = Header(default=""),
    db=Depends(get_db),
):
    """Temporary, code-gated bulk importer used only to move the local backup."""
    # MIGRATION_CODE is used when the deployment environment exposes it. The
    # existing server-only Blob credential is a secure fallback for the local
    # migration utility, and this route is removed immediately after import.
    expected = os.getenv("MIGRATION_CODE") or os.getenv("BLOB_READ_WRITE_TOKEN", "")
    if not expected or not secrets.compare_digest(expected, x_migration_code):
        raise HTTPException(status_code=404, detail="Not found")
    owner_id = payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=422, detail="Migration owner is required")

    models = {
        "documents": Document, "children": Child, "blocked_days": BlockedDay,
        "subjects": Subject, "curriculum_topics": CurriculumTopic,
        "time_windows": TimeWindow, "scheduled_slots": ScheduledSlot,
        "completions": Completion, "canvas_inserts": CanvasInsert,
        "canvas_ai_content": CanvasAIContent, "app_settings": AppSetting,
    }
    try:
        for name, values in payload.get("tables", {}).items():
            model = models.get(name)
            if model is None or not isinstance(values, list):
                raise HTTPException(status_code=422, detail="Invalid migration table")
            if not values:
                continue
            if name in {"documents", "children", "blocked_days", "app_settings"}:
                for value in values:
                    if value.get("owner_id") != owner_id:
                        raise HTTPException(status_code=422, detail="Owner mismatch")
            table = model.__table__
            statement = postgres_insert(table).values(values)
            update_values = {column.name: statement.excluded[column.name] for column in table.columns if column.name != "id"}
            db.execute(statement.on_conflict_do_update(index_elements=[table.c.id], set_=update_values))
        for table in models.values():
            db.execute(text(
                "select setval(pg_get_serial_sequence(:table_name, 'id'), "
                "coalesce((select max(id) from " + table.__table__.fullname + "), 1), true)"
            ), {"table_name": table.__table__.fullname})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"status": "imported", "tables": {name: len(values) for name, values in payload.get("tables", {}).items()}}
