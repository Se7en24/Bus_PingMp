"""
Hybrid OCR Engine — uses BOTH IndicPhotoOCR and EasyOCR.

IndicPhotoOCR  → Malayalam text (what it's trained for)
EasyOCR        → English text  (production-grade English scene text)

Each engine handles what it's best at — no more relying on
IndicPhotoOCR for English, which produces garbage like "CRACRE"
instead of "TUTTU MOTORS".
"""

import sys
import os
import re
import torch
import functools
import cv2
import numpy as np

# -- PyTorch 2.6 compatibility patch ------------------------------------------
try:
    import torch.optim.swa_utils
    torch.serialization.add_safe_globals([
        getattr,
        torch.optim.swa_utils.SWALR,
    ])
except (AttributeError, ImportError):
    pass

_original_torch_load = torch.load

@functools.wraps(_original_torch_load)
def _patched_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)

torch.load = _patched_torch_load
# -----------------------------------------------------------------------------

from config import INDIC_OCR_PATH

# Resolve to absolute path
_INDIC_OCR_PATH = os.path.abspath(INDIC_OCR_PATH)
_LIB_PARENT_DIR = os.path.dirname(_INDIC_OCR_PATH)

# Inject paths for imports
if _LIB_PARENT_DIR not in sys.path:
    sys.path.insert(0, _LIB_PARENT_DIR)
if _INDIC_OCR_PATH not in sys.path:
    sys.path.insert(0, _INDIC_OCR_PATH)

try:
    from IndicPhotoOCR.ocr import OCR
except ImportError:
    try:
        from ocr import OCR
    except ImportError as e:
        print(f"[CRITICAL] Error importing OCR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# EasyOCR for English
try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    print("[WARNING] EasyOCR not installed. English OCR will fall back to IndicPhotoOCR.")
    _EASYOCR_AVAILABLE = False


class IndicOCRWrapper:
    """
    Hybrid OCR wrapper:
      - EasyOCR for English text (bus names like "TUTTU MOTORS")
      - IndicPhotoOCR for Malayalam text (destinations like "കാഞ്ഞിരപ്പള്ളി")
    """

    def __init__(self, lang: str = "malayalam", device: str = "cpu"):
        print("[INFO] Initializing Hybrid OCR Engine...")

        # ── IndicPhotoOCR (Malayalam) ──
        original_cwd = os.getcwd()
        os.chdir(_LIB_PARENT_DIR)
        try:
            self.indic_ocr = OCR(identifier_lang=lang, device=device)
        finally:
            os.chdir(original_cwd)
        print("[INFO] IndicPhotoOCR ready (Malayalam) ✅")

        # ── EasyOCR (English) ──
        if _EASYOCR_AVAILABLE:
            # gpu=True if CUDA available, else CPU
            use_gpu = torch.cuda.is_available()
            self.easy_reader = easyocr.Reader(
                ['en'],
                gpu=use_gpu,
                verbose=False,
            )
            print(f"[INFO] EasyOCR ready (English, GPU={use_gpu}) ✅")
        else:
            self.easy_reader = None

        print("[INFO] Hybrid OCR Engine ready (OK)")

    def predict(self, image_path: str):
        """
        Run BOTH OCR engines and return the best of each:

        Returns:
            (malayalam_text, english_text)  — either can be None
        """
        image_path = os.path.abspath(image_path)

        malayalam_text = self._run_indic_ocr(image_path)
        english_text = self._run_easyocr(image_path)

        return malayalam_text, english_text

    def _run_indic_ocr(self, image_path: str) -> str | None:
        """Run IndicPhotoOCR and extract Malayalam text."""
        original_cwd = os.getcwd()
        os.chdir(_LIB_PARENT_DIR)
        try:
            raw_output = self.indic_ocr.get_ocr(image_path)

            if not raw_output:
                return None

            text = str(raw_output)

            # Extract Malayalam characters (Unicode range U+0D00–U+0D7F)
            ml_matches = re.findall(r"[\u0D00-\u0D7F]+", text)
            malayalam_text = " ".join(ml_matches).strip() or None

            return malayalam_text

        except Exception as e:
            print(f"[INDIC OCR ERROR] {e}")
            return None
        finally:
            os.chdir(original_cwd)

    def _run_easyocr(self, image_path: str) -> str | None:
        """Run EasyOCR for English text recognition."""
        if not self.easy_reader:
            # Fallback: extract English from IndicPhotoOCR output
            return self._fallback_english(image_path)

        try:
            # EasyOCR can read directly from file path
            results = self.easy_reader.readtext(
                image_path,
                detail=1,           # Get (bbox, text, confidence)
                paragraph=False,    # Don't merge into paragraphs
                min_size=20,        # Minimum text region size
                text_threshold=0.6, # Text confidence threshold
            )

            if not results:
                return None

            # Filter by confidence and collect English text
            good_texts = []
            for (bbox, text, conf) in results:
                # Only keep results with decent confidence
                if conf >= 0.3 and len(text.strip()) >= 2:
                    # Clean: keep only alphanumeric + spaces
                    cleaned = re.sub(r"[^A-Za-z0-9\s]", "", text).strip()
                    if cleaned:
                        good_texts.append((cleaned.upper(), conf))

            if not good_texts:
                return None

            # Join all detected English text fragments
            # Sort by confidence (best first), then combine
            good_texts.sort(key=lambda x: -x[1])
            combined = " ".join(t for t, c in good_texts)

            return combined if combined.strip() else None

        except Exception as e:
            print(f"[EASYOCR ERROR] {e}")
            return None

    def _fallback_english(self, image_path: str) -> str | None:
        """Fallback: extract English from IndicPhotoOCR output if EasyOCR not available."""
        original_cwd = os.getcwd()
        os.chdir(_LIB_PARENT_DIR)
        try:
            raw_output = self.indic_ocr.get_ocr(image_path)
            if not raw_output:
                return None
            text = str(raw_output)
            english_text = re.sub(r"[^A-Za-z0-9\s]", "", text).upper().strip() or None
            return english_text
        except Exception as e:
            print(f"[OCR FALLBACK ERROR] {e}")
            return None
        finally:
            os.chdir(original_cwd)
