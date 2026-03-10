"""
Main Detection Pipeline — the entry point that ties everything together.

Run this to start live bus detection:
    python pipeline.py

Or with a local video file for testing:
    python pipeline.py --video Data/bus1.mp4
"""

# ── PyTorch 2.6 compatibility — MUST be before all other imports ──
import torch
try:
    torch.serialization.add_safe_globals([getattr])
except AttributeError:
    pass
# ──────────────────────────────────────────────────────────────────
import sys
import os
import re
import cv2
import threading
import queue
import argparse
import time
import requests
from collections import Counter

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CAMERA_URL, CAMERA_ID, LOG_THRESHOLD, MATCH_THRESHOLD
from detection.detector import BusDetector
from detection.ocr_engine import IndicOCRWrapper
from detection.matcher import match_destination
from detection.preprocessor import preprocess_for_ocr
from detection.stream_loader import StreamLoader, VideoFileLoader


# ── Config ───────────────────────────────────────────────
BACKEND_URL = "http://127.0.0.1:8000/bus-detection"
ocr_queue: queue.Queue = queue.Queue(maxsize=10)

# How many seconds to accumulate readings for one bus before logging
ACCUMULATE_TIMEOUT = 8.0

# Global state — updated by OCR worker thread
current_destination = "Scanning..."
destination_conf = 0
current_bus_name = "Unknown"
last_logged_key = None

# ── Junk token patterns ──────────────────────────────────
# Unicode artifact tokens the OCR commonly produces — STRIPPED, not rejected
_JUNK_TOKENS = re.compile(
    r'^(U200[A-F0-9]|U?FEFF|U200D|U200C|U00A0)$',
    re.IGNORECASE,
)


def _strip_junk(text: str | None) -> str | None:
    """Remove junk tokens from text but keep everything else."""
    if not text:
        return None
    tokens = text.split()
    clean = [t for t in tokens if not _JUNK_TOKENS.match(t)]
    result = " ".join(clean).strip()
    return result if result else None


def _is_usable(text: str | None, min_len: int = 3) -> bool:
    """Check if cleaned text is long enough to be useful."""
    if not text:
        return False
    # Reject if entirely digits / punctuation / whitespace
    if re.match(r'^[\d\W]+$', text):
        return False
    return len(text.strip()) >= min_len


# ── Cross-Frame Accumulator ──────────────────────────────
# Bus name and destination are read on DIFFERENT frames.
# We accumulate both independently, then combine for DB logging.

class BusAccumulator:
    """Accumulates OCR readings across frames for ONE bus sighting."""

    def __init__(self):
        self.dest_votes: list[tuple[str, float]] = []   # (dest, conf)
        self.bus_votes: list[str] = []                   # bus names
        self.start_time: float = time.time()

    def add_destination(self, dest: str, conf: float):
        self.dest_votes.append((dest, conf))

    def add_bus_name(self, name: str):
        self.bus_votes.append(name)

    @property
    def age(self) -> float:
        return time.time() - self.start_time

    def best_destination(self) -> tuple[str | None, float]:
        """Most voted destination with average confidence."""
        if not self.dest_votes:
            return None, 0
        counter = Counter(d for d, _ in self.dest_votes)
        top_dest, count = counter.most_common(1)[0]
        if count >= 2:  # need at least 2 matching votes
            avg_conf = sum(c for d, c in self.dest_votes if d == top_dest) / count
            return top_dest, avg_conf
        # If only 1 vote but high confidence, still accept
        if len(self.dest_votes) >= 1:
            d, c = self.dest_votes[-1]
            return d, c
        return None, 0

    def best_bus_name(self) -> str | None:
        """Most voted bus name, preferring longer names."""
        if not self.bus_votes:
            return None
        counter = Counter(self.bus_votes)
        candidates = counter.most_common()
        # Prefer: highest count, then longest name
        candidates.sort(key=lambda x: (-x[1], -len(x[0])))
        return candidates[0][0]

    def is_ready_to_log(self) -> bool:
        """True when we have enough data OR timeout reached."""
        has_dest = len(self.dest_votes) >= 2
        has_bus = len(self.bus_votes) >= 1
        enough_votes = len(self.dest_votes) + len(self.bus_votes) >= 3
        timed_out = self.age > ACCUMULATE_TIMEOUT

        # Best case: both destination and bus name confirmed
        if has_dest and has_bus and enough_votes:
            return True
        # Timeout: log what we have if we at least have a destination
        if timed_out and has_dest:
            return True
        return False

    def reset(self):
        self.dest_votes.clear()
        self.bus_votes.clear()
        self.start_time = time.time()


