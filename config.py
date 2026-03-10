"""
Central configuration — loads everything from .env
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "supamen")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "smart_bus")

DATABASE_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ── Camera ────────────────────────────────────────────────
CAMERA_URL = os.getenv("CAMERA_URL", "")
CAMERA_ID = os.getenv("CAMERA_ID", "CAM_DEFAULT")

# ── Model Paths ──────────────────────────────────────────
YOLO_MODEL = os.getenv("YOLO_MODEL", "Models/yolo11s.pt")
INDIC_OCR_PATH = os.getenv(
    "INDIC_OCR_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "IndicPhotoOCR")
)

# ── Detection Thresholds ─────────────────────────────────
MIN_BUS_AREA = int(os.getenv("MIN_BUS_AREA", "20000"))
YOLO_WIDTH = int(os.getenv("YOLO_WIDTH", "800"))
MATCH_THRESHOLD = int(os.getenv("MATCH_THRESHOLD", "55"))
LOG_THRESHOLD = int(os.getenv("LOG_THRESHOLD", "80"))

# ── Destination Lists ────────────────────────────────────
ML_DESTINATIONS = [
    "പൊൻകുന്നം", "പാലാ", "കാഞ്ഞിരപ്പള്ളി",
    "നെടുങ്കണ്ടം", "കോട്ടയം", "എറണാകുളം", "എരുമേലി"
]

EN_DESTINATIONS = [
    "PONKUNNAM", "PALA", "KANJIRAPALLY",
    "NEDUMKANDAM", "KOTTAYAM", "ERNAKULAM", "ERUMELY"
]

# ── Learning Module ──────────────────────────────────────
TIME_WINDOW_MINUTES = int(os.getenv("TIME_WINDOW_MINUTES", "5"))
ANALYSIS_INTERVAL_SECONDS = int(os.getenv("ANALYSIS_INTERVAL_SECONDS", "300"))
