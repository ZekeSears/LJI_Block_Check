"""Fix 1c production-mode and telemetry integration tests."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import numpy as np

_CODE = Path(__file__).resolve().parent.parent / "code"
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

import phase3_block_roi as roi  # noqa: E402
import phase3_contour_profile as p3cp  # noqa: E402


def test_segment_with_block_roi_default_no_full_frame_fallback():
    sig = inspect.signature(roi.segment_with_block_roi)
    assert sig.parameters["allow_full_frame_fallback"].default is False


def test_production_roi_fail_empty_contours():
    tiny = np.full((12, 12, 3), 200, dtype=np.uint8)
    meta = {"role": "block_silhouette", "tissue_class": "lung"}
    seg = roi.segment_with_block_roi(
        tiny, meta, p3cp.clean_mask, allow_full_frame_fallback=False,
    )
    assert seg.contours == []
    assert seg.reshoot_recommended is True
    assert seg.segmentation_method == "failed"
    assert seg.roi_fail_reason != "" or not seg.roi_detection_ok


def test_measure_contours_records_zero_contour_row():
    tiny = np.full((12, 12, 3), 200, dtype=np.uint8)
    meta = {"role": "block_silhouette", "tissue_class": "lung"}
    row = p3cp.measure_contours_on_image(tiny, meta)
    assert row["contour_count"] == 0
    assert row["reshoot_recommended"] is True
    assert "cassette_method" in row
    assert "roi_fail_reason" in row


def test_pipeline_call_sites_use_production_default():
    root = Path(__file__).resolve().parent.parent / "code"
    for name in ("phase3_pipeline.py", "phase3_contour_profile.py", "phase2_descriptors.py"):
        src = (root / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "segment_with_block_roi":
                for kw in node.keywords:
                    if kw.arg == "allow_full_frame_fallback" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is False, f"{name} must not enable fallback in production"
