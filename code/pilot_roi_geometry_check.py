"""
Leaf: geometry pre-check on Fix 1d pilot sets using shared evaluate_roi_gates().
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

import phase3_block_roi as roi  # noqa: E402
import phase3_contour_profile as p3cp  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
INPUT = REPO / "iphone_images"
OUT = REPO / "phase3_outputs" / "pilot_roi_geometry_report.md"


def main() -> int:
    lines = ["# Pilot ROI geometry report", ""]
    n_ok = 0
    for set_id in sorted(roi.PILOT_SET_IDS):
        matches = list(INPUT.glob(f"set_{set_id:02d}_*silhouette*.jp*g"))
        if not matches:
            lines.append(f"- set_{set_id:02d}: **missing image**")
            continue
        bgr = cv2.imread(str(matches[0]))
        if bgr is None:
            lines.append(f"- set_{set_id:02d}: **read failed**")
            continue
        meta = p3cp.parse_image_filename(matches[0].stem)
        p3cp.enrich_tissue_fields(meta)
        det = roi.detect_cassette_interior_roi_detail(
            bgr, capture_source=roi.capture_source_from_meta(meta),
        )
        flags: list[str] = []
        if det.gate_failures:
            for g in det.gate_failures:
                if g in ("roi_sliver", "roi_oversize", "backlight_flood"):
                    flags.append(g)
        if not det.roi_detection_ok and det.roi_fail_reason in (
            "roi_sliver", "roi_oversize", "backlight_flood",
        ):
            flags.append(det.roi_fail_reason)
        if not flags:
            n_ok += 1
        flag_str = ", ".join(flags) if flags else "ok"
        lines.append(
            f"- set_{set_id:02d}: roi_ok={det.roi_detection_ok} "
            f"method={det.cassette_method} flags={flag_str}",
        )
        del bgr
    lines.extend([
        "",
        f"**Zero slit/flood flags:** {n_ok}/{len(roi.PILOT_SET_IDS)}",
        "",
    ])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
