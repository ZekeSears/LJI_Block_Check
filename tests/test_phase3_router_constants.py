"""Tests for provenance-gated router_constants.json loading (plan v2 Step 3.2)."""

from __future__ import annotations

import json

import phase3_router as p3r


def test_load_ignores_overlap_unresolved_stub(tmp_path, monkeypatch):
    stub = tmp_path / "router_constants.json"
    stub.write_text(
        json.dumps(
            {
                "status": "overlap_unresolved",
                "calibration_exit": 1,
                "overlap_reasons": ["area"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(p3r, "_ROUTER_CONSTANTS_PATH", stub)
    p3r.reload_router_constants()
    assert p3r.SLIDE_TOTAL_TISSUE_AREA_PX == 225_000.0
    assert p3r.DOMINANCE_MIN_FOR_SHAPE == 0.92
    assert p3r.router_constants_source() == "module_defaults"


def test_load_calibrated_json(tmp_path, monkeypatch):
    path = tmp_path / "router_constants.json"
    path.write_text(
        json.dumps(
            {
                "status": "calibrated",
                "calibration_exit": 0,
                "SLIDE_TOTAL_TISSUE_AREA_PX": 12_345.0,
                "DOMINANCE_MIN_FOR_SHAPE": 0.88,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(p3r, "_ROUTER_CONSTANTS_PATH", path)
    p3r.reload_router_constants()
    assert p3r.SLIDE_TOTAL_TISSUE_AREA_PX == 12_345.0
    assert p3r.DOMINANCE_MIN_FOR_SHAPE == 0.88
    assert p3r.router_constants_source() == "router_constants.json"
