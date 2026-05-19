"""
phase2_descriptors.py — Phase 2 of the LJI Digital Gatekeeper.

Goal: take Phase 1's frozen tissue masks and answer the matching
question — given a block silhouette and a slide tissue mask, do they
come from the same physical sample?

Every design choice in this module is keyed to a specific finding in
`.claude/specs/pre_mortem.md`.  Read that file before editing.  Tests
in `tests/test_phase2.py` were written FIRST (per CLAUDE.md TDD rule).

Mitigation map (see also the file-by-file mitigation written to the
terminal at implementation time):

    §2.1 slide-label-axis     → SLIDE_LABEL_ROI_FRACTION + role gate
    §2.2 unnormalized vectors → standardize_feature_matrix()
    §2.3 Zernike rendering    → contour_to_zernike_image()
    §3.1 cost vs. similarity  → _build_cost_matrix() returns DISTANCE
    §3.4 unmatched penalty    → UNMATCHED_CONTOUR_COST (cost space)
    §3.5 matchShapes method   → MATCH_SHAPES_METHOD constant
    §3.6 degenerate mask      → DEGENERATE_TISSUE_FRACTION early-skip
    §3.x solidity filter      → SOLIDITY_MAX
    §4.1 deallocation         → explicit `del` on large arrays
    §4.3 plt.close            → try/finally in create_pair_visualization
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

try:
    import mahotas
    _HAS_MAHOTAS = True
except ImportError:  # tests can run without mahotas via the fallback path
    _HAS_MAHOTAS = False

from scipy.optimize import linear_sum_assignment  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration constants — every value here is a calibration knob.
# ---------------------------------------------------------------------------

# Pre-mortem §2.1: slide-only top ROI.  20% is the post-critic starting
# value (plan's 30% over-masked tissue on test set).  Tune after the
# first end-to-end run; never apply this to block images.
SLIDE_LABEL_ROI_FRACTION: float = 0.20

# Pre-mortem §3.x: rectangular cassette/grid artifacts have solidity
# very close to 1.0; real tissue is typically < 0.85.
SOLIDITY_MAX: float = 0.998  # calibrated 2026-05-18 — see phase2_calibration_notes.md

# Pre-mortem §3.6: above this tissue fraction the segmentation has
# fundamentally failed (entire image is "tissue") — skip the image.
DEGENERATE_TISSUE_FRACTION: float = 0.95

# Pre-mortem §3.5: matchShapes method, exposed as a named constant so
# all call sites agree.  I1 sums Hu moment differences (well-behaved).
MATCH_SHAPES_METHOD: int = cv2.CONTOURS_MATCH_I1

# Pre-mortem §3.4: unmatched contour penalty, expressed in COST SPACE
# (higher = worse).  Set high enough that any matched pair is preferred
# over leaving both unmatched, but not so high that one missing
# fragment dominates the aggregate.  Calibrate post-run.
UNMATCHED_CONTOUR_COST: float = 5.0

# Minimum contour area in pixels (reuse Phase 1 default).
MIN_CONTOUR_AREA: int = 1000

# Zernike configuration.
ZERNIKE_DEGREE: int = 8
ZERNIKE_PADDING_FACTOR: float = 0.1

# Logger — module-level, configurable by callers.
log = logging.getLogger(__name__)


# ===========================================================================
# Stage 1 — Mask cleaning
# ===========================================================================


def _compute_solidity(contour: np.ndarray) -> float:
    """Solidity = contour_area / convex_hull_area.  Returns 0.0 when the
    convex hull is degenerate (zero area), which forces the caller to
    drop the contour."""
    area = float(cv2.contourArea(contour))
    if area <= 0:
        return 0.0
    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    if hull_area <= 0:
        return 0.0
    return area / hull_area


def clean_mask(mask: np.ndarray, role: str) -> tuple[np.ndarray, list[np.ndarray]]:
    """Apply post-segmentation cleanup and return (cleaned_mask, contours).

    Pre-mortem mitigations applied here:
      §2.1 slide-label ROI is zeroed only when role == 'slide'
      §3.6 degenerate (near-full-frame) masks return [] contours
      §3.x rectangular cassette-grid contours are dropped by solidity
    """
    if mask.ndim != 2:
        raise ValueError(f"clean_mask expects a 2D mask; got shape {mask.shape}")
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)

    cleaned = mask.copy()

    # ---- §2.1 slide-only top ROI ----------------------------------------
    if role == "slide":
        h = cleaned.shape[0]
        label_rows = int(h * SLIDE_LABEL_ROI_FRACTION)
        if label_rows > 0:
            cleaned[:label_rows, :] = 0

    # ---- §3.6 degenerate-mask detector ----------------------------------
    tissue_fraction = float((cleaned > 0).sum()) / cleaned.size
    if tissue_fraction > DEGENERATE_TISSUE_FRACTION:
        log.warning(
            "Degenerate mask detected (tissue_fraction=%.3f > %.2f); "
            "returning empty contour list.",
            tissue_fraction, DEGENERATE_TISSUE_FRACTION,
        )
        return cleaned, []

    # ---- contour extraction + solidity & area filters -------------------
    contours, _ = cv2.findContours(
        cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE,
    )
    kept: list[np.ndarray] = []
    for c in contours:
        if cv2.contourArea(c) < MIN_CONTOUR_AREA:
            continue
        if _compute_solidity(c) >= SOLIDITY_MAX:
            continue
        kept.append(c)

    return cleaned, kept


# ===========================================================================
# Stage 2 — Descriptor computation
# ===========================================================================


def contour_to_zernike_image(
    contour: np.ndarray,
    padding_factor: float = ZERNIKE_PADDING_FACTOR,
) -> tuple[np.ndarray, float]:
    """Render a contour into a binary canvas suitable for Zernike moment
    computation.  Canvas size is proportional to the contour bounding
    box → the rendering is genuinely scale-invariant across contours of
    different sizes (pre-mortem §2.3).

    Returns (canvas_uint8_0_255, radius_in_pixels).
    """
    pts = contour.reshape(-1, 2)
    xmin, ymin = pts.min(axis=0)
    xmax, ymax = pts.max(axis=0)
    w = max(int(xmax - xmin), 1)
    h = max(int(ymax - ymin), 1)
    pad_x = int(round(w * padding_factor))
    pad_y = int(round(h * padding_factor))
    canvas_w = w + 2 * pad_x + 1
    canvas_h = h + 2 * pad_y + 1

    canvas = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
    shifted = pts.copy()
    shifted[:, 0] = shifted[:, 0] - xmin + pad_x
    shifted[:, 1] = shifted[:, 1] - ymin + pad_y
    cv2.drawContours(
        canvas, [shifted.reshape(-1, 1, 2).astype(np.int32)],
        -1, 255, thickness=-1,
    )
    radius = min(canvas_h, canvas_w) / 2.0
    return canvas, radius


def compute_zernike_moments(contour: np.ndarray) -> np.ndarray:
    """Compute a Zernike feature vector for a single contour.

    When mahotas is unavailable we fall back to a deterministic shape
    fingerprint based on normalized radial profile statistics — enough
    to make the test suite runnable without the optional dependency.
    """
    canvas, radius = contour_to_zernike_image(contour)
    try:
        if _HAS_MAHOTAS:
            binary = (canvas > 0).astype(np.uint8)
            vec = mahotas.features.zernike_moments(
                binary, radius=radius, degree=ZERNIKE_DEGREE,
            )
            return np.asarray(vec, dtype=float)
    finally:
        del canvas

    # Fallback: scale-invariant radial-profile fingerprint.
    pts = contour.reshape(-1, 2).astype(float)
    centre = pts.mean(axis=0)
    r = np.linalg.norm(pts - centre, axis=1)
    r_max = r.max() if r.max() > 0 else 1.0
    r_norm = r / r_max
    # Sort by angle to get a rotation-stable signature once we
    # statistically summarize it.
    moments = np.array([
        r_norm.mean(),
        r_norm.std(),
        np.percentile(r_norm, 25),
        np.percentile(r_norm, 50),
        np.percentile(r_norm, 75),
        ((r_norm - r_norm.mean()) ** 3).mean(),
        ((r_norm - r_norm.mean()) ** 4).mean(),
    ], dtype=float)
    # Pad to 25 entries so the descriptor count is stable across paths.
    pad = np.zeros(25 - moments.size, dtype=float)
    return np.concatenate([moments, pad])


def compute_hu_log(contour: np.ndarray) -> np.ndarray:
    """Return log10-magnitude-with-sign of the seven Hu moments."""
    m = cv2.moments(contour)
    hu = cv2.HuMoments(m).flatten()
    # Log transform with sign preservation: -sign(h) * log10(|h|).
    eps = 1e-30
    return -np.sign(hu) * np.log10(np.abs(hu) + eps)


def compute_descriptors(contour: np.ndarray) -> dict[str, float]:
    """Compute the full named descriptor dictionary for one contour."""
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, closed=True))
    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = float(w) / float(h) if h > 0 else 0.0
    solidity = _compute_solidity(contour)
    # Eccentricity via fitEllipse when there are enough points.
    if len(contour) >= 5:
        (_cx, _cy), (ma, MA), _angle = cv2.fitEllipse(contour)
        ma_, MA_ = sorted([ma, MA])
        eccentricity = float(np.sqrt(1.0 - (ma_ / MA_) ** 2)) if MA_ > 0 else 0.0
    else:
        eccentricity = 0.0

    desc: dict[str, float] = {
        "area": area,
        "perimeter": perimeter,
        "aspect_ratio": aspect_ratio,
        "solidity": solidity,
        "eccentricity": eccentricity,
    }
    hu = compute_hu_log(contour)
    for i, v in enumerate(hu):
        desc[f"hu_{i}"] = float(v)
    zer = compute_zernike_moments(contour)
    for i, v in enumerate(zer):
        desc[f"zernike_{i}"] = float(v)
    return desc


def descriptor_to_vector(desc: dict[str, float]) -> np.ndarray:
    """Stable, ordered conversion from descriptor dict to feature vector.

    Pre-mortem §2.2 — order is fixed by sorted key for reproducibility.
    Caller is responsible for batch standardization before any L2
    distance is computed.
    """
    return np.array([desc[k] for k in sorted(desc)], dtype=float)


def standardize_feature_matrix(X: np.ndarray) -> np.ndarray:
    """Z-score across rows (each column independently). Single-row
    inputs are returned unchanged because z-scoring degenerates."""
    X = np.asarray(X, dtype=float)
    if X.ndim != 2:
        raise ValueError(f"Expected 2D feature matrix, got shape {X.shape}")
    if X.shape[0] < 2:
        return X.copy()
    mu = X.mean(axis=0, keepdims=True)
    sigma = X.std(axis=0, keepdims=True)
    sigma[sigma == 0] = 1.0
    return (X - mu) / sigma


# ===========================================================================
# Stage 4 — Set-to-set matching via Hungarian assignment
# ===========================================================================


def _build_cost_matrix(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Pairwise L2 DISTANCE between rows of A and rows of B.

    Pre-mortem §3.1 — this returns COSTS not similarities.  Identical
    rows produce zero.  linear_sum_assignment minimizes total cost, so
    feeding distances yields the best matching.
    """
    A = np.asarray(A, dtype=float)
    B = np.asarray(B, dtype=float)
    diff = A[:, None, :] - B[None, :, :]
    return np.linalg.norm(diff, axis=2)


