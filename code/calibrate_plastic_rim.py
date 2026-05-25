"""
Click gray plastic rim on block silhouettes → sample gray/HSV → viability report.

Usage (from repo root, venv active):
  cd code
  ..\\venv\\Scripts\\python.exe calibrate_plastic_rim.py
  ..\\venv\\Scripts\\python.exe calibrate_plastic_rim.py --set 4
  ..\\venv\\Scripts\\python.exe calibrate_plastic_rim.py --auto-feasibility

Interactive keys:
  Left-click  = sample plastic pixel (green dot)
  Right-click = cassette corner in order (cyan quad, 4 clicks)
  n / Space   = next image
  p           = previous image
  c           = clear corner clicks on this image
  z           = undo last click (plastic or corner)
  s           = save clicks JSON + print pooled stats
  q / Esc     = quit

Outputs:
  phase3_outputs/plastic_rim_clicks.json
  phase3_outputs/plastic_rim_viability.md  (--auto-feasibility or after save)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

_REPO = Path(__file__).resolve().parent.parent
IMAGE_DIR = _REPO / "iphone_images"
OUT_CLICKS = _REPO / "phase3_outputs" / "plastic_rim_clicks.json"
OUT_REPORT = _REPO / "phase3_outputs" / "plastic_rim_viability.md"

DEFAULT_PILOT = (2, 4, 6, 11, 28, 31, 33, 35, 40, 45)
FEASIBILITY_PILOT = (2, 4, 6, 11, 28, 33, 35, 40, 45)
FRAME_THRESH = 110
PLASTIC_LOW = 80
PLASTIC_HIGH = 135
CASSETTE_AREA_MIN_FRAC = 0.15


@dataclass
class ImageSession:
    set_id: int
    path: Path
    bgr: np.ndarray
    plastic_clicks: list[tuple[int, int]] = field(default_factory=list)
    corner_clicks: list[tuple[int, int]] = field(default_factory=list)
    # "plastic" | "corner" — order of clicks for undo (z)
    click_history: list[str] = field(default_factory=list)


def find_silhouette(set_id: int, image_dir: Path = IMAGE_DIR) -> Optional[Path]:
    matches = sorted(image_dir.glob(f"set_{set_id:02d}_*silhouette*.jp*g"))
    return matches[0] if matches else None


def sample_at(bgr: np.ndarray, x: int, y: int) -> dict[str, Any]:
    h, w = bgr.shape[:2]
    x = int(np.clip(x, 0, w - 1))
    y = int(np.clip(y, 0, h - 1))
    b, g, r = (int(v) for v in bgr[y, x])
    gray = int(round(0.114 * b + 0.587 * g + 0.299 * r))
    hsv = cv2.cvtColor(bgr[y:y + 1, x:x + 1], cv2.COLOR_BGR2HSV)[0, 0]
    return {
        "x": x,
        "y": y,
        "bgr": [b, g, r],
        "gray": gray,
        "hsv": [int(hsv[0]), int(hsv[1]), int(hsv[2])],
    }


def plastic_mask_stats(gray: np.ndarray, low: int, high: int) -> dict[str, float]:
    h, w = gray.shape
    img_area = h * w
    mask = ((gray >= low) & (gray <= high)).astype(np.uint8)
    pct_img = float(mask.sum()) / img_area * 100.0
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    largest_pct = 0.0
    if n >= 2:
        areas = stats[1:, cv2.CC_STAT_AREA]
        largest_pct = float(areas.max()) / img_area * 100.0
    return {
        "pct_image_in_band": pct_img,
        "largest_cc_pct": largest_pct,
        "passes_15pct_gate": largest_pct >= CASSETTE_AREA_MIN_FRAC * 100.0,
    }


def dark_frame_stats(gray: np.ndarray) -> dict[str, Any]:
    h, w = gray.shape
    img_area = h * w
    fg = (gray < FRAME_THRESH).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"frame_area_pct": 0.0, "frame_gray": None}
    c = max(contours, key=cv2.contourArea)
    mask = np.zeros((h, w), np.uint8)
    cv2.drawContours(mask, [c], -1, 255, -1)
    on_frame = mask > 0
    paraffin = (gray >= 140) & (gray < 240) & on_frame
    dark_px = gray[on_frame & ~paraffin]
    area_pct = float(on_frame.sum()) / img_area * 100.0
    if dark_px.size == 0:
        return {"frame_area_pct": area_pct, "frame_gray": None}
    p10, med, p90 = np.percentile(dark_px, [10, 50, 90])
    in_band = float(((dark_px >= PLASTIC_LOW) & (dark_px <= PLASTIC_HIGH)).sum())
    return {
        "frame_area_pct": area_pct,
        "frame_gray": {
            "p10": int(p10),
            "median": int(med),
            "p90": int(p90),
            "pct_in_80_135": in_band / dark_px.size * 100.0,
        },
    }


def pooled_click_stats(samples: list[dict[str, Any]]) -> Optional[dict[str, int]]:
    if not samples:
        return None
    grays = [s["gray"] for s in samples]
    arr = np.array(grays, dtype=np.int32)
    return {
        "n": len(grays),
        "min": int(arr.min()),
        "p10": int(np.percentile(arr, 10)),
        "median": int(np.median(arr)),
        "p90": int(np.percentile(arr, 90)),
        "max": int(arr.max()),
        "span": int(arr.max() - arr.min()),
    }


def viability_verdict(
        per_set_medians: list[tuple[int, int]],
        pooled_span: int,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    if not per_set_medians:
        return "INSUFFICIENT_DATA", ["No click samples yet."]
    medians = [m for _, m in per_set_medians]
    global_span = max(medians) - min(medians)
    square = [m for sid, m in per_set_medians if sid in (2, 4, 6, 28, 31, 33)]
    portrait = [m for sid, m in per_set_medians if sid in (11, 35, 40, 45)]
    if square and portrait:
        sq_med = int(np.median(square))
        pt_med = int(np.median(portrait))
        if abs(sq_med - pt_med) > 25:
            notes.append(
                f"Square vs portrait median gray differ by {abs(sq_med - pt_med)} "
                f"(square~{sq_med}, portrait~{pt_med}). Consider two JSON profiles.",
            )
    if pooled_span > 40 or global_span > 40:
        notes.append(
            f"Wide gray spread (pooled span={pooled_span}, set medians span="
            f"{global_span}). Single PLASTIC_GRAY band may be weak.",
        )
    if notes:
        return "MIXED_PROFILE", notes
    return "VIABLE_SINGLE_BAND", [
        "Clicks cluster reasonably; proceed with pooled p10/p90 for phone JSON.",
    ]


def build_auto_feasibility_report(pilot: tuple[int, ...]) -> str:
    lines = [
        "# Plastic rim viability (auto probe)",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Auto probe samples dark-frame pixels (not user clicks). "
        "Run interactive `calibrate_plastic_rim.py` to confirm on real plastic.",
        "",
        "| set | size | frame_area% | frame gray p10-med-p90 | % in 80-135 | "
        "largest plastic CC% | passes 15%? |",
        "|-----|------|-------------|------------------------|-------------|"
        "-------------------|------------|",
    ]
    for sid in pilot:
        path = find_silhouette(sid)
        if path is None:
            lines.append(f"| {sid:02d} | missing | | | | | |")
            continue
        bgr = cv2.imread(str(path))
        if bgr is None:
            lines.append(f"| {sid:02d} | read fail | | | | | |")
            continue
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        df = dark_frame_stats(gray)
        pm = plastic_mask_stats(gray, PLASTIC_LOW, PLASTIC_HIGH)
        fg = df.get("frame_gray")
        if fg:
            gstr = f"{fg['p10']}-{fg['median']}-{fg['p90']}"
            in_band = f"{fg['pct_in_80_135']:.1f}"
        else:
            gstr, in_band = "n/a", "n/a"
        pass15 = "Y" if pm["passes_15pct_gate"] else "N"
        lines.append(
            f"| {sid:02d} | {w}x{h} | {df['frame_area_pct']:.1f} | {gstr} | "
            f"{in_band} | {pm['largest_cc_pct']:.1f} | {pass15} |",
        )
        del bgr, gray
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- **passes 15%?** = largest connected component of gray 80-135 fills "
        ">=15% of image (current `plastic_frame` gate).",
        "- Square sets often **fail** despite gray on plastic — mask is fragmented.",
        "- Portrait sets often have **darker** frame gray; 80–135 may not apply.",
        "",
    ])
    return "\n".join(lines)


def sessions_to_json(sessions: list[ImageSession]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source": "iphone_images",
        "updated": datetime.now(timezone.utc).isoformat(),
        "sets": {},
    }
    all_plastic: list[dict[str, Any]] = []
    per_set_medians: list[tuple[int, int]] = []
    for sess in sessions:
        plastic_samples = [sample_at(sess.bgr, x, y) for x, y in sess.plastic_clicks]
        corner_samples = [sample_at(sess.bgr, x, y) for x, y in sess.corner_clicks]
        all_plastic.extend(plastic_samples)
        st = pooled_click_stats(plastic_samples)
        if st:
            per_set_medians.append((sess.set_id, st["median"]))
        gray = cv2.cvtColor(sess.bgr, cv2.COLOR_BGR2GRAY)
        out["sets"][f"set_{sess.set_id:02d}"] = {
            "path": str(sess.path.relative_to(_REPO)),
            "plastic_clicks": plastic_samples,
            "corner_clicks": corner_samples,
            "click_stats": st,
            "auto_plastic_mask": plastic_mask_stats(gray, PLASTIC_LOW, PLASTIC_HIGH),
            "auto_dark_frame": dark_frame_stats(gray),
        }
        del gray
    pooled = pooled_click_stats(all_plastic)
    verdict, notes = viability_verdict(
        per_set_medians,
        pooled["span"] if pooled else 0,
    )
    out["pooled_plastic"] = pooled
    out["viability"] = {"verdict": verdict, "notes": notes}
    if pooled:
        out["suggested_constants"] = {
            "PLASTIC_GRAY_LOW": max(0, pooled["p10"] - 8),
            "PLASTIC_GRAY_HIGH": min(255, pooled["p90"] + 8),
            "_comment": "From click p10/p90 padding; validate with --auto-feasibility",
        }
    return out


def save_artifacts(sessions: list[ImageSession]) -> Path:
    data = sessions_to_json(sessions)
    OUT_CLICKS.parent.mkdir(parents=True, exist_ok=True)
    OUT_CLICKS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Plastic rim viability (clicks + auto)",
        "",
        f"Updated: {data.get('updated', '')}",
        "",
        f"**Verdict:** {data.get('viability', {}).get('verdict', 'n/a')}",
        "",
    ]
    for note in data.get("viability", {}).get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    if pooled := data.get("pooled_plastic"):
        lines.append(
            f"Pooled clicks (n={pooled['n']}): gray "
            f"{pooled['p10']}-{pooled['median']}-{pooled['p90']} "
            f"(span {pooled['span']})",
        )
    if sugg := data.get("suggested_constants"):
        lines.append("")
        lines.append("Suggested JSON keys:")
        lines.append(f"- `PLASTIC_GRAY_LOW`: {sugg['PLASTIC_GRAY_LOW']}")
        lines.append(f"- `PLASTIC_GRAY_HIGH`: {sugg['PLASTIC_GRAY_HIGH']}")
    lines.append("")
    lines.append(f"Raw clicks: `{OUT_CLICKS.relative_to(_REPO)}`")
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return OUT_CLICKS


def run_interactive(sessions: list[ImageSession]) -> int:
    idx = 0
    win = "calibrate_plastic_rim (L=plastic R=corner n=next s=save q=quit)"

    def redraw() -> np.ndarray:
        sess = sessions[idx]
        disp = sess.bgr.copy()
        for x, y in sess.plastic_clicks:
            cv2.circle(disp, (x, y), 8, (0, 255, 0), 2)
        for i, (x, y) in enumerate(sess.corner_clicks):
            cv2.circle(disp, (x, y), 8, (255, 255, 0), 2)
            cv2.putText(
                disp, str(i + 1), (x + 10, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2,
            )
        if len(sess.corner_clicks) >= 2:
            pts = np.array(sess.corner_clicks, dtype=np.int32)
            closed = len(sess.corner_clicks) >= 4
            cv2.polylines(
                disp, [pts], closed, (255, 255, 0), 2, cv2.LINE_AA,
            )
        label = (
            f"set_{sess.set_id:02d} ({idx + 1}/{len(sessions)}) "
            f"plastic={len(sess.plastic_clicks)} corners={len(sess.corner_clicks)}"
        )
        cv2.putText(
            disp, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2,
        )
        return disp

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: Any) -> None:
        sess = sessions[idx]
        if event == cv2.EVENT_LBUTTONDOWN:
            sess.plastic_clicks.append((x, y))
            sess.click_history.append("plastic")
            s = sample_at(sess.bgr, x, y)
            print(f"  plastic @ ({x},{y}) gray={s['gray']} hsv={s['hsv']}")
        elif event == cv2.EVENT_RBUTTONDOWN:
            if len(sess.corner_clicks) >= 4:
                print("  corners full (4); press c to clear and redo")
                return
            sess.corner_clicks.append((x, y))
            sess.click_history.append("corner")
            s = sample_at(sess.bgr, x, y)
            n = len(sess.corner_clicks)
            print(f"  corner {n}/4 @ ({x},{y}) gray={s['gray']}")

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_mouse)

    while True:
        cv2.imshow(win, redraw())
        key = cv2.waitKey(50) & 0xFF
        if key in (ord("q"), 27):
            break
        if key in (ord("n"), ord(" ")):
            idx = (idx + 1) % len(sessions)
            print(f"-> set_{sessions[idx].set_id:02d}")
        elif key == ord("p"):
            idx = (idx - 1) % len(sessions)
            print(f"-> set_{sessions[idx].set_id:02d}")
        elif key == ord("c"):
            sess = sessions[idx]
            sess.corner_clicks.clear()
            sess.click_history = [k for k in sess.click_history if k != "corner"]
            print("  cleared corners on this image")
        elif key == ord("z"):
            sess = sessions[idx]
            if not sess.click_history:
                print("  nothing to undo")
            else:
                kind = sess.click_history.pop()
                if kind == "plastic" and sess.plastic_clicks:
                    x, y = sess.plastic_clicks.pop()
                    print(f"  undo plastic @ ({x},{y})")
                elif kind == "corner" and sess.corner_clicks:
                    x, y = sess.corner_clicks.pop()
                    print(f"  undo corner @ ({x},{y})")
        elif key == ord("s"):
            path = save_artifacts(sessions)
            print(f"Saved {path}")
            print(f"Report {OUT_REPORT}")

    cv2.destroyAllWindows()
    if any(s.plastic_clicks for s in sessions):
        save_artifacts(sessions)
    return 0


def load_sessions(
        pilot: tuple[int, ...],
        set_filter: Optional[int] = None,
) -> list[ImageSession]:
    ids = (set_filter,) if set_filter is not None else pilot
    sessions: list[ImageSession] = []
    for sid in ids:
        path = find_silhouette(sid)
        if path is None:
            print(f"warning: set_{sid:02d} silhouette not found", file=sys.stderr)
            continue
        bgr = cv2.imread(str(path))
        if bgr is None:
            print(f"warning: could not read {path}", file=sys.stderr)
            continue
        sessions.append(ImageSession(set_id=sid, path=path, bgr=bgr))
    return sessions


def main() -> int:
    parser = argparse.ArgumentParser(description="Plastic rim click calibration")
    parser.add_argument(
        "--auto-feasibility",
        action="store_true",
        help="Write auto probe report only (no GUI)",
    )
    parser.add_argument(
        "--set",
        type=int,
        default=None,
        help="Pilot set id only (e.g. 4)",
    )
    args = parser.parse_args()

    if args.auto_feasibility:
        report = build_auto_feasibility_report(FEASIBILITY_PILOT)
        OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        OUT_REPORT.write_text(report, encoding="utf-8")
        print(OUT_REPORT)
        try:
            print(report)
        except UnicodeEncodeError:
            print("(report written; open .md file for full table)")
        return 0

    pilot = DEFAULT_PILOT
    sessions = load_sessions(pilot, args.set)
    if not sessions:
        print("No images loaded.", file=sys.stderr)
        return 1

    print("Interactive calibration on iphone_images/")
    print("  L-click = gray plastic rim")
    print("  R-click = cassette corners in order (1-4, draws quad)")
    print("  n/space = next   p = prev   z = undo   c = clear corners   s = save   q = quit")
    for sess in sessions:
        print(f"  loaded set_{sess.set_id:02d}: {sess.path.name}")
    return run_interactive(sessions)


if __name__ == "__main__":
    raise SystemExit(main())
