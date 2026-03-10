"""
Arrival Predictor — queries arrival_patterns to predict upcoming buses.

Given the current day/time, returns a ranked list of buses
most likely to arrive in the next N hours.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import ArrivalPattern, BusProfile, BusDetection
from config import TIME_WINDOW_MINUTES

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _generate_windows(start_time: datetime, hours_ahead: float = 2.0):
    """
    Generate all time window strings from start_time to start_time + hours_ahead.
    """
    windows = []
    minutes_total = int(hours_ahead * 60)
    current = start_time

    for _ in range(0, minutes_total, TIME_WINDOW_MINUTES):
        h, m = current.hour, current.minute
        window_start = (h * 60 + m) // TIME_WINDOW_MINUTES * TIME_WINDOW_MINUTES
        wh, wm = divmod(window_start, 60)
        windows.append(f"{wh:02d}:{wm:02d}")
        current += timedelta(minutes=TIME_WINDOW_MINUTES)

    return list(dict.fromkeys(windows))  # deduplicate, preserve order


def predict_upcoming(
    db: Session,
    camera_id: str,
    now: datetime = None,
    hours_ahead: float = 2.0,
):
    """
    Predict which buses are likely to arrive in the next `hours_ahead` hours.

    How likelihood is calculated:
    - For each bus in a given time window, we look at detection_count
    - We estimate total_days = total days the camera has been running
      (from bus_profiles or a rough guess)
    - likelihood = (detection_count / total_days_observed) * 100
    - Capped at 100%

    Returns:
        list of dicts sorted by likelihood (highest first)
    """
    if now is None:
        now = datetime.now()

    dow = now.weekday()
    upcoming_windows = _generate_windows(now, hours_ahead)

    # Query patterns for this camera, this day of week, upcoming windows
    patterns = (
        db.query(ArrivalPattern)
        .filter(
            ArrivalPattern.camera_id == camera_id,
            ArrivalPattern.day_of_week == dow,
            ArrivalPattern.time_window.in_(upcoming_windows),
        )
        .order_by(desc(ArrivalPattern.detection_count))
        .all()
    )

    # Get bus profiles for enrichment
    bus_names = list({p.bus_name for p in patterns})
    profiles = {
        bp.bus_name: bp
        for bp in db.query(BusProfile).filter(BusProfile.bus_name.in_(bus_names)).all()
    } if bus_names else {}

    # Get the most common destination for each bus (from recent detections)
    bus_destinations = {}
    if bus_names:
        from sqlalchemy import func as sqlfunc
        dest_rows = (
            db.query(
                BusDetection.bus_name,
                BusDetection.destination_en,
                sqlfunc.count().label("cnt"),
            )
            .filter(BusDetection.bus_name.in_(bus_names))
            .filter(BusDetection.destination_en.isnot(None))
            .group_by(BusDetection.bus_name, BusDetection.destination_en)
            .order_by(sqlfunc.count().desc())
            .all()
        )
        for row in dest_rows:
            if row.bus_name not in bus_destinations:
                bus_destinations[row.bus_name] = row.destination_en

    # Calculate actual weeks of data for proper likelihood
    from sqlalchemy import func as sqlfunc2
    date_range = db.query(
        sqlfunc2.min(BusDetection.created_at),
        sqlfunc2.max(BusDetection.created_at),
    ).first()

    if date_range and date_range[0] and date_range[1]:
        first_det = date_range[0]
        last_det = date_range[1]
        # If they're strings, parse them
        if isinstance(first_det, str):
            first_det = datetime.fromisoformat(first_det)
        if isinstance(last_det, str):
            last_det = datetime.fromisoformat(last_det)
        total_days = max((last_det - first_det).days, 1)
        # How many times has this weekday occurred in our data range?
        total_weeks = max(total_days / 7, 1)
        # Each weekday appears roughly total_weeks times
        weekday_occurrences = max(int(total_weeks), 1)
    else:
        weekday_occurrences = 1

    predictions = []
    seen_buses = set()

    for pattern in patterns:
        if pattern.bus_name in seen_buses:
            continue
        seen_buses.add(pattern.bus_name)

        profile = profiles.get(pattern.bus_name)

        # Likelihood = what % of weeks did this bus appear in this window?
        likelihood = min(
            (pattern.detection_count / weekday_occurrences) * 100,
            99.0
        )

        # Human-readable reliability tier
        if likelihood >= 80:
            reliability = "Very Regular"
        elif likelihood >= 50:
            reliability = "Regular"
        elif likelihood >= 25:
            reliability = "Occasional"
        else:
            reliability = "Rare"

        window_end_m = (
            int(pattern.time_window[:2]) * 60 +
            int(pattern.time_window[3:]) +
            TIME_WINDOW_MINUTES
        )
        wh, wm = divmod(window_end_m, 60)
        window_label = f"{pattern.time_window}\u2013{wh:02d}:{wm:02d}"

        predictions.append({
            "bus_name": pattern.bus_name,
            "bus_type": profile.bus_type if profile else None,
            "destination": bus_destinations.get(pattern.bus_name, "Unknown"),
            "expected_window": window_label,
            "time_sort_key": pattern.time_window,
            "likelihood_pct": round(likelihood, 1),
            "reliability": reliability,
            "avg_confidence": round(pattern.avg_confidence, 1),
            "sample_size": pattern.detection_count,
        })

    # Sort by likelihood descending
    predictions.sort(key=lambda x: x["likelihood_pct"], reverse=True)

    return {
        "camera_id": camera_id,
        "current_day": DAY_NAMES[dow],
        "predictions": predictions,
    }


def get_bus_heatmap(db: Session, bus_name: str, camera_id: str = None):
    """
    Return the full week-long heatmap for a specific bus.
    """
    query = db.query(ArrivalPattern).filter(ArrivalPattern.bus_name == bus_name)
    if camera_id:
        query = query.filter(ArrivalPattern.camera_id == camera_id)

    patterns = query.order_by(
        ArrivalPattern.day_of_week,
        ArrivalPattern.time_window,
    ).all()

    total = sum(p.detection_count for p in patterns)

    heatmap = [
        {
            "day_of_week": p.day_of_week,
            "day_name": DAY_NAMES[p.day_of_week],
            "time_window": p.time_window,
            "detection_count": p.detection_count,
            "avg_confidence": round(p.avg_confidence, 1),
        }
        for p in patterns
    ]

    return {
        "bus_name": bus_name,
        "camera_id": camera_id or "ALL",
        "total_detections": total,
        "heatmap": heatmap,
    }
