"""
Phase 3 constellation matching, label detection, and routing — TDD suite.

Every test below was written BEFORE the production code in
code/phase3_*.py and is keyed to a specific finding in
.claude/specs/pre_mortem.md plus a resolution in
.claude/specs/proposed_plan.md v2.

Synthetic fixtures only (per the conftest discipline). Integration on the
real dataset lives in tests/integration/.
"""

from __future__ import annotations

import numpy as np
import pytest

import phase3_constellation as p3c
import phase3_label_detection as p3l
import phase3_router as p3r
import phase3_unified_matcher as p3u


# ===========================================================================
# Constellation signature — pre-mortem §2, §3, §5
# ===========================================================================


def test_signature_shape_is_canonical_55_elements(square_arrangement_contours):
    """Pre-mortem §3 critical: single canonical 55-element vector
    (45 padded pairwise distances + 10 padded area ratios)."""
    sig, meta = p3c.extract_constellation_signature(square_arrangement_contours)
    assert sig.shape == (p3c.SIGNATURE_LENGTH,)
    assert p3c.SIGNATURE_LENGTH == 55
    assert sig.dtype == np.float64
    assert "num_contours" in meta
    assert "normalization_ref_distance" in meta
    assert "normalization_ref_area" in meta


def test_signature_translation_invariant(square_arrangement_contours):
    """Sorted pairwise distances are translation-invariant by construction."""
    sig_a, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    shifted = [c + np.array([500, 300], dtype=np.int32).reshape(1, 1, 2)
               for c in square_arrangement_contours]
    sig_b, _ = p3c.extract_constellation_signature(shifted)
    assert float(np.linalg.norm(sig_a - sig_b)) < 0.01


def test_signature_scale_invariant():
    """Scale invariance: identical arrangement at 1x and 2x produces
    near-identical signatures (90th-percentile normalization absorbs scale)."""
    base = np.array([[300, 300], [700, 300], [700, 700], [300, 700]], dtype=float)
    centre = base.mean(axis=0)
    big = (base - centre) * 2.0 + centre
    from tests.conftest import _points_to_contours  # noqa: E402
    # Use the helper indirectly through known coords.
    import cv2

    def to_contours(pts, r):
        out = []
        for x, y in pts:
            theta = np.linspace(0, 2 * np.pi, 200, endpoint=False)
            xs = (x + r * np.cos(theta)).round().astype(np.int32)
            ys = (y + r * np.sin(theta)).round().astype(np.int32)
            out.append(np.stack([xs, ys], axis=1).reshape(-1, 1, 2))
        return out

    sig_a, _ = p3c.extract_constellation_signature(to_contours(base, 30))
    sig_b, _ = p3c.extract_constellation_signature(to_contours(big, 60))
    # 2x scale of radius preserves area-ratio normalization; 2x position
    # scale preserves distance-ratio normalization.
    assert float(np.linalg.norm(sig_a - sig_b)) < 0.05


def test_signature_rotation_invariant(square_arrangement_contours,
                                      square_arrangement_points,
                                      rotate_points_fn):
    """Pre-mortem §2 critical (replacement for PCA-instability test):
    rotate the arrangement through {0, 45, 90, 135, 180, 270} degrees;
    pairwise signature distances stay < 0.05."""
    base_sig, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    for deg in (45.0, 90.0, 135.0, 180.0, 270.0):
        rotated_pts = rotate_points_fn(square_arrangement_points, deg)
        # Rebuild circle contours at rotated centroids.
        import cv2

        def to_contours(pts, r=30):
            out = []
            for x, y in pts:
                theta = np.linspace(0, 2 * np.pi, 200, endpoint=False)
                xs = (x + r * np.cos(theta)).round().astype(np.int32)
                ys = (y + r * np.sin(theta)).round().astype(np.int32)
                out.append(np.stack([xs, ys], axis=1).reshape(-1, 1, 2))
            return out

        rot_sig, _ = p3c.extract_constellation_signature(to_contours(rotated_pts))
        dist = float(np.linalg.norm(base_sig - rot_sig))
        assert dist < 0.05, f"Rotation {deg}° signature drift {dist:.4f} exceeds tolerance"


def test_signature_near_symmetric_perturbation_stable(
        square_arrangement_contours, square_arrangement_perturbed_contours):
    """Pre-mortem §2/§5 critical: near-symmetric arrangement perturbed by
    1% of bbox diagonal must NOT produce a signature discontinuity
    (which is precisely what PCA-based v1 would have done)."""
    sig_a, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    sig_b, _ = p3c.extract_constellation_signature(square_arrangement_perturbed_contours)
    dist = float(np.linalg.norm(sig_a - sig_b))
    assert dist < 0.05, f"Perturbation produced unstable signature drift: {dist:.4f}"


