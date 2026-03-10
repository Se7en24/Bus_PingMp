"""
Image Preprocessing for OCR — enhances video frame crops before
sending them to the OCR engine for dramatically better text recognition.

Pipeline:
  1. Upscale small crops so OCR has enough pixels
  2. Denoise to remove camera grain/noise
  3. Sharpen text edges using unsharp mask
  4. CLAHE contrast enhancement (handles shadows, backlight)
  5. Adaptive binarization (black text on white background)

Usage:
    from detection.preprocessor import preprocess_for_ocr
    enhanced = preprocess_for_ocr(crop_img)
"""

import cv2
import numpy as np


# ── Minimum dimensions for OCR ──────────────────────────
MIN_OCR_WIDTH = 300   # Upscale if smaller than this
MIN_OCR_HEIGHT = 80


def preprocess_for_ocr(
    image: np.ndarray,
    upscale: bool = True,
    denoise: bool = True,
    sharpen: bool = True,
    enhance_contrast: bool = True,
    binarize: bool = False,
    debug: bool = False,
) -> np.ndarray:
    """
    Full preprocessing pipeline for OCR.

    Args:
        image:            BGR image (numpy array)
        upscale:          Upscale small images to min OCR dimensions
        denoise:          Remove camera noise
        sharpen:          Sharpen text edges
        enhance_contrast: Apply CLAHE contrast equalization
        binarize:         Convert to binary (black text on white)
        debug:            If True, show intermediate steps in windows

    Returns:
        Preprocessed BGR image (or grayscale if binarize=True)
    """
    if image is None or image.size == 0:
        return image

    result = image.copy()

    # ── Step 1: Upscale small crops ──────────────────────
    if upscale:
        result = _upscale_if_needed(result)

    if debug:
        cv2.imshow("1_upscaled", result)

    # ── Step 2: Denoise ──────────────────────────────────
    if denoise:
        result = _denoise(result)

    if debug:
        cv2.imshow("2_denoised", result)

    # ── Step 3: Sharpen ──────────────────────────────────
    if sharpen:
        result = _sharpen(result)

    if debug:
        cv2.imshow("3_sharpened", result)

    # ── Step 4: Contrast enhancement (CLAHE) ─────────────
    if enhance_contrast:
        result = _enhance_contrast(result)

    if debug:
        cv2.imshow("4_contrast", result)

    # ── Step 5: Binarization (optional — some OCR prefers color) ──
    if binarize:
        result = _binarize(result)

    if debug:
        if binarize:
            cv2.imshow("5_binary", result)
        cv2.waitKey(0)

    return result


def _upscale_if_needed(image: np.ndarray) -> np.ndarray:
    """Upscale image if it's too small for reliable OCR."""
    h, w = image.shape[:2]

    if w < MIN_OCR_WIDTH or h < MIN_OCR_HEIGHT:
        # Calculate scale factor to meet minimum dimensions
        scale_w = MIN_OCR_WIDTH / w if w < MIN_OCR_WIDTH else 1.0
        scale_h = MIN_OCR_HEIGHT / h if h < MIN_OCR_HEIGHT else 1.0
        scale = max(scale_w, scale_h)

        # Cap at 3x to avoid excessive upscaling
        scale = min(scale, 3.0)

        new_w = int(w * scale)
        new_h = int(h * scale)

        # Use INTER_CUBIC for upscaling — better quality than INTER_LINEAR
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    return image


def _denoise(image: np.ndarray) -> np.ndarray:
    """Remove camera noise while preserving edges (text)."""
    # fastNlMeansDenoisingColored is specifically designed for color images
    # h=6: moderate noise removal (higher = more smoothing, risk losing text)
    # hForColorComponents=6: same for color channels
    # templateWindowSize=7: search window
    # searchWindowSize=21: comparison window
    # fastNlMeansDenoisingColored(src, dst, h, hForColorComponents, templateWindowSize, searchWindowSize)
    # Using positional args for OpenCV 4.13+ compatibility
    return cv2.fastNlMeansDenoisingColored(image, None, 6, 6, 7, 21)


def _sharpen(image: np.ndarray) -> np.ndarray:
    """
    Unsharp mask sharpening — enhances text edges.

    Works by: subtracting a blurred version from the original,
    which amplifies high-frequency details (text edges).
    """
    # Create a Gaussian-blurred version
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=2.0)

    # Unsharp mask: original + (original - blurred) * amount
    # amount=1.5 gives moderate sharpening
    sharpened = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)

    return sharpened


def _enhance_contrast(image: np.ndarray) -> np.ndarray:
    """
    CLAHE (Contrast Limited Adaptive Histogram Equalization).

    Unlike global histogram equalization, CLAHE works on *tiles*
    of the image — so it handles uneven lighting beautifully
    (e.g. one half of the bus in shadow, other half in sun).
    """
    # Convert to LAB color space (L = lightness, A/B = color)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # Apply CLAHE to the L (lightness) channel only
    # clipLimit=3.0: controls contrast amplification (higher = more contrast)
    # tileGridSize=(8,8): divides image into 8x8 tiles for local equalization
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    # Merge back and convert to BGR
    lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
    result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    return result


def _binarize(image: np.ndarray) -> np.ndarray:
    """
    Adaptive binarization — converts to black text on white background.

    Uses Gaussian adaptive thresholding which handles uneven lighting
    much better than a simple global threshold.
    """
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold: computes threshold for each pixel based on
    # its local neighborhood (blockSize=15, C=8)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=8,
    )

    return binary
