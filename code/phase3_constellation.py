"""
phase3_constellation.py — Phase 3 constellation matching for multi-fragment
tissue (esophagus-like) samples.

Canonical signature (single representation, no point cloud, no PCA):

    [ 45 sorted normalized pairwise centroid distances (asc, padded with 1.5) ]
  + [ 10 sorted normalized contour areas (desc, padded with 0.0) ]
  = 55-element fixed-length float64 vector

Normalization references are 90th-percentile distance and 90th-percentile
contour area (NOT max — pre-mortem §2 ¶3: max-statistic is fragile under a
single spurious contour passing the upstream solidity filter).

Pairwise distances are intrinsically rotation, translation, and mirror
invariant — no axis alignment, no eigenvector sign ambiguity. Resolves
pre-mortem §2 ¶1 (PCA instability for near-symmetric esophagus arrangements).

Distance metric for matching is L2 on the padded 55-element vector throughout.
Single metric across equal-count and mismatched-count cases — pre-mortem §3
¶1/¶2 (incomparable L2/EMD score scales eliminated).

Mitigation map:
    §2 ¶1 PCA instability       → pairwise-distance signature, no PCA
    §2 ¶3 max normalization     → 90th-percentile reference
    §3 ¶1 dual representation   → single canonical 55-element vector
    §3 ¶2 incomparable scales   → single L2 metric throughout
    §4 ¶2 scipy version         → hard import-time check >=1.12
"""

from __future__ import annotations

import logging
from typing import Sequence

import cv2
import numpy as np

# Pre-mortem §4 ¶2: hard-pin scipy>=1.12. EMD was dropped in v2, but the
# version pin remains as defense against future drift if EMD is reconsidered.
try:
    import scipy
    _scipy_major, _scipy_minor, *_ = scipy.__version__.split(".")
    if (int(_scipy_major), int(_scipy_minor)) < (1, 12):
        raise ImportError(
            f"scipy>=1.12 required (found {scipy.__version__}); see "
            f".claude/specs/pre_mortem.md §4 for rationale."
        )
except ImportError as exc:
    raise ImportError(
        f"Phase 3 requires scipy>=1.12: {exc}"
    ) from exc


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration constants — every value here is a documented tradeoff.
# ---------------------------------------------------------------------------

# Pre-mortem §3: signature is a single canonical vector. 10 contours is the
# upper bound observed in the existing dataset; 10 choose 2 = 45 pairs.
MAX_CONTOUR_COUNT: int = 10
MAX_PAIR_COUNT: int = MAX_CONTOUR_COUNT * (MAX_CONTOUR_COUNT - 1) // 2  # 45

# Pad value for missing pairwise distances — chosen ABOVE the maximum
# possible normalized real distance (1.0 after 90th-percentile normalization,
# with rare overshoots to ~1.3). 1.5 ensures padding is consistently
# "more distant than any real pair" so matched pairs of differing counts
# get a predictable bounded penalty, not an arbitrary one.
PAIR_PADDING: float = 1.5

# Pad value for missing area ratios — 0 is below the minimum possible real
# normalized area (which is in [0, ~1.3]). Asymmetry from distance padding
# is intentional: missing fragments contribute "zero area" naturally.
AREA_PADDING: float = 0.0

SIGNATURE_LENGTH: int = MAX_PAIR_COUNT + MAX_CONTOUR_COUNT  # 55

# Pre-mortem §2 ¶3: 90th-percentile rather than max for the normalization
# reference. With ≤10 points the 90th percentile is robust to a single
# spurious contour from the upstream solidity filter.
NORMALIZATION_PERCENTILE: float = 90.0

# Pre-mortem §2 ¶3 / §5: contamination drift bound. Padding sentinels
# above the real-data range mean that adding contours legitimately shifts
# the signature (padding slots fill with real values). 90th-percentile
# normalization prevents the dominant signal from being CRUSHED, which is
# the property the test enforces; the gross L2 drift bound below
# accommodates count-change shifts.
CONTAMINATION_DRIFT_MAX: float = 2.0


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def _centroid(contour: np.ndarray) -> tuple[float, float]:
    """Centroid via image moments. Falls back to coordinate mean when
    the contour has zero area (degenerate, e.g. all-collinear)."""
    m = cv2.moments(contour)
    if m["m00"] > 0:
        return float(m["m10"] / m["m00"]), float(m["m01"] / m["m00"])
    pts = contour.reshape(-1, 2).astype(float)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def _pairwise_distances(centroids: np.ndarray) -> np.ndarray:
    """All N*(N-1)/2 pairwise Euclidean distances between rows of `centroids`.
    Returns a 1D array of length N*(N-1)/2. Empty when N < 2."""
    n = centroids.shape[0]
    if n < 2:
        return np.zeros(0, dtype=np.float64)
    diff = centroids[:, None, :] - centroids[None, :, :]
    dist = np.linalg.norm(diff, axis=2)
    iu = np.triu_indices(n, k=1)
    return dist[iu].astype(np.float64)