def test_signature_mirror_invariant(square_arrangement_contours,
                                    square_arrangement_points, mirror_points_fn):
    """Mirror invariance is accepted as desired behavior (glass slides
    physically flip). Pre-mortem §6 minor item — resolved by algorithm
    choice (pairwise distances are intrinsically mirror-invariant)."""
    base_sig, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    mirrored_pts = mirror_points_fn(square_arrangement_points, axis="x")

    def to_contours(pts, r=30):
        out = []
        for x, y in pts:
            theta = np.linspace(0, 2 * np.pi, 200, endpoint=False)
            xs = (x + r * np.cos(theta)).round().astype(np.int32)
            ys = (y + r * np.sin(theta)).round().astype(np.int32)
            out.append(np.stack([xs, ys], axis=1).reshape(-1, 1, 2))
        return out

    mirror_sig, _ = p3c.extract_constellation_signature(to_contours(mirrored_pts))
    assert float(np.linalg.norm(base_sig - mirror_sig)) < 0.05


def test_signature_dominant_signal_not_crushed_by_contamination(
        linear_arrangement_contours):
    """Pre-mortem §2 ¶3 moderate: the SPECIFIC failure mode flagged was
    that a single spurious contour passing the upstream solidity filter
    'becomes the normalization denominator and crushes the rest of the
    signature into a small dynamic range.' This test guards that
    invariant by checking that the dominant distances in the contaminated
    signature retain a meaningful fraction of their original magnitude
    — i.e., the dynamic range is preserved, not crushed to near-zero.

    The signature WILL drift when contour count changes (more pairwise
    pairs fill more slots), but the dominant signal must not collapse.
    90th-percentile normalization (not max) is the mechanism that bounds
    the crush.
    """
    sig_clean, _ = p3c.extract_constellation_signature(linear_arrangement_contours)
    theta = np.linspace(0, 2 * np.pi, 80, endpoint=False)
    tiny = np.stack([
        (450 + 3 * np.cos(theta)).round().astype(np.int32),
        (520 + 3 * np.sin(theta)).round().astype(np.int32),
    ], axis=1).reshape(-1, 1, 2)
    contaminated = list(linear_arrangement_contours) + [tiny]
    sig_dirty, _ = p3c.extract_constellation_signature(contaminated)

    # Look at the largest real distances in both signatures. If
    # normalization crushed the dynamic range, the dirty version's top
    # distances would be a tiny fraction of the clean version's. With
    # 90th-percentile normalization the ratio stays well above 0.5.
    clean_top = float(sig_clean[:6].max())
    dirty_top = float(sig_dirty[:10].max())
    ratio = dirty_top / clean_top
    assert ratio > 0.5, (
        f"Dynamic range crushed: dirty top {dirty_top:.3f} vs clean top "
        f"{clean_top:.3f} (ratio {ratio:.2f}). 90th-percentile "
        f"normalization should keep ratio > 0.5."
    )

    # And bound the gross drift to the documented constant — relaxed
    # to reflect that count-changes legitimately shift the signature.
    drift = float(np.linalg.norm(sig_clean - sig_dirty))
    assert drift < p3c.CONTAMINATION_DRIFT_MAX, (
        f"Contamination drift {drift:.4f} exceeds bound "
        f"{p3c.CONTAMINATION_DRIFT_MAX} — count-change drift is expected "
        f"but should remain bounded."
    )


def test_signature_deterministic(square_arrangement_contours):
    """Same input → byte-equal signature (no RNG, no nondeterminism)."""
    sig_a, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    sig_b, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    assert np.array_equal(sig_a, sig_b)


def test_signature_handles_single_contour(large_solid_contour):
    """Single-contour input must not crash (caller routes to shape).
    Signature is well-defined (all-padding); metadata.num_contours == 1."""
    sig, meta = p3c.extract_constellation_signature(large_solid_contour)
    assert sig.shape == (p3c.SIGNATURE_LENGTH,)
    assert meta["num_contours"] == 1


def test_signature_rejects_empty_contour_list():
    """Empty input is a programming error — caller must filter before
    invoking. Explicit ValueError, not silent zero-signature."""
    with pytest.raises(ValueError):
        p3c.extract_constellation_signature([])


# ===========================================================================
# Constellation matching — pre-mortem §3, §5
# ===========================================================================


