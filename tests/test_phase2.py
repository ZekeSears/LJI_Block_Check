"""
Phase 2 shape descriptor & matching — automated test suite (TDD).

Every test in this file is written BEFORE the production code in
code/phase2_descriptors.py and is keyed to a specific finding in
.claude/specs/pre_mortem.md (the Phase 2 critique). Test docstrings cite
the pre-mortem section so future maintainers can trace each test back to
the failure mode it was written to mitigate.

Tests use synthetic fixtures only (per the proposed_plan §6 rule). The
live-dataset cross-modal acceptance test lives in
tests/integration/test_cross_modal_ranking.py and is excluded from the
default `pytest tests/` run.
"""

from __future__ import annotations

from unittest import mock

import cv2
import numpy as np
import pytest

import phase2_descriptors as p2


# ---------------------------------------------------------------------------
# Stage 1: mask cleaning
# ---------------------------------------------------------------------------

def test_slide_label_roi_is_zeroed(slide_mask_with_label):
    """Pre-mortem §2.1: top SLIDE_LABEL_ROI_FRACTION of slide masks must
    be zeroed before contour extraction."""
    cleaned, _ = p2.clean_mask(slide_mask_with_label.copy(), role="slide")
    h = slide_mask_with_label.shape[0]
    label_rows = int(h * p2.SLIDE_LABEL_ROI_FRACTION)
    assert cleaned[:label_rows, :].sum() == 0, (
        "Label ROI region must contain zero foreground pixels after cleaning."
    )
    # Lower-half tissue must be preserved.
    assert cleaned[label_rows:, :].sum() > 0


def test_block_role_does_not_apply_label_roi(slide_mask_with_label):
    """The label ROI heuristic is slide-only; block masks must be untouched
    in their top region."""
    cleaned, _ = p2.clean_mask(slide_mask_with_label.copy(), role="block")
    h = slide_mask_with_label.shape[0]
    label_rows = int(h * p2.SLIDE_LABEL_ROI_FRACTION)
    # The synthetic 'label' rectangle is intentionally preserved for blocks.
    assert cleaned[:label_rows, :].sum() > 0


def test_solidity_filter_drops_rectangular_artifacts(block_mask_with_grid_artifact):
    """Pre-mortem §2.x: rectangular contours (solidity ~1.0) must be
    filtered out; lobed tissue (solidity <0.95) must survive."""
    _cleaned, contours = p2.clean_mask(
        block_mask_with_grid_artifact.copy(), role="block"
    )
    # Exactly one contour should survive: the lobed tissue blob.
    assert len(contours) == 1, (
        f"Expected 1 surviving contour after solidity filter, got {len(contours)}."
    )
    survivor_solidity = p2._compute_solidity(contours[0])
    assert survivor_solidity < p2.SOLIDITY_MAX


def test_degenerate_mask_detection_returns_no_contours():
    """Pre-mortem §3.6: a mask whose tissue_fraction > 0.95 after cleaning
    indicates background segmentation failed; pipeline must skip such an
    image (return empty contour list)."""
    # 95%+ of pixels are 255 — degenerate "whole image is tissue".
    mask = np.full((500, 500), 255, dtype=np.uint8)
    _cleaned, contours = p2.clean_mask(mask, role="slide")
    assert contours == [], (
        "Degenerate near-full-frame mask must produce empty contour list."
    )


# ---------------------------------------------------------------------------
# Stage 2: descriptor computation
# ---------------------------------------------------------------------------

def test_zernike_canvas_radius_scales_with_contour(lung_contour_at_1x,
                                                   lung_contour_at_2x):
    """Pre-mortem §2.3: contour_to_zernike_image() must produce a canvas
    whose radius is proportional to the contour bounding box, so identical
    shapes at different scales receive matching radii (true scale
    invariance, not just same-implementation invariance)."""
    canvas_1x, radius_1x = p2.contour_to_zernike_image(
        lung_contour_at_1x, padding_factor=0.1
    )
    canvas_2x, radius_2x = p2.contour_to_zernike_image(
        lung_contour_at_2x, padding_factor=0.1
    )
    # Radius for 2x contour should be approximately 2x the 1x radius.
    ratio = radius_2x / radius_1x
    assert 1.8 < ratio < 2.2, (
        f"Zernike canvas radius did not scale with contour size: "
        f"ratio={ratio:.3f}, expected ~2.0"
    )


def test_zernike_canvas_is_binary_and_centered(lung_contour_at_1x):
    """The rendered canvas must be a binary (0/255 or 0/1) image with the
    contour entirely contained within it."""
    canvas, _radius = p2.contour_to_zernike_image(
        lung_contour_at_1x, padding_factor=0.1
    )
    assert canvas.ndim == 2
    assert canvas.dtype == np.uint8
    unique_vals = set(np.unique(canvas).tolist())
    assert unique_vals.issubset({0, 255}) or unique_vals.issubset({0, 1})
    # Some foreground pixels exist.
    assert canvas.max() > 0


