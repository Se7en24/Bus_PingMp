"""
Frequency Analyzer — weekly deep analysis of bus arrival patterns.

Computes per-bus statistics:
- avg_days_per_week: how many days/week the bus shows up
- typical_times: most common arrival time clusters
- regularity_score: 0-100 how consistent the schedule is
- trend: increasing / stable / decreasing over recent weeks
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc

from app.models import BusDetection, BusProfile, BusFrequency
from config import TIME_WINDOW_MINUTES


def _snap_to_window(dt: datetime) -> str:
    """Snap a datetime to its 5-min window string, e.g. '14:50'."""
    minutes = dt.hour * 60 + dt.minute
    w = (minutes // TIME_WINDOW_MINUTES) * TIME_WINDOW_MINUTES
    h, m = divmod(w, 60)
    return f"{h:02d}:{m:02d}"


def _cluster_times(time_counts: dict[str, int], min_count: int = 2) -> list[str]:
    """
    Find the most common arrival times from a {window: count} dict.
    Merge adjacent windows into a single representative time.
    Returns up to 5 most common time strings sorted chronologically.
    """
    if not time_counts:
        return []

    # Filter out rare windows
    filtered = {t: c for t, c in time_counts.items() if c >= min_count}
    if not filtered:
        # Fall back to top windows even if count < min_count
        filtered = time_counts

    # Sort by time
    sorted_times = sorted(filtered.items(), key=lambda x: x[0])

    # Merge adjacent windows (within 10 min of each other)
    clusters = []
    current_cluster = [sorted_times[0]]

    for i in range(1, len(sorted_times)):
        t_prev = sorted_times[i - 1][0]
        t_curr = sorted_times[i][0]

        prev_min = int(t_prev[:2]) * 60 + int(t_prev[3:])
        curr_min = int(t_curr[:2]) * 60 + int(t_curr[3:])

        if curr_min - prev_min <= 10:
            current_cluster.append(sorted_times[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [sorted_times[i]]

    clusters.append(current_cluster)

    # Pick the representative time (highest count) from each cluster
    representatives = []
    for cluster in clusters:
        best = max(cluster, key=lambda x: x[1])
        representatives.append((best[0], sum(c for _, c in cluster)))

    # Sort by total count descending, take top 5
    representatives.sort(key=lambda x: x[1], reverse=True)
    top = [t for t, _ in representatives[:5]]
    top.sort()  # chronological order

    return top


def _calculate_regularity(weekly_day_counts: list[int]) -> int:
    """
    Calculate regularity score (0-100) based on week-to-week consistency.
    100 = appears every week with same frequency.
    0 = completely random / appeared only once.
    """
    if not weekly_day_counts or len(weekly_day_counts) < 2:
        return 0

    mean = sum(weekly_day_counts) / len(weekly_day_counts)
    if mean == 0:
        return 0

    # Coefficient of variation (lower = more regular)
    variance = sum((x - mean) ** 2 for x in weekly_day_counts) / len(weekly_day_counts)
    std_dev = variance ** 0.5
    cv = std_dev / mean if mean > 0 else 1.0

    # Convert to 0-100 score (lower CV = higher score)
    # CV of 0 → 100, CV of 1+ → ~20
    score = max(0, min(100, int(100 * (1 - cv * 0.8))))
    return score


def _detect_trend(weekly_counts: list[int]) -> str:
    """
    Detect if a bus is appearing more or less often recently.
    Compare last 2 weeks vs earlier weeks.
    """
    if len(weekly_counts) < 3:
        return "stable"

    recent = sum(weekly_counts[-2:]) / 2
    earlier = sum(weekly_counts[:-2]) / max(len(weekly_counts) - 2, 1)

    if earlier == 0:
        return "increasing" if recent > 0 else "stable"

    ratio = recent / earlier

    if ratio > 1.3:
        return "increasing"
    elif ratio < 0.7:
        return "decreasing"
    return "stable"


def analyze_bus_frequency(
    db: Session,
    camera_id: str = "CAM_TO_KANJIRAPALLY",
    weeks_back: int = 4,
) -> list[dict]:
    """
    Full frequency analysis for all buses seen by a camera.

    For each bus, computes:
    - avg_days_per_week: average number of unique days per week
    - typical_times: most common arrival windows
    - regularity_score: 0-100 consistency score
    - trend: increasing / stable / decreasing
    """
    cutoff = datetime.utcnow() - timedelta(weeks=weeks_back)

    print(f"[LEARN] Running frequency analysis (last {weeks_back} weeks)...")

    # Get all detections within the window
    detections = (
        db.query(
            BusDetection.bus_name,
            BusDetection.camera_id,
            BusDetection.created_at,
        )
        .filter(
            BusDetection.camera_id == camera_id,
            BusDetection.created_at >= cutoff,
            BusDetection.bus_name.isnot(None),
            BusDetection.bus_name != "",
        )
        .all()
    )

    if not detections:
        print("[LEARN] No detections found for analysis.")
        return []

    # Group by bus_name
    bus_data: dict[str, list] = defaultdict(list)
    for bus_name, cam_id, created_at in detections:
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        bus_data[bus_name].append(created_at)

    # Analyze each bus
    results = []
    for bus_name, timestamps in bus_data.items():
        # --- Days per week ---
        # Group timestamps by ISO week number
        week_day_sets: dict[int, set] = defaultdict(set)
        time_counts: dict[str, int] = defaultdict(int)
        week_counts: dict[int, int] = defaultdict(int)

        for ts in timestamps:
            iso_year, iso_week, _ = ts.isocalendar()
            week_key = iso_year * 100 + iso_week
            week_day_sets[week_key].add(ts.date())
            week_counts[week_key] += 1
            time_counts[_snap_to_window(ts)] += 1

        # Average unique days per week
        weeks_with_data = len(week_day_sets)
        days_per_week_list = [len(days) for days in week_day_sets.values()]
        avg_days = sum(days_per_week_list) / weeks_with_data if weeks_with_data else 0

        # --- Typical times ---
        typical_times = _cluster_times(time_counts)

        # --- Regularity ---
        # Use week-over-week sighting counts for consistency
        sorted_weeks = sorted(week_counts.keys())
        weekly_sightings = [week_counts[w] for w in sorted_weeks]
        regularity = _calculate_regularity(weekly_sightings)

        # --- Trend ---
        weekly_day_totals = [len(week_day_sets[w]) for w in sorted_weeks]
        trend = _detect_trend(weekly_day_totals)

        result = {
            "bus_name": bus_name,
            "camera_id": camera_id,
            "avg_days_per_week": round(avg_days, 1),
            "typical_times": typical_times,
            "regularity_score": regularity,
            "trend": trend,
            "weeks_analyzed": weeks_with_data,
            "total_sightings": len(timestamps),
        }
        results.append(result)

        # --- Upsert into bus_frequency table ---
        existing = (
            db.query(BusFrequency)
            .filter_by(bus_name=bus_name, camera_id=camera_id)
            .first()
        )

        if existing:
            existing.avg_days_per_week = result["avg_days_per_week"]
            existing.typical_times = json.dumps(result["typical_times"])
            existing.regularity_score = result["regularity_score"]
            existing.trend = result["trend"]
            existing.weeks_analyzed = result["weeks_analyzed"]
            existing.total_sightings = result["total_sightings"]
        else:
            db.add(BusFrequency(
                bus_name=bus_name,
                camera_id=camera_id,
                avg_days_per_week=result["avg_days_per_week"],
                typical_times=json.dumps(result["typical_times"]),
                regularity_score=result["regularity_score"],
                trend=result["trend"],
                weeks_analyzed=result["weeks_analyzed"],
                total_sightings=result["total_sightings"],
            ))

    db.commit()
    print(f"[LEARN] Frequency analysis complete — {len(results)} buses analyzed ✅")
    return results
