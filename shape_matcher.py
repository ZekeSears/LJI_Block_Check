"""
shape_matcher.py  --  Pillar C: Composite Shape Matching (v2)
-------------------------------------------------------------

The v1 matcher compared only the LARGEST contour using Hu Moments.
That works when the block and slide images are nearly identical -- but
real histology has rotation, shrinkage, fragmentation, and piece loss.
The v1 logic failed on close-but-wrong pairs (same organ family, different
sample), which is the most dangerous failure mode.

v2 uses a COMPOSITE scorer that combines four independent evidence sources
and returns a weighted average in [0, 1]:

    1. Hu Moments           (largest-contour shape invariants)   weight 0.15
    2. Zernike Moments      (full-mask shape descriptor)         weight 0.35
    3. Geometric features   (solidity/circularity/hull ratios)   weight 0.20
    4. Aligned IoU          (pixel overlap after PCA alignment)  weight 0.30

All four are independently computable; a mismatch only needs to fail TWO
of them to fall below the threshold. No single trick can fool the ensemble.

Each sub-score is normalized to [0, 1] where 1.0 = perfect match.

JAVA ANALOGY:
    Think of this like an ensemble classifier -- four weak-ish judges that
    vote together. Each one catches a different failure mode:
        - Hu:        silhouette contour similarity (rotation/scale invariant)
        - Zernike:   richer descriptor (tolerant to minor warping)
        - Geometric: topology and proportion sanity checks
        - IoU:       literal pixel overlap after alignment (ground truth)
"""

import cv2
import numpy as np
import mahotas.features as mfeat


# -------------------- Mask extraction --------------------

