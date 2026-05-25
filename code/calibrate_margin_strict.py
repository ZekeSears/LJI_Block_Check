"""
One-off: measure perimeter bright fraction on block silhouettes; emit p10 for phone JSON.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

_REPO = Path(__file__).resolve().parent.parent
CSV_PATH = _REPO / "phase3_outputs" / "contour_profile.csv"
IMAGE_DIR = _REPO / "iphone_images"
OUT_PHONE = _REPO / "phase3_outputs" / "block_roi_constants_phone.json"
BACKLIGHT_THRESH = 240


def perimeter_bright_fraction(gray: np.ndarray) -> float:
    bright = gray >= BACKLIGHT_THRESH
    perimeter = np.zeros_like(bright, dtype=bool)
    perimeter[0, :] = True
    perimeter[-1, :] = True
    perimeter[:, 0] = True
    perimeter[:, -1] = True
    return float(bright[perimeter].sum()) / max(1, perimeter.sum())


def main() -> int:
    if not CSV_PATH.is_file():
        print(f"missing {CSV_PATH}", file=sys.stderr)
        return 1
    fracs: list[float] = []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("role") != "block_silhouette":
                continue
            fname = row.get("filename") or ""
            if not fname:
                stem = row.get("filename_stem", "")
                matches = list(IMAGE_DIR.glob(f"{stem}.jp*g"))
                path = matches[0] if matches else None
            else:
                path = IMAGE_DIR / fname
                if not path.is_file():
                    matches = list(IMAGE_DIR.glob(path.stem + ".jp*g"))
                    path = matches[0] if matches else None
            if path is None or not path.is_file():
                continue
            bgr = cv2.imread(str(path))
            if bgr is None:
                continue
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            fracs.append(perimeter_bright_fraction(gray))
            del bgr, gray
    if not fracs:
        print("no block silhouettes measured", file=sys.stderr)
        return 1
    arr = np.array(fracs, dtype=np.float64)
    p10 = round(float(np.percentile(arr, 10)), 3)
    stats = {
        "n_rows": len(fracs),
        "min": round(float(arr.min()), 3),
        "median": round(float(np.median(arr)), 3),
        "p10": p10,
    }
    print(json.dumps(stats, indent=2))
    if OUT_PHONE.is_file():
        data = json.loads(OUT_PHONE.read_text(encoding="utf-8"))
    else:
        data = {}
    data["MARGIN_STRICT_MIN_PERIM_FRAC"] = p10
    data["_margin_calibration"] = stats
    OUT_PHONE.parent.mkdir(parents=True, exist_ok=True)
    OUT_PHONE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
