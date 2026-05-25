"""
segmentation_audit_pack.py — Mask overlay audit pack (leaf).

Uses the same segment_tissue + clean_mask path as phase3_contour_profile.py.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import cv2
import numpy as np

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

import phase3_block_roi as p3roi
import phase3_contour_profile as p3cp

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = REPO_ROOT / "iphone_images"
CONTOUR_CSV = REPO_ROOT / "phase3_outputs" / "contour_profile.csv"
OUT_ROOT = REPO_ROOT / "phase3_outputs" / "segmentation_audit"
OVERLAY_DIR = OUT_ROOT / "overlays"
INDEX_MD = OUT_ROOT / "index.md"
MAX_EDGE_PX = 1024


def _resize_for_overlay(bgr: np.ndarray, max_edge: int = MAX_EDGE_PX) -> np.ndarray:
    h, w = bgr.shape[:2]
    scale = min(1.0, max_edge / max(h, w))
    if scale >= 1.0:
        return bgr
    nw, nh = int(w * scale), int(h * scale)
    return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)


def overlay_mask_on_bgr(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Green tint where mask > 0."""
    out = bgr.copy()
    tint = out.copy()
    tint[mask > 0] = (0, 200, 0)
    cv2.addWeighted(out, 0.65, tint, 0.35, 0, out)
    return out


def render_overlay(
        path: Path,
        meta: dict,
        *,
        allow_full_frame_fallback: bool = False,
) -> np.ndarray | None:
    bgr = cv2.imread(str(path))
    if bgr is None:
        return None
    seg = p3roi.segment_with_block_roi(
        bgr, meta, p3cp.clean_mask,
        allow_full_frame_fallback=allow_full_frame_fallback,
    )
    cleaned = seg.cleaned_mask
    overlay = overlay_mask_on_bgr(bgr, cleaned)
    return _resize_for_overlay(overlay)


def run_segmentation_audit(
        input_dir: Path = INPUT_DIR,
        contour_csv: Path = CONTOUR_CSV,
        out_root: Path = OUT_ROOT,
        *,
        allow_full_frame_fallback: bool = False,
) -> Path:
    import pandas as pd

    out_root.mkdir(parents=True, exist_ok=True)
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(contour_csv)
    measured = df[df.get("measured") == True]  # noqa: E712
    flags: list[dict] = []
    total_bytes = 0

    for _, row in measured.iterrows():
        fname = str(row.get("filename", ""))
        if not fname:
            continue
        path = input_dir / fname
        stem = str(row.get("filename_stem", path.stem))
        meta = p3cp.parse_image_filename(stem)
        p3cp.enrich_tissue_fields(meta)

        out_png = OVERLAY_DIR / f"{stem}.png"
        auto_flags: list[str] = []
        if int(row.get("contour_count", 0)) == 0:
            auto_flags.append("contour_count==0")
        excl = row.get("measurement_exclusion")
        if excl is not None and str(excl) not in ("", "nan"):
            auto_flags.append(f"measurement_exclusion:{excl}")
        if meta.get("set_id") == 1 and meta.get("role") == "slide":
            auto_flags.append("set_01_ceiling_case")

        if path.is_file():
            rendered = render_overlay(
                path, meta,
                allow_full_frame_fallback=allow_full_frame_fallback,
            )
            if rendered is not None:
                cv2.imwrite(str(out_png), rendered)
                total_bytes += out_png.stat().st_size
        else:
            auto_flags.append("image_missing")

        flags.append({
            "filename": fname,
            "stem": stem,
            "overlay": str(out_png.relative_to(REPO_ROOT)),
            "flags": ";".join(auto_flags) if auto_flags else "",
        })

    review_csv = out_root / "review.csv"
    with review_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["filename", "stem", "overlay", "flags", "human_pass"],
        )
        writer.writeheader()
        for f in flags:
            writer.writerow({**f, "human_pass": ""})

    mb = total_bytes / (1024 * 1024)
    index_lines = [
        "# Segmentation audit pack",
        "",
        f"- Measured images: {len(flags)}",
        f"- Overlays: `{OVERLAY_DIR.relative_to(REPO_ROOT)}/`",
        f"- Total overlay size: {mb:.1f} MB (max edge {MAX_EDGE_PX}px)",
        f"- Review CSV: `{review_csv.relative_to(REPO_ROOT)}` (fill human_pass)",
        "",
        "## Auto-flags",
        "",
    ]
    flagged = [f for f in flags if f["flags"]]
    if flagged:
        for f in flagged[:50]:
            index_lines.append(f"- `{f['stem']}`: {f['flags']}")
        if len(flagged) > 50:
            index_lines.append(f"- ... and {len(flagged) - 50} more (see review.csv)")
    else:
        index_lines.append("- (none)")
    index_lines.append("")
    INDEX_MD.write_text("\n".join(index_lines), encoding="utf-8")
    return INDEX_MD


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Segmentation audit overlay pack")
    parser.add_argument(
        "--analysis-fallback",
        action="store_true",
        help="Allow full-frame / analysis fallback for block ROI failures",
    )
    args = parser.parse_args()
    if not CONTOUR_CSV.is_file():
        print(f"Missing {CONTOUR_CSV}", file=sys.stderr)
        return 1
    out = run_segmentation_audit(
        allow_full_frame_fallback=args.analysis_fallback,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