def test_match_constellations_self_similarity_is_one(square_arrangement_contours):
    """Pre-mortem §5 critical: self-similarity == 1.0 within float tolerance."""
    sig, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    sim = p3c.match_constellations(sig, sig)
    assert sim == pytest.approx(1.0, abs=1e-9)


def test_match_constellations_returns_in_unit_range(
        square_arrangement_contours, linear_arrangement_contours):
    """Output must be in [0, 1] for any pair of valid signatures."""
    sig_a, _ = p3c.extract_constellation_signature(square_arrangement_contours)
    sig_b, _ = p3c.extract_constellation_signature(linear_arrangement_contours)
    sim = p3c.match_constellations(sig_a, sig_b)
    assert 0.0 <= sim <= 1.0


def test_match_constellations_mismatched_count_no_crash(
        small_multi_fragment_contours, linear_arrangement_contours):
    """Mismatched contour counts (4 vs 4 here, but different
    arrangements/sizes) produce valid scores — the padding handles count
    differences via consistent sentinel value, no separate metric needed."""
    sig_a, _ = p3c.extract_constellation_signature(small_multi_fragment_contours)
    sig_b, _ = p3c.extract_constellation_signature(linear_arrangement_contours)
    sim = p3c.match_constellations(sig_a, sig_b)
    assert 0.0 <= sim <= 1.0


def test_match_constellations_padding_handles_count_mismatch():
    """3-contour vs 7-contour signatures must produce a valid bounded
    score via the padding sentinels."""
    import cv2

    def make_circles(n, base_x=300):
        out = []
        for i in range(n):
            theta = np.linspace(0, 2 * np.pi, 80, endpoint=False)
            cx, cy = base_x + i * 100, 500
            xs = (cx + 25 * np.cos(theta)).round().astype(np.int32)
            ys = (cy + 25 * np.sin(theta)).round().astype(np.int32)
            out.append(np.stack([xs, ys], axis=1).reshape(-1, 1, 2))
        return out

    sig_3, _ = p3c.extract_constellation_signature(make_circles(3))
    sig_7, _ = p3c.extract_constellation_signature(make_circles(7))
    sim = p3c.match_constellations(sig_3, sig_7)
    assert 0.0 <= sim <= 1.0


# ===========================================================================
# Algorithm router — pre-mortem §3, §5
# ===========================================================================


def test_router_selects_constellation_for_multi_small(small_multi_fragment_contours):
    """Both inputs: 4 contours, mean area ~1500 px → 'constellation'."""
    decision = p3r.route_comparison(small_multi_fragment_contours,
                                    small_multi_fragment_contours)
    assert decision == "constellation"


def test_router_selects_shape_for_single_large(large_solid_contour):
    """Both inputs: 1 contour, large area → 'shape'."""
    decision = p3r.route_comparison(large_solid_contour, large_solid_contour)
    assert decision == "shape"


def test_router_returns_shape_partial_on_1_vs_n(
        large_solid_contour, small_multi_fragment_contours):
    """Pre-mortem §3 critical: 1-vs-N case must surface 'shape_partial'
    — NOT silently route to shape and produce a misleading score."""
    decision = p3r.route_comparison(large_solid_contour, small_multi_fragment_contours)
    assert decision == "shape_partial"
    decision_reverse = p3r.route_comparison(small_multi_fragment_contours,
                                            large_solid_contour)
    assert decision_reverse == "shape_partial"


def test_router_1_vs_1_always_shape():
    """When both sides have exactly 1 contour, regardless of area, always
    route to shape (constellation requires >= 2 fragments)."""
    import cv2
    theta = np.linspace(0, 2 * np.pi, 80, endpoint=False)
    tiny = np.stack([
        (500 + 5 * np.cos(theta)).round().astype(np.int32),
        (500 + 5 * np.sin(theta)).round().astype(np.int32),
    ], axis=1).reshape(-1, 1, 2)
    decision = p3r.route_comparison([tiny], [tiny])
    assert decision == "shape"


def test_router_boundary_deterministic():
    """Repeated hybrid routing calls must agree (deterministic)."""
    import cv2
    theta = np.linspace(0, 2 * np.pi, 80, endpoint=False)
    target_area = p3r.SMALL_FRAGMENT_AREA_PX
    radius = int(np.sqrt(target_area / np.pi))
    contours = []
    for i in range(p3r.MULTI_FRAGMENT_THRESHOLD):
        xs = (500 + i * 200 + radius * np.cos(theta)).round().astype(np.int32)
        ys = (500 + radius * np.sin(theta)).round().astype(np.int32)
        contours.append(np.stack([xs, ys], axis=1).reshape(-1, 1, 2))
    decisions = {p3r.route_comparison(contours, contours) for _ in range(5)}
    assert len(decisions) == 1, f"Non-deterministic routing at boundary: {decisions}"


