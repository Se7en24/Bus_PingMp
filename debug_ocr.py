
import sys
import os
from config import INDIC_OCR_PATH

print(f"Adding path: {INDIC_OCR_PATH}")
sys.path.insert(0, INDIC_OCR_PATH)

try:
    import ocr
    print("Successfully imported ocr module")
    from ocr import OCR
    print("Successfully imported OCR class")
except Exception as e:
    print(f"Error importing: {e}")
    import traceback
    traceback.print_exc()

print(f"sys.path: {sys.path}")