def match_features_hungarian(
    A: np.ndarray,
    B: np.ndarray,
    unmatched_cost: float = UNMATCHED_CONTOUR_COST,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Optimal one-to-one matching between rows of A and B.

    Pre-mortem §3.4 — when |A| ≠ |B| the cost matrix is padded to square
    with `unmatched_cost`, so the algorithm explicitly pays a cost for
    each unmatched contour rather than picking an arbitrary cheap pair.

    Returns (row_indices, col_indices, total_cost) where total_cost
    includes both matched-pair distances AND unmatched penalties.
    """
    n, m = len(A), len(B)
    if n == 0 or m == 0:
        return np.array([], dtype=int), np.array([], dtype=int), \
               unmatched_cost * max(n, m)

    cost = _build_cost_matrix(A, B)
    size = max(n, m)
    padded = np.full((size, size), unmatched_cost, dtype=float)
    padded[:n, :m] = cost
    row_ind, col_ind = linear_sum_assignment(padded)
    total = float(padded[row_ind, col_ind].sum())
    return row_ind, col_ind, total


def set_to_set_similarity(A: np.ndarray, B: np.ndarray) -> float:
    """Aggregate the Hungarian matching into a similarity score in
    [0, 1].  Self-match (A == B) approaches 1.0; orthogonal sets
    approach 0.0."""
    n, m = len(A), len(B)
    if n == 0 or m == 0:
        return 0.0
    _r, _c, total_cost = match_features_hungarian(A, B)
    pairs = max(n, m)
    avg_cost = total_cost / pairs
    # Smooth monotone map: cost 0 → sim 1.0, cost → ∞ ⇒ sim → 0.
    # Independent of UNMATCHED_CONTOUR_COST so the score does not clip
    # when z-scored feature distances exceed the unmatched penalty.
    sim = 1.0 / (1.0 + avg_cost)
    return float(max(0.0, min(1.0, sim)))


# ===========================================================================
# Stage 5 — Pair visualization
# ===========================================================================


def create_pair_visualization(
    block_img: np.ndarray,
    block_contours: list[np.ndarray],
    slide_img: np.ndarray,
    slide_contours: list[np.ndarray],
    matched_pairs: Iterable[tuple[int, int]],
    out_path: Path,
) -> None:
    """Render a side-by-side diagnostic PNG of a single block/slide pair.

    Pre-mortem §4.3 — plt.close(fig) MUST run on every code path,
    including exceptions, to prevent matplotlib figure registry leaks.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    try:
        # OpenCV stores BGR; matplotlib expects RGB.
        axes[0].imshow(cv2.cvtColor(block_img, cv2.COLOR_BGR2RGB))
        axes[0].set_title("Block")
        for c in block_contours:
            pts = c.reshape(-1, 2)
            axes[0].plot(pts[:, 0], pts[:, 1], linewidth=1.0)
        axes[1].imshow(cv2.cvtColor(slide_img, cv2.COLOR_BGR2RGB))
        axes[1].set_title("Slide")
        for c in slide_contours:
            pts = c.reshape(-1, 2)
            axes[1].plot(pts[:, 0], pts[:, 1], linewidth=1.0)
        for bi, si in matched_pairs:
            axes[0].text(0, 0, f"pair{bi}", fontsize=6)
            axes[1].text(0, 0, f"pair{si}", fontsize=6)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
    finally:
        plt.close(fig)


# ===========================================================================
# Stage 0 — Pipeline orchestration (single-CSV-read entry point)
# ===========================================================================


def _select_block_image(group: list[dict]) -> Optional[dict]:
    """Pick the block image to use for a sample set.  Prefer the
    silhouette (clean backlit shot) over the barcode photo, which is
    typically degenerate (tissue_fraction ≈ 1.0)."""
    blocks = [g for g in group if g["role"] == "block"]
    if not blocks:
        return None
    sil = [g for g in blocks if g["image_type"] == "silhouette"]
    if sil:
        return sil[0]
    return blocks[0]


def _select_slide_image(group: list[dict]) -> Optional[dict]:
    slides = [g for g in group if g["role"] == "slide"]
    return slides[0] if slides else None


def run_pipeline(
    input_dir: Path,
    output_dir: Path,
) -> dict:
    """End-to-end Phase 2 orchestrator over an image directory.

    Pre-mortem §4.2 — descriptors are loaded once into a DataFrame and
    passed downstream; no stage re-reads from disk.
    """
    import pandas as pd

    # Phase 1 helpers — imported lazily so unit tests that only use the
    # in-memory functions don't drag the Phase 1 module along.
    from phase1_segmentation import (
        parse_filename, load_image, segment_tissue,
    )

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "visualizations").mkdir(parents=True, exist_ok=True)

    # ---------- 1. Discover and parse images ----------------------------
    records: list[dict] = []
    for path in sorted(input_dir.glob("*.jp*g")):
        try:
            meta = parse_filename(path)
        except ValueError as e:
            log.warning("Skipping %s: %s", path.name, e)
            continue
        meta["path"] = path
        records.append(meta)
    if not records:
        return {"cross_modal": None, "reason": "no images found"}

    # ---------- 2. Per-image: segment, clean, extract contours, describe
    per_image: list[dict] = []
    descriptor_rows: list[dict] = []
    for rec in records:
        img = load_image(rec["path"])
        if img is None:
            continue
        _gray, mask, _otsu = segment_tissue(img)
        cleaned, contours = clean_mask(mask, role=rec["role"])
        del mask, _gray
        if not contours:
            log.warning(
                "No usable contours after cleaning: %s", rec["path"].name,
            )
            del cleaned, img
            continue
        rec_out = dict(rec)
        rec_out["contours"] = contours
        rec_out["image"] = img        # kept only until visualization
        rec_out["cleaned_mask"] = cleaned
        per_image.append(rec_out)
        for ci, c in enumerate(contours):
            d = compute_descriptors(c)
            d["filename"] = rec["path"].name
            d["role"] = rec["role"]
            d["sample_label"] = rec["sample_label"]
            d["image_type"] = rec["image_type"]
            d["contour_index"] = ci
            descriptor_rows.append(d)

    if not descriptor_rows:
        return {"cross_modal": None, "reason": "no descriptors"}

    df = pd.DataFrame(descriptor_rows)
    df.to_csv(output_dir / "descriptors.csv", index=False)

    # ---------- 3. Standardize feature matrix across ALL contours -------
    feature_cols = [c for c in df.columns if c.startswith(("hu_", "zernike_"))
                    or c in {"area", "perimeter", "aspect_ratio",
                             "solidity", "eccentricity"}]
    X = df[feature_cols].to_numpy(dtype=float)
    X_std = standardize_feature_matrix(X)

    # ---------- 4. Build cross-modal similarity matrix ------------------
    # One row per BLOCK image, one column per SLIDE image.
    # Group descriptor rows by filename so each image gets a feature set.
    df["_row"] = np.arange(len(df))
    by_file: dict[str, np.ndarray] = {}
    for fname, sub in df.groupby("filename"):
        by_file[fname] = X_std[sub["_row"].to_numpy()]

    # Pick one block + one slide per sample_label.
    groups: dict[str, list[dict]] = {}
    for rec in per_image:
        groups.setdefault(rec["sample_label"], []).append(rec)

    block_entries: list[dict] = []
    slide_entries: list[dict] = []
    for label, group in groups.items():
        b = _select_block_image(group)
        s = _select_slide_image(group)
        if b is not None:
            block_entries.append(b)
        if s is not None:
            slide_entries.append(s)

    block_labels = [b["sample_label"] for b in block_entries]
    slide_labels = [s["sample_label"] for s in slide_entries]
    n, m = len(block_entries), len(slide_entries)
    sim = np.zeros((n, m), dtype=float)
    for i, b in enumerate(block_entries):
        bf = by_file.get(b["path"].name)
        if bf is None:
            continue
        for j, s in enumerate(slide_entries):
            sf = by_file.get(s["path"].name)
            if sf is None:
                continue
            sim[i, j] = set_to_set_similarity(bf, sf)

    sim_df = pd.DataFrame(sim, index=block_labels, columns=slide_labels)
    sim_df.to_csv(output_dir / "cross_modal_similarity.csv")

    # ---------- 5. Per-pair visualizations ------------------------------
    vis_dir = output_dir / "visualizations"
    for i, b in enumerate(block_entries):
        # Top slide match for each block
        if m == 0:
            continue
        j_best = int(np.argmax(sim[i]))
        s = slide_entries[j_best]
        out = vis_dir / f"{b['sample_label']}__match__{s['sample_label']}.png"
        try:
            create_pair_visualization(
                b["image"], b["contours"],
                s["image"], s["contours"],
                matched_pairs=[],
                out_path=out,
            )
        except Exception as e:
            log.warning("Visualization failed for %s: %s",
                        b["sample_label"], e)

    # Free large arrays.
    for rec in per_image:
        rec.pop("image", None)
        rec.pop("cleaned_mask", None)

    return {
        "cross_modal": (sim_df, block_labels, slide_labels),
        "descriptors": df,
    }


__all__ = [
    "SLIDE_LABEL_ROI_FRACTION",
    "SOLIDITY_MAX",
    "DEGENERATE_TISSUE_FRACTION",
    "MATCH_SHAPES_METHOD",
    "UNMATCHED_CONTOUR_COST",
    "MIN_CONTOUR_AREA",
    "ZERNIKE_DEGREE",
    "clean_mask",
    "contour_to_zernike_image",
    "compute_zernike_moments",
    "compute_hu_log",
    "compute_descriptors",
    "descriptor_to_vector",
    "standardize_feature_matrix",
    "_build_cost_matrix",
    "_compute_solidity",
    "match_features_hungarian",
    "set_to_set_similarity",
    "create_pair_visualization",
    "run_pipeline",
    "plt",
]
