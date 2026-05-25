"""
phase3_block_roi.py — Plastic-first cassette ROI + Otsu-only block seg (Fix 1d).

Phone: plastic-first chain (no backlight_cc); Pi: backlight_cc only with strong margin.
Gates G1–G5; deferred ambiguous_orientation; production fail-closed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from phase1_segmentation import MORPH_KERNEL_SIZE, segment_tissue

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CFG_CACHE: dict[str, dict[str, Any]] = {}

# Pilot visual gate (phone library); full 47-set regen only after pass.
PILOT_VISUAL_PASS_MIN = 8
PILOT_SET_IDS = frozenset({2, 4, 6, 11, 28, 31, 33, 35, 40, 45})

# Defaults until JSON load (tests may import before reload).
BACKLIGHT_THRESH = 240
BACKLIGHT_EDGE_FRAC = 0.03
MARGIN_STRICT_MIN_PERIM_FRAC = 0.03
PLASTIC_GRAY_LOW = 80
PLASTIC_GRAY_HIGH = 135
FRAME_THRESH = 110
PARAFFIN_ROW_MEAN = 165
PARAFFIN_PIXEL_LOW = 140
PARAFFIN_MIN_WIDTH_FRAC = 0.42
PARAFFIN_MIN_HEIGHT_FRAC = 0.08
PARAFFIN_ROW_MIN_FRAC = 0.05
MORPH_CLOSE_PARAFFIN = (25, 41)
INNER_INSET_FRAC = 0.06
ASPECT_NEAR_SQUARE_MIN = 0.95
ASPECT_NEAR_SQUARE_MAX = 1.05
ASPECT_AMBIGUOUS_EPS = 0.05
AMBIGUOUS_SCORE_TIE_EPS = 0.10
STRIP_DELTA_MIN = 0.10
GRID_STRIP_FRAC = 0.15
LABEL_STRIP_FRAC = 0.18
GRID_SCORE_TIE_FRAC = 0.10
G1_PARAFFIN_MIN_FRAC = 0.12
G2_ROI_WIDTH_MIN_FRAC = 0.42
G3_BACKLIGHT_MAX_FRAC = 0.25
G4_MIN_HEIGHT_FRAC = 0.15
G5_MAX_AREA_FRAC = 0.90
EMPTY_WAX_MAX_FRAC = 0.0003
CASSETTE_AREA_MIN_FRAC = 0.15
CASSETTE_AREA_MAX_FRAC = 0.92
ENVELOPE_MIN_WIDTH_FRAC = 0.35
GEOMETRIC_INSET_FRAC = 0.08
OTSU_MASK_FRAC_MIN = 0.0003
OTSU_MASK_FRAC_MAX = 0.85
SEG_BLOB_FRAC = 0.55
SEG_BLOB_MAX_CONTOURS = 2


def reload_block_roi_constants() -> None:
    """Clear JSON cache (tests after editing constants files)."""
    _CFG_CACHE.clear()
    _apply_constants("phone")


def _constants_path(source: str) -> Path:
    return _REPO_ROOT / "phase3_outputs" / f"block_roi_constants_{source}.json"


def load_block_roi_constants(capture_source: str = "phone") -> dict[str, Any]:
    key = "pi" if capture_source == "pi" else "phone"
    if key not in _CFG_CACHE:
        path = _constants_path(key)
        if not path.is_file():
            raise FileNotFoundError(f"missing ROI constants: {path}")
        _CFG_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
    return _CFG_CACHE[key]


def _apply_constants(capture_source: str = "phone") -> None:
    global BACKLIGHT_THRESH, BACKLIGHT_EDGE_FRAC, MARGIN_STRICT_MIN_PERIM_FRAC
    global PLASTIC_GRAY_LOW, PLASTIC_GRAY_HIGH, FRAME_THRESH
    global PARAFFIN_ROW_MEAN, PARAFFIN_PIXEL_LOW, PARAFFIN_MIN_WIDTH_FRAC
    global PARAFFIN_MIN_HEIGHT_FRAC, PARAFFIN_ROW_MIN_FRAC, MORPH_CLOSE_PARAFFIN
    global INNER_INSET_FRAC, ASPECT_NEAR_SQUARE_MIN, ASPECT_NEAR_SQUARE_MAX
    global AMBIGUOUS_SCORE_TIE_EPS, STRIP_DELTA_MIN, GRID_STRIP_FRAC, LABEL_STRIP_FRAC
    global G1_PARAFFIN_MIN_FRAC, G2_ROI_WIDTH_MIN_FRAC, G3_BACKLIGHT_MAX_FRAC
    global G4_MIN_HEIGHT_FRAC, G5_MAX_AREA_FRAC, EMPTY_WAX_MAX_FRAC
    global CASSETTE_AREA_MIN_FRAC, CASSETTE_AREA_MAX_FRAC, ENVELOPE_MIN_WIDTH_FRAC
    global GEOMETRIC_INSET_FRAC, OTSU_MASK_FRAC_MIN, OTSU_MASK_FRAC_MAX
    global SEG_BLOB_FRAC, SEG_BLOB_MAX_CONTOURS

    cfg = load_block_roi_constants(capture_source)
    BACKLIGHT_THRESH = int(cfg["BACKLIGHT_THRESH"])
    BACKLIGHT_EDGE_FRAC = float(cfg["BACKLIGHT_EDGE_FRAC"])
    margin = float(cfg["MARGIN_STRICT_MIN_PERIM_FRAC"])
    MARGIN_STRICT_MIN_PERIM_FRAC = max(margin, BACKLIGHT_EDGE_FRAC)
    PLASTIC_GRAY_LOW = int(cfg["PLASTIC_GRAY_LOW"])
    PLASTIC_GRAY_HIGH = int(cfg["PLASTIC_GRAY_HIGH"])
    FRAME_THRESH = int(cfg["FRAME_THRESH"])
    PARAFFIN_ROW_MEAN = int(cfg["PARAFFIN_ROW_MEAN"])
    PARAFFIN_PIXEL_LOW = int(cfg["PARAFFIN_PIXEL_LOW"])
    PARAFFIN_MIN_WIDTH_FRAC = float(cfg["PARAFFIN_MIN_WIDTH_FRAC"])
    PARAFFIN_MIN_HEIGHT_FRAC = float(cfg["PARAFFIN_MIN_HEIGHT_FRAC"])
    PARAFFIN_ROW_MIN_FRAC = float(cfg["PARAFFIN_ROW_MIN_FRAC"])
    MORPH_CLOSE_PARAFFIN = (
        int(cfg["MORPH_CLOSE_PARAFFIN_W"]),
        int(cfg["MORPH_CLOSE_PARAFFIN_H"]),
    )
    INNER_INSET_FRAC = float(cfg["INNER_INSET_FRAC"])
    ASPECT_NEAR_SQUARE_MIN = float(cfg["ASPECT_NEAR_SQUARE_MIN"])
    ASPECT_NEAR_SQUARE_MAX = float(cfg["ASPECT_NEAR_SQUARE_MAX"])
    AMBIGUOUS_SCORE_TIE_EPS = float(cfg["AMBIGUOUS_SCORE_TIE_EPS"])
    STRIP_DELTA_MIN = float(cfg["STRIP_DELTA_MIN"])
    GRID_STRIP_FRAC = float(cfg["GRID_STRIP_FRAC"])
    LABEL_STRIP_FRAC = float(cfg["LABEL_STRIP_FRAC"])
    G1_PARAFFIN_MIN_FRAC = float(cfg["G1_PARAFFIN_MIN_FRAC"])
    G2_ROI_WIDTH_MIN_FRAC = float(cfg["G2_ROI_WIDTH_MIN_FRAC"])
    G3_BACKLIGHT_MAX_FRAC = float(cfg["G3_BACKLIGHT_MAX_FRAC"])
    G4_MIN_HEIGHT_FRAC = float(cfg["G4_MIN_HEIGHT_FRAC"])
    G5_MAX_AREA_FRAC = float(cfg["G5_MAX_AREA_FRAC"])
    EMPTY_WAX_MAX_FRAC = float(cfg["EMPTY_WAX_MAX_FRAC"])
    CASSETTE_AREA_MIN_FRAC = float(cfg["CASSETTE_AREA_MIN_FRAC"])
    CASSETTE_AREA_MAX_FRAC = float(cfg["CASSETTE_AREA_MAX_FRAC"])
    ENVELOPE_MIN_WIDTH_FRAC = float(cfg["ENVELOPE_MIN_WIDTH_FRAC"])
    GEOMETRIC_INSET_FRAC = float(cfg["GEOMETRIC_INSET_FRAC"])
    OTSU_MASK_FRAC_MIN = float(cfg["OTSU_MASK_FRAC_MIN"])
    OTSU_MASK_FRAC_MAX = float(cfg["OTSU_MASK_FRAC_MAX"])
    SEG_BLOB_FRAC = float(cfg["SEG_BLOB_FRAC"])
    SEG_BLOB_MAX_CONTOURS = int(cfg["SEG_BLOB_MAX_CONTOURS"])


_apply_constants("phone")



def capture_source_from_meta(meta: dict[str, Any]) -> str:
    src = meta.get("capture_source")
    if src in ("phone", "pi"):
        return src
    return "phone"

MIN_ROI_W = 2 * MORPH_KERNEL_SIZE
MIN_ROI_H = 2 * MORPH_KERNEL_SIZE
MIN_ROI_AREA = MIN_ROI_W * MIN_ROI_H


@dataclass(frozen=True)
class RoiDetectionResult:
    roi_detection_ok: bool
    roi_bbox: tuple[int, int, int, int]
    cassette_method: str = ""
    roi_fail_reason: str = ""
    low_confidence: bool = False
    strip_method: str = ""
    paraffin_method: str = ""
    ambiguous_orientation: bool = False
    gate_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreprocessResult:
    bgr_for_segmentation: np.ndarray
    roi_bbox: tuple[int, int, int, int]
    roi_detection_ok: bool
    crop_origin: tuple[int, int]
    full_shape: tuple[int, int]
    cassette_method: str = ""
    roi_fail_reason: str = ""
    low_confidence: bool = False


@dataclass(frozen=True)
class SegmentationWithRoi:
    cleaned_mask: np.ndarray
    contours: list[np.ndarray]
    otsu_threshold: int
    roi_detection_ok: bool
    roi_bbox: tuple[int, int, int, int]
    crop_origin: tuple[int, int]
    segmentation_method: str = "otsu"
    cassette_method: str = ""
    roi_fail_reason: str = ""
    seg_fail_reason: str = ""
    reshoot_recommended: bool = False
    low_confidence: bool = False


def _validate_bgr(bgr: np.ndarray) -> None:
    if bgr.ndim != 3 or bgr.shape[2] != 3 or bgr.dtype != np.uint8:
        raise ValueError(f"bgr must be HxWx3 uint8; got {bgr.shape!r} {bgr.dtype!r}")


def _roi_valid(w: int, h: int) -> bool:
    return w >= MIN_ROI_W and h >= MIN_ROI_H and (w * h) >= MIN_ROI_AREA


def perimeter_bright_fraction(gray: np.ndarray) -> float:
    bright = gray >= BACKLIGHT_THRESH
    perimeter = np.zeros_like(bright, dtype=bool)
    perimeter[0, :] = True
    perimeter[-1, :] = True
    perimeter[:, 0] = True
    perimeter[:, -1] = True
    return float(bright[perimeter].sum()) / max(1, perimeter.sum())


def detect_has_backlight_margin(gray: np.ndarray) -> bool:
    """Legacy weak margin (tests / diagnostics)."""
    if perimeter_bright_fraction(gray) < BACKLIGHT_EDGE_FRAC:
        return False
    bright = gray >= BACKLIGHT_THRESH
    edges_hit = sum([
        bright[0, :].any(),
        bright[-1, :].any(),
        bright[:, 0].any(),
        bright[:, -1].any(),
    ])
    return edges_hit >= 2


def detect_has_strong_margin(gray: np.ndarray) -> bool:
    """Data-derived strict margin for Pi backlight_cc eligibility."""
    if perimeter_bright_fraction(gray) < MARGIN_STRICT_MIN_PERIM_FRAC:
        return False
    bright = gray >= BACKLIGHT_THRESH
    edges_hit = sum([
        bright[0, :].any(),
        bright[-1, :].any(),
        bright[:, 0].any(),
        bright[:, -1].any(),
    ])
    return edges_hit >= 2


def _cassette_bbox_from_plastic(gray: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    h, w = gray.shape[:2]
    img_area = h * w
    fg = (
        (gray >= PLASTIC_GRAY_LOW) & (gray <= PLASTIC_GRAY_HIGH)
    ).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best: Optional[tuple[int, int, int, int]] = None
    best_area = 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < CASSETTE_AREA_MIN_FRAC * img_area:
            continue
        if area > CASSETTE_AREA_MAX_FRAC * img_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if area > best_area:
            best_area = area
            best = (int(x), int(y), int(bw), int(bh))
    return best


def _cassette_bbox_from_frame(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Dark plastic frame (Fix 1b compat)."""
    h, w = gray.shape[:2]
    fg = (gray < FRAME_THRESH).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0, 0, w, h
    largest = max(contours, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(largest)
    return (int(x), int(y), int(bw), int(bh))


_cassette_bbox = _cassette_bbox_from_frame


def _cassette_bbox_backlight_cc(gray: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    h, w = gray.shape[:2]
    not_bright = (gray < BACKLIGHT_THRESH).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(not_bright, connectivity=8)
    if n < 2:
        return None
    best_idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x = int(stats[best_idx, cv2.CC_STAT_LEFT])
    y = int(stats[best_idx, cv2.CC_STAT_TOP])
    bw = int(stats[best_idx, cv2.CC_STAT_WIDTH])
    bh = int(stats[best_idx, cv2.CC_STAT_HEIGHT])
    if bw < MIN_ROI_W or bh < MIN_ROI_H:
        return None
    return x, y, bw, bh


def _cassette_bbox_paraffin_envelope(gray: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    h, w = gray.shape[:2]
    pm = (
        (gray >= PARAFFIN_PIXEL_LOW) & (gray < BACKLIGHT_THRESH)
    ).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(pm, connectivity=8)
    if n < 2:
        return None
    best: Optional[tuple[int, int, int, int]] = None
    best_area = 0.0
    for idx in range(1, n):
        bw = int(stats[idx, cv2.CC_STAT_WIDTH])
        if bw < int(w * ENVELOPE_MIN_WIDTH_FRAC):
            continue
        touches_all = (
            stats[idx, cv2.CC_STAT_LEFT] == 0
            and stats[idx, cv2.CC_STAT_TOP] == 0
            and stats[idx, cv2.CC_STAT_LEFT] + bw >= w - 2
            and stats[idx, cv2.CC_STAT_TOP] + stats[idx, cv2.CC_STAT_HEIGHT] >= h - 2
        )
        if touches_all:
            continue
        area = float(stats[idx, cv2.CC_STAT_AREA])
        if area > best_area:
            best_area = area
            x = int(stats[idx, cv2.CC_STAT_LEFT])
            y = int(stats[idx, cv2.CC_STAT_TOP])
            bh = int(stats[idx, cv2.CC_STAT_HEIGHT])
            best = (x, y, bw, bh)
    return best


def _geometric_cassette_bbox(h: int, w: int) -> tuple[int, int, int, int]:
    ix = int(w * GEOMETRIC_INSET_FRAC)
    iy = int(h * GEOMETRIC_INSET_FRAC)
    return ix, iy, w - 2 * ix, h - 2 * iy


def detect_cassette_bbox(
        gray: np.ndarray,
        *,
        capture_source: str = "phone",
        has_strong_margin: Optional[bool] = None,
) -> tuple[tuple[int, int, int, int], str, bool]:
    """Return (bbox, cassette_method, low_confidence). Phone: no backlight_cc."""
    h, w = gray.shape[:2]
    img_area = h * w
    if has_strong_margin is None:
        has_strong_margin = detect_has_strong_margin(gray)
    if capture_source == "pi" and has_strong_margin:
        bb = _cassette_bbox_backlight_cc(gray)
        if bb is not None:
            return bb, "backlight_cc", False
    bb = _cassette_bbox_from_plastic(gray)
    if bb is not None:
        return bb, "plastic_frame", False
    bb = _cassette_bbox_from_frame(gray)
    bb_area = bb[2] * bb[3]
    if CASSETTE_AREA_MIN_FRAC * img_area <= bb_area <= CASSETTE_AREA_MAX_FRAC * img_area:
        return bb, "dark_frame", False
    bb = _cassette_bbox_paraffin_envelope(gray)
    if bb is not None:
        return bb, "paraffin_envelope", False
    return _geometric_cassette_bbox(h, w), "geometric_inset", True


def _inner_bbox(cassette: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    cx, cy, cw, ch = cassette
    ix = max(2, int(cw * INNER_INSET_FRAC))
    iy = max(2, int(ch * INNER_INSET_FRAC))
    return cx + ix, cy + iy, cw - 2 * ix, ch - 2 * iy


def _row_transition_counts(row: np.ndarray) -> int:
    if row.size < 2:
        return 0
    return int(np.sum(np.abs(np.diff(row.astype(np.int16))) > 0))


def _short_end_transition_scores(
        gray: np.ndarray,
        inner: tuple[int, int, int, int],
) -> tuple[float, float, bool]:
    """Scores for the two short ends; returns (end0, end1, vertical_short_ends)."""
    ix, iy, iw, ih = inner
    vertical = iw <= ih
    band = max(3, int((iw if vertical else ih) * GRID_STRIP_FRAC))
    sub = gray[iy:iy + ih, ix:ix + iw]
    if vertical:
        left = sub[:, :band]
        right = sub[:, iw - band:]
        s0 = float(np.mean([_row_transition_counts(left[r, :]) for r in range(ih)]))
        s1 = float(np.mean([_row_transition_counts(right[r, :]) for r in range(ih)]))
    else:
        top = sub[:band, :]
        bottom = sub[ih - band:, :]
        s0 = float(np.mean([_row_transition_counts(top[:, c]) for c in range(iw)]))
        s1 = float(np.mean([_row_transition_counts(bottom[:, c]) for c in range(iw)]))
    return s0, s1, vertical


def _inner_aspect_near_square(inner: tuple[int, int, int, int]) -> bool:
    _, _, iw, ih = inner
    if ih == 0:
        return True
    ratio = iw / float(ih)
    return ASPECT_NEAR_SQUARE_MIN <= ratio <= ASPECT_NEAR_SQUARE_MAX


def _orientation_ambiguous(
        gray: np.ndarray,
        inner: tuple[int, int, int, int],
        *,
        paraffin_morph_failed: bool,
) -> bool:
    """Deferred: only after paraffin morph fails, near-square, tied short ends."""
    if not paraffin_morph_failed:
        return False
    if not _inner_aspect_near_square(inner):
        return False
    s0, s1, _ = _short_end_transition_scores(gray, inner)
    return abs(s0 - s1) <= AMBIGUOUS_SCORE_TIE_EPS * max(s0, s1, 1.0)


def _strip_end_band(
        bbox: tuple[int, int, int, int],
        inner: tuple[int, int, int, int],
        *,
        strip_first_end: bool,
        vertical_short: bool,
        frac: float,
) -> tuple[int, int, int, int]:
    x, y, w, h = bbox
    ix, iy, iw, ih = inner
    if vertical_short:
        band = max(2, int(iw * frac))
        if strip_first_end:
            nx, nw = x + band, w - band
            if nw >= MIN_ROI_W:
                return nx, y, nw, h
        else:
            nw = w - band
            if nw >= MIN_ROI_W:
                return x, y, nw, h
    else:
        band = max(2, int(ih * frac))
        if strip_first_end:
            ny, nh = y + band, h - band
            if nh >= MIN_ROI_H:
                return x, ny, w, nh
        else:
            nh = h - band
            if nh >= MIN_ROI_H:
                return x, y, w, nh
    return bbox


def _strip_grid_and_label(
        gray: np.ndarray,
        bbox: tuple[int, int, int, int],
        inner: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], str]:
    s0, s1, vertical = _short_end_transition_scores(gray, inner)
    denom = max(s0, s1, 1.0)
    if abs(s0 - s1) / denom <= STRIP_DELTA_MIN:
        return bbox, "none"
    grid_on_first = s0 >= s1
    out = bbox
    if grid_on_first:
        out = _strip_end_band(out, inner, strip_first_end=True,
                              vertical_short=vertical, frac=GRID_STRIP_FRAC)
        out = _strip_end_band(out, inner, strip_first_end=False,
                              vertical_short=vertical, frac=LABEL_STRIP_FRAC)
    else:
        out = _strip_end_band(out, inner, strip_first_end=False,
                              vertical_short=vertical, frac=GRID_STRIP_FRAC)
        out = _strip_end_band(out, inner, strip_first_end=True,
                              vertical_short=vertical, frac=LABEL_STRIP_FRAC)
    return out, "opposite_end"


def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: Optional[int] = None
    for i, val in enumerate(mask):
        if val and start is None:
            start = i
        elif not val and start is not None:
            runs.append((start, i - start))
            start = None
    if start is not None:
        runs.append((start, len(mask) - start))
    return runs


def _find_paraffin_window_bbox_morph(
        gray: np.ndarray,
        cassette: tuple[int, int, int, int],
) -> Optional[tuple[int, int, int, int]]:
    cx, cy, cw, ch = cassette
    if cw < MIN_ROI_W or ch < MIN_ROI_H:
        return None
    sub = gray[cy:cy + ch, cx:cx + cw]
    pm = (
        (sub >= PARAFFIN_PIXEL_LOW) & (sub < BACKLIGHT_THRESH)
    ).astype(np.uint8) * 255
    kw, kh = MORPH_CLOSE_PARAFFIN
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
    closed = cv2.morphologyEx(pm, cv2.MORPH_CLOSE, kernel)
    del pm
    contours, _ = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )
    del closed
    if not contours:
        return None

    min_w = int(cw * PARAFFIN_MIN_WIDTH_FRAC)
    min_h = int(ch * PARAFFIN_MIN_HEIGHT_FRAC)
    candidates: list[tuple[float, int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_w or h < min_h:
            continue
        if h >= int(ch * 0.92) and y <= int(ch * 0.08):
            continue
        area = float(cv2.contourArea(contour))
        candidates.append((area, x, y, w, h))

    if not candidates:
        return None

    def _score(item: tuple[float, int, int, int, int]) -> float:
        area, _x, y, w, h = item
        cy_frac = (y + h / 2.0) / ch
        width_frac = w / float(cw)
        center_w = 1.0 if 0.18 <= cy_frac <= 0.92 else 0.35
        return area * width_frac * center_w

    _, x, y, w, h = max(candidates, key=_score)
    return cx + x, cy + y, w, h


def _find_paraffin_window_bbox_rows(
        gray: np.ndarray,
        cassette: tuple[int, int, int, int],
) -> Optional[tuple[int, int, int, int]]:
    cx, cy, cw, ch = cassette
    sub = gray[cy:cy + ch, cx:cx + cw]
    row_means = np.zeros(ch, dtype=np.float64)
    for i in range(ch):
        px = sub[i, :]
        bright_px = px[(px >= PARAFFIN_PIXEL_LOW) & (px < BACKLIGHT_THRESH)]
        if bright_px.size >= max(8, int(cw * 0.12)):
            row_means[i] = float(bright_px.mean())
    bright = row_means >= PARAFFIN_ROW_MEAN
    runs = _contiguous_runs(bright)
    if not runs:
        return None
    run_start, run_len = max(runs, key=lambda r: r[1])
    if run_len < MIN_ROI_H:
        return None
    py0 = cy + run_start
    paraffin_rows = sub[run_start:run_start + run_len, :]
    col_means = paraffin_rows.mean(axis=0)
    col_bright = col_means >= (PARAFFIN_ROW_MEAN - 15)
    if not col_bright.any():
        return None
    cols = np.where(col_bright)[0]
    px0 = cx + int(cols[0])
    px1 = cx + int(cols[-1]) + 1
    return px0, py0, px1 - px0, run_len


def evaluate_roi_gates(
        gray: np.ndarray,
        bbox: tuple[int, int, int, int],
        inner: tuple[int, int, int, int],
        image_size: tuple[int, int],
) -> tuple[bool, str, list[str]]:
    """G1–G6 shared by production and pilot_roi_geometry_check."""
    x, y, w, h = bbox
    img_h, img_w = image_size
    _, _, iw, ih_inner = inner
    failures: list[str] = []
    if not _roi_valid(w, h):
        failures.append("roi_narrow")
    sub = gray[y:y + h, x:x + w]
    if sub.size == 0:
        failures.append("empty_wax")
    else:
        paraffin_frac = float(
            ((sub >= PARAFFIN_PIXEL_LOW) & (sub < BACKLIGHT_THRESH)).sum(),
        ) / sub.size
        if paraffin_frac < G1_PARAFFIN_MIN_FRAC:
            failures.append("paraffin_low")
        if w < int(iw * G2_ROI_WIDTH_MIN_FRAC):
            failures.append("roi_narrow")
        backlight_frac = float((sub >= BACKLIGHT_THRESH).sum()) / sub.size
        if backlight_frac >= G3_BACKLIGHT_MAX_FRAC:
            failures.append("backlight_flood")
        dark_frac = float((sub < 120).sum()) / sub.size
        if dark_frac < EMPTY_WAX_MAX_FRAC:
            failures.append("empty_wax")
    if ih_inner > 0 and h < int(ih_inner * G4_MIN_HEIGHT_FRAC):
        failures.append("roi_sliver")
    if img_w * img_h > 0 and (w * h) > G5_MAX_AREA_FRAC * img_w * img_h:
        failures.append("roi_oversize")
    if failures:
        return False, failures[0], failures
    return True, "", []


def validate_paraffin_roi_gates(
        gray: np.ndarray,
        bbox: tuple[int, int, int, int],
        inner: tuple[int, int, int, int],
        image_size: Optional[tuple[int, int]] = None,
) -> tuple[bool, str]:
    if image_size is None:
        image_size = gray.shape[:2]
    ok, reason, _ = evaluate_roi_gates(gray, bbox, inner, image_size)
    return ok, reason


def validate_paraffin_roi(
        gray: np.ndarray,
        bbox: tuple[int, int, int, int],
        cassette: tuple[int, int, int, int],
) -> bool:
    """Backward-compatible bool wrapper (Fix 1b tests)."""
    inner = _inner_bbox(cassette)
    ok, _ = validate_paraffin_roi_gates(gray, bbox, inner)
    return ok


def _resolve_paraffin_bbox(
        gray: np.ndarray,
        cassette: tuple[int, int, int, int],
        inner: tuple[int, int, int, int],
) -> tuple[Optional[tuple[int, int, int, int]], str, bool]:
    """Rows first inside cassette; morph fallback. Returns morph_failed flag."""
    _, _, iw, ih = inner
    inner_area = max(1, iw * ih)
    row_bbox = _find_paraffin_window_bbox_rows(gray, inner)
    if row_bbox is None:
        row_bbox = _find_paraffin_window_bbox_rows(gray, cassette)
    morph_bbox = _find_paraffin_window_bbox_morph(gray, inner)
    if morph_bbox is None:
        morph_bbox = _find_paraffin_window_bbox_morph(gray, cassette)
    morph_failed = morph_bbox is None
    if row_bbox is not None:
        _, _, rw, rh = row_bbox
        if (rw * rh) >= PARAFFIN_ROW_MIN_FRAC * inner_area:
            return row_bbox, "rows", morph_failed
    if morph_bbox is not None:
        return morph_bbox, "morph", morph_failed
    if row_bbox is not None:
        return row_bbox, "rows", morph_failed
    return None, "", morph_failed


def detect_cassette_interior_roi_detail(
        bgr: np.ndarray,
        *,
        capture_source: str = "phone",
) -> RoiDetectionResult:
    _validate_bgr(bgr)
    h, w = bgr.shape[:2]
    full = (0, 0, w, h)
    if h < MIN_ROI_H or w < MIN_ROI_W:
        return RoiDetectionResult(False, full, "", "roi_narrow", False)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cassette, cassette_method, low_conf = detect_cassette_bbox(
        gray, capture_source=capture_source,
    )
    inner = _inner_bbox(cassette)

    paraffin_bbox, paraffin_method, morph_failed = _resolve_paraffin_bbox(
        gray, cassette, inner,
    )
    strip_method = "none"

    if paraffin_bbox is None:
        if _orientation_ambiguous(gray, inner, paraffin_morph_failed=morph_failed):
            return RoiDetectionResult(
                False, full, cassette_method, "ambiguous_orientation", low_conf,
                ambiguous_orientation=True,
            )
        reason = (
            "cassette_chain_exhausted"
            if cassette_method == "geometric_inset"
            else "paraffin_low"
        )
        return RoiDetectionResult(
            False, full, cassette_method, reason, low_conf,
        )

    stripped, strip_method = _strip_grid_and_label(gray, paraffin_bbox, inner)
    fail_reason = "paraffin_low"
    gate_failures: tuple[str, ...] = ()
    for bbox in (stripped, paraffin_bbox):
        bx, by, bw, bh = bbox
        if not _roi_valid(bw, bh):
            continue
        if bw >= int(w * 0.98) and bh >= int(h * 0.98):
            fail_reason = "roi_oversize"
            gate_failures = ("roi_oversize",)
            continue
        ok, reason, fails = evaluate_roi_gates(
            gray, bbox, inner, (h, w),
        )
        if ok:
            return RoiDetectionResult(
                True, bbox, cassette_method, "", low_conf,
                strip_method=strip_method,
                paraffin_method=paraffin_method,
            )
        fail_reason = reason
        gate_failures = tuple(fails)

    return RoiDetectionResult(
        False, full, cassette_method, fail_reason,
        low_conf, strip_method=strip_method,
        paraffin_method=paraffin_method,
        gate_failures=gate_failures,
    )


# Backward-compatible alias for older call sites / tests
_find_paraffin_window_bbox = _find_paraffin_window_bbox_morph


def detect_cassette_interior_roi(
        bgr: np.ndarray,
) -> tuple[bool, tuple[int, int, int, int]]:
    r = detect_cassette_interior_roi_detail(bgr)
    return r.roi_detection_ok, r.roi_bbox


def preprocess_for_segmentation(
        bgr: np.ndarray,
        meta: dict[str, Any],
) -> PreprocessResult:
    _validate_bgr(bgr)
    h, w = bgr.shape[:2]
    full_shape = (h, w)
    full_bbox = (0, 0, w, h)

    if meta.get("role") != "block_silhouette":
        return PreprocessResult(
            bgr, full_bbox, True, (0, 0), full_shape,
        )

    src = capture_source_from_meta(meta)
    det = detect_cassette_interior_roi_detail(bgr, capture_source=src)
    if not det.roi_detection_ok:
        return PreprocessResult(
            bgr, full_bbox, False, (0, 0), full_shape,
            det.cassette_method, det.roi_fail_reason, det.low_confidence,
        )

    x, y, bw, bh = det.roi_bbox
    cropped = bgr[y:y + bh, x:x + bw].copy()
    return PreprocessResult(
        cropped, det.roi_bbox, True, (x, y), full_shape,
        det.cassette_method, "", det.low_confidence,
    )


def offset_contours(
        contours: list[np.ndarray],
        origin: tuple[int, int],
) -> list[np.ndarray]:
    ox, oy = origin
    if ox == 0 and oy == 0:
        return contours
    out: list[np.ndarray] = []
    for c in contours:
        shifted = c.copy()
        shifted[:, 0, 0] = np.clip(
            shifted[:, 0, 0].astype(np.int32) + ox, 0, 2**31 - 1,
        )
        shifted[:, 0, 1] = np.clip(
            shifted[:, 0, 1].astype(np.int32) + oy, 0, 2**31 - 1,
        )
        out.append(shifted)
    return out


def paste_mask_to_full(
        mask_crop: np.ndarray,
        roi_bbox: tuple[int, int, int, int],
        full_shape: tuple[int, int],
) -> np.ndarray:
    fh, fw = full_shape
    full = np.zeros((fh, fw), dtype=np.uint8)
    x, y, w, h = roi_bbox
    ch, cw = mask_crop.shape[:2]
    hh = min(h, ch, fh - y)
    ww = min(w, cw, fw - x)
    if hh <= 0 or ww <= 0:
        return full
    full[y:y + hh, x:x + ww] = mask_crop[:hh, :ww]
    return full


def tissue_fraction_full_image(full_mask: np.ndarray) -> float:
    h, w = full_mask.shape[:2]
    denom = h * w
    if denom == 0:
        return 0.0
    return float((full_mask > 0).sum()) / denom


def segment_tissue_in_paraffin_roi(bgr_crop: np.ndarray) -> np.ndarray:
    """Legacy HSV helper — not used on blocks in production (Fix 1c)."""
    _validate_bgr(bgr_crop)
    hsv = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    tissue = ((sat > 25) | (val < 220)).astype(np.uint8) * 255
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    tissue = cv2.morphologyEx(tissue, cv2.MORPH_CLOSE, k_close)
    tissue = cv2.morphologyEx(tissue, cv2.MORPH_OPEN, k_open)
    del hsv
    return tissue


def _validate_block_segmentation(
        mask_crop: np.ndarray,
        roi_area: int,
        contour_count: int,
        tissue_class: Optional[str],
) -> tuple[bool, str]:
    n = mask_crop.size
    if n == 0:
        return False, "seg_empty"
    frac = float((mask_crop > 0).sum()) / n
    if frac < OTSU_MASK_FRAC_MIN:
        return False, "seg_empty"
    if frac > OTSU_MASK_FRAC_MAX:
        return False, "seg_flood"
    if tissue_class == "esophagus":
        if (
            frac > SEG_BLOB_FRAC
            and contour_count <= SEG_BLOB_MAX_CONTOURS
        ):
            return False, "seg_blob"
    return True, ""


def _empty_segmentation_result(
        prep: PreprocessResult,
        *,
        segmentation_method: str = "failed",
        seg_fail_reason: str = "",
) -> SegmentationWithRoi:
    fh, fw = prep.full_shape
    empty = np.zeros((fh, fw), dtype=np.uint8)
    return SegmentationWithRoi(
        cleaned_mask=empty,
        contours=[],
        otsu_threshold=-1,
        roi_detection_ok=prep.roi_detection_ok,
        roi_bbox=prep.roi_bbox,
        crop_origin=prep.crop_origin,
        segmentation_method=segmentation_method,
        cassette_method=prep.cassette_method,
        roi_fail_reason=prep.roi_fail_reason,
        seg_fail_reason=seg_fail_reason,
        reshoot_recommended=True,
        low_confidence=prep.low_confidence,
    )


def segment_with_block_roi(
        bgr: np.ndarray,
        meta: dict[str, Any],
        clean_mask_fn,
        *,
        allow_full_frame_fallback: bool = False,
) -> SegmentationWithRoi:
    """ROI crop → Otsu only on blocks; fail → empty contours unless analysis fallback."""
    prep = preprocess_for_segmentation(bgr, meta)
    tissue_class = meta.get("tissue_class")

    if meta.get("role") == "block_silhouette" and not prep.roi_detection_ok:
        if allow_full_frame_fallback:
            prep = PreprocessResult(
                bgr, prep.roi_bbox, False, (0, 0), prep.full_shape,
                prep.cassette_method, prep.roi_fail_reason, prep.low_confidence,
            )
        else:
            return _empty_segmentation_result(prep, seg_fail_reason="roi_failed")

    _gray, mask_crop, otsu = segment_tissue(prep.bgr_for_segmentation)
    role = "slide" if meta.get("role") == "slide" else "block"
    cleaned_crop, contours_crop = clean_mask_fn(mask_crop, role=role)

    if meta.get("role") == "block_silhouette" and prep.roi_detection_ok:
        seg_ok, seg_reason = _validate_block_segmentation(
            cleaned_crop,
            cleaned_crop.shape[0] * cleaned_crop.shape[1],
            len(contours_crop),
            tissue_class,
        )
        if not seg_ok:
            del _gray, mask_crop, cleaned_crop
            if allow_full_frame_fallback:
                _gray2, mask_crop2, otsu2 = segment_tissue(bgr)
                cleaned2, contours2 = clean_mask_fn(mask_crop2, role=role)
                del _gray2, mask_crop2
                return SegmentationWithRoi(
                    cleaned2, contours2, otsu2,
                    False, prep.roi_bbox, (0, 0),
                    "analysis_fallback", prep.cassette_method,
                    prep.roi_fail_reason, seg_reason, True, prep.low_confidence,
                )
            return _empty_segmentation_result(
                prep, seg_fail_reason=seg_reason,
            )

    method = "otsu"
    fh, fw = prep.full_shape
    ch, cw = cleaned_crop.shape[:2]
    if (ch, cw) != (fh, fw):
        contours = offset_contours(contours_crop, prep.crop_origin)
        cleaned = paste_mask_to_full(
            cleaned_crop, prep.roi_bbox, prep.full_shape,
        )
    else:
        contours = contours_crop
        cleaned = cleaned_crop

    del _gray, mask_crop, cleaned_crop
    return SegmentationWithRoi(
        cleaned_mask=cleaned,
        contours=contours,
        otsu_threshold=otsu,
        roi_detection_ok=prep.roi_detection_ok,
        roi_bbox=prep.roi_bbox,
        crop_origin=prep.crop_origin,
        segmentation_method=method,
        cassette_method=prep.cassette_method,
        roi_fail_reason=prep.roi_fail_reason,
        seg_fail_reason="",
        reshoot_recommended=False,
        low_confidence=prep.low_confidence,
    )


def roi_fields_from_result(
        result: SegmentationWithRoi,
        det: Optional[RoiDetectionResult] = None,
        meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    x, y, w, h = result.roi_bbox
    fields: dict[str, Any] = {
        "roi_detection_ok": result.roi_detection_ok,
        "roi_x": x,
        "roi_y": y,
        "roi_w": w,
        "roi_h": h,
        "segmentation_method": result.segmentation_method,
        "cassette_method": result.cassette_method,
        "roi_fail_reason": result.roi_fail_reason,
        "seg_fail_reason": result.seg_fail_reason,
        "reshoot_recommended": result.reshoot_recommended,
        "low_confidence": result.low_confidence,
    }
    if meta is not None:
        fields["capture_source"] = capture_source_from_meta(meta)
    if det is not None:
        fields["strip_method"] = det.strip_method
        fields["paraffin_method"] = det.paraffin_method
        fields["ambiguous_orientation"] = det.ambiguous_orientation
        if det.gate_failures:
            fields["gate_failures"] = ",".join(det.gate_failures)
    return fields


def write_roi_crop_audit_png(
        bgr: np.ndarray,
        meta: dict[str, Any],
        out_path: "Path",
        clean_mask_fn,
        *,
        max_edge: int = 1024,
        allow_full_frame_fallback: bool = False,
) -> None:
    from pathlib import Path

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seg = segment_with_block_roi(
        bgr, meta, clean_mask_fn,
        allow_full_frame_fallback=allow_full_frame_fallback,
    )
    x, y, w, h = seg.roi_bbox

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h_img, w_img = rgb.shape[:2]
    scale = min(1.0, max_edge / max(h_img, w_img))
    if scale < 1.0:
        nw, nh = int(w_img * scale), int(h_img * scale)
        rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
        mask = cv2.resize(seg.cleaned_mask, (nw, nh), interpolation=cv2.INTER_NEAREST)
        x, y, w, h = [int(v * scale) for v in (x, y, w, h)]
    else:
        mask = seg.cleaned_mask

    overlay = rgb.copy()
    overlay[mask > 0] = (0, 200, 0)

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    axes[0].imshow(rgb)
    axes[0].add_patch(patches.Rectangle(
        (x, y), w, h, linewidth=2, edgecolor="cyan", facecolor="none",
    ))
    fb = "analysis" if allow_full_frame_fallback else "production"
    title = (
        f"ROI ok={seg.roi_detection_ok} seg={seg.segmentation_method} "
        f"fallback={fb} method={seg.cassette_method}"
    )
    if seg.roi_fail_reason:
        title += f" roi_fail={seg.roi_fail_reason}"
    if seg.seg_fail_reason:
        title += f" seg_fail={seg.seg_fail_reason}"
    axes[0].set_title(title)
    axes[0].axis("off")
    axes[1].imshow(overlay)
    axes[1].set_title("Tissue mask (full frame)")
    axes[1].axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def run_roi_crop_audit(
        input_dir: "Path",
        out_dir: "Path",
        parse_fn,
        enrich_fn,
        *,
        pilot_set_ids: Optional[frozenset[int]] = None,
        allow_full_frame_fallback: bool = False,
) -> int:
    from pathlib import Path

    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from phase3_contour_profile import clean_mask

    pilot = pilot_set_ids if pilot_set_ids is not None else PILOT_SET_IDS
    n = 0
    for path in sorted(input_dir.glob("*.jp*g")):
        meta = parse_fn(path.stem)
        enrich_fn(meta)
        if meta.get("role") != "block_silhouette":
            continue
        if pilot and meta.get("set_id") not in pilot:
            continue
        bgr = cv2.imread(str(path))
        if bgr is None:
            continue
        write_roi_crop_audit_png(
            bgr, meta, out_dir / f"{path.stem}_roi_audit.png", clean_mask,
            allow_full_frame_fallback=allow_full_frame_fallback,
        )
        n += 1
        del bgr
    return n