def test_router_hybrid_lung_metadata_prefers_shape_over_constellation(
        small_multi_fragment_contours):
    """Lung tissue from filename → shape even when contour count is high."""
    decision = p3r.route_comparison_hybrid(
        small_multi_fragment_contours,
        small_multi_fragment_contours,
        tissue_a="lung",
        tissue_b="lung",
        role_a="slide",
        role_b="slide",
    )
    assert decision == "shape"


def test_router_hybrid_esophagus_metadata_prefers_constellation(
        small_multi_fragment_contours):
    decision = p3r.route_comparison_hybrid(
        small_multi_fragment_contours,
        small_multi_fragment_contours,
        tissue_a="esophagus",
        tissue_b="esophagus",
        role_a="slide",
        role_b="slide",
    )
    assert decision == "constellation"


def test_router_hybrid_high_dominance_slide_metrics_prefers_shape():
    """One dominant blob (high max/total) → shape without tissue metadata."""
    import cv2
    theta = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    big = np.stack([
        (800 + 200 * np.cos(theta)).round().astype(np.int32),
        (800 + 200 * np.sin(theta)).round().astype(np.int32),
    ], axis=1).reshape(-1, 1, 2)
    speck = np.stack([
        (200 + 8 * np.cos(theta)).round().astype(np.int32),
        (200 + 8 * np.sin(theta)).round().astype(np.int32),
    ], axis=1).reshape(-1, 1, 2)
    contours = [big, speck]
    decision = p3r.route_comparison_hybrid(
        contours, contours, role_a="slide", role_b="slide",
    )
    assert decision == "shape"


def test_compute_side_metrics_dominance():
    import cv2
    theta = np.linspace(0, 2 * np.pi, 80, endpoint=False)
    big = np.stack([
        (500 + 100 * np.cos(theta)).round().astype(np.int32),
        (500 + 100 * np.sin(theta)).round().astype(np.int32),
    ], axis=1).reshape(-1, 1, 2)
    small = np.stack([
        (700 + 10 * np.cos(theta)).round().astype(np.int32),
        (700 + 10 * np.sin(theta)).round().astype(np.int32),
    ], axis=1).reshape(-1, 1, 2)
    m = p3r.compute_side_metrics([big, small])
    assert m.contour_count == 2
    assert m.dominance > 0.9
    assert m.total_tissue_area > 0


# ===========================================================================
# Label detection — pre-mortem §2, §5
# ===========================================================================


def test_label_detection_finds_realistic_printed_label(
        synthetic_label_with_printed_noise):
    """Pre-mortem §2 critical: detector must work on labels with
    high-frequency printed interior. v1's uniformity criterion would
    have rejected this exact case."""
    result = p3l.detect_label_region(synthetic_label_with_printed_noise)
    assert result.found is True
    # Label rectangle was placed at (80, 60) with size (440, 180).
    x, y, w, h = result.bounding_rect
    assert 60 <= x <= 110
    assert 40 <= y <= 90
    assert 400 <= w <= 480
    assert 150 <= h <= 220


def test_label_detection_rejects_rectangular_tissue(
        synthetic_rectangular_tissue_no_border):
    """Pre-mortem §5: tissue with high bounding-box rectangularity but
    SOFT edges must not be classified as a label. The border-edge density
    criterion is what disambiguates."""
    result = p3l.detect_label_region(synthetic_rectangular_tissue_no_border)
    assert result.found is False, (
        "Soft-edged rectangular tissue must NOT be detected as a label."
    )


def test_label_detection_falls_back_to_top_roi(synthetic_no_rectangle_image):
    """Pre-mortem §5: when no candidate passes, fallback masks the top
    LABEL_FALLBACK_ROI_FRACTION of the image."""
    masked = p3l.apply_label_mask(synthetic_no_rectangle_image)
    h = synthetic_no_rectangle_image.shape[0]
    fallback_rows = int(h * p3l.LABEL_FALLBACK_ROI_FRACTION)
    # The fallback path zeroes the top band on the masked image.
    assert masked[:fallback_rows, :, :].sum() == 0


def test_label_detection_aspect_ratio_constraint_rejects_square():
    """A perfect square (aspect ratio 1.0) must NOT be classified as a
    label — labels are characteristically elongated rectangles."""
    import cv2
    img = np.full((800, 600, 3), 240, dtype=np.uint8)
    cv2.rectangle(img, (200, 200), (400, 400), (255, 255, 255), thickness=-1)
    cv2.rectangle(img, (200, 200), (400, 400), (0, 0, 0), thickness=3)
    result = p3l.detect_label_region(img)
    assert result.found is False


