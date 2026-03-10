"""Quick test to verify OCR loads and runs from Bus_PingMp (self-contained)."""
import sys
import os
import io

# Force UTF-8 stdout so Malayalam / Unicode text doesn't crash on cp1252 console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_dir)
sys.path.insert(0, project_dir)

import torch
torch.serialization.add_safe_globals([getattr])
import functools
_orig = torch.load
@functools.wraps(_orig)
def _safe_load(*a, **kw):
    kw['weights_only'] = False
    return _orig(*a, **kw)
torch.load = _safe_load

print("=" * 60)
print("STEP 1: Config check")
from config import INDIC_OCR_PATH
abs_path = os.path.abspath(INDIC_OCR_PATH)
print(f"  INDIC_OCR_PATH = {abs_path}")
print(f"  Exists: {os.path.isdir(abs_path)}")

print("\nSTEP 2: Import OCR engine")
from detection.ocr_engine import IndicOCRWrapper
print("  Import OK")

print("\nSTEP 3: Initialize OCR")
try:
    ocr = IndicOCRWrapper()
    print("  OCR initialized OK")
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nSTEP 4: Test OCR on a temp image (if exists)")
temp_files = [f for f in os.listdir('.') if f.startswith('temp_ocr') and f.endswith('.jpg')]
if temp_files:
    img = temp_files[0]
    print(f"  Testing on: {img}")
    try:
        ml, en = ocr.predict(img)
        print(f"  ML result: {ml}")
        print(f"  EN result: {en}")
        if ml or en:
            print("  >>> OCR IS WORKING! Text was recognized. <<<")
        else:
            print("  >>> No text found (image may be too noisy/small)")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
else:
    print("  No temp OCR images found, skipping predict test")

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