# ── OCR Worker Thread ────────────────────────────────────

def ocr_worker(ocr_engine: IndicOCRWrapper):
    """
    Background thread: pulls bus crops, runs OCR, accumulates results
    across frames, and logs to DB only when readings are stable.

    Key insight: bus name (EN) and destination (ML) often appear on
    DIFFERENT frames. We accumulate them independently and combine.
    """
    global current_destination, destination_conf, current_bus_name, last_logged_key

    print("[OCR WORKER] Started (OK)")
    accumulator = BusAccumulator()

    while True:
        try:
            crop_img = ocr_queue.get(timeout=2)
        except queue.Empty:
            # Check if accumulator should flush on timeout
            if accumulator.is_ready_to_log():
                _try_log(accumulator)
            continue

        if crop_img is None:
            break  # poison pill

        try:
            # ── Preprocess the crop for better OCR accuracy ──
            enhanced = preprocess_for_ocr(crop_img)

            # Save enhanced crop for OCR (library needs file path)
            temp_name = f"temp_ocr_{threading.get_ident()}.jpg"
            cv2.imwrite(temp_name, enhanced)

            ml_text, en_text = ocr_engine.predict(temp_name)

            # Strip junk tokens (U200D etc.) but keep remaining text
            en_text = _strip_junk(en_text)
            ml_text = _strip_junk(ml_text) if ml_text else None

            print(f"  [OCR RAW] ML: {ml_text}  |  EN: {en_text}")

            # ── Accumulate DESTINATION (from ML or EN) ──
            dest_match, dest_score = match_destination(ml_text, en_text)

            if dest_match and dest_score >= MATCH_THRESHOLD:
                accumulator.add_destination(dest_match, dest_score)
                current_destination = dest_match
                destination_conf = dest_score
                print(f"  [+ DEST] {dest_match} ({int(dest_score)}%)")

            # ── Accumulate BUS NAME (from EN primarily) ──
            bus_name = _extract_bus_name(ml_text, en_text, dest_match)
            if bus_name:
                accumulator.add_bus_name(bus_name)
                current_bus_name = bus_name
                print(f"  [+ BUS]  {bus_name}")

            if not dest_match and not bus_name:
                print(f"  [--] No usable text")

            # ── Check if ready to log ──
            if accumulator.is_ready_to_log():
                _try_log(accumulator)

            # Cleanup temp file
            if os.path.exists(temp_name):
                os.remove(temp_name)

        except Exception as e:
            print(f"  [OCR ERROR] {e}")

        ocr_queue.task_done()


def _try_log(acc: BusAccumulator):
    """Attempt to log the accumulated readings to the backend."""
    global current_destination, destination_conf, current_bus_name, last_logged_key

    best_dest, best_conf = acc.best_destination()
    best_bus = acc.best_bus_name()

    if not best_dest or best_conf < LOG_THRESHOLD:
        # Not confident enough — reset and try again
        acc.reset()
        return

    # Update globals
    current_destination = best_dest
    destination_conf = best_conf
    if best_bus:
        current_bus_name = best_bus

    log_key = (best_dest, current_bus_name)
    if log_key != last_logged_key:
        print(f"  ==> LOGGING: dest={best_dest} ({int(best_conf)}%)  bus={current_bus_name}")
        _send_to_backend(best_dest, best_conf, current_bus_name)
        last_logged_key = log_key

    acc.reset()


