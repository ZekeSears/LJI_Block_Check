"""
TDD suite for phase3_contour_profile.py — keyed to
.cursor/specs/proposed_plan.md and .cursor/specs/pre_mortem.md.
"""

from __future__ import annotations

import numpy as np
import pytest

import phase3_contour_profile as p3cp


# ---------------------------------------------------------------------------
# Filename parser
# ---------------------------------------------------------------------------


def test_parse_canonical_block_silhouette_eight_tokens():
    meta = p3cp.parse_image_filename(
        "set_20_block_silhouette_lung_HE_TWKO1_WO7842"
    )
    assert meta["parse_ok"] is True
    assert meta["set_id"] == 20
    assert meta["role"] == "block_silhouette"
    assert meta["tissue"] == "lung"
    assert meta["stain"] == "HE"
    assert meta["genotype"] == "TWKO1"
    assert meta["work_order"] == "WO7842"
    assert meta["label_type"] == "white"


def test_parse_slide_role_without_subtype():
    meta = p3cp.parse_image_filename("set_09_slide_lung_HE_WT2_WO7842")
    assert meta["parse_ok"] is True
    assert meta["role"] == "slide"
    assert meta["tissue"] == "lung"
    assert meta["stain"] == "HE"
    assert meta["genotype"] == "WT2"
    assert meta["work_order"] == "WO7842"


def test_parse_minimal_slide_three_tokens():
    meta = p3cp.parse_image_filename("set_05_slide")
    assert meta["parse_ok"] is True
    assert meta["role"] == "slide"
    assert meta["set_id"] == 5
    assert meta["tissue"] == ""
    assert meta["work_order"] == ""


def test_parse_set1_missing_work_order_token():
    meta = p3cp.parse_image_filename(
        "set_01_block_silhouette_lung_MT_TWKOB4"
    )
    assert meta["parse_ok"] is True
    assert meta["set_id"] == 1
    assert meta["work_order"] == ""
    assert meta["label_type"] == "yellow"


def test_parse_malformed_unknown_role_prefix():
    meta = p3cp.parse_image_filename(
        "set_99_unknown_silhouette_lung_HE_X_WO7842"
    )
    assert meta["parse_ok"] is False
    assert "unknown role" in meta["parse_error"].lower()


def test_label_type_yellow_only_set_one():
    assert p3cp.label_type_for_set(1) == "yellow"
    assert p3cp.label_type_for_set(2) == "white"


def test_barcode_role_excluded_from_measurement():
    meta = p3cp.parse_image_filename(
        "set_20_block_barcode_lung_HE_TWKO1_WO7842"
    )
    assert meta["parse_ok"] is True
    assert p3cp.should_measure_contours(meta) is False


def test_block_silhouette_is_measured():
    meta = p3cp.parse_image_filename(
        "set_20_block_silhouette_lung_HE_TWKO1_WO7842"
    )
    assert p3cp.should_measure_contours(meta) is True


# ---------------------------------------------------------------------------
# Grouping & percentiles
# ---------------------------------------------------------------------------


def test_group_by_tissue_and_role():
    records = [
        {"tissue_class": "lung", "role": "slide", "label_type": "white",
         "contour_count": 2, "eligible_for_threshold": True},
        {"tissue_class": "lung", "role": "block_silhouette", "label_type": "white",
         "contour_count": 1, "eligible_for_threshold": True},
        {"tissue_class": "esophagus", "role": "slide", "label_type": "white",
         "contour_count": 5, "eligible_for_threshold": True},
    ]
    groups = p3cp.group_measurement_records(records)
    assert len(groups[("lung", "slide")]) == 1
    assert len(groups[("lung", "block_silhouette")]) == 1
    assert len(groups[("esophagus", "slide")]) == 1


def test_yellow_tag_excluded_from_threshold_pool():
    records = [
        {"tissue_class": "lung", "role": "slide", "label_type": "yellow",
         "contour_count": 99, "eligible_for_threshold": False},
        {"tissue_class": "lung", "role": "slide", "label_type": "white",
         "contour_count": 2, "eligible_for_threshold": True},
    ]
    pool = p3cp.white_tag_threshold_records(records)
    assert len(pool) == 1
    assert pool[0]["contour_count"] == 2


