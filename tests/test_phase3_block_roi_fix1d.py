"""Fix 1d: plastic-first chain, G4/G5, constants, phone backlight policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

_CODE = Path(__file__).resolve().parent.parent / "code"
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

import phase3_block_roi as roi  # noqa: E402
import phase3_contour_profile as p3cp  # noqa: E402

PHONE_JSON = Path(__file__).resolve().parent.parent / "phase3_outputs" / "block_roi_constants_phone.json"
PI_JSON = Path(__file__).resolve().parent.parent / "phase3_outputs" / "block_roi_constants_pi.json"
IPHONE = Path(__file__).resolve().parent.parent / "iphone_images"


def test_load_phone_constants():
    cfg = roi.load_block_roi_constants("phone")
    assert "G4_MIN_HEIGHT_FRAC" in cfg
    roi.reload_block_roi_constants()


def test_load_pi_constants_stub():
    cfg = roi.load_block_roi_constants("pi")
    assert cfg["G5_MAX_AREA_FRAC"] == pytest.approx(0.9)
    roi.reload_block_roi_constants()


def test_margin_strict_from_json():
    data = json.loads(PHONE_JSON.read_text(encoding="utf-8"))
    roi.reload_block_roi_constants()
    assert roi.MARGIN_STRICT_MIN_PERIM_FRAC >= roi.BACKLIGHT_EDGE_FRAC
    assert "_margin_calibration" in data
    assert data["_margin_calibration"]["n_rows"] >= 40


def test_reload_block_roi_constants():
    roi.reload_block_roi_constants()
    before = roi.G4_MIN_HEIGHT_FRAC
    data = json.loads(PHONE_JSON.read_text(encoding="utf-8"))
    data["G4_MIN_HEIGHT_FRAC"] = 0.12
    PHONE_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        roi.reload_block_roi_constants()
        assert roi.G4_MIN_HEIGHT_FRAC == pytest.approx(0.12)
    finally:
        data["G4_MIN_HEIGHT_FRAC"] = before
        PHONE_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        roi.reload_block_roi_constants()


def test_phone_never_backlight_cc():
    gray = np.full((400, 400), 250, dtype=np.uint8)
    gray[0, :] = 255
    gray[-1, :] = 255
    gray[:, 0] = 255
    gray[:, -1] = 255
    gray[50:350, 50:350] = 90
    _, method, _ = roi.detect_cassette_bbox(gray, capture_source="phone")
    assert method != "backlight_cc"


def test_pi_may_use_backlight_cc_with_margin():
    gray = np.full((400, 400), 250, dtype=np.uint8)
    gray[0, :] = 255
    gray[-1, :] = 255
    gray[:, 0] = 255
    gray[:, -1] = 255
    gray[50:350, 50:350] = 90
    assert roi.detect_has_strong_margin(gray) or roi.detect_has_backlight_margin(gray)
    _, method, _ = roi.detect_cassette_bbox(gray, capture_source="pi")
    assert method in ("backlight_cc", "plastic_frame", "dark_frame", "paraffin_envelope", "geometric_inset")


def test_cassette_chain_fail_closed():
    blank = np.full((400, 400, 3), 250, dtype=np.uint8)
    det = roi.detect_cassette_interior_roi_detail(blank, capture_source="phone")
    assert det.roi_detection_ok is False
    assert det.roi_fail_reason in (
        "cassette_chain_exhausted", "paraffin_low", "ambiguous_orientation",
        "roi_narrow", "roi_sliver", "roi_oversize",
    )


def test_geometry_g4_sliver_synthetic():
    gray = np.full((200, 200), 180, dtype=np.uint8)
    inner = (10, 10, 180, 180)
    bbox = (20, 90, 160, 8)
    ok, reason, fails = roi.evaluate_roi_gates(gray, bbox, inner, (200, 200))
    assert ok is False
    assert "roi_sliver" in fails or reason == "roi_sliver"


def test_capture_source_default_documented():
    meta = p3cp.parse_image_filename("set_04_block_silhouette_esophagus_MT_NAIVE_WO7842")
    p3cp.enrich_tissue_fields(meta)
    assert meta["capture_source"] == "phone"
    assert meta.get("capture_source_defaulted") is True


@pytest.mark.skipif(
    not list(IPHONE.glob("set_02*silhouette*.jp*g")),
    reason="iphone_images missing",
)
def test_set02_strip_not_ambiguous():
    path = list(IPHONE.glob("set_02*silhouette*.jp*g"))[0]
    bgr = cv2.imread(str(path))
    det = roi.detect_cassette_interior_roi_detail(bgr, capture_source="phone")
    assert det.roi_fail_reason != "ambiguous_orientation" or det.roi_detection_ok
    if det.roi_detection_ok:
        assert det.strip_method in ("opposite_end", "none")


@pytest.mark.skipif(
    not list(IPHONE.glob("set_06*silhouette*.jp*g")),
    reason="iphone_images missing",
)
def test_set06_sliver_class():
    path = list(IPHONE.glob("set_06*silhouette*.jp*g"))[0]
    bgr = cv2.imread(str(path))
    det = roi.detect_cassette_interior_roi_detail(bgr, capture_source="phone")
    assert not det.roi_detection_ok or "roi_sliver" not in det.gate_failures