def test_zernike_moments_scale_invariant(lung_contour_at_1x, lung_contour_at_2x):
    """Pre-mortem §2.3 acceptance: scale-invariance of Zernike vectors
    given proper bbox-relative rendering."""
    z1 = p2.compute_zernike_moments(lung_contour_at_1x)
    z2 = p2.compute_zernike_moments(lung_contour_at_2x)
    dist = float(np.linalg.norm(z1 - z2))
    assert dist < 0.05, (
        f"Zernike vectors should be near-identical across 2x scale; got dist={dist:.4f}"
    )


def test_hu_moments_rotation_invariant(lung_contour_at_1x, lung_contour_rotated_90):
    """Hu moments are theoretically rotation-invariant; their log-magnitudes
    must match between a contour and its 90-degree rotation."""
    h1 = p2.compute_hu_log(lung_contour_at_1x)
    h2 = p2.compute_hu_log(lung_contour_rotated_90)
    # Loose tolerance — discretisation of integer pixel coordinates
    # introduces small Hu noise. The first 6 moments are robustly invariant.
    diff = np.abs(h1[:6] - h2[:6]).max()
    assert diff < 0.5, f"Hu log-magnitudes diverged across rotation: {diff:.3f}"


def test_descriptor_dict_has_expected_keys(lung_contour_at_1x):
    """Descriptor must expose named fields so downstream code does not
    rely on positional ordering."""
    d = p2.compute_descriptors(lung_contour_at_1x)
    expected = {"area", "perimeter", "aspect_ratio", "solidity", "eccentricity"}
    expected |= {f"hu_{i}" for i in range(7)}
    # Zernike fields exist; exact count depends on ZERNIKE_DEGREE.
    zer = {k for k in d if k.startswith("zernike_")}
    assert expected.issubset(set(d))
    assert len(zer) > 10


# ---------------------------------------------------------------------------
# Feature normalization (§2.2 + §5.2)
# ---------------------------------------------------------------------------

def test_normalization_makes_scale_close_shape_far(lung_contour_at_1x,
                                                   lung_contour_at_2x,
                                                   differently_shaped_contour):
    """Pre-mortem §5.2: after feature normalization, two same-shape
    contours at different scales must be closer in feature space than
    either is to a differently-shaped contour at the same scale."""
    contours = [lung_contour_at_1x, lung_contour_at_2x, differently_shaped_contour]
    descriptors = [p2.compute_descriptors(c) for c in contours]
    feats = p2.standardize_feature_matrix(
        np.array([p2.descriptor_to_vector(d) for d in descriptors], dtype=float)
    )
    same_shape_dist = float(np.linalg.norm(feats[0] - feats[1]))
    cross_shape_dist_1 = float(np.linalg.norm(feats[0] - feats[2]))
    cross_shape_dist_2 = float(np.linalg.norm(feats[1] - feats[2]))
    assert same_shape_dist < cross_shape_dist_1, (
        f"After normalization, same-shape distance ({same_shape_dist:.3f}) "
        f"should be < cross-shape distance ({cross_shape_dist_1:.3f})."
    )
    assert same_shape_dist < cross_shape_dist_2


# ---------------------------------------------------------------------------
# Stage 4: Hungarian cost-matrix construction (§3.1 + §5.3)
# ---------------------------------------------------------------------------

def test_cost_matrix_is_distance_not_similarity():
    """Pre-mortem §3.1: cost matrix must contain DISTANCES (low = good),
    not similarities (high = good). Identical vectors should produce a
    zero on the diagonal."""
    a = np.array([[0.0, 0.0], [1.0, 1.0]])
    b = np.array([[0.0, 0.0], [1.0, 1.0]])
    cost = p2._build_cost_matrix(a, b)
    assert cost.shape == (2, 2)
    assert cost[0, 0] == pytest.approx(0.0, abs=1e-9)
    assert cost[1, 1] == pytest.approx(0.0, abs=1e-9)
    # Cross-pairs are at L2 distance sqrt(2).
    assert cost[0, 1] > cost[0, 0]
    assert cost[1, 0] > cost[1, 1]


def test_hungarian_finds_correct_pairing():
    """Cost matrix where correct pairing is (0↔0, 1↔1); incorrect pairing
    is (0↔1, 1↔0). linear_sum_assignment on the cost matrix must select
    the cheaper, correct one."""
    a = np.array([[0.0, 0.0], [10.0, 10.0]])
    b = np.array([[0.0, 0.0], [10.0, 10.0]])
    row_ind, col_ind, total_cost = p2.match_features_hungarian(
        a, b, unmatched_cost=p2.UNMATCHED_CONTOUR_COST
    )
    assert list(col_ind[:len(row_ind)]) == [0, 1]
    assert total_cost == pytest.approx(0.0, abs=1e-9)


