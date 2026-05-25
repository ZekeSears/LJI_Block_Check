"""
Phase 1 segmentation — automated test suite.

Per CLAUDE.md the tests in this file are written BEFORE the production
code in code/phase1_segmentation.py. Each test corresponds to a failure
mode flagged in .claude/specs/pre_mortem.md. The test ids referenced in
docstrings below map back to that document so future maintainers can
trace every test to the risk it was written to mitigate.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import pytest

import phase1_segmentation as p1


# ---------------------------------------------------------------------------
# §5.2 — Zero-contours guard
# ---------------------------------------------------------------------------

def test_compute_metrics_zero_contours_guard(solid_white_image):
    """Pre-mortem §2.2: the EXPLICIT zero-contours code path in
    compute_metrics() must emit sentinel values without calling
    min/max/mean on the empty list."""
    bgr = solid_white_image
    # Build a benign mask + threshold; force filtered=[] directly so we
    # exercise the guard branch independently of Otsu's behaviour on
    # degenerate input.
    mask = np.zeros(bgr.shape[:2], dtype=np.uint8)
    threshold = 0
    meta = {
        "filename": "synth.jpg", "role": "block",
        "sample_label": "test", "stain": "",
    }
    metrics = p1.compute_metrics(bgr, mask, [], threshold, meta)
    assert metrics["num_contours_filtered"] == 0
    assert metrics["largest_contour_area_px"] == 0
    assert metrics["smallest_contour_area_px"] == 0
    assert metrics["mean_contour_area_px"] == 0.0
    assert metrics["total_tissue_area_px"] == 0
    assert metrics["tissue_fraction"] == 0.0
    assert metrics["success_heuristic"] == "REVIEW"


@pytest.mark.parametrize("fixture_name", ["solid_black_image", "solid_white_image"])
def test_pipeline_does_not_crash_on_degenerate_input(fixture_name, request):
    """Pre-mortem §2.2 (integration): the full per-image pipeline must
    complete on a degenerate uniform image without raising ValueError or
    ZeroDivisionError. Otsu on a flat histogram may saturate the mask
    (yielding one whole-image contour) or zero it (yielding none) —
    BOTH outcomes must produce a valid metrics row."""
    bgr = request.getfixturevalue(fixture_name)
    gray_inv, mask, threshold = p1.segment_tissue(bgr)
    _, filtered = p1.extract_contours(mask, min_area=p1.MIN_CONTOUR_AREA)
    meta = {
        "filename": "synth.jpg", "role": "block",
        "sample_label": "test", "stain": "",
    }
    metrics = p1.compute_metrics(bgr, mask, filtered, threshold, meta)

    # Required CSV columns are present and numerically sane.
    for k in (
        "num_contours_total", "num_contours_filtered",
        "total_tissue_area_px", "largest_contour_area_px",
        "smallest_contour_area_px", "mean_contour_area_px",
        "tissue_fraction", "success_heuristic",
    ):
        assert k in metrics
    assert metrics["mean_contour_area_px"] >= 0.0
    assert metrics["tissue_fraction"] >= 0.0
    assert metrics["success_heuristic"] in ("PASS", "REVIEW")


# ---------------------------------------------------------------------------
# §5.3 — Filename parser
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,expected", [
    # --- Convention A (original plan filenames) ---
    ("IMG_3084_block_WT5_lungs.jpg",
        {"role": "block", "sample_label": "WT5_lungs", "stain": "",
         "is_reference": False, "image_type": "block"}),
    ("IMG_3084_slide_WT5_lungs_HE.jpg",
        {"role": "slide", "sample_label": "WT5_lungs", "stain": "HE",
         "is_reference": False, "image_type": "slide"}),
    ("IMG_3091_slide_TWKOB1_lungs_MT.jpeg",
        {"role": "slide", "sample_label": "TWKOB1_lungs", "stain": "MT",
         "is_reference": False, "image_type": "slide"}),
    ("IMG_3085_block_WT4_esophagus.jpg",
        {"role": "block", "sample_label": "WT4_esophagus", "stain": "",
         "is_reference": False, "image_type": "block"}),
    ("IMG_3085_slide_WT4_esophagus_HE.jpg",
        {"role": "slide", "sample_label": "WT4_esophagus", "stain": "HE",
         "is_reference": False, "image_type": "slide"}),
    ("IMG_3089_slide_TWKO5_esophagus_HE.jpg",
        {"role": "slide", "sample_label": "TWKO5_esophagus", "stain": "HE",
         "is_reference": False, "image_type": "slide"}),
    ("IMG_3090_reference_tray.jpg",
        {"role": "reference", "sample_label": "tray", "stain": "",
         "is_reference": True, "image_type": "reference"}),
    ("IMG_3080_block_esophagus_1.jpg",
        {"role": "block", "sample_label": "esophagus_1", "stain": "",
         "is_reference": False, "image_type": "block"}),
    # --- Convention B (set-prefixed; identity from filename tokens) ---
    ("set_01_block_silhouette_lung_MT_TWKOB4.jpeg",
        {"role": "block", "sample_label": "lung_MT_TWKOB4", "stain": "",
         "is_reference": False, "image_type": "silhouette"}),
    ("set_01_slide_lung_MT_TWKOB4.jpeg",
        {"role": "slide", "sample_label": "lung_MT_TWKOB4", "stain": "",
         "is_reference": False, "image_type": "slide"}),
    ("set_02_block_barcode_lungs_HE_WT3_WO7842.jpeg",
        {"role": "block", "sample_label": "lungs_HE_WT3_WO7842", "stain": "",
         "is_reference": False, "image_type": "barcode"}),
    ("set_02_block_silhouette_lungs_HE_WT3_WO7842.jpeg",
        {"role": "block", "sample_label": "lungs_HE_WT3_WO7842", "stain": "",
         "is_reference": False, "image_type": "silhouette"}),
    ("set_02_slide_lungs_HE_WT3_WO7842.jpeg",
        {"role": "slide", "sample_label": "lungs_HE_WT3_WO7842", "stain": "",
         "is_reference": False, "image_type": "slide"}),
    ("set_06_block_barcode_lungs_HE_TWKO5_WO7842.jpeg",
        {"role": "block", "sample_label": "lungs_HE_TWKO5_WO7842", "stain": "",
         "is_reference": False, "image_type": "barcode"}),
    # Short legacy name: sample_label falls back to set prefix
    ("set_06_block_silhouette.jpeg",
        {"role": "block", "sample_label": "set_06", "stain": "",
         "is_reference": False, "image_type": "silhouette"}),
])
def test_parse_filename_all_patterns(filename, expected):
    """Pre-mortem §3.3: multi-underscore labels and stain suffix detection."""
    assert p1.parse_filename(Path(filename)) == expected


def test_parse_filename_rejects_malformed():
    """Pre-mortem §3.3: malformed names must raise so main() can skip."""
    with pytest.raises(ValueError):
        p1.parse_filename(Path("not_a_valid_filename.jpg"))
    with pytest.raises(ValueError):
        p1.parse_filename(Path("IMG_3084_unknownrole_thing.jpg"))


# ---------------------------------------------------------------------------
# §5.4 — Success heuristic boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("num_contours,tissue_fraction,image_pixels,expected", [
    # Zero contours: always REVIEW
    (0, 0.0,       1_000_000, "REVIEW"),
    (0, 0.1,       1_000_000, "REVIEW"),
    # 1 Mpx, MIN=1000 → floor = max(0.0005, 0.001) = 0.001
    (1, 0.0004,    1_000_000, "REVIEW"),
    (1, 0.001,     1_000_000, "PASS"),
    (3, 0.05,      1_000_000, "PASS"),
    # Above upper bound
    (1, 0.6,       1_000_000, "REVIEW"),
    (1, 0.51,      1_000_000, "REVIEW"),
    # Exactly at upper bound is inclusive PASS
    (1, 0.5,       1_000_000, "PASS"),
    # iPhone-resolution edge cases: 12 Mpx, MIN=1000 → ratio = 0.0000833
    #   absolute floor 0.0005 wins → floor = 0.0005
    (1, 0.0000833, 12_000_000, "REVIEW"),
    # Six minimum-area contours on 12 Mpx exactly meet the absolute floor.
    (6, 0.0005,    12_000_000, "PASS"),
])
def test_success_heuristic_boundaries(num_contours, tissue_fraction,
                                      image_pixels, expected):
    """Pre-mortem §2.3 + §5.4: adaptive floor and upper-bound logic."""
    result = p1.compute_success_heuristic(
        num_contours=num_contours,
        tissue_fraction=tissue_fraction,
        image_pixels=image_pixels,
        min_contour_area=p1.MIN_CONTOUR_AREA,
    )
    assert result == expected


# ---------------------------------------------------------------------------
# §5.5 — Diagnostic visualization channel order
# ---------------------------------------------------------------------------

def test_visualization_color_order(red_patch_image, tmp_path):
    """Pre-mortem §2.1: top-left panel must be RGB, not BGR-as-RGB."""
    gray_inv, mask, _threshold = p1.segment_tissue(red_patch_image)
    # min_area tiny so the whole-image "tissue" survives filtering. (Otsu
    # on a uniform red image picks a degenerate threshold; the test does
    # not depend on contour quality, only on panel colours.)
    _, contours = p1.extract_contours(mask, min_area=1)
    out = tmp_path / "color_test.png"

    p1.create_diagnostic_visualization(
        red_patch_image, gray_inv, mask, contours, out
    )
    assert out.exists(), "Visualization function did not write its output."

    saved_bgr = cv2.imread(str(out))
    assert saved_bgr is not None, "Saved PNG could not be read back."
    saved_rgb = cv2.cvtColor(saved_bgr, cv2.COLOR_BGR2RGB)

    # Sample inside the top-left quadrant (the original-colour panel).
    # We avoid the very edges where matplotlib whitespace/axes may live.
    h, w = saved_rgb.shape[:2]
    sample = saved_rgb[h // 4, w // 4]
    r, g, b = int(sample[0]), int(sample[1]), int(sample[2])

    assert r > b, (
        "Top-left panel shows B > R for a red-dominant input. "
        f"Got R={r}, G={g}, B={b}. "
        "Did you forget cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)?"
    )


# ---------------------------------------------------------------------------
# §8.3 supplementary — Otsu sanity, contour filtering, main() integration
# ---------------------------------------------------------------------------

def test_segment_tissue_returns_threshold_in_valid_range(synthetic_dark_blob_image):
    """Otsu threshold must be a valid uint8 value."""
    gray_inv, mask, threshold = p1.segment_tissue(synthetic_dark_blob_image)
    assert gray_inv.shape == synthetic_dark_blob_image.shape[:2]
    assert mask.shape == synthetic_dark_blob_image.shape[:2]
    assert mask.dtype == np.uint8
    # Otsu returns a float; cast and bound-check.
    assert 0 <= int(threshold) <= 255


def test_segment_tissue_rejects_non_bgr():
    """Shape assertion: pre-mortem requires explicit input validation."""
    with pytest.raises((AssertionError, ValueError)):
        p1.segment_tissue(np.zeros((100, 100), dtype=np.uint8))  # 2-D
    with pytest.raises((AssertionError, ValueError)):
        p1.segment_tissue(np.zeros((100, 100, 4), dtype=np.uint8))  # 4-channel


def test_extract_contours_respects_min_area(mixed_blob_mask):
    """A small blob below MIN_CONTOUR_AREA must be filtered out."""
    all_c, filtered = p1.extract_contours(mixed_blob_mask, min_area=1000)
    assert len(all_c) == 2
    assert len(filtered) == 1  # tiny blob (~79 px) filtered out


def test_main_skips_reference_files(tmp_path, synthetic_dark_blob_image, monkeypatch):
    """A *_reference_*.jpg file must produce no diagnostic PNG / CSV row."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    # One real-looking processable file + one reference file.
    cv2.imwrite(str(in_dir / "IMG_0001_block_synth.jpg"),
                synthetic_dark_blob_image)
    cv2.imwrite(str(in_dir / "IMG_3090_reference_tray.jpg"),
                synthetic_dark_blob_image)

    monkeypatch.setattr(p1, "INPUT_DIR", in_dir)
    monkeypatch.setattr(p1, "OUTPUT_DIR", out_dir)

    p1.main()

    viz_dir = out_dir / p1.VISUALIZATION_SUBDIR
    diagnostics = list(viz_dir.glob("*.png"))
    diag_names = {d.name for d in diagnostics}
    assert any("IMG_0001_block_synth" in n for n in diag_names)
    assert not any("reference" in n for n in diag_names)

    csv_path = out_dir / p1.METRICS_FILENAME
    assert csv_path.exists()
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "IMG_0001_block_synth" in csv_text
    assert "reference_tray" not in csv_text


