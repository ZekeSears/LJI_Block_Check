"""
phase3_label_detection.py — robust slide-label detection.

Replaces Phase 2's percentage-based SLIDE_LABEL_ROI_FRACTION with a
geometric+edge-density classifier:

    rectangularity (contourArea / minAreaRect_area) ≥ LABEL_RECTANGULARITY
        AND  aspect_ratio ∈ LABEL_ASPECT_RATIO_RANGE
        AND  border-band Canny edge density ≥ LABEL_EDGE_DENSITY_MIN

Pre-mortem §2 ¶2 critical: v1's "low interior variance" / uniformity
criterion is REMOVED. Real labels carry printed barcodes/text/QR — high
interior variance is the norm, not the exception. The reliable signal is
the sharp rectangular border edge.

Frozen-interface discipline: this module is NEW and does NOT modify
clean_mask() in code/phase2_descriptors.py. The unified matcher
(phase3_unified_matcher.py) calls detect_label_region() or
apply_label_mask() on the raw BGR slide image BEFORE segment_tissue() runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Calibration constants
# ---------------------------------------------------------------------------

LABEL_RECTANGULARITY_THRESHOLD: float = 0.90
LABEL_ASPECT_RATIO_RANGE: tuple[float, float] = (1.5, 4.0)
LABEL_EDGE_DENSITY_MIN: float = 0.03  # fraction of border-band pixels marked as edges
LABEL_FALLBACK_ROI_FRACTION: float = 0.30
LABEL_MIN_AREA_FRACTION: float = 0.01
LABEL_MAX_AREA_FRACTION: float = 0.50
BORDER_BAND_FRACTION: float = 0.10


@dataclass(frozen=True)
class LabelDetectionResult:
    found: bool
    bounding_rect: Optional[tuple[int, int, int, int]]  # (x, y, w, h)
    rectangularity: Optional[float]
    aspect_ratio: Optional[float]
    border_edge_density: Optional[float]
    reason: str


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _candidate_external_contours(bgr_image: np.ndarray) -> list[np.ndarray]:
    """Otsu-threshold the raw grayscale image and return external contours.
    Used to enumerate candidate rectangular regions for label
    classification — distinct from Phase 1's segment_tissue() which
    inverts first."""
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    # Backlit-slide convention: glass is BRIGHT (transilluminator), and
    # both the opaque label and the tissue appear DARK. We invert before
    # Otsu so darker-than-background regions (label + tissue) become
    # foreground, matching Phase 1's segment_tissue() convention. The
    # label classifier then distinguishes label from tissue by geometry
    # and border-edge density, not by polarity.
    gray_inv = cv2.bitwise_not(gray)
    _, mask = cv2.threshold(gray_inv, 0, 255,
                            cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    return list(contours)


def _classify_candidate(contour: np.ndarray, gray: np.ndarray,
                        image_area: float) -> LabelDetectionResult:
    """Apply the three-criterion classifier to a single candidate contour."""
    area = float(cv2.contourArea(contour))
    if area <= 0:
        return LabelDetectionResult(False, None, None, None, None,
                                    "zero-area contour")
    area_frac = area / image_area
    if area_frac < LABEL_MIN_AREA_FRACTION:
        return LabelDetectionResult(False, None, None, None, None,
                                    "below min area fraction")
    if area_frac > LABEL_MAX_AREA_FRACTION:
        return LabelDetectionResult(False, None, None, None, None,
                                    "above max area fraction")

    rect = cv2.minAreaRect(contour)
    (_cx, _cy), (rw, rh), _angle = rect
    if rw <= 0 or rh <= 0:
        return LabelDetectionResult(False, None, None, None, None,
                                    "degenerate min-area rect")
    rectangularity = area / (rw * rh)
    if rectangularity < LABEL_RECTANGULARITY_THRESHOLD:
        return LabelDetectionResult(False, None, rectangularity, None, None,
                                    "rectangularity below threshold")

    long_side = max(rw, rh)
    short_side = min(rw, rh)
    aspect = long_side / short_side
    lo, hi = LABEL_ASPECT_RATIO_RANGE
    if not (lo <= aspect <= hi):
        return LabelDetectionResult(False, None, rectangularity, aspect, None,
                                    "aspect ratio out of range")

    # ---- Canny border-band edge density ------------------------------------
    x, y, w, h = cv2.boundingRect(contour)
    H, W = gray.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return LabelDetectionResult(False, None, rectangularity, aspect, None,
                                    "empty ROI")

    edges = cv2.Canny(roi, 50, 150)
    band = max(1, int(min(roi.shape) * BORDER_BAND_FRACTION))
    border_mask = np.zeros_like(edges, dtype=bool)
    border_mask[:band, :] = True
    border_mask[-band:, :] = True
    border_mask[:, :band] = True
    border_mask[:, -band:] = True
    border_pixels = int(border_mask.sum())
    if border_pixels == 0:
        density = 0.0
    else:
        density = float((edges[border_mask] > 0).sum()) / float(border_pixels)
    if density < LABEL_EDGE_DENSITY_MIN:
        return LabelDetectionResult(False, None, rectangularity, aspect,
                                    density, "border edge density too low")

    return LabelDetectionResult(
        found=True,
        bounding_rect=(int(x), int(y), int(w), int(h)),
        rectangularity=float(rectangularity),
        aspect_ratio=float(aspect),
        border_edge_density=float(density),
        reason="passed",
    )


def detect_label_region(bgr_image: np.ndarray) -> LabelDetectionResult:
    """Find the slide-label region in a raw BGR slide image.

    Returns a LabelDetectionResult; `.found` is True iff a candidate
    passed all three criteria. When multiple candidates pass, the one
    with the highest rectangularity is returned.
    """
    if bgr_image is None or bgr_image.ndim != 3 or bgr_image.shape[2] != 3:
        raise ValueError("detect_label_region requires a non-empty HxWx3 BGR image.")
    if bgr_image.dtype != np.uint8:
        raise ValueError("detect_label_region requires uint8 BGR input.")

    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape[:2]
    image_area = float(H * W)

    contours = _candidate_external_contours(bgr_image)
    passing: list[LabelDetectionResult] = []
    for c in contours:
        res = _classify_candidate(c, gray, image_area)
        if res.found:
            passing.append(res)
    if not passing:
        return LabelDetectionResult(False, None, None, None, None,
                                    "no candidate passed")
    return max(passing, key=lambda r: r.rectangularity or 0.0)


def apply_label_mask(bgr_image: np.ndarray) -> np.ndarray:
    """Return a copy of bgr_image with the detected label region zeroed,
    or — when no label is detected — with the top
    LABEL_FALLBACK_ROI_FRACTION of rows zeroed (preserving Phase 2
    behavior as a safety net for hard cases such as set_01_slide).
    """
    if bgr_image is None or bgr_image.ndim != 3 or bgr_image.shape[2] != 3:
        raise ValueError("apply_label_mask requires a non-empty HxWx3 BGR image.")
    out = bgr_image.copy()
    result = detect_label_region(bgr_image)
    if result.found and result.bounding_rect is not None:
        x, y, w, h = result.bounding_rect
        out[y:y + h, x:x + w, :] = 0
        return out
    # Fallback: top-band ROI.
    H = out.shape[0]
    fallback_rows = int(H * LABEL_FALLBACK_ROI_FRACTION)
    if fallback_rows > 0:
        out[:fallback_rows, :, :] = 0
    return out


__all__ = [
    "LABEL_RECTANGULARITY_THRESHOLD",
    "LABEL_ASPECT_RATIO_RANGE",
    "LABEL_EDGE_DENSITY_MIN",
    "LABEL_FALLBACK_ROI_FRACTION",
    "BORDER_BAND_FRACTION",
    "LabelDetectionResult",
    "detect_label_region",
    "apply_label_mask",
]
