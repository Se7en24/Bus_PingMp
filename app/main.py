"""
FastAPI application — entry point.
Creates tables on startup, schedules background pattern analysis,
and includes all routers.
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.database import engine, Base, SessionLocal
from app.routers import detections, analytics
from app import models  # noqa: F401 — ensures models are registered
from learning.pattern_analyzer import rebuild_patterns
from learning.frequency_analyzer import analyze_bus_frequency
from config import ANALYSIS_INTERVAL_SECONDS


# ── Background Scheduler ─────────────────────────────────

scheduler = BackgroundScheduler()


def _scheduled_rebuild():
    """Runs every ANALYSIS_INTERVAL_SECONDS to rebuild patterns."""
    db = SessionLocal()
    try:
        rebuild_patterns(db, days_back=60)
    except Exception as e:
        print(f"[SCHEDULER ERROR] {e}")
    finally:
        db.close()


def _scheduled_frequency_analysis():
    """Runs weekly to compute bus frequency stats."""
    db = SessionLocal()
    try:
        analyze_bus_frequency(db, camera_id="CAM_TO_KANJIRAPALLY", weeks_back=4)
    except Exception as e:
        print(f"[SCHEDULER ERROR] Frequency analysis failed: {e}")
    finally:
        db.close()


# ── App Lifespan ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    print("[STARTUP] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[STARTUP] Tables ready ✅")

    # Start background pattern analyzer
    scheduler.add_job(
        _scheduled_rebuild,
        "interval",
        seconds=ANALYSIS_INTERVAL_SECONDS,
        id="pattern_rebuild",
        replace_existing=True,
    )
    # Weekly frequency analysis (every Sunday at midnight)
    scheduler.add_job(
        _scheduled_frequency_analysis,
        "cron",
        day_of_week="sun",
        hour=0,
        minute=0,
        id="weekly_frequency",
        replace_existing=True,
    )
    scheduler.start()
    print(
        f"[STARTUP] Pattern analyzer scheduled "
        f"(every {ANALYSIS_INTERVAL_SECONDS}s) ✅"
    )
    print("[STARTUP] Weekly frequency analysis scheduled (Sun 00:00) ✅")

    # Run frequency analysis once at startup
    try:
        _scheduled_frequency_analysis()
    except Exception as e:
        print(f"[STARTUP] Initial frequency analysis skipped: {e}")

    yield  # — app is running —

    # SHUTDOWN
    scheduler.shutdown(wait=False)
    print("[SHUTDOWN] Scheduler stopped")


# ── FastAPI App ──────────────────────────────────────────

app = FastAPI(
    title="Bus PingMp — Smart Bus Detection & Learning",
    description=(
        "Detects buses via camera, reads destination boards with OCR, "
        "and learns arrival patterns over time."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(detections.router)
app.include_router(analytics.router)


# Serve static files (dashboard assets)
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
def root():
    """Redirect to the student dashboard by default."""
    html_path = _static_dir / "student.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    return {
        "app": "Bus PingMp",
        "status": "running",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "student": "/student",
    }


@app.get("/dashboard")
def dashboard():
    """Serve the admin SmartBus Dashboard."""
    html_path = _static_dir / "dashboard.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    return {"error": "Dashboard not found. Create static/dashboard.html"}


@app.get("/student")
def student_dashboard():
    """Serve the student-facing bus prediction dashboard."""
    html_path = _static_dir / "student.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    return {"error": "Student dashboard not found. Create static/student.html"}
