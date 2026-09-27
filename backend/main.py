"""Homeschooling home server: one process serving the API and the built frontend."""
import logging
import os
import re
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from dependencies import IdempotencyMiddleware, context, set_context
from routers import annotations, calendar, canvas, checklist, children, documents, progress, scheduler, subjects, \
    system, time_windows, tutor
from security.network import PrivateNetworkMiddleware
from storage import DuplicateOperation, FileUnavailable, OutsideBoundary, RevisionConflict, StoreError

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
FRONTEND_DIST = Path(os.getenv("HOMESCHOOLING_FRONTEND", Path(__file__).resolve().parents[1] / "frontend" / "dist"))


def _keep_host_awake(enable: bool):
    """Ask Windows not to sleep while the shared server runs (the display may still turn off)."""
    if sys.platform != "win32":
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if enable else 0))


class CompressText:
    """Gzip text responses (the app's script, JSON). PDFs and audio are compressed already, and books can be
    large, so their bytes pass through untouched."""

    SKIP = re.compile(r"^/api/(documents/\d+/content|tutor/audio/[^/]+/parts/)")

    def __init__(self, app):
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not self.SKIP.match(scope["path"]):
            return await self.gzip(scope, receive, send)
        return await self.app(scope, receive, send)


class LongCachedAssets(StaticFiles):
    """Built assets carry a content hash in their names, so browsers may keep them for a year."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def create_app(app_context=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app_context is None:
            from app_context import AppContext
            set_context(AppContext())
            context().announce()
        _keep_host_awake(True)
        try:
            yield
        finally:
            _keep_host_awake(False)
            context().shutdown()

    if app_context is not None:
        set_context(app_context)
    app = FastAPI(title="Homeschooling", description="Private home server for one homeschool family",
                  version="3.0.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(PrivateNetworkMiddleware,
                       extra_hosts=(app_context.config.get("allowed_hosts") if app_context else ()) or ())
    app.add_middleware(CompressText)

    app.include_router(system.router, prefix="/api", tags=["System"])
    app.include_router(children.router, prefix="/api/children", tags=["Children"])
    app.include_router(subjects.router, prefix="/api/subjects", tags=["Subjects"])
    app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendar"])
    app.include_router(scheduler.router, prefix="/api/schedule", tags=["Scheduler"])
    app.include_router(checklist.router, prefix="/api/checklist", tags=["Checklist"])
    app.include_router(progress.router, prefix="/api/progress", tags=["Progress"])
    app.include_router(time_windows.router, prefix="/api/time-windows", tags=["Time Windows"])
    app.include_router(canvas.router, prefix="/api/canvas", tags=["Canvas"])
    app.include_router(documents.router, prefix="/api")
    app.include_router(annotations.router, prefix="/api")
    app.include_router(tutor.router, prefix="/api/tutor", tags=["Tutor"])

    @app.exception_handler(RevisionConflict)
    async def revision_conflict(request: Request, exc: RevisionConflict):
        return JSONResponse(status_code=409, content={"detail": {"message": str(exc), "current": _jsonable(exc.current)}})

    @app.exception_handler(DuplicateOperation)
    async def duplicate(request: Request, exc: DuplicateOperation):
        return JSONResponse(status_code=409, content={"detail": str(exc), "operation_id": exc.operation_id,
                                                      "state": exc.state, "same_request": exc.same_request})

    @app.exception_handler(StoreError)
    async def store_error(request: Request, exc: StoreError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(FileUnavailable)
    async def file_unavailable(request: Request, exc: FileUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(OutsideBoundary)
    async def outside(request: Request, exc: OutsideBoundary):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled error on %s %s: %s\n%s", request.method, request.url.path, exc, traceback.format_exc())
        return JSONResponse(status_code=500, content={"detail": "An internal server error occurred. Please try again."})

    @app.get("/api")
    def root():
        return {"message": "Homeschooling home server"}

    if FRONTEND_DIST.exists():
        app.mount("/assets", LongCachedAssets(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            candidate = (FRONTEND_DIST / path).resolve()
            if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
    return app


def _jsonable(record):
    if record is None:
        return None
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in record.items()}


app = create_app() if os.getenv("HOMESCHOOLING_SKIP_APP") != "1" else None
