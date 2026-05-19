"""
phase3_unified_matcher.py — Unified cross-modal matcher with explicit
score-scale handling.

For each (block, slide) pair: route via phase3_router.route_comparison(),
invoke the selected matcher, and record routing decision + raw similarity
+ routing_uncertain flag. Per-branch z-score normalization brings each
branch onto a common standard-deviation scale; absolute cross-branch
comparison remains explicitly invalid (documented in calibration notes).

Pre-mortem critical resolutions covered here:
    §3 ¶2  cross-branch score scales      → per-branch z-score + raw
    §3 ¶4  1-vs-N silent partial-alignment → routing_uncertain + penalty
    §5 ¶3  self-similarity on both branches → exact 1.0 on diagonal
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

import phase2_descriptors as p2
import phase3_constellation as p3c
import phase3_router as p3r


# Pre-mortem §3 ¶4: documented count-mismatch penalty for shape_partial.
# Applied as a multiplicative shrinkage on the otherwise-misleading
# partial-alignment similarity, so the output cannot be confused with a
# genuine same-count match.
SHAPE_PARTIAL_PENALTY: float = 0.5


@dataclass(frozen=True)
class UnifiedMatchResult:
    routing_decision: p3r.RoutingDecision
    raw_similarity: float
    routing_uncertain: bool
    notes: str


def _shape_similarity(features_a: np.ndarray, features_b: np.ndarray) -> float:
    """Phase 2 set-to-set shape similarity wrapper. Identical inputs →
    similarity == 1.0 (Phase 2 self-similarity guarantee carried forward)."""
    if features_a is None or features_b is None:
        return 0.0
    if features_a.size == 0 or features_b.size == 0:
        return 0.0
    return p2.set_to_set_similarity(features_a, features_b)


def _shape_partial_similarity(features_a: np.ndarray,
                              features_b: np.ndarray) -> float:
    """Comparison path for the 1-vs-N case.

    Compares the single contour's feature row against the closest row of
    the multi-contour side (nearest L2 in feature space), then applies
    SHAPE_PARTIAL_PENALTY so the result cannot be mistaken for a genuine
    same-count match.

    Pre-mortem §3 ¶4: this is the explicit replacement for the silent
    fall-through in v1, which would have invoked the full Hungarian
    set-to-set with arbitrary unmatched-cost padding and produced a
    misleadingly OK score on accidental alignment.
    """
    if features_a is None or features_b is None:
        return 0.0
    if features_a.size == 0 or features_b.size == 0:
        return 0.0
    n_a = features_a.shape[0]
    if n_a == 1:
        single, multi = features_a[0], features_b
    else:
        single, multi = features_b[0], features_a
    diffs = multi - single[None, :]
    dists = np.linalg.norm(diffs, axis=1)
    best = float(dists.min())
    sim = 1.0 / (1.0 + best)
    return float(max(0.0, min(1.0, sim * SHAPE_PARTIAL_PENALTY)))


def unified_compare(
    contours_a: Sequence[np.ndarray],
    contours_b: Sequence[np.ndarray],
    features_a: Optional[np.ndarray],
    features_b: Optional[np.ndarray],
    signature_a: Optional[np.ndarray],
    signature_b: Optional[np.ndarray],
) -> UnifiedMatchResult:
    """Route the comparison, invoke the chosen matcher, return result.

    `features_*` are the per-contour standardized feature matrices used
    by Phase 2's shape matcher. `signature_*` are the canonical 55-element
    constellation signatures from phase3_constellation.

    Self-similarity is exactly 1.0 on the "shape" and "constellation"
    branches (carried forward from Phase 2 and from p3c.match_constellations
    respectively). Pre-mortem §5 critical.
    """
    decision = p3r.route_comparison(contours_a, contours_b)

    if decision == "constellation":
        if signature_a is None or signature_b is None:
            raise ValueError(
                "Routing decided 'constellation' but signatures were not "
                "provided to unified_compare()."
            )
        sim = p3c.match_constellations(signature_a, signature_b)
        return UnifiedMatchResult(decision, sim, False,
                                  "constellation L2 on 55-element signature")

    if decision == "shape_partial":
        sim = _shape_partial_similarity(features_a, features_b)
        return UnifiedMatchResult(decision, sim, True,
                                  f"shape_partial penalty={SHAPE_PARTIAL_PENALTY}")

    # decision == "shape"
    sim = _shape_similarity(features_a, features_b)
    return UnifiedMatchResult(decision, sim, False,
                              "Phase 2 set-to-set Hungarian shape similarity")


# ---------------------------------------------------------------------------
# Per-branch z-score normalization
# ---------------------------------------------------------------------------


def per_branch_zscore(raw: np.ndarray, branches: np.ndarray) -> np.ndarray:
    """Z-score `raw` within each branch independently.

    Pre-mortem §3 ¶2: cross-branch absolute comparison is invalid by
    design. This function brings each branch onto a common
    standard-deviation scale (within-branch only). A branch with fewer
    than 2 samples has undefined std and returns 0 for those entries
    (not NaN — silent NaN in a CSV is far worse than a documented zero).
    """
    raw = np.asarray(raw, dtype=float)
    branches = np.asarray(branches)
    out = np.zeros_like(raw, dtype=float)
    for label in np.unique(branches):
        mask = branches == label
        block = raw[mask]
        if block.size < 2:
            out[mask] = 0.0
            continue
        mu = float(block.mean())
        sigma = float(block.std())
        if sigma == 0.0:
            out[mask] = 0.0
        else:
            out[mask] = (block - mu) / sigma
    return out


__all__ = [
    "SHAPE_PARTIAL_PENALTY",
    "UnifiedMatchResult",
    "unified_compare",
    "per_branch_zscore",
]
