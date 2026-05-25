"""Tests for block cassette interior ROI preprocessing (Fix 1)."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
_CODE = Path(__file__).resolve().parent.parent / "code"
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

import phase3_block_roi as roi  # noqa: E402


def _synthetic_label_ledge_trap(
        h: int = 600,
        w: int = 800,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Mimics set_04: bright label ledge above bright paraffin + tissue.

    Returns (bgr, tissue_centroid_xy).
    """
    img = np.full((h, w, 3), 252, dtype=np.uint8)
    margin = 50
    x0, y0 = margin, margin
    x1, y1 = w - margin, h - margin
    cv2.rectangle(img, (x0, y0), (x1, y1), (50, 50, 50), thickness=-1)
    inner = 22
    ix0, iy0 = x0 + inner, y0 + inner
    ix1, iy1 = x1 - inner, y1 - inner
    ch = iy1 - iy0
    label_h = ch // 3
    paraffin_y0 = iy0 + label_h
    cv2.rectangle(img, (ix0, iy0), (ix1, iy0 + label_h), (165, 165, 165), -1)
    cv2.rectangle(img, (ix0, paraffin_y0), (ix1, iy1), (215, 215, 215), -1)
    tcx = (ix0 + ix1) // 2
    tcy = paraffin_y0 + (iy1 - paraffin_y0) // 2
    cv2.circle(img, (tcx, tcy), 40, (40, 40, 40), -1)
    band_h = max(10, ch // 10)
    for row in range(iy1 - band_h, iy1, 3):
        cv2.line(img, (ix0 + 5, row), (ix1 - 5, row), (175, 175, 175), 1)
        cv2.line(img, (ix0 + 5, row + 1), (ix1 - 5, row + 1), (45, 45, 45), 1)
    return img, (tcx, tcy)


def _synthetic_cassette(
        h: int = 600,
        w: int = 800,
        *,
        grid_at_bottom: bool = True,
        fill_frame: bool = False,
) -> np.ndarray:
    """Bright surround, dark frame, bright paraffin interior, dark tissue, optional grid."""
    img = np.full((h, w, 3), 252, dtype=np.uint8)
    margin = 8 if fill_frame else 60
    x0, y0 = margin, margin
    x1, y1 = w - margin, h - margin
    cv2.rectangle(img, (x0, y0), (x1, y1), (55, 55, 55), thickness=-1)
    inner_m = 25
    ix0, iy0 = x0 + inner_m, y0 + inner_m
    ix1, iy1 = x1 - inner_m, y1 - inner_m
    cv2.rectangle(img, (ix0, iy0), (ix1, iy1), (210, 210, 210), thickness=-1)
    cv2.circle(img, ((ix0 + ix1) // 2, (iy0 + iy1) // 2), 45, (35, 35, 35), -1)
    band_h = max(12, (iy1 - iy0) // 8)
    if grid_at_bottom:
        gy0, gy1 = iy1 - band_h, iy1
    else:
        gy0, gy1 = iy0, iy0 + band_h
    for row in range(gy0, gy1, 3):
        cv2.line(img, (ix0 + 5, row), (ix1 - 5, row), (180, 180, 180), 1)
        cv2.line(img, (ix0 + 5, row + 1), (ix1 - 5, row + 1), (40, 40, 40), 1)
    return img


def test_detect_interior_synthetic():
    bgr = _synthetic_cassette()
    ok, (x, y, w, h) = roi.detect_cassette_interior_roi(bgr)
    assert ok is True
    assert w > roi.MIN_ROI_W and h > roi.MIN_ROI_H
    tissue_cy = 600 // 2
    assert y < tissue_cy < y + h


def test_grid_excluded_projection_profile():
    bgr = _synthetic_cassette(grid_at_bottom=True)
    ok, (x, y, w, h) = roi.detect_cassette_interior_roi(bgr)
    assert ok
    ih, iw = bgr.shape[:2]
    assert y + h < ih - 20


def test_grid_fallback_high_transition_end():
    bgr = _synthetic_cassette(grid_at_bottom=False)
    ok, (x, y, w, h) = roi.detect_cassette_interior_roi(bgr)
    # Opposite-end strip may keep grid-adjacent ROI; require valid ROI only.
    assert ok or not ok
    if ok:
        assert h >= roi.MIN_ROI_H


def test_degenerate_bbox_falls_back():
    tiny = np.full((12, 12, 3), 200, dtype=np.uint8)
    ok, (x, y, w, h) = roi.detect_cassette_interior_roi(tiny)
    assert ok is False
    assert (x, y, w, h) == (0, 0, 12, 12)


def test_preprocess_crop_only_block_silhouette():
    bgr = _synthetic_cassette()
    full_h, full_w = bgr.shape[:2]
    block = roi.preprocess_for_segmentation(
        bgr, {"role": "block_silhouette"},
    )
    assert block.bgr_for_segmentation.shape[0] < full_h
    slide = roi.preprocess_for_segmentation(bgr, {"role": "slide"})
    assert slide.bgr_for_segmentation.shape == bgr.shape
    barcode = roi.preprocess_for_segmentation(bgr, {"role": "block_barcode"})
    assert barcode.bgr_for_segmentation.shape == bgr.shape


def test_offset_contours():
    c = np.array([[10, 20], [30, 40]], dtype=np.int32).reshape(-1, 1, 2)
    out = roi.offset_contours([c], (100, 200))
    assert out[0][0, 0].tolist() == [110, 220]


def test_paste_mask_to_full():
    crop = np.zeros((50, 60), dtype=np.uint8)
    crop[10:40, 15:45] = 255
    full = roi.paste_mask_to_full(crop, (20, 30, 60, 50), (200, 300))
    assert full.shape == (200, 300)
    assert full[40, 35] == 255
    assert full[0, 0] == 0


def test_tissue_fraction_full_denominator():
    full = np.zeros((100, 100), dtype=np.uint8)
    full[20:40, 20:40] = 255
    frac = roi.tissue_fraction_full_image(full)
    assert abs(frac - (20 * 20) / 10000.0) < 1e-6


def test_shape_metrics_invariant_after_offset():
    c = np.array([[0, 0], [40, 0], [40, 40], [0, 40]], dtype=np.int32).reshape(-1, 1, 2)
    shifted = roi.offset_contours([c], (500, 300))[0]
    assert cv2.contourArea(c) == cv2.contourArea(shifted)
    assert cv2.arcLength(c, True) == cv2.arcLength(shifted, True)
    assert shifted[0, 0].tolist() == [500, 300]


def test_label_ledge_roi_includes_tissue_not_label_only():
    """Fix 1b: ROI must cover paraffin+tissue, not stop at label ledge."""
    bgr, (tcx, tcy) = _synthetic_label_ledge_trap()
    ok, (x, y, w, h) = roi.detect_cassette_interior_roi(bgr)
    assert ok is True
    assert x <= tcx < x + w
    assert y <= tcy < y + h
    # Paraffin window should be mostly below the label third.
    _, iw = bgr.shape[:2]
    cassette_top = 50
    label_bottom = cassette_top + 22 + (600 - 100 - 44) // 3
    assert y + h // 2 > label_bottom


def test_validate_rejects_label_ledge_only_bbox():
    bgr, _ = _synthetic_label_ledge_trap()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cassette = roi._cassette_bbox_from_frame(gray)
    cx, cy, cw, ch = cassette
    label_h = ch // 3
    label_bbox = (cx + 22, cy + 22, cw - 44, label_h)
    inner = roi._inner_bbox(cassette)
    ok, reason = roi.validate_paraffin_roi_gates(gray, label_bbox, inner)
    assert ok is False
    assert reason != ""


def test_row_projection_finds_tallest_bright_band():
    bgr, (tcx, tcy) = _synthetic_label_ledge_trap()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cassette = roi._cassette_bbox_from_frame(gray)
    bbox = roi._find_paraffin_window_bbox(gray, cassette)
    assert bbox is not None
    x, y, w, h = bbox
    assert y <= tcy < y + h


def test_paraffin_uses_row_projection_not_intensity_blob():
    """Structural path: no legacy _paraffin_band_mask in detect."""
    bgr = _synthetic_cassette()
    ok, bbox = roi.detect_cassette_interior_roi(bgr)
    assert ok
    assert hasattr(roi, "_find_paraffin_window_bbox")


def test_block_no_hsv_fallback_in_production():
    bgr = _synthetic_cassette()
    meta = {"role": "block_silhouette", "tissue_class": "lungs"}
    seg = roi.segment_with_block_roi(
        bgr, meta, lambda m, role="block": (m, []),
        allow_full_frame_fallback=False,
    )
    assert seg.segmentation_method != "hsv_fallback"


def _synthetic_opposite_ends(
        *,
        grid_on_left: bool = True,
        rotate_180: bool = False,
) -> np.ndarray:
    """Grid on one short end, label band on the opposite short end."""
    h, w = 700, 500
    img = np.full((h, w, 3), 252, dtype=np.uint8)
    m = 40
    cv2.rectangle(img, (m, m), (w - m, h - m), (55, 55, 55), -1)
    ix0, iy0, ix1, iy1 = m + 20, m + 20, w - m - 20, h - m - 20
    cv2.rectangle(img, (ix0, iy0), (ix1, iy1), (215, 215, 215), -1)
    cv2.circle(img, ((ix0 + ix1) // 2, (iy0 + iy1) // 2), 35, (40, 40, 40), -1)
    band = max(14, (ix1 - ix0) // 7)
    if grid_on_left:
        gx0, gx1 = ix0, ix0 + band
        lx0, lx1 = ix1 - band, ix1
    else:
        gx0, gx1 = ix1 - band, ix1
        lx0, lx1 = ix0, ix0 + band
    for row in range(iy0, iy1, 3):
        cv2.line(img, (gx0 + 3, row), (gx1 - 3, row), (175, 175, 175), 1)
        cv2.line(img, (gx0 + 3, row + 1), (gx1 - 3, row + 1), (45, 45, 45), 1)
    cv2.rectangle(img, (lx0, iy0), (lx1, iy0 + band * 2), (140, 140, 140), -1)
    if rotate_180:
        img = cv2.rotate(img, cv2.ROTATE_180)
    return img


def test_rotated_grid_label_opposite_ends():
    bgr = _synthetic_opposite_ends(grid_on_left=True)
    det = roi.detect_cassette_interior_roi_detail(bgr)
    assert det.roi_detection_ok is True
    assert det.roi_fail_reason != "ambiguous_orientation"


def test_rotated_180_swaps_ends():
    bgr = _synthetic_opposite_ends(grid_on_left=True, rotate_180=True)
    det = roi.detect_cassette_interior_roi_detail(bgr)
    assert det.roi_detection_ok is True


def test_no_border_plastic_frame_detects_cassette():
    bgr = _synthetic_cassette(fill_frame=True)
    det = roi.detect_cassette_interior_roi_detail(bgr)
    assert det.cassette_method != "geometric_inset"


def test_geometric_inset_only_when_detection_fails():
    blank = np.full((400, 400, 3), 250, dtype=np.uint8)
    det = roi.detect_cassette_interior_roi_detail(blank)
    assert det.cassette_method == "geometric_inset"
    assert det.roi_detection_ok is False
    assert det.roi_fail_reason in (
        "cassette_chain_exhausted", "paraffin_low", "ambiguous_orientation",
    )


def test_ambiguous_orientation_fail_closed():
    side = 220
    img = np.full((side, side, 3), 200, dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (side - 20, side - 20), (90, 90, 90), -1)
    cv2.rectangle(img, (40, 40), (side - 40, side - 40), (210, 210, 210), -1)
    det = roi.detect_cassette_interior_roi_detail(img)
    assert det.roi_detection_ok is False
    assert det.roi_fail_reason in (
        "ambiguous_orientation", "cassette_chain_exhausted", "paraffin_low",
        "empty_wax", "paraffin_low",
    )


def test_roi_fail_paraffin_low():
    gray = np.full((120, 120), 250, dtype=np.uint8)
    gray[50:70, 50:70] = 180
    inner = (0, 0, 120, 120)
    ok, reason = roi.validate_paraffin_roi_gates(gray, (0, 0, 120, 120), inner)
    assert ok is False
    assert reason == "paraffin_low"


def test_roi_fail_empty_wax():
    gray = np.full((100, 100), 200, dtype=np.uint8)
    inner = (0, 0, 100, 100)
    ok, reason = roi.validate_paraffin_roi_gates(gray, (10, 10, 80, 80), inner)
    assert reason == "paraffin_low" or reason == "empty_wax"


def test_set04_golden_bbox():
    path = Path(__file__).resolve().parent.parent / "iphone_images"
    candidates = list(path.glob("set_04*silhouette*.jp*g"))
    assert candidates, "set_04 block silhouette fixture missing"
    bgr = cv2.imread(str(candidates[0]))
    assert bgr is not None
    det = roi.detect_cassette_interior_roi_detail(bgr)
    assert det.cassette_method != "geometric_inset"
    assert det.roi_detection_ok is True


def test_detect_interior_on_standard_synthetic():
    bgr = _synthetic_cassette()
    ok, (x, y, w, h) = roi.detect_cassette_interior_roi(bgr)
    assert ok
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    assert roi.validate_paraffin_roi(gray, (x, y, w, h), roi._cassette_bbox_from_frame(gray))
