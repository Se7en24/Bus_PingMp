"""
SQLAlchemy ORM models for all three tables.
"""

from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, Float,
    TIMESTAMP, UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class BusDetection(Base):
    """
    Every single detection event — one row per bus spotted.
    """
    __tablename__ = "bus_detections"

    id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        index=True,
    )

    camera_id = Column(String(50), index=True)

    destination_en = Column(Text)
    destination_ml = Column(Text)
    destination_conf = Column(Integer)

    bus_name = Column(Text, index=True)
    bus_type = Column(String(20))          # KSRTC, PRIVATE, etc.

    image_path_board = Column(Text)
    image_path_full = Column(Text)


class BusProfile(Base):
    """
    One row per unique bus — acts as a registry.
    Upserted whenever a bus is detected.

    confirmed_name: The manually-verified canonical name.
                    When set, OCR results fuzzy-matching this bus
                    will be auto-corrected to this name.
    """
    __tablename__ = "bus_profiles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bus_name = Column(String(100), unique=True, nullable=False, index=True)
    confirmed_name = Column(String(100), nullable=True)  # canonical name
    bus_type = Column(String(20))

    first_seen = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_seen = Column(TIMESTAMP(timezone=True), server_default=func.now())
    total_detections = Column(Integer, default=0)


class ArrivalPattern(Base):
    """
    Aggregated heatmap data — one row per
    (bus_name, camera_id, day_of_week, time_window).

    day_of_week: 0=Monday … 6=Sunday
    time_window: string like "14:45" (start of the 5‑min window)
    detection_count: how many times this bus was seen in this window
    """
    __tablename__ = "arrival_patterns"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bus_name = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(50), nullable=False)

    day_of_week = Column(Integer, nullable=False)        # 0‑6
    time_window = Column(String(5), nullable=False)      # "HH:MM"
    window_minutes = Column(Integer, default=5)

    detection_count = Column(Integer, default=0)
    avg_confidence = Column(Float, default=0.0)
    last_updated = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "bus_name", "camera_id", "day_of_week", "time_window",
            name="uq_arrival_pattern",
        ),
    )


class BusFrequency(Base):
    """
    Weekly frequency analysis — one row per (bus_name, camera_id).

    Computed by the learning system's weekly analysis job.
    Answers: "How often does this bus come? At what times? How reliable?"
    """
    __tablename__ = "bus_frequency"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bus_name = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(50), nullable=False)

    # Weekly stats
    avg_days_per_week = Column(Float, default=0)        # e.g. 4.5
    typical_times = Column(Text)                        # JSON: ["11:15","14:30"]
    regularity_score = Column(Integer, default=0)       # 0–100
    trend = Column(String(20), default="stable")        # increasing / stable / decreasing

    # Context
    weeks_analyzed = Column(Integer, default=0)
    total_sightings = Column(Integer, default=0)
    last_analyzed = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "bus_name", "camera_id",
            name="uq_bus_frequency",
        ),
    )
