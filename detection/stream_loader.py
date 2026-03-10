"""
Threaded MJPEG / RTSP stream reader with automatic reconnection.
"""

import cv2
import numpy as np
import time
import requests


class StreamLoader:
    """
    Reads frames from an MJPEG stream URL.
    Yields the latest frame and auto-reconnects on failure.
    """

    def __init__(self, url: str, max_retries: int = 10, retry_delay: float = 3.0):
        self.url = url
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def frames(self):
        """
        Generator that yields BGR frames from the stream.
        Auto-reconnects on connection loss.
        """
        retries = 0

        while retries < self.max_retries:
            try:
                print(f"[STREAM] Connecting to {self.url} ...")
                response = requests.get(self.url, stream=True, timeout=10)
                print("[STREAM] Connected (OK)")
                retries = 0  # reset on successful connect

                buffer = b""
                for chunk in response.iter_content(chunk_size=4096):
                    buffer += chunk

                    # Find JPEG start (0xFFD8) and end (0xFFD9)
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9")

                    if start != -1 and end != -1 and end > start:
                        jpg_bytes = buffer[start:end + 2]
                        buffer = buffer[end + 2:]

                        frame = cv2.imdecode(
                            np.frombuffer(jpg_bytes, dtype=np.uint8),
                            cv2.IMREAD_COLOR,
                        )
                        if frame is not None:
                            yield frame

            except requests.exceptions.RequestException as e:
                retries += 1
                print(
                    f"[STREAM] Connection lost ({e}). "
                    f"Retry {retries}/{self.max_retries} in {self.retry_delay}s..."
                )
                time.sleep(self.retry_delay)

            except Exception as e:
                retries += 1
                print(f"[STREAM] Unexpected error: {e}. Retrying...")
                time.sleep(self.retry_delay)

        print("[STREAM] Max retries exceeded. Giving up.")


class VideoFileLoader:
    """
    Reads frames from a local video file (for testing with .mp4 files).
    """

    def __init__(self, path: str, loop: bool = True):
        self.path = path
        self.loop = loop

    def frames(self):
        while True:
            cap = cv2.VideoCapture(self.path)
            if not cap.isOpened():
                print(f"[VIDEO] Cannot open: {self.path}")
                return

            print(f"[VIDEO] Playing: {self.path}")
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                yield frame

            cap.release()
            if not self.loop:
                break
            print("[VIDEO] Looping...")
