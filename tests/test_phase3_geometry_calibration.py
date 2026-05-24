"""Tests for geometry-based router threshold derivation (plan v2 Step 3)."""

from __future__ import annotations

import phase3_contour_profile as p3cp


def _slide_record(area: float, dominance: float, contour_count: int = 3) -> dict:
    return {
        "role": "slide",
        "label_type": "white",
        "eligible_for_threshold": True,
        "total_tissue_area": area,
        "dominance": dominance,
        "contour_count": contour_count,
        "measurement_exclusion": None,
    }


def test_derive_geometry_router_thresholds_separable_clusters():
    pool = (
        [_slide_record(80_000, 0.95) for _ in range(4)]
        + [_slide_record(6_000, 0.55) for _ in range(4)]
    )
    result = p3cp.derive_geometry_router_thresholds(pool)
    assert result["overlap"] is False
    assert result["slide_area_result"]["threshold"] is not None
    assert result["dominance_result"]["threshold"] is not None
    assert result["geometry"]["shape_like_n"] >= 2
    assert result["geometry"]["constellation_like_n"] >= 2


def test_derive_geometry_router_thresholds_forced_overlap_flag(monkeypatch):
    pool = [_slide_record(10_000, 0.8) for _ in range(8)]

    def _fake_derive(high, low):
        return {"overlap": True, "threshold": None, "method": None}

    monkeypatch.setattr(p3cp, "derive_high_low_separation_threshold", _fake_derive)
    result = p3cp.derive_geometry_router_thresholds(pool)
    assert result["overlap"] is True


def test_derive_geometry_router_thresholds_pool_too_small():
    pool = [_slide_record(10_000, 0.8) for _ in range(3)]
    result = p3cp.derive_geometry_router_thresholds(pool)
    assert result["overlap"] is True