def _extract_bus_name(ml_text: str, en_text: str, dest_match: str) -> str | None:
    """
    Extract bus name by removing the destination text from OCR output.
    Whatever is left after removing destination words is likely the bus name.
    """
    # Try English text first (most bus names are in English)
    if en_text and _is_usable(en_text):
        name = en_text
        # Remove destination text if found
        if dest_match:
            for word in dest_match.upper().split():
                name = name.replace(word, "")
        name = " ".join(name.split()).strip()
        if _is_usable(name, min_len=3):
            return name

    # Try Malayalam text (bus name could be in ML too)
    if ml_text and _is_usable(ml_text, min_len=2):
        name = ml_text
        if dest_match:
            for word in dest_match.split():
                name = name.replace(word, "")
        name = " ".join(name.split()).strip()
        if _is_usable(name, min_len=2):
            return name

    return None


def _send_to_backend(destination: str, confidence: float, bus_name: str):
    """POST detection to FastAPI backend."""
    payload = {
        "camera_id": CAMERA_ID,
        "destination_en": destination,
        "destination_ml": destination,
        "destination_conf": int(confidence),
        "bus_name": bus_name if bus_name != "Unknown" else destination,
        "bus_type": "PRIVATE",
        "image_path_board": None,
        "image_path_full": None,
    }

    try:
        resp = requests.post(BACKEND_URL, json=payload, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  [DB] Logged -> id={data.get('id')}  bus={bus_name}  dest={destination} (OK)")
        else:
            print(f"  [DB ERROR] {resp.status_code}: {resp.text}")
    except requests.exceptions.ConnectionError:
        print("  [DB] Backend not running — detection not saved")
    except Exception as e:
        print(f"  [DB ERROR] {e}")


# ── Main Loop ────────────────────────────────────────────

def run_pipeline(video_path: str = None):
    """
    Main detection loop:
      1. Read frames from stream or video
      2. YOLO bus detection
      3. Crop top half of bus for OCR (contains both name + destination)
      4. OCR reads ALL text, then smart-separates name vs destination
      5. Display results
    """
    # Initialize components
    detector = BusDetector()
    ocr_engine = IndicOCRWrapper()

    # Start OCR worker thread
    worker = threading.Thread(target=ocr_worker, args=(ocr_engine,), daemon=True)
    worker.start()

    # Choose source
    if video_path:
        loader = VideoFileLoader(video_path, loop=True)
        print(f"[PIPELINE] Source: local video -> {video_path}")
    else:
        loader = StreamLoader(CAMERA_URL)
        print(f"[PIPELINE] Source: live stream -> {CAMERA_URL}")

    print("[PIPELINE] Starting detection. Press 'q' to quit.\n")

    frame_count = 0
    OCR_EVERY_N_FRAMES = 15  # Only run OCR every N frames

    for frame in loader.frames():
        frame_count += 1

        # Run YOLO detection
        detections, display_frame = detector.detect_buses(frame)

        for det in detections:
            bbox = det["bbox"]
            x1, y1, x2, y2 = bbox

            # Draw bounding box
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Only attempt OCR every N frames
            if frame_count % OCR_EVERY_N_FRAMES != 0:
                continue

            roi = det["roi_hires"]  # Full-resolution for OCR
            h, w = roi.shape[:2]

            # Crop TOP HALF of bus — contains both name AND destination
            # Bus name = painted at top / above windshield
            # Destination board = behind/below windshield
            # Both are in the top ~50% of the bus ROI
            ocr_crop = roi[0:int(h * 0.55), :]

            if ocr_crop is not None and ocr_crop.size > 0 and not ocr_queue.full():
                ocr_queue.put(ocr_crop)

        # Draw status overlay
        cv2.putText(
            display_frame,
            f"Dest: {current_destination} ({int(destination_conf)}%)",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
        cv2.putText(
            display_frame,
            f"Bus: {current_bus_name}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 200, 255),
            2,
        )
        cv2.putText(
            display_frame,
            f"Camera: {CAMERA_ID}  |  Buses: {len(detections)}",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (200, 200, 200),
            1,
        )

        cv2.imshow("Bus PingMp — Detection", display_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Cleanup
    ocr_queue.put(None)  # poison pill for worker
    cv2.destroyAllWindows()
    print("\n[PIPELINE] Stopped.")


# ── CLI ──────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bus PingMp Detection Pipeline")
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="Path to a local video file (for testing). If not set, uses live camera.",
    )
    args = parser.parse_args()

    run_pipeline(video_path=args.video)
