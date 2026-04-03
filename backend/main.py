import os
import logging
import traceback
import io
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader, PdfWriter
from dotenv import load_dotenv

from database import engine, Base
from routers import children, subjects, calendar, scheduler, checklist, progress, time_windows, canvas
# Import all models so Base.metadata.create_all catches them
import models  # noqa: F401

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Create all tables (including new AppSetting table)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Homeschool Scheduler",
    description="A local scheduling app for homeschool families",
    version="1.0.0",
)

# Serve uploaded PDFs
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# CORS — allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(children.router, prefix="/children", tags=["Children"])
app.include_router(subjects.router, prefix="/subjects", tags=["Subjects"])
app.include_router(calendar.router, prefix="/calendar", tags=["Calendar"])
app.include_router(scheduler.router, prefix="/schedule", tags=["Scheduler"])
app.include_router(checklist.router, prefix="/checklist", tags=["Checklist"])
app.include_router(progress.router, prefix="/progress", tags=["Progress"])
app.include_router(time_windows.router, prefix="/time-windows", tags=["Time Windows"])
app.include_router(canvas.router, prefix="/canvas", tags=["Canvas"])


# Global error handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please try again.",
            "error_type": type(exc).__name__,
        },
    )


@app.get("/")
def root():
    return {"message": "Homeschool Scheduler API", "docs": "/docs"}


@app.get("/pdf/slice")
def get_pdf_slice(path: str, start: int, end: int):
    # Security check: ensure the path is within uploads directory
    if ".." in path or not (path.startswith("uploads/") or path.startswith("uploads\\")):
        raise HTTPException(status_code=400, detail="Invalid path")
        
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF not found")
        
    try:
        reader = PdfReader(path)
        writer = PdfWriter()
        
        start_idx = max(0, start - 1)
        end_idx = min(len(reader.pages) - 1, end - 1)
        
        for i in range(start_idx, end_idx + 1):
            writer.add_page(reader.pages[i])
            
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        
        return Response(
            content=output.read(),
            media_type="application/pdf",
        )
    except Exception as e:
        logger.error(f"Failed to slice PDF {path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create PDF slice")


@app.get("/health")
def health_check():
    return {"status": "ok"}
