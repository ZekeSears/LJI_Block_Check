"""
phase3_router.py — Hybrid algorithm router (metadata + slide metrics).

Routes (block, slide) comparisons between Phase 2 shape matching and
Phase 3 constellation matching.

v3 (2026-05): Routing is **metrics-only** — no filename tissue tokens.
Uses contour count, slide total_tissue_area, dominance (max/total area),
and mean contour area vs calibrated thresholds from router_constants.json.
Tissue names in filenames are for inventory/TPR reporting only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Sequence

import cv2
import numpy as np


# Module defaults when JSON is missing or overlap_unresolved.
SLIDE_TOTAL_TISSUE_AREA_PX: float = 225_000.0
DOMINANCE_MIN_FOR_SHAPE: float = 0.92
_ROUTER_CONSTANTS_SOURCE: str = "module_defaults"

# Legacy fallback (demoted — contour count overlapped on real data).
MULTI_FRAGMENT_THRESHOLD: int = 3
SMALL_FRAGMENT_AREA_PX: float = 5000.0

_ROUTER_CONSTANTS_PATH = (
    Path(__file__).resolve().parent.parent / "phase3_outputs" / "router_constants.json"
)

RoutingDecision = Literal["shape", "constellation", "shape_partial"]


@dataclass(frozen=True)
class SideMetrics:
    contour_count: int
    total_tissue_area: float
    max_contour_area: float
    dominance: float
    mean_contour_area: float


def _load_router_constants() -> None:
    global SLIDE_TOTAL_TISSUE_AREA_PX, DOMINANCE_MIN_FOR_SHAPE
    global MULTI_FRAGMENT_THRESHOLD, SMALL_FRAGMENT_AREA_PX
    global _ROUTER_CONSTANTS_SOURCE
    _ROUTER_CONSTANTS_SOURCE = "module_defaults"
    if not _ROUTER_CONSTANTS_PATH.is_file():
        return
    try:
        data = json.loads(_ROUTER_CONSTANTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if data.get("status") != "calibrated":
        return
    if "SLIDE_TOTAL_TISSUE_AREA_PX" in data:
        SLIDE_TOTAL_TISSUE_AREA_PX = float(data["SLIDE_TOTAL_TISSUE_AREA_PX"])
    if "DOMINANCE_MIN_FOR_SHAPE" in data:
        DOMINANCE_MIN_FOR_SHAPE = float(data["DOMINANCE_MIN_FOR_SHAPE"])
    if data.get("MULTI_FRAGMENT_THRESHOLD") is not None:
        MULTI_FRAGMENT_THRESHOLD = int(data["MULTI_FRAGMENT_THRESHOLD"])
    if data.get("SMALL_FRAGMENT_AREA_PX") is not None:
        SMALL_FRAGMENT_AREA_PX = float(data["SMALL_FRAGMENT_AREA_PX"])
    _ROUTER_CONSTANTS_SOURCE = "router_constants.json"


def reload_router_constants() -> None:
    """Re-read router_constants.json (tests / post-calibration subprocess)."""
    _load_router_constants()


def router_constants_source() -> str:
    """Provenance: module_defaults vs calibrated JSON."""
    return _ROUTER_CONSTANTS_SOURCE


_load_router_constants()


def compute_side_metrics(contours: Sequence[np.ndarray]) -> SideMetrics:
    areas = [float(cv2.contourArea(c)) for c in contours]
    n = len(areas)
    total = float(sum(areas))
    max_a = float(max(areas)) if areas else 0.0
    dominance = (max_a / total) if total > 0 else 0.0
    mean_a = (total / n) if n else 0.0
    return SideMetrics(
        contour_count=n,
        total_tissue_area=total,
        max_contour_area=max_a,
        dominance=dominance,
        mean_contour_area=mean_a,
    )


def side_prefers_shape(
        tissue_class: Optional[str],
        metrics: SideMetrics,
        role: Optional[str] = None,
) -> bool:
    del tissue_class  # unused — routing must not depend on filename tissue
    if metrics.contour_count == 0:
        return False
    use_slide_metrics = role in (None, "slide")
    if use_slide_metrics:
        if metrics.total_tissue_area >= SLIDE_TOTAL_TISSUE_AREA_PX:
            return True
        if metrics.dominance >= DOMINANCE_MIN_FOR_SHAPE:
            return True
    elif metrics.dominance >= DOMINANCE_MIN_FOR_SHAPE:
        return True
    return False


def side_prefers_constellation(
        tissue_class: Optional[str],
        metrics: SideMetrics,
        role: Optional[str] = None,
) -> bool:
    del tissue_class  # unused — routing must not depend on filename tissue
    if metrics.contour_count < 2:
        return False
    use_slide_metrics = role in (None, "slide")
    if use_slide_metrics:
        low_area = metrics.total_tissue_area < SLIDE_TOTAL_TISSUE_AREA_PX
        low_dom = metrics.dominance < DOMINANCE_MIN_FOR_SHAPE
        return low_area and low_dom
    return (
        metrics.contour_count >= MULTI_FRAGMENT_THRESHOLD
        and metrics.mean_contour_area < SMALL_FRAGMENT_AREA_PX
    )


def route_comparison_hybrid(
        contours_a: Sequence[np.ndarray],
        contours_b: Sequence[np.ndarray],
        *,
        tissue_a: Optional[str] = None,
        tissue_b: Optional[str] = None,
        role_a: Optional[str] = None,
        role_b: Optional[str] = None,
) -> RoutingDecision:
    """Hybrid router: contour metrics and calibrated area/dominance thresholds only."""
    n_a, n_b = len(contours_a), len(contours_b)
    if n_a == 1 and n_b == 1:
        return "shape"
    if (n_a == 1) ^ (n_b == 1):
        return "shape_partial"

    ma = compute_side_metrics(contours_a)
    mb = compute_side_metrics(contours_b)

    shape_a = side_prefers_shape(tissue_a, ma, role_a)
    shape_b = side_prefers_shape(tissue_b, mb, role_b)
    const_a = side_prefers_constellation(tissue_a, ma, role_a)
    const_b = side_prefers_constellation(tissue_b, mb, role_b)

    if shape_a or shape_b:
        if not (const_a and const_b):
            return "shape"

    if const_a and const_b:
        return "constellation"
    if const_a or const_b:
        if min(n_a, n_b) >= 2:
            return "constellation"

    if (min(n_a, n_b) >= MULTI_FRAGMENT_THRESHOLD
            and max(ma.mean_contour_area, mb.mean_contour_area)
            < SMALL_FRAGMENT_AREA_PX):
        return "constellation"
    return "shape"


def route_comparison(contours_a: Sequence[np.ndarray],
                     contours_b: Sequence[np.ndarray]) -> RoutingDecision:
    """Route without metadata (metrics-only / legacy fallback)."""
    return route_comparison_hybrid(contours_a, contours_b)


__all__ = [
    "SLIDE_TOTAL_TISSUE_AREA_PX",
    "DOMINANCE_MIN_FOR_SHAPE",
    "MULTI_FRAGMENT_THRESHOLD",
    "SMALL_FRAGMENT_AREA_PX",
    "SideMetrics",
    "RoutingDecision",
    "compute_side_metrics",
    "side_prefers_shape",
    "side_prefers_constellation",
    "route_comparison",
    "route_comparison_hybrid",
    "reload_router_constants",
    "router_constants_source",
]