def test_hungarian_fragment_mismatch_padded_with_unmatched_cost():
    """Pre-mortem §3.4: fragment count mismatch must be handled by padding
    the cost matrix with UNMATCHED_CONTOUR_COST (a cost-space value).
    A 4-vs-3 case must produce a valid assignment whose total cost is
    higher than the matched-only baseline."""
    a = np.array([[0.0], [1.0], [2.0], [3.0]])
    b = np.array([[0.0], [1.0], [2.0]])
    _row, _col, total_cost = p2.match_features_hungarian(
        a, b, unmatched_cost=p2.UNMATCHED_CONTOUR_COST
    )
    # The three matched-up pairs cost 0; the one unmatched contributes
    # UNMATCHED_CONTOUR_COST.
    assert total_cost == pytest.approx(p2.UNMATCHED_CONTOUR_COST, rel=1e-6)


def test_hungarian_known_pair_set_to_set_score(pair_of_known_contours):
    """End-to-end set-to-set matching on known contour pairs must (a)
    select the correct index-wise pairing and (b) return a similarity
    score in [0, 1]. The absolute score depends on how many contours
    are pooled for z-scoring (very few here → inflated distances), so
    we validate the assignment itself, not a magic threshold."""
    block, slide = pair_of_known_contours
    block_descs = [p2.compute_descriptors(c) for c in block]
    slide_descs = [p2.compute_descriptors(c) for c in slide]
    all_vecs = np.array(
        [p2.descriptor_to_vector(d) for d in block_descs + slide_descs],
        dtype=float,
    )
    normed = p2.standardize_feature_matrix(all_vecs)
    nblock = len(block_descs)
    block_feats = normed[:nblock]
    slide_feats = normed[nblock:]
    row, col, _total = p2.match_features_hungarian(block_feats, slide_feats)
    # Correct pairing is index-wise: block[0]↔slide[0], block[1]↔slide[1].
    assignment = dict(zip(row.tolist(), col.tolist()))
    assert assignment[0] == 0
    assert assignment[1] == 1
    similarity = p2.set_to_set_similarity(block_feats, slide_feats)
    assert 0.0 <= similarity <= 1.0


# ---------------------------------------------------------------------------
# Stage 3: intra-class self-similarity (§5.4)
# ---------------------------------------------------------------------------

def test_self_similarity_is_approximately_one(lung_contour_at_1x):
    """Pre-mortem §5.4: self-similarity must be 1.0 within float tolerance
    (NOT exact equality — Zernike/Hu computation has FP drift)."""
    desc = p2.compute_descriptors(lung_contour_at_1x)
    vec = np.array([p2.descriptor_to_vector(desc)], dtype=float)
    # Trivial standardization on a 1-row matrix: returns zeros; bypass by
    # passing the raw vector through set_to_set_similarity which builds
    # the cost matrix directly.
    similarity = p2.set_to_set_similarity(vec, vec)
    assert similarity == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Stage 5: pair visualization (§4.3)
# ---------------------------------------------------------------------------

def test_create_pair_visualization_closes_figure(tmp_path, lung_contour_at_1x):
    """plt.close(fig) must be called per figure to prevent matplotlib
    figure registry leak (Phase 1 §4.1 carried forward to Stage 5)."""
    block_img = np.full((400, 400, 3), 240, dtype=np.uint8)
    slide_img = np.full((400, 400, 3), 240, dtype=np.uint8)
    # Translate the contour into the image coordinate frame.
    c = lung_contour_at_1x.copy()
    c[:, 0, 0] += 200
    c[:, 0, 1] += 200
    out = tmp_path / "pair.png"
    with mock.patch.object(p2.plt, "close", wraps=p2.plt.close) as spy:
        p2.create_pair_visualization(
            block_img, [c], slide_img, [c],
            matched_pairs=[(0, 0)], out_path=out,
        )
    assert out.exists()
    assert spy.call_count >= 1


# ---------------------------------------------------------------------------
# Documented limitation — left-edge label orientation (§5.5)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="Left-edge label orientation is out of Phase 2 scope (proposed_plan §6); "
           "documented as a hard capture-protocol assumption."
)
def test_left_edge_label_is_zeroed():
    """If a slide is photographed in landscape with the label on the LEFT
    edge, the current top-only ROI does not mask it. This test documents
    the limitation so it remains visible in pytest output."""
    mask = np.zeros((800, 1000), dtype=np.uint8)
    # "Label" on the left edge (first 20% of width).
    cv2.rectangle(mask, (50, 100), (180, 700), 255, thickness=-1)
    # Real tissue on the right.
    cv2.circle(mask, (700, 400), 80, 255, thickness=-1)
    cleaned, _ = p2.clean_mask(mask, role="slide")
    w = mask.shape[1]
    label_cols = int(w * p2.SLIDE_LABEL_ROI_FRACTION)
    assert cleaned[:, :label_cols].sum() == 0