def test_apply_label_mask_returns_zeroed_region(synthetic_label_with_printed_noise):
    """apply_label_mask() must zero the detected region in a COPY,
    leaving the original untouched (pre-mortem discipline — no caller
    array mutation)."""
    original = synthetic_label_with_printed_noise.copy()
    masked = p3l.apply_label_mask(synthetic_label_with_printed_noise)
    # Caller's array unchanged.
    assert np.array_equal(synthetic_label_with_printed_noise, original)
    # Returned image has the label region zeroed.
    # Verify by sampling the label centre.
    cx, cy = 300, 150
    assert masked[cy, cx, :].sum() == 0


# ===========================================================================
# Unified matcher — pre-mortem §3, §5 critical
# ===========================================================================


def test_unified_matcher_self_similarity_shape_branch(large_solid_contour):
    """Pre-mortem §5 critical: self-similarity == 1.0 on the shape branch."""
    # Build a degenerate pool of feature vectors for shape matching.
    feats = np.array([[1.0, 2.0, 3.0]], dtype=float)
    result = p3u.unified_compare(
        contours_a=large_solid_contour, contours_b=large_solid_contour,
        features_a=feats, features_b=feats,
        signature_a=None, signature_b=None,
    )
    assert result.routing_decision == "shape"
    assert result.raw_similarity == pytest.approx(1.0, abs=1e-6)


def test_unified_matcher_self_similarity_constellation_branch(
        small_multi_fragment_contours):
    """Pre-mortem §5 critical: self-similarity == 1.0 on the constellation
    branch."""
    sig, _ = p3c.extract_constellation_signature(small_multi_fragment_contours)
    # Shape features are unused when routed to constellation, but must be
    # non-empty so the function signature isn't degenerate.
    feats = np.zeros((len(small_multi_fragment_contours), 3), dtype=float)
    result = p3u.unified_compare(
        contours_a=small_multi_fragment_contours,
        contours_b=small_multi_fragment_contours,
        features_a=feats, features_b=feats,
        signature_a=sig, signature_b=sig,
    )
    assert result.routing_decision == "constellation"
    assert result.raw_similarity == pytest.approx(1.0, abs=1e-9)


def test_unified_matcher_1_vs_n_emits_routing_uncertain(
        large_solid_contour, small_multi_fragment_contours):
    """Pre-mortem §3 critical: the 'shape_partial' path must set
    routing_uncertain=True AND apply the documented count-mismatch
    penalty rather than producing a silent partial-alignment score."""
    feats_a = np.array([[1.0, 2.0, 3.0]], dtype=float)
    feats_b = np.random.RandomState(0).rand(
        len(small_multi_fragment_contours), 3).astype(float)
    result = p3u.unified_compare(
        contours_a=large_solid_contour, contours_b=small_multi_fragment_contours,
        features_a=feats_a, features_b=feats_b,
        signature_a=None, signature_b=None,
    )
    assert result.routing_decision == "shape_partial"
    assert result.routing_uncertain is True
    assert 0.0 <= result.raw_similarity <= 1.0


def test_per_branch_zscore_normalization():
    """Pre-mortem §3 critical: per-branch z-scoring brings each branch
    onto a common standard-deviation scale. Synthetic input with known
    values yields mean ≈ 0 and std ≈ 1 per branch."""
    raw = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=float)
    branches = np.array(["shape", "shape", "shape", "constellation",
                         "constellation"], dtype=object)
    zscored = p3u.per_branch_zscore(raw, branches)
    shape_mask = branches == "shape"
    const_mask = branches == "constellation"
    assert abs(float(zscored[shape_mask].mean())) < 1e-9
    # std uses default ddof=0; require std ≈ 1 within tolerance.
    assert abs(float(zscored[shape_mask].std()) - 1.0) < 1e-9
    assert abs(float(zscored[const_mask].mean())) < 1e-9
    # Two-element branch has std defined; check it normalizes.
    assert abs(float(zscored[const_mask].std()) - 1.0) < 1e-9


def test_per_branch_zscore_single_sample_branch_returns_zero():
    """A branch with only one sample has undefined std; z-score returns 0
    rather than NaN."""
    raw = np.array([0.5, 0.1, 0.9], dtype=float)
    branches = np.array(["shape", "constellation", "constellation"], dtype=object)
    zscored = p3u.per_branch_zscore(raw, branches)
    shape_mask = branches == "shape"
    assert float(zscored[shape_mask][0]) == 0.0