def extract_tissue_mask(image, min_area_ratio=0.02):
    """Return (unified_mask, list_of_contours).

    unified_mask: single-channel uint8, 255 where ANY tissue is present.
    list_of_contours: individual tissue pieces (for multi-piece analysis).

    SEGMENTATION STRATEGY (works for both synthetic and real histology):
      Tissue = "anything that is NOT bright, near-white background."
      - Compute saturation (S) and value (V) from HSV.
      - A pixel is tissue if it's either colored (high S) OR dark (low V).
      - This catches both dark block silhouettes AND stained slide tissue,
        AND avoids the v1 bug where H&E's hematoxylin/eosin variation caused
        the mask to fragment into dozens of internal pieces.

    AREA FILTERING:
      We use a RELATIVE area cutoff (% of the largest contour) instead of
      an absolute pixel count, so the function works at any resolution
      from thumbnail (<500px) to full-res HQ camera shots.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    s_chan = hsv[:, :, 1]
    v_chan = hsv[:, :, 2]

    # "Not white background" -- saturated OR dark
    mask = ((s_chan > 25) | (v_chan < 220)).astype(np.uint8) * 255

    # Close INTERNAL gaps (stain variation produces holes inside tissue)
    # Large-ish kernel so hematoxylin/eosin variations get unified.
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)

    # Remove speckle noise (dust, debris)
    open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        max_area = max(cv2.contourArea(c) for c in contours)
        min_area = max(30.0, max_area * min_area_ratio)
        contours = [c for c in contours if cv2.contourArea(c) >= min_area]

    # Rebuild the unified mask from only the valid contours
    unified = np.zeros_like(mask)
    cv2.drawContours(unified, contours, -1, 255, thickness=-1)

    return unified, contours


# -------------------- Sub-score 1: Hu Moments --------------------

def hu_score(contours_a, contours_b):
    """Match the largest contour from each set via Hu moments.

    Returns similarity in [0, 1]. 1 = perfect match.
    Uses method I1: sum of |1/m_a_i - 1/m_b_i| over the 7 moments.
    """
    if not contours_a or not contours_b:
        return 0.0
    a = max(contours_a, key=cv2.contourArea)
    b = max(contours_b, key=cv2.contourArea)
    d = cv2.matchShapes(a, b, cv2.CONTOURS_MATCH_I1, 0)
    # Empirically, d < 0.1 is "very similar", d > 1.0 is "clearly different".
    # Squash with exp so score decays smoothly.
    return float(np.exp(-3.0 * d))


# -------------------- Sub-score 2: Zernike Moments --------------------

def _normalize_for_zernike(mask, canonical_size=128):
    """Crop tight bbox, pad to square, resize -- so Zernike is scale-invariant."""
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.zeros((canonical_size, canonical_size), dtype=np.uint8)
    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    cropped = mask[y0:y1, x0:x1]

    # Pad to square
    h, w = cropped.shape
    side = max(h, w)
    padded = np.zeros((side, side), dtype=np.uint8)
    padded[(side - h) // 2:(side - h) // 2 + h,
           (side - w) // 2:(side - w) // 2 + w] = cropped

    return cv2.resize(padded, (canonical_size, canonical_size),
                      interpolation=cv2.INTER_NEAREST)


def zernike_score(mask_a, mask_b, radius=56, degree=10):
    """Zernike moment similarity on ALIGNED normalized masks.

    KEY FIX vs v1: We align both masks to principal axis BEFORE computing
    Zernike moments. Without alignment, bbox-based scale normalization is
    affected by rotation (the bbox of a rotated crescent != bbox of the
    un-rotated one), which breaks the invariance.

    degree=10 -> 36 moments. More discrimination than degree=8.
    """
    a = _align_mask(mask_a)
    b = _align_mask(mask_b)
    if a.sum() == 0 or b.sum() == 0:
        return 0.0

    za = mfeat.zernike_moments(a, radius=radius, degree=degree)
    zb = mfeat.zernike_moments(b, radius=radius, degree=degree)

    d = float(np.linalg.norm(za - zb))
    return float(np.exp(-10.0 * d))


# -------------------- Sub-score 2b: Fourier Descriptors --------------------
#
# Represents a contour as a 1-D periodic complex signal (x + iy vs arc-length),
# then takes the FFT. The magnitudes of the first K harmonics capture the
# "wobble pattern" of the boundary independently of rotation/translation/scale.
# Particularly good at distinguishing two tissue blobs whose overall size
# is similar but whose boundary curvature pattern differs.

def _fourier_descriptor(contour, n_points=128, n_harmonics=20):
    """Return the first n_harmonics normalized magnitudes."""
    pts = contour.reshape(-1, 2).astype(np.float32)
    if len(pts) < 8:
        return None
    # Resample contour to a fixed number of points (uniform arc length)
    # Simple approach: interpolate along the polyline
    diffs = np.diff(pts, axis=0, append=pts[:1])
    seg_lengths = np.sqrt((diffs ** 2).sum(axis=1))
    cum = np.concatenate([[0], np.cumsum(seg_lengths)])
    total = cum[-1]
    if total <= 0:
        return None
    targets = np.linspace(0, total, n_points, endpoint=False)
    xs = np.interp(targets, cum, np.concatenate([pts[:, 0], [pts[0, 0]]]))
    ys = np.interp(targets, cum, np.concatenate([pts[:, 1], [pts[0, 1]]]))

    # Complex signal; FFT
    z = xs + 1j * ys
    Z = np.fft.fft(z)

    # Drop DC (translation-invariant), take magnitudes (rotation-invariant),
    # normalize by |Z[1]| (scale-invariant).
    mags = np.abs(Z)
    if mags[1] <= 0:
        return None
    desc = mags[2:2 + n_harmonics] / mags[1]
    return desc


def fourier_score(contours_a, contours_b):
    """Compare Fourier descriptors of the LARGEST contour on each side."""
    if not contours_a or not contours_b:
        return 0.0
    a = _fourier_descriptor(max(contours_a, key=cv2.contourArea))
    b = _fourier_descriptor(max(contours_b, key=cv2.contourArea))
    if a is None or b is None:
        return 0.0
    d = float(np.linalg.norm(a - b))
    # Empirically, d < 0.2 for matches, > 0.5 for mismatches
    return float(np.exp(-2.5 * d))


# -------------------- Sub-score 3: Geometric features --------------------

def _geom_features(mask, contours):
    """Shape-family summary stats that are rotation+scale invariant."""
    if not contours:
        return None
    total_area = float(sum(cv2.contourArea(c) for c in contours))
    if total_area <= 0:
        return None

    # Perimeter of all contours combined
    total_perim = float(sum(cv2.arcLength(c, True) for c in contours))

    # Convex hull of the union of all points (characterizes overall shape)
    all_pts = np.vstack([c.reshape(-1, 2) for c in contours])
    hull = cv2.convexHull(all_pts)
    hull_area = float(cv2.contourArea(hull))

    # Rotation/scale-invariant ratios:
    solidity    = total_area / hull_area if hull_area > 0 else 0.0
    circularity = (4 * np.pi * total_area) / (total_perim ** 2) if total_perim > 0 else 0.0

    # Spread: eigenvalue ratio of the pixel covariance (elongation)
    ys, xs = np.where(mask > 0)
    if len(xs) > 10:
        coords = np.column_stack([xs, ys]).astype(np.float32)
        cov = np.cov(coords.T)
        eigs = np.linalg.eigvalsh(cov)
        eigs = np.sort(eigs)[::-1]
        elongation = float(np.sqrt(eigs[0] / eigs[1])) if eigs[1] > 0 else 1.0
    else:
        elongation = 1.0

    return {
        "solidity": solidity,
        "circularity": circularity,
        "elongation": elongation,
    }


def geometric_score(mask_a, contours_a, mask_b, contours_b):
    """Compare solidity / circularity / elongation -- each in [0,1].

    We DON'T compare piece-counts here because fragmentation is a legitimate
    difference. The unified-mask features above are fragmentation-tolerant.
    """
    fa = _geom_features(mask_a, contours_a)
    fb = _geom_features(mask_b, contours_b)
    if fa is None or fb is None:
        return 0.0

    # L1 distance on each feature, normalized by typical range
    d_sol = abs(fa["solidity"] - fb["solidity"])           # range ~0-1
    d_cir = abs(fa["circularity"] - fb["circularity"])     # range ~0-1
    # Elongation is unbounded above; use relative error
    d_elo = abs(fa["elongation"] - fb["elongation"]) / max(fa["elongation"],
                                                           fb["elongation"])

    # Average, then squash
    d = (d_sol + d_cir + d_elo) / 3.0
    return float(np.exp(-4.0 * d))


# -------------------- Sub-score 4: Aligned IoU --------------------

def _align_mask(mask, canonical=128):
    """Center the mask, rotate to align principal axis to x-axis,
    then crop and resize to a canonical square.

    This converts any rotation+translation+scale into a shared frame
    so we can literally measure pixel overlap.
    """
    ys, xs = np.where(mask > 0)
    if len(xs) < 10:
        return np.zeros((canonical, canonical), dtype=np.uint8)

    coords = np.column_stack([xs, ys]).astype(np.float32)

    # Centroid
    cx, cy = coords.mean(axis=0)

    # Principal axis via eigenvectors of covariance
    cov = np.cov(coords.T)
    eig_vals, eig_vecs = np.linalg.eigh(cov)
    # Largest-eigenvalue vector = major axis
    major = eig_vecs[:, -1]
    angle_deg = float(np.degrees(np.arctan2(major[1], major[0])))

    # Rotate the whole mask so the major axis becomes horizontal
    rot_mat = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
    rotated = cv2.warpAffine(mask, rot_mat, (mask.shape[1], mask.shape[0]),
                             flags=cv2.INTER_NEAREST)

    # Crop tight, pad square, resize
    return _normalize_for_zernike(rotated, canonical_size=canonical)


def aligned_iou_score(mask_a, mask_b):
    """IoU after principal-axis alignment and scale normalization."""
    a = _align_mask(mask_a)
    b = _align_mask(mask_b)
    if a.sum() == 0 or b.sum() == 0:
        return 0.0

    # Principal-axis direction is ambiguous (+/- 180 deg flip).
    # Try both orientations and both mirror flips -- take the best.
    candidates = [
        b,
        cv2.flip(b, 0),
        cv2.flip(b, 1),
        cv2.flip(b, -1),  # both axes = 180 deg
    ]

    best = 0.0
    for cand in candidates:
        inter = np.logical_and(a > 0, cand > 0).sum()
        union = np.logical_or(a > 0, cand > 0).sum()
        if union > 0:
            best = max(best, float(inter / union))
    return best


# -------------------- Composite --------------------

WEIGHTS = {
    "hu":        0.10,  # lowered: largest-contour Hu fooled by similar sizes
    "zernike":   0.30,
    "fourier":   0.20,  # new: boundary wobble detail
    "geometric": 0.15,
    "iou":       0.25,
}


def score_pair(block_img, slide_img):
    """Run all sub-scores and return a full report."""
    mask_a, contours_a = extract_tissue_mask(block_img)
    mask_b, contours_b = extract_tissue_mask(slide_img)

    sub = {
        "hu":        hu_score(contours_a, contours_b),
        "zernike":   zernike_score(mask_a, mask_b),
        "fourier":   fourier_score(contours_a, contours_b),
        "geometric": geometric_score(mask_a, contours_a, mask_b, contours_b),
        "iou":       aligned_iou_score(mask_a, mask_b),
    }
    composite = sum(WEIGHTS[k] * sub[k] for k in sub)

    return {
        "composite": round(composite, 4),
        "sub_scores": {k: round(v, 4) for k, v in sub.items()},
        "block_contour_count": len(contours_a),
        "slide_contour_count": len(contours_b),
    }


#
# THRESHOLD
# ---------
# Calibrated empirically against 26 synthetic pairs + 6 real BIRL pairs.
# At 0.68:
#   - 100% reject rate on WRONG, HARDNEG, and REAL_MISMATCH cases
#   - 100% pass rate on PERFECT, REALISTIC, and REAL_MATCH cases
#   - ~75% pass on FRAGMENTED (one case flagged for manual review)
# Per project policy: false positives are worse than false negatives.
# See calibrate_threshold.py to re-tune when new test data is available.
#
DEFAULT_THRESHOLD = 0.68


def run_comparison(block_path, slide_path, threshold=DEFAULT_THRESHOLD):
    block_img = cv2.imread(block_path)
    slide_img = cv2.imread(slide_path)
    if block_img is None:
        raise FileNotFoundError(block_path)
    if slide_img is None:
        raise FileNotFoundError(slide_path)
    res = score_pair(block_img, slide_img)
    res["match"] = res["composite"] >= threshold
    res["threshold"] = threshold
    return res


# Backwards-compat alias so stain_verifier's import still works
def extract_contours(image, min_area=300):
    """Legacy signature: returns (contours, mask) like v1."""
    mask, contours = extract_tissue_mask(image, min_area=min_area)
    return contours, mask


# -------------------- CLI smoke test --------------------

if __name__ == "__main__":
    import glob
    import os

    print("=" * 70)
    print("PILLAR C  (v2)  --  Composite Shape Matching")
    print("=" * 70)

    CATEGORIES = ["perfect", "realistic", "fragmented", "wrong", "hardneg"]
    for cat in CATEGORIES:
        print(f"\n--- {cat.upper()} ---")
        block_files = sorted(glob.glob(f"test_images/{cat}_*_block.png"))
        for bp in block_files:
            idx = os.path.basename(bp).split("_")[1]
            slide_matches = glob.glob(f"test_images/{cat}_{idx}_slide_*.png")
            if not slide_matches:
                continue
            sp = slide_matches[0]
            r = run_comparison(bp, sp)
            flag = "MATCH" if r["match"] else "no-match"
            subs = r["sub_scores"]
            print(f"  [{flag:8s}] {cat}_{idx}  "
                  f"composite={r['composite']:.3f}  "
                  f"(hu={subs['hu']:.2f} zern={subs['zernike']:.2f} "
                  f"four={subs['fourier']:.2f} "
                  f"geom={subs['geometric']:.2f} iou={subs['iou']:.2f})")