def test_percentile_summary_known_array():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    summary = p3cp.compute_percentile_summary(values)
    assert summary["p50"] == pytest.approx(5.5, abs=0.01)
    assert summary["p90"] == pytest.approx(9.1, abs=0.1)
    assert summary["p10"] == pytest.approx(1.9, abs=0.1)


# ---------------------------------------------------------------------------
# Threshold derivation (pre-mortem critical)
# ---------------------------------------------------------------------------


def test_derive_count_threshold_clean_separation():
    lung = [1.0, 1.0, 2.0, 2.0, 2.0]
    esoph = [8.0, 9.0, 10.0, 11.0, 12.0]
    result = p3cp.derive_count_threshold(lung, esoph)
    assert result["overlap"] is False
    assert result["threshold"] is not None
    assert result["threshold"] == int(round((np.percentile(lung, 90)
                                            + np.percentile(esoph, 10)) / 2))


def test_derive_count_threshold_heavy_overlap():
    lung = [5.0, 6.0, 7.0, 8.0]
    esoph = [4.0, 5.0, 6.0, 7.0]
    result = p3cp.derive_count_threshold(lung, esoph)
    assert result["overlap"] is True
    assert result["threshold"] is None


def test_derive_count_threshold_p90_equals_p10():
    lung = [4.0, 4.0, 5.0]
    esoph = [5.0, 6.0, 6.0]
    result = p3cp.derive_count_threshold(lung, esoph)
    assert result["overlap"] is False
    assert result["threshold"] == 5


def test_derive_area_threshold_uses_median_statistic():
    lung = [50000.0, 52000.0, 48000.0]
    esoph = [800.0, 900.0, 700.0]
    result = p3cp.derive_area_threshold(lung, esoph)
    assert result["overlap"] is False
    assert result["statistic"] == "median"


def test_sanity_check_thresholds_in_range():
    ok, msg = p3cp.validate_threshold_sanity(10, 5000.0, max_image_pixels=4_000_000)
    assert ok is True
    assert msg == ""

    bad_count, msg_c = p3cp.validate_threshold_sanity(1, 5000.0)
    assert bad_count is False

    bad_area, msg_a = p3cp.validate_threshold_sanity(10, 50.0)
    assert bad_area is False


# ---------------------------------------------------------------------------
# Degenerate segmentation handling
# ---------------------------------------------------------------------------


def test_exclusion_reason_zero_contours():
    assert p3cp.measurement_exclusion_reason(0, 0.0) == "no_contours"


def test_exclusion_reason_degenerate_single_contour():
    assert p3cp.measurement_exclusion_reason(
        1, 0.96,
    ) == "degenerate_single_contour"


def test_exclusion_reason_none_when_valid():
    assert p3cp.measurement_exclusion_reason(3, 0.2) is None


def test_derive_high_low_separation_slide_total_area():
    lung = [300_000.0, 280_000.0, 320_000.0]
    esoph = [120_000.0, 140_000.0, 100_000.0]
    result = p3cp.derive_high_low_separation_threshold(lung, esoph)
    assert result["overlap"] is False
    assert result["threshold"] is not None
    assert result["method"] == "median_midpoint"
    assert result["threshold"] == pytest.approx(210_000.0)


def test_derive_high_low_separation_overlap_when_ranges_touch():
    lung = [100.0, 110.0]
    esoph = [105.0, 120.0]
    result = p3cp.derive_high_low_separation_threshold(lung, esoph)
    assert result["overlap"] is True


def test_validate_hybrid_router_sanity_pass():
    ok, msg = p3cp.validate_hybrid_router_sanity(225_000.0, 0.92)
    assert ok is True
    assert msg == ""


def test_overlap_detection_flags_heavy_overlap():
    assert p3cp.detect_distribution_overlap(
        [1, 2, 3], [2, 3, 4],
    ) is True
    assert p3cp.detect_distribution_overlap(
        [1, 1, 2], [9, 10, 11],
    ) is False
