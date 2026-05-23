"""
phase3_contour_profile.py — One-shot calibration over the 23-set iPhone dataset.

Measures per-image contour statistics, derives router thresholds, and writes
audit artifacts under phase3_outputs/.

Keyed to .cursor/specs/proposed_plan.md and .cursor/specs/pre_mortem.md.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd

from phase1_segmentation import segment_tissue
from phase2_descriptors import clean_mask


log = logging.getLogger(__name__)

# Phase 4 should encode label color in filenames; until then, maintain here.
YELLOW_TAG_SET_IDS: frozenset[int] = frozenset({1})

INPUT_DIR = Path("./iphone_images/")
OUTPUT_ROOT = Path("./phase3_outputs/")
CSV_PATH = OUTPUT_ROOT / "contour_profile.csv"
HISTOGRAM_DIR = OUTPUT_ROOT / "calibration_histograms"
NOTES_PATH = OUTPUT_ROOT / "phase3_calibration_notes.md"
ROUTER_CONSTANTS_PATH = OUTPUT_ROOT / "router_constants.json"

BLOCK_SUBTYPES = frozenset({"silhouette", "barcode"})
PERCENTILE_LEVELS = (10, 25, 50, 75, 90)
MIN_SAMPLES_FOR_CONFIDENT_PERCENTILES = 15

# Sanity bounds for hybrid router constants
SLIDE_AREA_MIN_PX = 10_000.0
SLIDE_AREA_MAX_PX = 2_000_000.0
DOMINANCE_MIN_BOUND = 0.5
DOMINANCE_MAX_BOUND = 1.0

# Legacy count/mean-area bounds (demoted metrics)
COUNT_THRESHOLD_MIN = 2
COUNT_THRESHOLD_MAX = 50
AREA_THRESHOLD_MIN_PX = 100.0
AREA_THRESHOLD_MAX_FRACTION = 0.5

DEGENERATE_SINGLE_CONTOUR_FRACTION = 0.95


# ---------------------------------------------------------------------------
# Filename parsing (core — tested first)
# ---------------------------------------------------------------------------


def label_type_for_set(set_id: int) -> str:
    return "yellow" if set_id in YELLOW_TAG_SET_IDS else "white"


def parse_image_filename(stem: str) -> dict[str, Any]:
    """Parse set_NN_<role>... filename stem into metadata.

  Compound-role rule (pre-mortem critical):
    - If token[2] == 'block' and token[3] in {silhouette, barcode}:
        role = 'block_{subtype}', fields begin at index 4.
    - Else if token[2] == 'slide': role = 'slide', fields begin at index 3.
    - Else: parse_ok=False.
    """
    tokens = stem.split("_")
    base: dict[str, Any] = {
        "filename_stem": stem,
        "parse_ok": False,
        "parse_error": "",
        "set_id": None,
        "role": "",
        "tissue": "",
        "stain": "",
        "genotype": "",
        "work_order": "",
        "label_type": "white",
    }

    if len(tokens) < 3 or tokens[0] != "set":
        base["parse_error"] = "expected set_NN prefix"
        return base

    try:
        set_id = int(tokens[1])
    except ValueError:
        base["parse_error"] = f"invalid set id: {tokens[1]!r}"
        return base

    base["set_id"] = set_id
    base["label_type"] = label_type_for_set(set_id)

    role_token = tokens[2]
    if role_token == "block":
        if len(tokens) < 4:
            base["parse_error"] = "block role missing subtype"
            return base
        subtype = tokens[3]
        if subtype not in BLOCK_SUBTYPES:
            base["parse_error"] = f"unknown block subtype: {subtype!r}"
            return base
        role = f"block_{subtype}"
        field_start = 4
    elif role_token == "slide":
        role = "slide"
        field_start = 3
    else:
        base["parse_error"] = f"unknown role prefix: {role_token!r}"
        return base

    base["role"] = role
    remaining = tokens[field_start:]
    base["tissue"] = remaining[0] if len(remaining) >= 1 else ""
    base["stain"] = remaining[1] if len(remaining) >= 2 else ""
    base["genotype"] = remaining[2] if len(remaining) >= 3 else ""
    base["work_order"] = remaining[3] if len(remaining) >= 4 else ""
    if len(remaining) > 4:
        base["parse_error"] = f"unexpected extra tokens: {remaining[4:]}"
        return base

    base["parse_ok"] = True
    return base


def normalize_tissue_class(tissue: str) -> Optional[str]:
    t = tissue.lower()
    if "lung" in t or t == "lungs":
        return "lung"
    if "esoph" in t:
        return "esophagus"
    if t == "":
        return None
    return None


def should_measure_contours(meta: dict[str, Any]) -> bool:
    if not meta.get("parse_ok"):
        return False
    return meta.get("role") != "block_barcode"


def clean_mask_role(meta: dict[str, Any]) -> str:
    return "slide" if meta.get("role") == "slide" else "block"


# ---------------------------------------------------------------------------
# Measurement & statistics
# ---------------------------------------------------------------------------


def measurement_exclusion_reason(contour_count: int,
                                 max_contour_area_fraction: float) -> Optional[str]:
    if contour_count == 0:
        return "no_contours"
    if (contour_count == 1
            and max_contour_area_fraction >= DEGENERATE_SINGLE_CONTOUR_FRACTION):
        return "degenerate_single_contour"
    return None


def compute_percentile_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    arr = np.asarray(values, dtype=np.float64)
    out: dict[str, float] = {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }
    for p in PERCENTILE_LEVELS:
        out[f"p{p}"] = float(np.percentile(arr, p))
    return out


def group_measurement_records(
        records: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        tissue = rec.get("tissue_class")
        role = rec.get("role")
        if tissue and role:
            groups[(tissue, role)].append(rec)
    return dict(groups)


def white_tag_threshold_records(
        records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        r for r in records
        if r.get("eligible_for_threshold") and r.get("measurement_exclusion") is None
    ]


def detect_distribution_overlap(lung_values: list[float],
                                esoph_values: list[float]) -> bool:
    if not lung_values or not esoph_values:
        return True
    lung_p90 = float(np.percentile(lung_values, 90))
    esp_p10 = float(np.percentile(esoph_values, 10))
    return lung_p90 >= esp_p10


def derive_count_threshold(
        lung_counts: list[float],
        esoph_counts: list[float],
) -> dict[str, Any]:
    """Deterministic rule (pre-mortem §6 critical).

    If lung_p90 < esophagus_p10: threshold = round((lung_p90 + esp_p10) / 2).
    If lung_p90 == esp_p10: threshold = int(lung_p90) (documented edge case).
    Else: overlap — no threshold emitted.
    """
    if not lung_counts or not esoph_counts:
        return {"overlap": True, "threshold": None, "lung_p90": None, "esophagus_p10": None}

    lung_p90 = float(np.percentile(lung_counts, 90))
    esp_p10 = float(np.percentile(esoph_counts, 10))
    result: dict[str, Any] = {
        "lung_p90": lung_p90,
        "esophagus_p10": esp_p10,
        "overlap": False,
        "threshold": None,
    }
    if lung_p90 < esp_p10:
        result["threshold"] = int(round((lung_p90 + esp_p10) / 2.0))
    elif lung_p90 == esp_p10:
        result["threshold"] = int(lung_p90)
    else:
        result["overlap"] = True
    return result


def derive_high_low_separation_threshold(
        lung_values: list[float],
        esoph_values: list[float],
) -> dict[str, Any]:
    """Lung values are higher than esophagus (total area, dominance on slides).

    Primary rule: midpoint of medians when lung_median > esophagus_median
    (stable for small n). If that fails, try lung_p10 > esophagus_p90.
    """
    if not lung_values or not esoph_values:
        return {
            "overlap": True,
            "threshold": None,
            "lung_median": None,
            "esophagus_median": None,
            "method": None,
        }
    lung_median = float(np.median(lung_values))
    esp_median = float(np.median(esoph_values))
    lung_p10 = float(np.percentile(lung_values, 10))
    esp_p90 = float(np.percentile(esoph_values, 90))
    result: dict[str, Any] = {
        "lung_median": lung_median,
        "esophagus_median": esp_median,
        "lung_p10": lung_p10,
        "esophagus_p90": esp_p90,
        "overlap": False,
        "threshold": None,
        "method": None,
    }
    if lung_median > esp_median:
        result["threshold"] = float((lung_median + esp_median) / 2.0)
        result["method"] = "median_midpoint"
    elif lung_p10 > esp_p90:
        result["threshold"] = float((lung_p10 + esp_p90) / 2.0)
        result["method"] = "percentile_midpoint"
    elif lung_median == esp_median:
        result["threshold"] = float(lung_median)
        result["method"] = "median_equal"
    else:
        result["overlap"] = True
    return result


def derive_area_threshold(
        lung_areas: list[float],
        esoph_areas: list[float],
) -> dict[str, Any]:
    """Per-image *median* contour areas — inverted percentile rule vs count.

    Lung tissue has larger areas; esophagus fragments are smaller. Separation when
    esophagus_p90 < lung_p10; threshold = midpoint. Router runtime still uses mean.
    """
    if not lung_areas or not esoph_areas:
        return {
            "overlap": True,
            "threshold": None,
            "lung_p10": None,
            "esophagus_p90": None,
            "statistic": "median",
        }

    lung_p10 = float(np.percentile(lung_areas, 10))
    esp_p90 = float(np.percentile(esoph_areas, 90))
    result: dict[str, Any] = {
        "lung_p10": lung_p10,
        "esophagus_p90": esp_p90,
        "overlap": False,
        "threshold": None,
        "statistic": "median",
    }
    if esp_p90 < lung_p10:
        result["threshold"] = float((esp_p90 + lung_p10) / 2.0)
    elif esp_p90 == lung_p10:
        result["threshold"] = float(lung_p10)
    else:
        result["overlap"] = True
    return result


def validate_hybrid_router_sanity(
        slide_area_threshold: Optional[float],
        dominance_threshold: Optional[float],
) -> tuple[bool, str]:
    if slide_area_threshold is None or dominance_threshold is None:
        return False, "hybrid router thresholds not derived (overlap or empty data)"
    if not (SLIDE_AREA_MIN_PX <= slide_area_threshold <= SLIDE_AREA_MAX_PX):
        return False, (
            f"SLIDE_TOTAL_TISSUE_AREA_PX={slide_area_threshold} outside "
            f"[{SLIDE_AREA_MIN_PX}, {SLIDE_AREA_MAX_PX}]"
        )
    if not (DOMINANCE_MIN_BOUND <= dominance_threshold <= DOMINANCE_MAX_BOUND):
        return False, (
            f"DOMINANCE_MIN_FOR_SHAPE={dominance_threshold} outside "
            f"[{DOMINANCE_MIN_BOUND}, {DOMINANCE_MAX_BOUND}]"
        )
    return True, ""


def validate_threshold_sanity(
        count_threshold: Optional[int],
        area_threshold: Optional[float],
        max_image_pixels: int = 4_000_000,
) -> tuple[bool, str]:
    if count_threshold is None or area_threshold is None:
        return False, "legacy thresholds not derived (overlap or empty data)"
    max_area = AREA_THRESHOLD_MAX_FRACTION * max_image_pixels
    if not (COUNT_THRESHOLD_MIN <= count_threshold <= COUNT_THRESHOLD_MAX):
        return False, (
            f"MULTI_FRAGMENT_THRESHOLD={count_threshold} outside "
            f"[{COUNT_THRESHOLD_MIN}, {COUNT_THRESHOLD_MAX}]"
        )
    if not (AREA_THRESHOLD_MIN_PX <= area_threshold <= max_area):
        return False, (
            f"SMALL_FRAGMENT_AREA_PX={area_threshold} outside "
            f"[{AREA_THRESHOLD_MIN_PX}, {max_area}]"
        )
    return True, ""


def measure_contours_on_image(bgr: np.ndarray, meta: dict[str, Any]) -> dict[str, Any]:
    h, w = bgr.shape[:2]
    image_pixels = h * w
    _, mask, otsu = segment_tissue(bgr)
    cleaned, contours = clean_mask(mask, clean_mask_role(meta))

    areas = [float(cv2.contourArea(c)) for c in contours]
    contour_count = len(contours)
    max_area = max(areas) if areas else 0.0
    max_frac = max_area / image_pixels if image_pixels else 0.0
    exclusion = measurement_exclusion_reason(contour_count, max_frac)

    tissue_fraction = float((cleaned > 0).sum()) / image_pixels
    dominance = (max_area / float(sum(areas))) if areas else float("nan")
    return {
        "contour_count": contour_count,
        "dominance": dominance,
        "mean_contour_area": float(np.mean(areas)) if areas else float("nan"),
        "median_contour_area": float(np.median(areas)) if areas else float("nan"),
        "max_contour_area": max_area,
        "min_contour_area": float(min(areas)) if areas else float("nan"),
        "total_tissue_area": float(sum(areas)),
        "tissue_fraction": tissue_fraction,
        "image_height": h,
        "image_width": w,
        "otsu_threshold": otsu,
        "measurement_exclusion": exclusion,
    }


# ---------------------------------------------------------------------------
# Reporting (leaf)
# ---------------------------------------------------------------------------


def _write_histograms(df: pd.DataFrame, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    measured = df[df["measurement_exclusion"].isna()].copy()

    def _hist(column: str, title: str, fname: str) -> None:
        fig, ax = plt.subplots(figsize=(8, 5))
        for tissue, sub in measured.groupby("tissue_class"):
            if sub[column].notna().any():
                ax.hist(sub[column].dropna(), bins=15, alpha=0.5, label=tissue)
        ax.set_title(title)
        ax.legend()
        path = out_dir / fname
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)

    slides = measured[measured["role"] == "slide"] if "role" in measured.columns else measured

    def _hist_slide(column: str, title: str, fname: str) -> None:
        fig, ax = plt.subplots(figsize=(8, 5))
        for tissue, sub in slides.groupby("tissue_class"):
            if sub[column].notna().any():
                ax.hist(sub[column].dropna(), bins=15, alpha=0.5, label=tissue)
        ax.set_title(title)
        ax.legend()
        path = out_dir / fname
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)

    _hist("contour_count", "Contour count by tissue (all measured)",
          "contour_count_by_tissue.png")
    _hist_slide("total_tissue_area",
                "Slide total tissue area by tissue (white-tag)",
                "slide_total_tissue_area_by_tissue.png")
    _hist_slide("dominance",
                "Slide dominance (max/total area) by tissue",
                "slide_dominance_by_tissue.png")

    fig, ax = plt.subplots(figsize=(8, 5))
    for label, sub in measured.groupby("label_type"):
        if sub["contour_count"].notna().any():
            ax.hist(sub["contour_count"].dropna(), bins=12, alpha=0.5, label=label)
    ax.set_title("Contour count: white vs yellow label")
    ax.legend()
    p = out_dir / "contour_count_white_vs_yellow.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)
    return paths


def _format_stats_table(groups: dict[tuple[str, str], list[dict[str, Any]]]) -> str:
    lines = ["| tissue | role | n | contour_count median | median_area median |",
             "|--------|------|---|----------------------|---------------------|"]
    for (tissue, role), recs in sorted(groups.items()):
        counts = [r["contour_count"] for r in recs
                  if r.get("measurement_exclusion") is None]
        areas = [r["median_contour_area"] for r in recs
                 if r.get("measurement_exclusion") is None and not np.isnan(
                     r.get("median_contour_area", float("nan")))]
        cc_med = f"{np.median(counts):.1f}" if counts else "—"
        ar_med = f"{np.median(areas):.0f}" if areas else "—"
        lines.append(f"| {tissue} | {role} | {len(recs)} | {cc_med} | {ar_med} |")
    return "\n".join(lines)


def write_router_constants_json(
        slide_area_result: dict[str, Any],
        dominance_result: dict[str, Any],
        count_result: dict[str, Any],
        area_result: dict[str, Any],
) -> None:
    payload: dict[str, Any] = {
        "routing_strategy": "hybrid_v2",
        "SLIDE_TOTAL_TISSUE_AREA_PX": slide_area_result.get("threshold"),
        "DOMINANCE_MIN_FOR_SHAPE": dominance_result.get("threshold"),
        "MULTI_FRAGMENT_THRESHOLD": count_result.get("threshold"),
        "SMALL_FRAGMENT_AREA_PX": area_result.get("threshold"),
    }
    ROUTER_CONSTANTS_PATH.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def write_calibration_notes(
        *,
        slide_area_result: dict[str, Any],
        dominance_result: dict[str, Any],
        count_result: dict[str, Any],
        area_result: dict[str, Any],
        sanity_ok: bool,
        sanity_msg: str,
        parse_warnings: list[str],
        groups: dict[tuple[str, str], list[dict[str, Any]]],
        yellow_records: list[dict[str, Any]],
        histogram_paths: list[Path],
        low_n_warnings: list[str],
) -> None:
    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 3 calibration notes",
        "",
        f"**Date:** {date.today().isoformat()}",
        "",
        "## Provenance",
        "",
        "- **Dataset:** `iphone_images/` — iPhone backlit captures, single shooting session",
        "- **Re-calibration:** Required if images are re-shot or lighting changes materially",
        "",
        "## Recommended router thresholds (hybrid v2)",
        "",
        "Primary routing uses **tissue in filename** when available, then **slide**",
        "`total_tissue_area` and **dominance** (max contour area / sum of areas).",
        "Contour-count thresholds are legacy fallback only.",
        "",
    ]
    hybrid_overlap = (
        slide_area_result.get("overlap") or dominance_result.get("overlap")
    )
    if hybrid_overlap:
        lines.append(
            "> **Hybrid metric overlap** — slide area and/or dominance thresholds "
            "could not be derived. Review histograms before locking constants."
        )
        lines.append("")
    else:
        lines.extend([
            "| Constant | Value | Derivation |",
            "|----------|-------|------------|",
            f"| `SLIDE_TOTAL_TISSUE_AREA_PX` | "
            f"{slide_area_result.get('threshold'):.0f} | "
            f"{slide_area_result.get('method')} on slide total tissue area "
            f"(lung median {slide_area_result.get('lung_median'):.0f}, "
            f"esophagus median {slide_area_result.get('esophagus_median'):.0f}) |",
            f"| `DOMINANCE_MIN_FOR_SHAPE` | "
            f"{dominance_result.get('threshold'):.3f} | "
            f"{dominance_result.get('method')} on slide dominance "
            f"(lung median {dominance_result.get('lung_median'):.3f}, "
            f"esophagus median {dominance_result.get('esophagus_median'):.3f}) |",
            "",
        ])
    if count_result.get("overlap"):
        lines.extend([
            "- Contour-count calibration **overlapped** (expected on this dataset); "
            "do not use count for primary routing.",
            "",
        ])
    else:
        lines.extend([
            "### Legacy fallback (demoted)",
            "",
            f"- `MULTI_FRAGMENT_THRESHOLD` = {count_result.get('threshold')}",
            f"- `SMALL_FRAGMENT_AREA_PX` = {area_result.get('threshold')}",
            "",
        ])
    lines.extend([
        f"**Sanity check:** {'PASS' if sanity_ok else 'FAIL — ' + sanity_msg}",
        "",
        "## Per-(tissue, role) statistics",
        "",
        _format_stats_table(groups),
        "",
        "## Yellow-tag (Set 1) separate findings",
        "",
        f"Measured yellow-tag images: {len(yellow_records)} "
        "(excluded from white-tag threshold pool).",
        "",
        "## Parse warnings",
        "",
    ])
    if parse_warnings:
        lines.extend(f"- {w}" for w in parse_warnings)
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "## Yellow-tag recommendation",
        "",
        "Only one yellow-tag set exists (Set 1). Add more yellow-tag samples "
        "before Phase 4 if Set 1 metrics diverge from white-tag norms.",
        "",
        "## Histograms",
        "",
    ])
    for p in histogram_paths:
        lines.append(f"- `{p.as_posix()}`")
    if low_n_warnings:
        lines.extend(["", "## Low sample-size warnings", ""])
        lines.extend(f"- {w}" for w in low_n_warnings)
    NOTES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_calibration(input_dir: Path = INPUT_DIR,
                    output_root: Path = OUTPUT_ROOT) -> int:
    """Run full calibration. Returns process exit code (0 ok, 1 sanity/overlap fail)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    output_root.mkdir(parents=True, exist_ok=True)
    HISTOGRAM_DIR.mkdir(parents=True, exist_ok=True)

    parse_warnings: list[str] = []
    records: list[dict[str, Any]] = []
    image_paths = sorted(input_dir.glob("*.jpeg")) + sorted(input_dir.glob("*.jpg"))

    for path in image_paths:
        meta = parse_image_filename(path.stem)
        meta["filename"] = path.name
        if not meta["parse_ok"]:
            parse_warnings.append(f"{path.name}: {meta['parse_error']}")
            records.append(meta)
            continue

        if not should_measure_contours(meta):
            meta["measured"] = False
            meta["eligible_for_threshold"] = False
            records.append(meta)
            continue

        bgr = cv2.imread(str(path))
        if bgr is None:
            parse_warnings.append(f"{path.name}: cv2.imread failed")
            meta["parse_ok"] = False
            records.append(meta)
            continue

        meta["tissue_class"] = normalize_tissue_class(meta["tissue"])
        metrics = measure_contours_on_image(bgr, meta)
        meta.update(metrics)
        meta["measured"] = True
        meta["eligible_for_threshold"] = meta["label_type"] == "white"
        records.append(meta)
        del bgr

    df = pd.DataFrame(records)
    df.to_csv(CSV_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    pool = white_tag_threshold_records(records)
    lung = [r for r in pool if r.get("tissue_class") == "lung"]
    esoph = [r for r in pool if r.get("tissue_class") == "esophagus"]
    lung_slides = [r for r in lung if r.get("role") == "slide"]
    esp_slides = [r for r in esoph if r.get("role") == "slide"]

    lung_slide_areas = [float(r["total_tissue_area"]) for r in lung_slides]
    esp_slide_areas = [float(r["total_tissue_area"]) for r in esp_slides]
    lung_slide_dom = [float(r["dominance"]) for r in lung_slides
                      if not np.isnan(r.get("dominance", float("nan")))]
    esp_slide_dom = [float(r["dominance"]) for r in esp_slides
                     if not np.isnan(r.get("dominance", float("nan")))]

    slide_area_result = derive_high_low_separation_threshold(
        lung_slide_areas, esp_slide_areas,
    )
    dominance_result = derive_high_low_separation_threshold(
        lung_slide_dom, esp_slide_dom,
    )
    hybrid_overlap = (
        slide_area_result.get("overlap") or dominance_result.get("overlap")
    )

    lung_counts = [float(r["contour_count"]) for r in lung]
    esp_counts = [float(r["contour_count"]) for r in esoph]
    lung_areas = [float(r["median_contour_area"]) for r in lung
                  if not np.isnan(r.get("median_contour_area", float("nan")))]
    esp_areas = [float(r["median_contour_area"]) for r in esoph
                 if not np.isnan(r.get("median_contour_area", float("nan")))]
    count_result = derive_count_threshold(lung_counts, esp_counts)
    area_result = derive_area_threshold(lung_areas, esp_areas)

    sanity_ok, sanity_msg = validate_hybrid_router_sanity(
        slide_area_result.get("threshold"),
        dominance_result.get("threshold"),
    )

    low_n: list[str] = []
    for label, subset in (("lung slide", lung_slides), ("esophagus slide", esp_slides)):
        if 0 < len(subset) < MIN_SAMPLES_FOR_CONFIDENT_PERCENTILES:
            low_n.append(
                f"{label} calibration pool n={len(subset)} "
                f"(<{MIN_SAMPLES_FOR_CONFIDENT_PERCENTILES}); percentiles are unstable."
            )

    groups = group_measurement_records(
        [r for r in records if r.get("measured")],
    )
    yellow_records = [r for r in records if r.get("label_type") == "yellow" and r.get("measured")]

    hist_paths = _write_histograms(df, HISTOGRAM_DIR)
    if not hybrid_overlap:
        write_router_constants_json(
            slide_area_result, dominance_result, count_result, area_result,
        )
    write_calibration_notes(
        slide_area_result=slide_area_result,
        dominance_result=dominance_result,
        count_result=count_result,
        area_result=area_result,
        sanity_ok=sanity_ok,
        sanity_msg=sanity_msg,
        parse_warnings=parse_warnings,
        groups=groups,
        yellow_records=yellow_records,
        histogram_paths=hist_paths,
        low_n_warnings=low_n,
    )

    log.info("Parsed/measured/skipped: %d images, %d measured, %d parse warnings",
             len(image_paths), sum(1 for r in records if r.get("measured")),
             len(parse_warnings))
    if slide_area_result.get("threshold") is not None:
        log.info("SLIDE_TOTAL_TISSUE_AREA_PX = %.0f",
                 slide_area_result["threshold"])
    if dominance_result.get("threshold") is not None:
        log.info("DOMINANCE_MIN_FOR_SHAPE = %.3f", dominance_result["threshold"])
    if hybrid_overlap:
        log.warning("Hybrid slide metrics overlapped — check calibration notes")
    if not sanity_ok:
        log.error("Sanity check failed: %s", sanity_msg)
        return 1
    if hybrid_overlap:
        return 1
    return 0


def main() -> None:
    sys.exit(run_calibration())


if __name__ == "__main__":
    main()
