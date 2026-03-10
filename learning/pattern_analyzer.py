"""
Pattern Analyzer — builds time-window heatmaps from raw detections.

Divides each day into N-minute windows (default 5 min = 288 windows/day).
For each (bus_name, camera_id, day_of_week, window),
counts how many detections exist and upserts into arrival_patterns.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc, text

from app.models import BusDetection, BusProfile, ArrivalPattern
from config import TIME_WINDOW_MINUTES

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _time_to_window(dt: datetime) -> str:
    """
    Snap a datetime to the start of its time window.
    E.g.  14:52 with 5-min windows → "14:50"
    """
    minutes = dt.hour * 60 + dt.minute
    window_start = (minutes // TIME_WINDOW_MINUTES) * TIME_WINDOW_MINUTES
    h, m = divmod(window_start, 60)
    return f"{h:02d}:{m:02d}"


def rebuild_patterns(db: Session, days_back: int = 60):
    """
    Full rebuild: scan all detections from the last `days_back` days
    and populate the arrival_patterns table.

    This is the "learning" step — it converts raw detections
    into aggregated heatmap data.
    """
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    print(f"[LEARN] Rebuilding patterns from last {days_back} days...")

    # ── Step 1: Aggregate detections ─────────────────────
    rows = (
        db.query(
            BusDetection.bus_name,
            BusDetection.camera_id,
            BusDetection.created_at,
            BusDetection.destination_conf,
        )
        .filter(
            BusDetection.created_at >= cutoff,
            BusDetection.bus_name.isnot(None),
            BusDetection.bus_name != "",
        )
        .all()
    )

    # Group into (bus, camera, dow, window) → [confidences]
    agg: dict[tuple, list[int]] = {}
    for bus_name, camera_id, created_at, conf in rows:
        dow = created_at.weekday()  # 0=Mon
        window = _time_to_window(created_at)
        key = (bus_name, camera_id, dow, window)
        agg.setdefault(key, []).append(conf or 0)

    # ── Step 2: Upsert into arrival_patterns ─────────────
    upserted = 0
    for (bus_name, camera_id, dow, window), confs in agg.items():
        count = len(confs)
        avg_conf = sum(confs) / count if count else 0

        existing = (
            db.query(ArrivalPattern)
            .filter_by(
                bus_name=bus_name,
                camera_id=camera_id,
                day_of_week=dow,
                time_window=window,
            )
            .first()
        )

        if existing:
            existing.detection_count = count
            existing.avg_confidence = round(avg_conf, 1)
            existing.window_minutes = TIME_WINDOW_MINUTES
        else:
            db.add(ArrivalPattern(
                bus_name=bus_name,
                camera_id=camera_id,
                day_of_week=dow,
                time_window=window,
                window_minutes=TIME_WINDOW_MINUTES,
                detection_count=count,
                avg_confidence=round(avg_conf, 1),
            ))
        upserted += 1

    db.commit()
    print(f"[LEARN] Upserted {upserted} pattern rows ✅")
    return upserted


def update_bus_profile(db: Session, bus_name: str, bus_type: str = None):
    """
    Upsert the bus_profiles table whenever a bus is detected.
    """
    profile = db.query(BusProfile).filter_by(bus_name=bus_name).first()

    if profile:
        profile.last_seen = sqlfunc.now()
        profile.total_detections = (profile.total_detections or 0) + 1
        if bus_type and not profile.bus_type:
            profile.bus_type = bus_type
    else:
        profile = BusProfile(
            bus_name=bus_name,
            bus_type=bus_type,
            total_detections=1,
        )
        db.add(profile)

    db.commit()
    return profile
