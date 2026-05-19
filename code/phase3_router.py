"""
phase3_router.py — Hard-switch algorithm router with explicit 1-vs-N
sentinel.

Routes (block, slide) comparisons between Phase 2 shape matching and
Phase 3 constellation matching based on measured contour-list properties.

Pre-mortem §3 critical resolution: the 1-vs-N case returns the EXPLICIT
sentinel "shape_partial" (with the unified matcher applying a documented
count-mismatch penalty and emitting routing_uncertain=True) — NOT a
silent fall-through to set-to-set shape matching that would produce a
misleadingly OK partial-alignment score.

Default thresholds (MULTI_FRAGMENT_THRESHOLD, SMALL_FRAGMENT_AREA_PX) are
starting values to be calibrated from the real dataset via the
contour-profiling script before locking. Per pre-mortem §3 ¶5: do not
trust these without empirical justification.
"""

from __future__ import annotations

from typing import Literal, Sequence

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Calibration constants — provisional defaults
# ---------------------------------------------------------------------------

MULTI_FRAGMENT_THRESHOLD: int = 3
SMALL_FRAGMENT_AREA_PX: float = 5000.0

RoutingDecision = Literal["shape", "constellation", "shape_partial"]


def _mean_area(contours: Sequence[np.ndarray]) -> float:
    if len(contours) == 0:
        return 0.0
    areas = [float(cv2.contourArea(c)) for c in contours]
    return float(np.mean(areas))


def route_comparison(contours_a: Sequence[np.ndarray],
                     contours_b: Sequence[np.ndarray]) -> RoutingDecision:
    """Decide which matcher to use for a single (block, slide) comparison.

    Rules (in evaluation order — first match wins, no fall-through):

      1. (1, 1)            → "shape"
      2. (1, N) or (N, 1)  → "shape_partial"   (N >= 2; explicit sentinel)
      3. min(n_a, n_b) >= MULTI_FRAGMENT_THRESHOLD
         AND max(mean_area_a, mean_area_b) < SMALL_FRAGMENT_AREA_PX
                           → "constellation"
      4. otherwise         → "shape"
    """
    n_a, n_b = len(contours_a), len(contours_b)
    if n_a == 1 and n_b == 1:
        return "shape"
    if (n_a == 1) ^ (n_b == 1):
        return "shape_partial"
    if (min(n_a, n_b) >= MULTI_FRAGMENT_THRESHOLD
            and max(_mean_area(contours_a), _mean_area(contours_b))
            < SMALL_FRAGMENT_AREA_PX):
        return "constellation"
    return "shape"


__all__ = [
    "MULTI_FRAGMENT_THRESHOLD",
    "SMALL_FRAGMENT_AREA_PX",
    "RoutingDecision",
    "route_comparison",
]
