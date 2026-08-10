import logging
import os
import traceback

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auth import SetupRequest, create_first_family_account, require_family_user
from database import get_db
from routers import annotations, calendar, canvas, checklist, children, documents, progress, scheduler, subjects, time_windows

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
app.include_router(annotations.router, prefix="/api", dependencies=protected)


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