def test_main_creates_output_directories(tmp_path, synthetic_dark_blob_image,
                                         monkeypatch):
    """Pre-mortem §4.2: output directory must be created up front."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "does_not_exist_yet" / "out"  # nested, missing parent
    in_dir.mkdir()
    cv2.imwrite(str(in_dir / "IMG_0001_block_synth.jpg"),
                synthetic_dark_blob_image)

    monkeypatch.setattr(p1, "INPUT_DIR", in_dir)
    monkeypatch.setattr(p1, "OUTPUT_DIR", out_dir)

    # Must not raise FileNotFoundError.
    p1.main()
    assert (out_dir / p1.VISUALIZATION_SUBDIR).is_dir()
    assert (out_dir / p1.METRICS_FILENAME).exists()


def test_matplotlib_figures_closed(red_patch_image, tmp_path):
    """Pre-mortem §4.1: plt.close(fig) must be called per figure to prevent leak."""
    gray_inv, mask, _ = p1.segment_tissue(red_patch_image)
    _, contours = p1.extract_contours(mask, min_area=1)

    with mock.patch.object(p1.plt, "close", wraps=p1.plt.close) as spy:
        p1.create_diagnostic_visualization(
            red_patch_image, gray_inv, mask, contours,
            tmp_path / "leak_test.png",
        )
    assert spy.call_count >= 1, (
        "plt.close was never called — figure registry will leak across batch."
    )