def _robust_reference(values: np.ndarray, fallback: float) -> float:
    """90th-percentile reference. Returns `fallback` for empty input or
    when the percentile is zero (avoids div-by-zero on degenerate input)."""
    if values.size == 0:
        return fallback
    ref = float(np.percentile(values, NORMALIZATION_PERCENTILE))
    return ref if ref > 0 else fallback


def extract_constellation_signature(
        contours: Sequence[np.ndarray]) -> tuple[np.ndarray, dict]:
    """Build the canonical 55-element signature for a list of contours.

    Returns (signature, metadata) where metadata exposes the normalization
    reference values used (per pre-mortem §6 ¶4: enables cross-version
    diagnostic reconstruction; CSV schema includes these alongside the
    raw 55 float columns).
    """
    if len(contours) == 0:
        raise ValueError(
            "extract_constellation_signature requires at least one contour; "
            "caller must filter empty inputs upstream."
        )

    # ---- centroids and areas ------------------------------------------------
    centroids = np.array([_centroid(c) for c in contours], dtype=np.float64)
    areas = np.array([float(cv2.contourArea(c)) for c in contours],
                     dtype=np.float64)

    # ---- pairwise distance vector (sorted asc, 90th%ile-normalized) --------
    raw_distances = _pairwise_distances(centroids)
    dist_ref = _robust_reference(raw_distances, fallback=1.0)
    norm_distances = np.sort(raw_distances) / dist_ref

    distance_block = np.full(MAX_PAIR_COUNT, PAIR_PADDING, dtype=np.float64)
    take_d = min(norm_distances.size, MAX_PAIR_COUNT)
    if take_d > 0:
        distance_block[:take_d] = norm_distances[:take_d]

    # ---- area vector (sorted desc, 90th%ile-normalized) --------------------
    area_ref = _robust_reference(areas, fallback=1.0)
    norm_areas = np.sort(areas / area_ref)[::-1]  # descending

    area_block = np.full(MAX_CONTOUR_COUNT, AREA_PADDING, dtype=np.float64)
    take_a = min(norm_areas.size, MAX_CONTOUR_COUNT)
    if take_a > 0:
        area_block[:take_a] = norm_areas[:take_a]

    signature = np.concatenate([distance_block, area_block])
    metadata = {
        "num_contours": int(len(contours)),
        "normalization_ref_distance": float(dist_ref),
        "normalization_ref_area": float(area_ref),
    }
    return signature, metadata


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def match_constellations(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    """L2 distance on the 55-element padded vectors, mapped to similarity
    in [0, 1] via 1 / (1 + d). Self-similarity is exactly 1.0.

    Pre-mortem §3 critical resolution: single metric for equal-count and
    mismatched-count cases. The padding sentinel (PAIR_PADDING above the
    real-data maximum) provides a consistent count-mismatch penalty per
    missing fragment without inventing a second metric.
    """
    if sig_a.shape != (SIGNATURE_LENGTH,) or sig_b.shape != (SIGNATURE_LENGTH,):
        raise ValueError(
            f"Signatures must be length-{SIGNATURE_LENGTH} 1D arrays; "
            f"got {sig_a.shape} and {sig_b.shape}."
        )
    d = float(np.linalg.norm(sig_a - sig_b))
    sim = 1.0 / (1.0 + d)
    return float(max(0.0, min(1.0, sim)))


__all__ = [
    "MAX_CONTOUR_COUNT",
    "MAX_PAIR_COUNT",
    "SIGNATURE_LENGTH",
    "PAIR_PADDING",
    "AREA_PADDING",
    "NORMALIZATION_PERCENTILE",
    "CONTAMINATION_DRIFT_MAX",
    "extract_constellation_signature",
    "match_constellations",
]
