"""
YOLO-based bus detection + destination board segmentation.
"""

import cv2
import numpy as np
from ultralytics import YOLO

from config import YOLO_MODEL, MIN_BUS_AREA, YOLO_WIDTH


class BusDetector:
    """
    Detects buses in a video frame using YOLOv11,
    then segments the destination board from each bus ROI.
    """

    def __init__(self):
        print(f"[INFO] Loading YOLO model: {YOLO_MODEL}")
        self.model = YOLO(YOLO_MODEL)
        print("[INFO] YOLO ready (OK)")

    def detect_buses(self, frame):
        """
        Detect bus bounding boxes in a frame.

        Args:
            frame: BGR image (numpy array)

        Returns:
            list of dicts:
                [{"bbox": (x1,y1,x2,y2), "conf": float, "roi": np.array, "roi_hires": np.array}, ...]
            display_frame: resized frame for display
        """
        orig_h, orig_w = frame.shape[:2]
        scale = orig_w / YOLO_WIDTH
        new_h = int(orig_h / scale)
        small = cv2.resize(frame, (YOLO_WIDTH, new_h))

        results = self.model(small, classes=[5], verbose=False)

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                area = (x2 - x1) * (y2 - y1)

                if area < MIN_BUS_AREA / (scale * scale):
                    continue

                roi = small[y1:y2, x1:x2]

                # Scale coordinates back to original frame for high-res crop
                ox1 = int(x1 * scale)
                oy1 = int(y1 * scale)
                ox2 = int(x2 * scale)
                oy2 = int(y2 * scale)
                roi_hires = frame[oy1:oy2, ox1:ox2]

                detections.append({
                    "bbox": (x1, y1, x2, y2),
                    "conf": float(box.conf[0]),
                    "roi": roi,            # small, for display
                    "roi_hires": roi_hires, # full resolution, for OCR
                })

        return detections, small

    @staticmethod
    def segment_board(bus_roi):
        """
        Find the destination board in a bus ROI using contour analysis.
        Looks for the widest rectangular region in the top 75% of the ROI.

        Returns:
            (board_crop, rect) or (None, None)
        """
        if bus_roi is None or bus_roi.size == 0:
            return None, None

        h, w = bus_roi.shape[:2]
        crop_h = int(h * 0.75)
        search_area = bus_roi[0:crop_h, 0:w]

        gray = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        best_crop, best_rect, max_score = None, None, 0
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            aspect = cw / max(ch, 1)
            area = cw * ch

            # Destination boards are wide rectangles
            if aspect > 2.0 and area > max_score:
                max_score = area
                best_crop = search_area[y:y + ch, x:x + cw]
                best_rect = (x, y, cw, ch)

        return best_crop, best_rect
