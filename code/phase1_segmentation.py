"""
phase1_segmentation.py — Phase 1 of the LJI Digital Gatekeeper.

Goal: validate that Otsu thresholding can isolate tissue from a flat
backlit background on real iPhone sample images.  Produces a 4-panel
diagnostic PNG per input image plus a single CSV of per-image metrics.

Functions segment_tissue() and extract_contours() have FROZEN SIGNATURES
— Phase 2 (shape matching) imports them unchanged.

Every design decision below is keyed to either the proposed plan
(.claude/specs/proposed_plan.md) or the pre-mortem
(.claude/specs/pre_mortem.md).  Read those before modifying this file.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

import cv2
import matplotlib  # noqa: E402  (must call .use() before importing pyplot)
matplotlib.use("Agg")  # headless: required so the script runs without a display
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

INPUT_DIR = Path("./iPhone_test_images/")
OUTPUT_DIR = Path("./phase1_outputs/")
VISUALIZATION_SUBDIR = "visualizations"
METRICS_FILENAME = "segmentation_metrics.csv"

MIN_CONTOUR_AREA = 1000           # px; tune after Phase 1 review
# Pre-mortem §3.1 — 5x5 is provisional; cassette grid holes at iPhone
# resolution may be much larger.  Configurable so tuning doesn't require
# editing the segmentation function body.
MORPH_KERNEL_SIZE = 5

KNOWN_STAINS = {"HE", "MT", "PAS", "PSRFG", "SMA"}
KNOWN_ROLES = {"block", "slide", "reference"}

# ---------------------------------------------------------------------------
# Set metadata — read manually from slide/block barcode labels.
# Maps the set prefix (e.g. "set_01") to the real sample identity so
# every file in a set (slide, block silhouette, block barcode) shares the
# correct sample_label and stain.
# ---------------------------------------------------------------------------
SET_METADATA = {
    "set_01": {
        "sample_label": "TWKOB5_lungs",
        "stain": "MT",
        "wo": "7842",
        "block_id": "",       # set 01 has no barcode image
    },
    "set_02": {
        "sample_label": "WT3_lungs",
        "stain": "HE",
        "wo": "7842",
        "block_id": "1382",
    },
    "set_03": {
        "sample_label": "TWKO4_esophagus",
        "stain": "HE",
        "wo": "7842",
        "block_id": "1377",
    },
    "set_04": {
        "sample_label": "WT2_lungs",
        "stain": "HE",
        "wo": "7842",
        "block_id": "1381",
    },
    "set_05": {
        "sample_label": "WT5_esophagus",
        "stain": "HE",
        "wo": "7842",
        "block_id": "1373",
    },
    "set_06": {
        "sample_label": "TWKO5_lungs",
        "stain": "SMA",
        "wo": "7842",
        "block_id": "1389",
    },
}

OTSU_LOW_WARN = 10                # warn if Otsu picks below this
OTSU_HIGH_WARN = 245              # warn if Otsu picks above this
HEURISTIC_FRACTION_UPPER = 0.5    # tissue_fraction PASS upper bound (inclusive)
# Absolute floor; the adaptive lower bound used at runtime is
#     max(HEURISTIC_FRACTION_FLOOR, MIN_CONTOUR_AREA / total_pixels)
HEURISTIC_FRACTION_FLOOR = 0.0005

VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

CSV_COLUMNS = [
    "filename", "role", "image_type", "sample_label", "stain",
    "image_width_px", "image_height_px",
    "otsu_threshold",
    "num_contours_total", "num_contours_filtered",
    "total_tissue_area_px",
    "largest_contour_area_px", "smallest_contour_area_px",
    "mean_contour_area_px",
    "tissue_fraction", "success_heuristic",
]

# Module-level logger configured by main(); silent by default so imports
# in tests don't spam stderr.
logger = logging.getLogger("phase1")


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

def parse_filename(filepath: Path) -> dict:
    """Extract {role, sample_label, stain, is_reference, image_type}
    from a filename.

    Supports two naming conventions:

    Convention A (plan §3.2, original):
        <prefix>_<role>_<sample_label>[_<stain>].<ext>
        Example: IMG_3084_block_WT5_lungs.jpg
                 IMG_3084_slide_WT5_lungs_HE.jpg

    Convention B (cropped set pairs):
        <set_id>_<role>[_<detail>].<ext>
        Example: set_01_block_silhouette.jpeg  (block on backlight)
                 set_01_slide.jpeg             (slide on backlight)
                 set_02_block_barcode.jpeg     (block barcode photo)

    For convention B files whose prefix matches SET_METADATA, the real
    sample_label and stain are pulled from the metadata table so all
    files in a set share the correct identity.

    image_type is one of: "silhouette", "barcode", "slide", "block".
    """
    stem = filepath.stem
    if not stem:
        raise ValueError(f"Empty filename stem: {filepath!r}")

    parts = stem.split("_")
    if len(parts) < 3:
        raise ValueError(
            f"Filename does not match expected naming "
            f"convention: {filepath.name!r}"
        )

    # Locate the role segment.  Scan left-to-right; first match wins.
    role_idx: Optional[int] = None
    for i, seg in enumerate(parts):
        if seg in KNOWN_ROLES:
            role_idx = i
            break
    if role_idx is None or role_idx == 0:
        raise ValueError(
            f"No recognised role segment in {filepath.name!r}; "
            f"expected one of {sorted(KNOWN_ROLES)} after a prefix."
        )

    role = parts[role_idx]
    prefix = "_".join(parts[:role_idx])   # e.g. "set_01" or "IMG_3084"
    remainder = parts[role_idx + 1:]      # everything after the role

    # Detect image type from suffix keywords.
    image_type = role  # default: "block", "slide", or "reference"
    if remainder and remainder[0].lower() == "barcode":
        image_type = "barcode"
        remainder = remainder[1:]
    elif remainder and remainder[0].lower() == "silhouette":
        image_type = "silhouette"
        remainder = remainder[1:]

    # --- Convention B: look up real identity from SET_METADATA ---
    if prefix in SET_METADATA:
        meta = SET_METADATA[prefix]
        return {
            "role": role,
            "sample_label": meta["sample_label"],
            "stain": meta["stain"],
            "is_reference": (role == "reference"),
            "image_type": image_type,
        }

    # --- Convention A: parse sample_label and stain from filename ---
    stain = ""
    if remainder and remainder[-1] in KNOWN_STAINS:
        stain = remainder[-1]
        remainder = remainder[:-1]

    if remainder:
        sample_label = "_".join(remainder)
    elif role == "slide":
        # Convention B slide with no SET_METADATA entry — use prefix
        sample_label = prefix
    else:
        sample_label = prefix

    if not sample_label:
        raise ValueError(
            f"Filename {filepath.name!r} has role={role!r} but "
            f"no sample_label could be determined."
        )

    return {
        "role": role,
        "sample_label": sample_label,
        "stain": stain,
        "is_reference": (role == "reference"),
        "image_type": image_type,
    }


# ---------------------------------------------------------------------------
# Image I/O
# ---------------------------------------------------------------------------

def load_image(filepath: Path) -> Optional[np.ndarray]:
    """Load a BGR image via cv2.imread; return None on failure (logged)."""
    img = cv2.imread(str(filepath))
    if img is None:
        logger.warning("Could not read image: %s", filepath)
        return None
    return img


# ---------------------------------------------------------------------------
# Core segmentation — FROZEN SIGNATURE (used unchanged by Phase 2)
# ---------------------------------------------------------------------------

def segment_tissue(bgr_image: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Apply Otsu thresholding to isolate tissue from a bright backlight.

    Returns (grayscale_inverted, binary_mask, otsu_threshold_value).

    Tissue appears DARK on a bright LED backlight, so we invert the
    grayscale before thresholding — Otsu then separates "bright = tissue"
    from "dark = background", which lines up with cv2.findContours()'s
    convention of finding boundaries around bright (255) regions.

    A morphological OPEN (removes speckle) followed by CLOSE (fills small
    holes) is applied with a kernel of MORPH_KERNEL_SIZE (config constant).
    """
    # Pre-mortem: explicit input validation, deterministic execution.
    if not isinstance(bgr_image, np.ndarray):
        raise ValueError("bgr_image must be a numpy ndarray.")
    if bgr_image.ndim != 3 or bgr_image.shape[2] != 3:
        raise ValueError(
            f"bgr_image must be HxWx3 BGR; got shape {bgr_image.shape!r}."
        )
    if bgr_image.dtype != np.uint8:
        raise ValueError(
            f"bgr_image must be uint8; got dtype {bgr_image.dtype!r}."
        )

    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    gray_inv = cv2.bitwise_not(gray)

    otsu_value, mask = cv2.threshold(
        gray_inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    k = max(1, int(MORPH_KERNEL_SIZE))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    return gray_inv, mask, int(otsu_value)


# ---------------------------------------------------------------------------
# Contour extraction — FROZEN SIGNATURE
# ---------------------------------------------------------------------------

def extract_contours(binary_mask: np.ndarray, min_area: int) -> tuple[list, list]:
    """Find external contours and split by area threshold.

    Returns (all_contours, filtered_contours_above_min_area).
    """
    if binary_mask is None or binary_mask.ndim != 2:
        raise ValueError("binary_mask must be a 2-D single-channel image.")

    contours, _hierarchy = cv2.findContours(
        binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contours = list(contours)
    filtered = [c for c in contours if cv2.contourArea(c) >= min_area]
    return contours, filtered


# ---------------------------------------------------------------------------
# Success heuristic — pure function, separately testable
# ---------------------------------------------------------------------------

def compute_success_heuristic(num_contours: int, tissue_fraction: float,
                              image_pixels: int, min_contour_area: int) -> str:
    """Return 'PASS' or 'REVIEW' from the per-image summary stats.

    Logic (plan §3.4 + pre-mortem §2.3):
        if num_contours == 0:           REVIEW
        else:
            floor = max(HEURISTIC_FRACTION_FLOOR,
                        min_contour_area / image_pixels)
            if floor <= tissue_fraction <= HEURISTIC_FRACTION_UPPER: PASS
            else:                                                    REVIEW
    """
    if num_contours <= 0:
        return "REVIEW"
    if image_pixels <= 0:
        return "REVIEW"
    adaptive_floor = max(
        HEURISTIC_FRACTION_FLOOR,
        float(min_contour_area) / float(image_pixels),
    )
    if adaptive_floor <= tissue_fraction <= HEURISTIC_FRACTION_UPPER:
        return "PASS"
    return "REVIEW"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(bgr_image: np.ndarray, mask: np.ndarray,
                    filtered_contours: list, threshold: int,
                    filename_meta: dict) -> dict:
    """Build a single CSV row from the segmentation outputs.

    NOTE on areas: cv2.contourArea() returns geometric polygon area, which
    systematically undercounts pixel coverage for concave shapes (common
    in biopsy fragments).  Acceptable for Phase 1 diagnostics; do not
    treat tissue_fraction as a precise pixel measurement.

    GUARDED ZERO-CONTOURS PATH (pre-mortem §2.2): if no contours survived
    filtering, min/max/mean are never invoked on the empty list — we emit
    sentinel zeros and a REVIEW flag.
    """
    h, w = bgr_image.shape[:2]
    total_pixels = int(h) * int(w)

    # num_contours_total comes from re-running RETR_EXTERNAL on the mask;
    # we don't need it precisely here, just a count for the diagnostics
    # CSV.  Recompute from the mask to keep this function self-contained.
    all_contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    num_total = len(all_contours)
    num_filtered = len(filtered_contours)

    if num_filtered == 0:
        # Sentinel values — do NOT call min/max/mean on []
        total_area = 0
        largest = 0
        smallest = 0
        mean_area = 0.0
        tissue_fraction = 0.0
    else:
        areas = [float(cv2.contourArea(c)) for c in filtered_contours]
        total_area = float(sum(areas))
        largest = float(max(areas))
        smallest = float(min(areas))
        mean_area = total_area / len(areas)
        tissue_fraction = (total_area / total_pixels) if total_pixels > 0 else 0.0

    heuristic = compute_success_heuristic(
        num_contours=num_filtered,
        tissue_fraction=tissue_fraction,
        image_pixels=total_pixels,
        min_contour_area=MIN_CONTOUR_AREA,
    )

    return {
        "filename": filename_meta.get("filename", ""),
        "role": filename_meta.get("role", ""),
        "image_type": filename_meta.get("image_type", ""),
        "sample_label": filename_meta.get("sample_label", ""),
        "stain": filename_meta.get("stain", ""),
        "image_width_px": int(w),
        "image_height_px": int(h),
        "otsu_threshold": int(threshold),
        "num_contours_total": int(num_total),
        "num_contours_filtered": int(num_filtered),
        "total_tissue_area_px": int(round(total_area)),
        "largest_contour_area_px": int(round(largest)),
        "smallest_contour_area_px": int(round(smallest)),
        "mean_contour_area_px": float(mean_area),
        "tissue_fraction": float(tissue_fraction),
        "success_heuristic": heuristic,
    }


# ---------------------------------------------------------------------------
# Diagnostic visualization
# ---------------------------------------------------------------------------

def create_diagnostic_visualization(bgr_image: np.ndarray,
                                    gray_inv: np.ndarray,
                                    mask: np.ndarray,
                                    contours: list,
                                    output_path: Path) -> None:
    """Save the per-image 4-panel diagnostic PNG.

    Layout (2x2):
        TL: original colour    TR: inverted grayscale
        BL: binary mask        BR: contour overlay with per-contour area labels

    Pre-mortem §2.1: cv2.imread loads BGR; matplotlib expects RGB.  We
    MUST call cv2.cvtColor(..., COLOR_BGR2RGB) for any 3-channel panel,
    or red/blue silently swap.

    Pre-mortem §4.1: plt.close(fig) immediately after savefig() —
    otherwise matplotlib's figure registry accumulates across the batch
    and the script consumes hundreds of MB of RAM on a 20-image run.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)

    # Contour overlay drawn on a COPY so we don't mutate the caller's array.
    overlay_bgr = bgr_image.copy()
    cv2.drawContours(overlay_bgr, contours, -1, (0, 255, 0), thickness=3)
    for c in contours:
        area = cv2.contourArea(c)
        m = cv2.moments(c)
        if m["m00"] > 0:
            cx = int(m["m10"] / m["m00"])
            cy = int(m["m01"] / m["m00"])
            cv2.putText(
                overlay_bgr, f"{int(area)}", (cx, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2, cv2.LINE_AA,
            )
    overlay_rgb = cv2.cvtColor(overlay_bgr, cv2.COLOR_BGR2RGB)

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes[0, 0].imshow(rgb_image)
    axes[0, 0].set_title("Original (BGR→RGB)")
    axes[0, 1].imshow(gray_inv, cmap="gray")
    axes[0, 1].set_title("Inverted grayscale")
    axes[1, 0].imshow(mask, cmap="gray")
    axes[1, 0].set_title("Otsu binary mask")
    axes[1, 1].imshow(overlay_rgb)
    axes[1, 1].set_title(f"Contours (n={len(contours)})")

    for ax in axes.ravel():
        ax.set_xticks([])
        ax.set_yticks([])

    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", dpi=100)
    plt.close(fig)  # MUST be present — see docstring


# ---------------------------------------------------------------------------
# Per-image pipeline
# ---------------------------------------------------------------------------

def process_image(filepath: Path, output_dir: Path,
                  min_area: int) -> Optional[dict]:
    """Run the full pipeline on a single image.  Returns a metrics row,
    or None if the file should be skipped (load failure, reference image,
    or malformed filename)."""
    try:
        meta = parse_filename(filepath)
    except ValueError as exc:
        logger.warning("Skipping %s: %s", filepath.name, exc)
        return None

    if meta["is_reference"]:
        logger.info("Skipping reference image: %s", filepath.name)
        return None

    bgr = load_image(filepath)
    if bgr is None:
        return None

    gray_inv, mask, threshold = segment_tissue(bgr)
    _, filtered = extract_contours(mask, min_area=min_area)

    viz_path = output_dir / VISUALIZATION_SUBDIR / f"{filepath.stem}_diagnostic.png"
    create_diagnostic_visualization(bgr, gray_inv, mask, filtered, viz_path)

    row_meta = {
        "filename": filepath.name,
        "role": meta["role"],
        "image_type": meta.get("image_type", meta["role"]),
        "sample_label": meta["sample_label"],
        "stain": meta["stain"],
    }
    row = compute_metrics(bgr, mask, filtered, threshold, row_meta)

    # Explicit Otsu outlier warning (pre-mortem §3.2 / plan §3.4).
    if row["otsu_threshold"] < OTSU_LOW_WARN or row["otsu_threshold"] > OTSU_HIGH_WARN:
        logger.warning(
            "%s Otsu threshold at extreme value (%d) — possible segmentation failure.",
            filepath.name, row["otsu_threshold"],
        )

    return row


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def write_metrics_csv(rows: list[dict], output_path: Path) -> None:
    """Write all metrics rows to CSV with the canonical column order."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def main() -> None:
    """Phase 1 entry point.

    1. Create OUTPUT_DIR + visualizations subdir BEFORE any image work
       (pre-mortem §4.2).
    2. Discover all images in INPUT_DIR with a supported extension.
    3. Process each; skip reference / malformed / load-failure files.
    4. Emit CSV + console summary.
    """
    _configure_logging()

    viz_dir = OUTPUT_DIR / VISUALIZATION_SUBDIR
    viz_dir.mkdir(parents=True, exist_ok=True)

    if not INPUT_DIR.is_dir():
        logger.warning("Input directory does not exist: %s", INPUT_DIR)
        write_metrics_csv([], OUTPUT_DIR / METRICS_FILENAME)
        return

    candidates = sorted(
        p for p in INPUT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTS
    )

    rows: list[dict] = []
    pass_count = 0
    review_count = 0
    skipped = 0
    for path in candidates:
        row = process_image(path, OUTPUT_DIR, MIN_CONTOUR_AREA)
        if row is None:
            skipped += 1
            continue
        rows.append(row)
        if row["success_heuristic"] == "PASS":
            pass_count += 1
        else:
            review_count += 1

    csv_path = OUTPUT_DIR / METRICS_FILENAME
    write_metrics_csv(rows, csv_path)

    logger.info("Processed=%d  PASS=%d  REVIEW=%d  Skipped=%d",
                len(rows), pass_count, review_count, skipped)
    logger.info("CSV:  %s", csv_path)
    logger.info("PNGs: %s", viz_dir)


if __name__ == "__main__":
    main()
