"""
Pydantic schemas for request / response validation.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# ── Detection Schemas ────────────────────────────────────

class BusDetectionCreate(BaseModel):
    camera_id: str
    destination_en: Optional[str] = None
    destination_ml: Optional[str] = None
    destination_conf: Optional[int] = None
    bus_name: Optional[str] = None
    bus_type: Optional[str] = None
    image_path_board: Optional[str] = None
    image_path_full: Optional[str] = None


class BusDetectionOut(BaseModel):
    id: int
    created_at: datetime
    camera_id: str
    destination_en: Optional[str] = None
    destination_ml: Optional[str] = None
    destination_conf: Optional[int] = None
    bus_name: Optional[str] = None
    bus_type: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Bus Profile Schemas ──────────────────────────────────

class BusProfileOut(BaseModel):
    id: int
    bus_name: str
    bus_type: Optional[str] = None
    first_seen: datetime
    last_seen: datetime
    total_detections: int

    model_config = {"from_attributes": True}


# ── Analytics / Prediction Schemas ───────────────────────

class ArrivalPatternOut(BaseModel):
    bus_name: str
    camera_id: str
    day_of_week: int
    time_window: str
    detection_count: int
    avg_confidence: float

    model_config = {"from_attributes": True}


class PredictionItem(BaseModel):
    bus_name: str
    bus_type: Optional[str] = None
    destination: Optional[str] = "Unknown"
    expected_window: str
    time_sort_key: Optional[str] = None
    likelihood_pct: float
    reliability: Optional[str] = None
    avg_confidence: float
    sample_size: int


class PredictionResponse(BaseModel):
    camera_id: str
    current_day: str
    predictions: list[PredictionItem]


class HeatmapCell(BaseModel):
    day_of_week: int
    day_name: str
    time_window: str
    detection_count: int
    avg_confidence: float


class HeatmapResponse(BaseModel):
    bus_name: str
    camera_id: str
    total_detections: int
    heatmap: list[HeatmapCell]


# ── Frequency / Learning Schemas ─────────────────────────

class BusFrequencyOut(BaseModel):
    bus_name: str
    camera_id: str
    avg_days_per_week: float
    typical_times: Optional[list[str]] = None
    regularity_score: int
    trend: str
    weeks_analyzed: int
    total_sightings: int
