"""
Detection routes — store and query bus detections.

Includes:
- Time-window deduplication (same bus within 60s → keep best)
- Bus name auto-correction (fuzzy-match against known bus_profiles)
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import BusDetection, BusProfile, ArrivalPattern
from app.schemas import BusDetectionCreate, BusDetectionOut
from learning.pattern_analyzer import update_bus_profile, rebuild_patterns

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

router = APIRouter(tags=["Detections"])

# ── Settings ─────────────────────────────────────────────
DEDUP_WINDOW_SECONDS = 60      # detections within this window are same bus
BUS_NAME_MATCH_THRESHOLD = 80  # fuzzy match score to auto-correct


# ── Helper: Bus Name Auto-Correction ─────────────────────

def _auto_correct_bus_name(db: Session, raw_name: str) -> str:
    """
    Try to match the OCR bus name against known bus_profiles.
    If a good fuzzy match is found, return the canonical name.
    Otherwise return the raw name as-is.

    Rules:
    - Never shorten a name (don't lose information)
    - Only correct to names with confirmed_name set OR high detection count
    - Use strict matching to avoid false positives
    """
    if not raw_name or not HAS_RAPIDFUZZ:
        return raw_name

    raw_upper = raw_name.strip().upper()

    # Get all known bus names (only consider profiles with enough data)
    profiles = db.query(BusProfile).filter(
        BusProfile.total_detections >= 2   # need at least 2 sightings
    ).all()
    if not profiles:
        return raw_name

    best_match = None
    best_score = 0

    for profile in profiles:
        # Use confirmed_name if set, otherwise use bus_name
        canonical = (profile.confirmed_name or profile.bus_name).strip()
        canonical_upper = canonical.upper()

        # Skip if canonical is shorter than raw — don't lose info
        # Exception: confirmed names can be shorter (human said so)
        if len(canonical) < len(raw_name) and not profile.confirmed_name:
            continue

        # Exact match — always accept
        if raw_upper == canonical_upper:
            return canonical

        # Fuzzy match — use token_sort_ratio for word-order independence
        score = fuzz.token_sort_ratio(raw_upper, canonical_upper)
        if score > best_score:
            best_score = score
            best_match = canonical

    if best_score >= BUS_NAME_MATCH_THRESHOLD and best_match:
        if best_match.upper() != raw_upper:
            print(f"  [AUTO-CORRECT] '{raw_name}' -> '{best_match}' ({best_score}%)")
        return best_match

    return raw_name


# ── Helper: Deduplication ────────────────────────────────

def _find_duplicate(
    db: Session,
    camera_id: str,
    destination: str | None,
    window_seconds: int = DEDUP_WINDOW_SECONDS,
) -> BusDetection | None:
    """
    Check if there's already a detection from the same camera
    with the same destination within the time window.
    """
    if not destination:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

    return (
        db.query(BusDetection)
        .filter(
            BusDetection.camera_id == camera_id,
            BusDetection.destination_en == destination,
            BusDetection.created_at >= cutoff,
        )
        .order_by(desc(BusDetection.destination_conf))
        .first()
    )


def _is_better_detection(
    existing: BusDetection,
    new_conf: int | None,
    new_bus_name: str | None,
) -> bool:
    """
    Return True if the new detection is 'better' than the existing one.
    Better = higher confidence, or same confidence but longer bus name.
    """
    old_conf = existing.destination_conf or 0
    new_conf = new_conf or 0

    if new_conf > old_conf:
        return True

    if new_conf == old_conf:
        old_name_len = len(existing.bus_name or "")
        new_name_len = len(new_bus_name or "")
        if new_name_len > old_name_len:
            return True

    return False


# ── Routes ───────────────────────────────────────────────

@router.post("/bus-detection", response_model=dict)
def create_detection(
    payload: BusDetectionCreate,
    db: Session = Depends(get_db),
):
    """
    Store a new bus detection event.

    Smart features:
    - Deduplication: if same camera + destination within 60s,
      keeps the one with higher confidence / longer bus name.
    - Auto-correction: fuzzy-matches bus_name against known
      bus_profiles and corrects typos/OCR errors.
    """
    try:
        # ── Step 1: Auto-correct bus name ──
        corrected_name = _auto_correct_bus_name(db, payload.bus_name)

        # ── Step 2: Check for duplicate ──
        existing = _find_duplicate(
            db, payload.camera_id, payload.destination_en
        )

        if existing:
            if _is_better_detection(existing, payload.destination_conf, corrected_name):
                # Replace existing with better detection
                existing.destination_en = payload.destination_en
                existing.destination_ml = payload.destination_ml
                existing.destination_conf = payload.destination_conf
                existing.bus_name = corrected_name
                existing.bus_type = payload.bus_type or existing.bus_type
                existing.image_path_board = payload.image_path_board or existing.image_path_board
                existing.image_path_full = payload.image_path_full or existing.image_path_full
                db.commit()
                db.refresh(existing)

                print(f"  [DEDUP] Updated id={existing.id} with better data")

                return {
                    "message": "Detection updated (better data)",
                    "id": existing.id,
                    "bus_name": existing.bus_name,
                    "destination": existing.destination_en,
                    "action": "updated",
                }
            else:
                # Existing is already better — skip
                print(f"  [DEDUP] Skipped (existing id={existing.id} is better)")
                return {
                    "message": "Detection skipped (duplicate, existing is better)",
                    "id": existing.id,
                    "bus_name": existing.bus_name,
                    "destination": existing.destination_en,
                    "action": "skipped",
                }

        # ── Step 3: Insert new detection ──
        detection = BusDetection(
            camera_id=payload.camera_id,
            destination_en=payload.destination_en,
            destination_ml=payload.destination_ml,
            destination_conf=payload.destination_conf,
            bus_name=corrected_name,
            bus_type=payload.bus_type,
            image_path_board=payload.image_path_board,
            image_path_full=payload.image_path_full,
        )
        db.add(detection)
        db.commit()
        db.refresh(detection)

        # Update bus profile if we have a bus name
        if corrected_name:
            update_bus_profile(
                db,
                bus_name=corrected_name,
                bus_type=payload.bus_type,
            )

        return {
            "message": "Detection stored",
            "id": detection.id,
            "bus_name": detection.bus_name,
            "destination": detection.destination_en,
            "action": "created",
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detections", response_model=list[BusDetectionOut])
def list_detections(
    limit: int = Query(50, ge=1, le=500),
    bus_name: str = Query(None),
    camera_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """
    List recent detections, optionally filtered by bus name or camera.
    """
    query = db.query(BusDetection).order_by(desc(BusDetection.created_at))

    if bus_name:
        query = query.filter(BusDetection.bus_name == bus_name)
    if camera_id:
        query = query.filter(BusDetection.camera_id == camera_id)

    return query.limit(limit).all()


@router.get("/detections/{bus_name}", response_model=list[BusDetectionOut])
def get_detections_for_bus(
    bus_name: str,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Get all detections for a specific bus.
    """
    results = (
        db.query(BusDetection)
        .filter(BusDetection.bus_name == bus_name)
        .order_by(desc(BusDetection.created_at))
        .limit(limit)
        .all()
    )

    if not results:
        raise HTTPException(status_code=404, detail=f"No detections for bus '{bus_name}'")

    return results


# ── Bus Name Management ──────────────────────────────────

@router.put("/bus-profile/{bus_name}/confirm")
def confirm_bus_name(
    bus_name: str,
    confirmed_name: str = Query(..., description="The correct canonical name"),
    db: Session = Depends(get_db),
):
    """
    Manually set the confirmed (canonical) name for a bus.

    If the confirmed_name matches an existing bus profile, MERGE:
    - Move all detections from old profile to the target
    - Add detection counts together
    - Keep the earliest first_seen and latest last_seen
    - Delete the old profile

    If no target profile exists, rename the current profile.
    """
    source = db.query(BusProfile).filter_by(bus_name=bus_name).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Bus '{bus_name}' not found")

    # Same name? Just set confirmed_name
    if confirmed_name.strip() == bus_name.strip():
        source.confirmed_name = confirmed_name.strip()
        db.commit()
        return {
            "message": f"Bus '{bus_name}' confirmed",
            "bus_name": bus_name,
            "confirmed_name": confirmed_name,
            "action": "confirmed",
        }

    target = db.query(BusProfile).filter_by(bus_name=confirmed_name).first()

    if target:
        # ── MERGE: target profile exists — absorb source into it ──

        # 1. Reassign all detections from source bus_name to target
        moved = db.query(BusDetection).filter_by(bus_name=bus_name).update(
            {"bus_name": confirmed_name}
        )

        # 2. Reassign all arrival patterns from source to target
        #    For patterns that exist in both, merge detection counts
        source_patterns = db.query(ArrivalPattern).filter_by(bus_name=bus_name).all()
        patterns_moved = 0
        for sp in source_patterns:
            existing = db.query(ArrivalPattern).filter_by(
                bus_name=confirmed_name,
                camera_id=sp.camera_id,
                day_of_week=sp.day_of_week,
                time_window=sp.time_window,
            ).first()
            if existing:
                # Merge: add counts together
                existing.detection_count += sp.detection_count
                existing.avg_confidence = (
                    (existing.avg_confidence + sp.avg_confidence) / 2
                )
                db.delete(sp)
            else:
                # Just rename
                sp.bus_name = confirmed_name
            patterns_moved += 1

        # 3. Merge counts
        target.total_detections = (target.total_detections or 0) + (source.total_detections or 0)

        # 4. Keep earliest first_seen, latest last_seen
        if source.first_seen and (not target.first_seen or source.first_seen < target.first_seen):
            target.first_seen = source.first_seen
        if source.last_seen and (not target.last_seen or source.last_seen > target.last_seen):
            target.last_seen = source.last_seen

        # 5. Set confirmed_name on the target
        target.confirmed_name = confirmed_name

        # 6. Delete the source profile
        db.delete(source)
        db.commit()

        # 7. Rebuild patterns to ensure consistency
        try:
            rebuild_patterns(db, days_back=60)
        except Exception as e:
            print(f"  [REBUILD WARNING] {e}")

        print(f"  [MERGE] '{bus_name}' -> '{confirmed_name}': moved {moved} detections, {patterns_moved} patterns")

        return {
            "message": f"Merged '{bus_name}' into '{confirmed_name}' ({moved} detections moved)",
            "bus_name": confirmed_name,
            "confirmed_name": confirmed_name,
            "detections_moved": moved,
            "patterns_moved": patterns_moved,
            "action": "merged",
        }
    else:
        # ── RENAME: no target profile — rename the current one ──

        # 1. Reassign all detections
        moved = db.query(BusDetection).filter_by(bus_name=bus_name).update(
            {"bus_name": confirmed_name}
        )

        # 2. Reassign all arrival patterns
        patterns_moved = db.query(ArrivalPattern).filter_by(bus_name=bus_name).update(
            {"bus_name": confirmed_name}
        )

        # 3. Rename the profile itself
        source.bus_name = confirmed_name
        source.confirmed_name = confirmed_name
        db.commit()

        # 4. Rebuild patterns to ensure consistency
        try:
            rebuild_patterns(db, days_back=60)
        except Exception as e:
            print(f"  [REBUILD WARNING] {e}")

        print(f"  [RENAME] '{bus_name}' -> '{confirmed_name}': moved {moved} detections, {patterns_moved} patterns")

        return {
            "message": f"Renamed '{bus_name}' to '{confirmed_name}' ({moved} detections updated)",
            "bus_name": confirmed_name,
            "confirmed_name": confirmed_name,
            "detections_moved": moved,
            "patterns_moved": patterns_moved,
            "action": "renamed",
        }
