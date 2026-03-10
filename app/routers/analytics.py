"""
Analytics routes — predictions, heatmaps, bus profiles, frequency analysis.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import BusProfile, BusFrequency, ArrivalPattern
from app.schemas import (
    BusProfileOut,
    BusFrequencyOut,
    PredictionResponse,
    HeatmapResponse,
)
from learning.pattern_analyzer import rebuild_patterns
from learning.predictor import predict_upcoming, get_bus_heatmap
from learning.frequency_analyzer import analyze_bus_frequency

router = APIRouter(prefix="/analytics", tags=["Analytics / Learning"])


@router.get("/buses", response_model=list[BusProfileOut])
def list_buses(db: Session = Depends(get_db)):
    """
    List all known buses with their stats
    (first seen, last seen, total detections).
    """
    return (
        db.query(BusProfile)
        .order_by(BusProfile.total_detections.desc())
        .all()
    )


@router.get("/bus/{bus_name}", response_model=BusProfileOut)
def get_bus_profile(bus_name: str, db: Session = Depends(get_db)):
    """
    Get profile for a specific bus.
    """
    profile = db.query(BusProfile).filter_by(bus_name=bus_name).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Bus '{bus_name}' not found")
    return profile


@router.get("/predictions", response_model=PredictionResponse)
def get_predictions(
    camera_id: str = Query("CAM_TO_KANJIRAPALLY"),
    hours_ahead: float = Query(2.0, ge=0.5, le=12.0),
    db: Session = Depends(get_db),
):
    """
    Predict which buses are likely to arrive in the next N hours.

    Based on historical arrival patterns built from detection data.
    The system "learns" by aggregating detections into 5-minute
    time windows and tracking how often each bus appears.

    Example response after 2-3 weeks of data:
    ```json
    {
      "camera_id": "CAM_TO_KANJIRAPALLY",
      "current_day": "Monday",
      "predictions": [
        {
          "bus_name": "ANGEL",
          "bus_type": "PRIVATE",
          "expected_window": "14:45–14:50",
          "likelihood_pct": 87.5,
          "avg_confidence": 82.3,
          "sample_size": 14
        }
      ]
    }
    ```
    """
    return predict_upcoming(
        db,
        camera_id=camera_id,
        now=datetime.now(),
        hours_ahead=hours_ahead,
    )


@router.get("/heatmap/{bus_name}", response_model=HeatmapResponse)
def get_heatmap(
    bus_name: str,
    camera_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get the full week-long arrival heatmap for a bus.
    Shows when this bus typically appears at each time window
    for every day of the week.
    """
    result = get_bus_heatmap(db, bus_name, camera_id)
    if not result["heatmap"]:
        raise HTTPException(
            status_code=404,
            detail=f"No pattern data for bus '{bus_name}'. Run /analytics/rebuild first.",
        )
    return result


@router.post("/rebuild")
def trigger_rebuild(
    days_back: int = Query(60, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """
    Manually trigger a full pattern rebuild.
    Scans all detections from the last N days and rebuilds
    the arrival_patterns heatmap table.

    This is the "learning" step. It also runs automatically
    every 5 minutes in the background.
    """
    count = rebuild_patterns(db, days_back=days_back)
    return {
        "message": "Pattern rebuild complete ✅",
        "patterns_upserted": count,
        "days_analyzed": days_back,
    }


@router.get("/summary")
def analytics_summary(
    camera_id: str = Query("CAM_TO_KANJIRAPALLY"),
    db: Session = Depends(get_db),
):
    """
    Quick summary — total buses known, total detections,
    total pattern rows.
    """
    total_buses = db.query(BusProfile).count()
    total_patterns = db.query(ArrivalPattern).count()
    total_detections = sum(
        p.total_detections or 0
        for p in db.query(BusProfile).all()
    )

    return {
        "total_unique_buses": total_buses,
        "total_detections": total_detections,
        "total_pattern_windows": total_patterns,
        "camera_id": camera_id,
    }


# ── Frequency / Learning Endpoints ───────────────────────

@router.get("/frequency", response_model=list[BusFrequencyOut])
def get_all_frequencies(
    camera_id: str = Query("CAM_TO_KANJIRAPALLY"),
    db: Session = Depends(get_db),
):
    """
    Get weekly frequency analysis for all buses.
    Returns how often each bus comes, typical times, reliability.
    """
    rows = (
        db.query(BusFrequency)
        .filter_by(camera_id=camera_id)
        .order_by(BusFrequency.avg_days_per_week.desc())
        .all()
    )

    results = []
    for r in rows:
        results.append(BusFrequencyOut(
            bus_name=r.bus_name,
            camera_id=r.camera_id,
            avg_days_per_week=r.avg_days_per_week,
            typical_times=json.loads(r.typical_times) if r.typical_times else [],
            regularity_score=r.regularity_score,
            trend=r.trend or "stable",
            weeks_analyzed=r.weeks_analyzed,
            total_sightings=r.total_sightings,
        ))
    return results


@router.get("/frequency/{bus_name}", response_model=BusFrequencyOut)
def get_bus_frequency(
    bus_name: str,
    camera_id: str = Query("CAM_TO_KANJIRAPALLY"),
    db: Session = Depends(get_db),
):
    """
    Get weekly frequency analysis for a specific bus.
    """
    row = (
        db.query(BusFrequency)
        .filter_by(bus_name=bus_name, camera_id=camera_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No frequency data for '{bus_name}'. Run /analytics/analyze first.",
        )
    return BusFrequencyOut(
        bus_name=row.bus_name,
        camera_id=row.camera_id,
        avg_days_per_week=row.avg_days_per_week,
        typical_times=json.loads(row.typical_times) if row.typical_times else [],
        regularity_score=row.regularity_score,
        trend=row.trend or "stable",
        weeks_analyzed=row.weeks_analyzed,
        total_sightings=row.total_sightings,
    )


@router.post("/analyze")
def trigger_frequency_analysis(
    camera_id: str = Query("CAM_TO_KANJIRAPALLY"),
    weeks_back: int = Query(4, ge=1, le=52),
    db: Session = Depends(get_db),
):
    """
    Manually trigger a full frequency analysis.
    Analyzes how often each bus appears, at what times, and how
    consistent the schedule is.
    """
    results = analyze_bus_frequency(db, camera_id=camera_id, weeks_back=weeks_back)
    return {
        "message": "Frequency analysis complete ✅",
        "buses_analyzed": len(results),
        "weeks_analyzed": weeks_back,
        "results": results,
    }
