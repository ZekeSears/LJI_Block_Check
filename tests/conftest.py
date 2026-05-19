"""
Pytest fixtures for Phase 1 segmentation tests.

All fixtures produce SYNTHETIC images so tests are fully deterministic
and do not depend on any user-supplied iPhone image being present in the
repo. This is required because tests must be runnable in CI without
shipping multi-megabyte JPEGs.

NOTE on channel order: OpenCV stores colour images as BGR. Tests that
care about colour (red_patch_image) deliberately set channel 2 (= R in
BGR) high — see comment inline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

# Make `code/` importable so tests can `from phase1_segmentation import ...`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CODE_DIR = _REPO_ROOT / "code"
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))


@pytest.fixture
def solid_black_image() -> np.ndarray:
    """1000x1000 BGR image, all zeros.

    Used to exercise the zero-contours guard in compute_metrics():
    Otsu on a degenerate single-value histogram can pick threshold 0,
    producing a mask of all 0 or all 255 with no usable contours.
    """
    return np.zeros((1000, 1000, 3), dtype=np.uint8)


@pytest.fixture
def solid_white_image() -> np.ndarray:
    """1000x1000 BGR image, all 255s. Same purpose as solid_black."""
    return np.full((1000, 1000, 3), 255, dtype=np.uint8)


@pytest.fixture
def red_patch_image() -> np.ndarray:
    """1000x1000 BGR image of a red patch.

    cv2 stores colour as BGR so channel index 2 == R. A correctly-written
    diagnostic visualization will save a PNG whose top-left panel (the
    "original colour" panel) renders this image with R > B. If the BGR→RGB
    conversion is omitted, the saved PNG will have B > R at that pixel.
    """
    img = np.zeros((1000, 1000, 3), dtype=np.uint8)
    img[:, :, 2] = 220  # Red  (BGR channel 2)
    img[:, :, 1] = 30   # Green
    img[:, :, 0] = 30   # Blue
    return img


@pytest.fixture
def synthetic_dark_blob_image() -> np.ndarray:
    """White background with one central dark circle.

    Used as a positive control: Otsu after inversion MUST find this blob
    and produce exactly one filtered contour, regardless of kernel size.
    Circle radius 40 → area ~5026 px, well above MIN_CONTOUR_AREA=1000.
    """
    img = np.full((1000, 1000, 3), 240, dtype=np.uint8)
    cv2.circle(img, (500, 500), 40, (30, 30, 30), -1)
    return img


@pytest.fixture
def mixed_blob_mask() -> np.ndarray:
    """Pre-built binary mask with one large blob (~5000 px) and one tiny
    blob (~100 px). Used to verify extract_contours() filters by area."""
    mask = np.zeros((1000, 1000), dtype=np.uint8)
    cv2.circle(mask, (300, 300), 40, 255, -1)   # large: ~5026 px
    cv2.circle(mask, (700, 700), 5, 255, -1)    # tiny:   ~79 px
    return mask


# ---------------------------------------------------------------------------
# Phase 2 fixtures.  See .claude/specs/pre_mortem.md (Phase 2 critique).
# Every fixture below is referenced by at least one test in
# tests/test_phase2.py and exists to make a specific failure mode reproducible.
# ---------------------------------------------------------------------------


def _make_circle_contour(cx: int, cy: int, r: int) -> np.ndarray:
    """Build an OpenCV contour (Nx1x2 int32) for a circle by sampling its perimeter."""
    theta = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    xs = (cx + r * np.cos(theta)).round().astype(np.int32)
    ys = (cy + r * np.sin(theta)).round().astype(np.int32)
    pts = np.stack([xs, ys], axis=1).reshape(-1, 1, 2)
    return pts


def _make_rect_contour(x: int, y: int, w: int, h: int) -> np.ndarray:
    pts = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
                   dtype=np.int32).reshape(-1, 1, 2)
    return pts


def _make_lobed_contour(cx: int, cy: int, r: int, lobes: int = 5,
                        amplitude: float = 0.3) -> np.ndarray:
    """A non-convex flower-like blob: solidity well below 1."""
    theta = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    rr = r * (1.0 + amplitude * np.cos(lobes * theta))
    xs = (cx + rr * np.cos(theta)).round().astype(np.int32)
    ys = (cy + rr * np.sin(theta)).round().astype(np.int32)
    return np.stack([xs, ys], axis=1).reshape(-1, 1, 2)


@pytest.fixture
def slide_mask_with_label() -> np.ndarray:
    """A binary mask simulating a post-Otsu slide image with:
      - a bright "label" rectangle in the top 20% of the frame
      - a real tissue blob in the lower half.
    Used to verify the Stage 1 label-ROI mask zeroes the top region.
    """
    mask = np.zeros((1000, 800), dtype=np.uint8)
    # Label artifact: top rectangular block (within top 20%)
    cv2.rectangle(mask, (100, 50), (700, 180), 255, thickness=-1)
    # Real tissue blob: lower half, centred
    cv2.circle(mask, (400, 700), 80, 255, thickness=-1)
    return mask


@pytest.fixture
def block_mask_with_grid_artifact() -> np.ndarray:
    """A binary mask with one lobed tissue contour (low solidity) plus
    several rectangular contours (solidity ~1.0) representing cassette
    grid edges. Used by the solidity-filter test."""
    mask = np.zeros((800, 800), dtype=np.uint8)
    # Real tissue: low-solidity lobed blob
    real = _make_lobed_contour(400, 400, 120, lobes=5, amplitude=0.3)
    cv2.drawContours(mask, [real], -1, 255, thickness=-1)
    # Grid artifact rectangles (high solidity)
    cv2.rectangle(mask, (50, 50), (130, 130), 255, thickness=-1)
    cv2.rectangle(mask, (650, 50), (760, 120), 255, thickness=-1)
    cv2.rectangle(mask, (50, 650), (120, 760), 255, thickness=-1)
    return mask


@pytest.fixture
def lung_contour_at_1x() -> np.ndarray:
    """A reference 'lung-like' lobed contour at 1x scale, centred at origin."""
    return _make_lobed_contour(0, 0, 200, lobes=3, amplitude=0.4)


@pytest.fixture
def lung_contour_at_2x() -> np.ndarray:
    """Same shape as lung_contour_at_1x but scaled 2x."""
    return _make_lobed_contour(0, 0, 400, lobes=3, amplitude=0.4)


@pytest.fixture
def lung_contour_rotated_90() -> np.ndarray:
    """Same lung-like contour rotated 90 degrees (Hu invariance check)."""
    base = _make_lobed_contour(0, 0, 200, lobes=3, amplitude=0.4)
    pts = base.reshape(-1, 2).astype(np.float64)
    # Rotate 90 deg about origin: (x, y) -> (-y, x)
    rot = np.stack([-pts[:, 1], pts[:, 0]], axis=1).round().astype(np.int32)
    return rot.reshape(-1, 1, 2)


@pytest.fixture
def differently_shaped_contour() -> np.ndarray:
    """A square contour of comparable bounding-box size to the lung
    contours — same scale, different shape. Used to verify normalized
    feature vectors discriminate by shape, not by raw area."""
    return _make_rect_contour(-200, -200, 400, 400)


@pytest.fixture
def pair_of_known_contours():
    """Returns (block_contours, slide_contours) where each list has 2
    contours and the obvious correct Hungarian pairing is
    (block[0]↔slide[0], block[1]↔slide[1]) because shapes match index-wise.
    """
    block = [
        _make_lobed_contour(0, 0, 200, lobes=3, amplitude=0.4),
        _make_circle_contour(0, 0, 150),
    ]
    slide = [
        # Same lobed shape, slightly scaled
        _make_lobed_contour(0, 0, 180, lobes=3, amplitude=0.4),
        # Same circle shape, slightly scaled
        _make_circle_contour(0, 0, 140),
    ]
    return block, slide


# ---------------------------------------------------------------------------
# Phase 3 fixtures — constellation matching, label detection, routing.
# See .claude/specs/pre_mortem.md (Phase 3 critique).
# ---------------------------------------------------------------------------


def _points_to_contours(points: np.ndarray, radius: int = 30) -> list[np.ndarray]:
    """Convert an Nx2 array of centroid coords into N circle contours of
    fixed radius — used to build synthetic 'fragment' arrangements for
    constellation signature tests."""
    return [_make_circle_contour(int(x), int(y), radius) for x, y in points]


@pytest.fixture
def square_arrangement_points() -> np.ndarray:
    """Four centroids on the corners of a 400x400 square, centred at (500,500).
    Near-symmetric — exactly the case that destroys PCA principal-axis
    alignment in v1 (pre-mortem §2 ¶1)."""
    return np.array([
        [300, 300], [700, 300], [700, 700], [300, 700],
    ], dtype=float)


@pytest.fixture
def square_arrangement_contours(square_arrangement_points) -> list[np.ndarray]:
    return _points_to_contours(square_arrangement_points)


@pytest.fixture
def square_arrangement_perturbed_contours(square_arrangement_points) -> list[np.ndarray]:
    """Square arrangement with one centroid shifted by ~1% of the bbox
    diagonal (~5.6 px). Tests near-symmetric perturbation stability."""
    pts = square_arrangement_points.copy()
    pts[0] = pts[0] + np.array([4.0, 4.0])
    return _points_to_contours(pts)


@pytest.fixture
def linear_arrangement_points() -> np.ndarray:
    """Four collinear centroids — an asymmetric multi-fragment esophagus-like
    arrangement."""
    return np.array([
        [200, 500], [400, 500], [600, 500], [800, 500],
    ], dtype=float)


@pytest.fixture
def linear_arrangement_contours(linear_arrangement_points) -> list[np.ndarray]:
    return _points_to_contours(linear_arrangement_points)


def rotate_points(points: np.ndarray, degrees: float,
                  centre: tuple[float, float] = (500.0, 500.0)) -> np.ndarray:
    """Rotate an Nx2 array about a centre by `degrees`."""
    theta = np.deg2rad(degrees)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    cx, cy = centre
    shifted = points - np.array([cx, cy])
    rot = np.stack([
        shifted[:, 0] * cos_t - shifted[:, 1] * sin_t,
        shifted[:, 0] * sin_t + shifted[:, 1] * cos_t,
    ], axis=1)
    return rot + np.array([cx, cy])


def mirror_points(points: np.ndarray, axis: str = "x",
                  centre: tuple[float, float] = (500.0, 500.0)) -> np.ndarray:
    """Mirror across vertical (axis='x') or horizontal (axis='y') line
    through `centre`."""
    cx, cy = centre
    out = points.copy()
    if axis == "x":
        out[:, 0] = 2 * cx - out[:, 0]
    else:
        out[:, 1] = 2 * cy - out[:, 1]
    return out


@pytest.fixture
def rotate_points_fn():
    return rotate_points


@pytest.fixture
def mirror_points_fn():
    return mirror_points


@pytest.fixture
def small_multi_fragment_contours() -> list[np.ndarray]:
    """Four small contours (radius ~22 → area ~1500 px) — esophagus-like
    multi-fragment routing target."""
    pts = np.array([
        [300, 300], [400, 300], [350, 380], [330, 460],
    ], dtype=int)
    return [_make_circle_contour(int(x), int(y), 22) for x, y in pts]


@pytest.fixture
def large_solid_contour() -> list[np.ndarray]:
    """One large contour (radius ~100 → area ~31400 px) — lung-like solid
    routing target."""
    return [_make_circle_contour(500, 500, 100)]


@pytest.fixture
def synthetic_label_with_printed_noise() -> np.ndarray:
    """BGR image containing a rectangular 'label' region whose interior
    has high-frequency noise simulating printed text + barcode. This is
    the realistic-label fixture required by pre-mortem §5: detector must
    NOT rely on low interior variance."""
    # Realistic backlit-slide convention: glass = bright (transilluminator),
    # label = darker opaque sticker, tissue = dark blob in lower half.
    img = np.full((800, 600, 3), 250, dtype=np.uint8)  # bright glass bg
    x0, y0, w, h = 80, 60, 440, 180  # aspect ~2.44, in [1.5, 4.0]
    # Label fill: medium-dark uniform sticker base.
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (90, 90, 90), thickness=-1)
    # Strong rectangular DARK border (printed label edge / sticker outline).
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (10, 10, 10), thickness=4)
    # High-variance "printed text" interior — small dark rectangles giving
    # the realistic high interior intensity variance that defeats the v1
    # uniformity criterion.
    rng = np.random.default_rng(42)
    for _ in range(60):
        rx = rng.integers(x0 + 15, x0 + w - 40)
        ry = rng.integers(y0 + 15, y0 + h - 20)
        rw = int(rng.integers(8, 40))
        rh = int(rng.integers(6, 14))
        cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), (20, 20, 20),
                      thickness=-1)
    # A tissue-like dark blob far from the label, in the lower half.
    cv2.circle(img, (300, 600), 70, (40, 40, 40), thickness=-1)
    return img


@pytest.fixture
def synthetic_rectangular_tissue_no_border() -> np.ndarray:
    """BGR image with a roughly rectangular tissue-like blob (high
    rectangularity) but NO sharp rectangular border edges — tests the
    border-edge-density criterion's role in rejecting tissue."""
    img = np.full((800, 600, 3), 240, dtype=np.uint8)
    # A dark rectangle with FUZZY edges — simulate tissue with a smooth
    # boundary via Gaussian blur after drawing.
    block = np.full((800, 600), 240, dtype=np.uint8)
    cv2.rectangle(block, (150, 300), (450, 600), 40, thickness=-1)
    block = cv2.GaussianBlur(block, (31, 31), sigmaX=12)
    img[:, :, 0] = block
    img[:, :, 1] = block
    img[:, :, 2] = block
    return img


@pytest.fixture
def synthetic_no_rectangle_image() -> np.ndarray:
    """BGR image with only a circular dark blob — no rectangular regions
    at all. Fallback ROI must engage."""
    img = np.full((800, 600, 3), 240, dtype=np.uint8)
    cv2.circle(img, (300, 500), 100, (40, 40, 40), thickness=-1)
    return img


@pytest.fixture
def fragment_mismatch_pair():
    """Block has 4 contours, slide has 3 — fragment loss case."""
    block = [
        _make_lobed_contour(0, 0, 200, lobes=3, amplitude=0.4),
        _make_circle_contour(0, 0, 150),
        _make_lobed_contour(0, 0, 180, lobes=4, amplitude=0.3),
        _make_rect_contour(-50, -50, 100, 100),
    ]
    slide = [
        _make_lobed_contour(0, 0, 180, lobes=3, amplitude=0.4),
        _make_circle_contour(0, 0, 140),
        _make_lobed_contour(0, 0, 170, lobes=4, amplitude=0.3),
    ]
    return block, slide
