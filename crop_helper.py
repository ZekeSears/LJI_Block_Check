"""
crop_helper.py — Interactive tool to crop iPhone images into single-sample
files with the naming convention required by phase1_segmentation.py.

HOW TO USE:
    python crop_helper.py

    For each raw iPhone image in iPhone_test_images/:
      1. A window shows the full image (scaled to fit your screen).
      2. Draw a rectangle around ONE sample (block or slide).
         - Click and drag to draw.  Press ENTER/SPACE to confirm.
         - Press 'c' to cancel and redraw.
      3. The console asks for: role (block/slide/reference), sample label,
         and stain (for slides only).
      4. The crop is saved to iPhone_test_images/ with the correct filename.
      5. It asks "Another crop from this image? (y/n)".
         Press 'y' to draw another ROI on the same image.
         Press 'n' to move to the next image.
      6. Press 'q' at any time to quit early.

    At the end, all your crops are in iPhone_test_images/ ready for
    phase1_segmentation.py to process.

FILENAME CONVENTION (plan §3.2):
    <original_id>_<role>_<sample_label>[_<stain>].<ext>
    Example: IMG_3084_block_WT5_lungs.jpg
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2


INPUT_DIR = Path("./iPhone_test_images/")
KNOWN_STAINS = {"HE", "MT", "PAS", "PSRFG"}
KNOWN_ROLES = {"block", "slide", "reference"}

# Image metadata from the README — shown as hints so the user doesn't
# have to remember what each image contains.
IMAGE_HINTS = {
    "IMG_3080.jpg":  "3 esophagus BLOCKS arranged on backlight",
    "IMG_3081.jpg":  "3 esophagus BLOCKS in vertical arrangement",
    "IMG_3084.jpg":  "PAIRED — Lung BLOCK + SLIDE (WT 5 Lungs HDM, HE). Best clean pair.",
    "IMG_3085.jpg":  "PAIRED — Esophagus BLOCK + SLIDE (WT 4, HE). Tiny fragments.",
    "IMG_3086.jpg":  "PAIRED — Esophagus BLOCK + SLIDE (WT 3, HE). Tiny fragments.",
    "IMG_3087.jpg":  "PAIRED — Esophagus BLOCK + SLIDE (WT 2, HE). HAS MOUNTING ARTIFACT.",
    "IMG_3088.jpg":  "PAIRED — Esophagus BLOCK + SLIDE (WT 1, HE). Tiny fragments.",
    "IMG_3089.jpg":  "PAIRED — Esophagus BLOCK + SLIDE (TWKO 5, HE). Single small fragment.",
    "IMG_3090.jpg":  "REFERENCE — Block tray inventory. Rename and skip.",
    "IMG_3091.jpeg": "4 lung SLIDES (TWKO B1-B4, all MT stain).",
    "IMG_3092.jpeg": "4 lung SLIDES: TWKO A4/A3 (MT), TWKO B4 (HE), HDM A5 (HE). Mixed stains.",
}


def prompt_metadata(original_stem: str) -> dict | None:
    """Ask the user for role, label, and stain via the console.

    Returns a dict with keys {role, sample_label, stain, output_name},
    or None if the user wants to skip/cancel.
    """
    print()
    print(f"  Crop from: {original_stem}")
    print("  Roles: block, slide, reference")

    role = input("  Role (block/slide/reference): ").strip().lower()
    if role == "q":
        return None
    if role not in KNOWN_ROLES:
        print(f"  Unknown role '{role}'. Skipping this crop.")
        return None

    if role == "reference":
        label = input("  Label (e.g. 'tray'): ").strip()
        if not label:
            label = "tray"
        out_name = f"{original_stem}_reference_{label}"
        return {"role": role, "sample_label": label, "stain": "",
                "output_name": out_name}

    label = input("  Sample label (e.g. 'WT5_lungs'): ").strip()
    if not label:
        print("  Empty label. Skipping.")
        return None

    stain = ""
    if role == "slide":
        stain_opts = ", ".join(sorted(KNOWN_STAINS))
        stain = input(f"  Stain ({stain_opts}, or ENTER for none): ").strip().upper()
        if stain and stain not in KNOWN_STAINS:
            print(f"  Unknown stain '{stain}'. Saving without stain suffix.")
            stain = ""

    # Build filename
    parts = [original_stem, role, label]
    if stain:
        parts.append(stain)
    out_name = "_".join(parts)

    return {"role": role, "sample_label": label, "stain": stain,
            "output_name": out_name}


# Target display size — the image is scaled to fit inside this box
# while keeping aspect ratio.  ROI coordinates are mapped back to the
# original full-resolution image so crops are always full-quality.
MAX_DISPLAY_W = 1200
MAX_DISPLAY_H = 800


def _fit_to_display(img):
    """Return (display_img, scale_factor).

    display_img fits inside MAX_DISPLAY_W x MAX_DISPLAY_H.
    scale_factor converts display-pixel coords back to original pixels:
        original_coord = int(display_coord / scale_factor)
    """
    h, w = img.shape[:2]
    scale = min(MAX_DISPLAY_W / w, MAX_DISPLAY_H / h, 1.0)
    if scale < 1.0:
        new_w = int(w * scale)
        new_h = int(h * scale)
        display = cv2.resize(img, (new_w, new_h),
                             interpolation=cv2.INTER_AREA)
    else:
        display = img.copy()
        scale = 1.0
    return display, scale


def process_one_image(filepath: Path) -> bool:
    """Show the image and let the user crop repeatedly.

    Returns False if the user pressed 'q' to quit entirely.
    """
    img = cv2.imread(str(filepath))
    if img is None:
        print(f"  Could not read {filepath.name}, skipping.")
        return True

    original_stem = filepath.stem
    ext = filepath.suffix  # keep original extension

    hint = IMAGE_HINTS.get(filepath.name, "")
    h_orig, w_orig = img.shape[:2]
    display, scale = _fit_to_display(img)
    h_disp, w_disp = display.shape[:2]

    print()
    print("=" * 70)
    print(f"IMAGE: {filepath.name}")
    if hint:
        print(f"  HINT: {hint}")
    print(f"  Original: {w_orig}x{h_orig} px  |  "
          f"Display: {w_disp}x{h_disp} px  (scale {scale:.2f})")
    print("  Draw a rectangle around ONE sample, then press ENTER/SPACE.")
    print("  Press 'c' to cancel/redraw. Press ESC to skip this image.")
    print("=" * 70)

    crop_count = 0
    while True:
        window_name = (f"{filepath.name} — draw ROI, "
                       "ENTER to confirm, ESC to skip")
        roi = cv2.selectROI(window_name, display,
                            showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(window_name)

        dx, dy, dw, dh = roi
        if dw == 0 or dh == 0:
            print("  No ROI selected (ESC or zero-size box). "
                  "Skipping image.")
            break

        # Map display coords back to original resolution.
        x = int(dx / scale)
        y = int(dy / scale)
        w = int(dw / scale)
        h = int(dh / scale)
        # Clamp to image bounds.
        x = max(0, min(x, w_orig - 1))
        y = max(0, min(y, h_orig - 1))
        w = min(w, w_orig - x)
        h = min(h, h_orig - y)

        crop = img[y:y+h, x:x+w]

        # Show crop preview scaled to fit too.
        preview, _ = _fit_to_display(crop)
        preview_name = "Crop preview — press any key"
        cv2.imshow(preview_name, preview)
        cv2.waitKey(1500)
        cv2.destroyWindow(preview_name)

        meta = prompt_metadata(original_stem)
        if meta is None:
            resp = input("  Skip this crop or quit? "
                         "(s=skip / q=quit): ").strip().lower()
            if resp == "q":
                return False
            continue

        out_path = filepath.parent / f"{meta['output_name']}{ext}"
        cv2.imwrite(str(out_path), crop)
        crop_count += 1
        print(f"  SAVED: {out_path.name}  ({w}x{h} px, full-res)")

        again = input("  Another crop from this image? "
                      "(y/n/q): ").strip().lower()
        if again == "q":
            return False
        if again != "y":
            break

    print(f"  {crop_count} crop(s) saved from {filepath.name}.")
    return True


def main():
    if not INPUT_DIR.is_dir():
        print(f"Error: {INPUT_DIR} not found.")
        sys.exit(1)

    # Only process the original raw images (no underscores after IMG_XXXX)
    # so we don't re-process previously cropped outputs.
    candidates = sorted(
        p for p in INPUT_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        and p.name in IMAGE_HINTS  # only known raw images
    )

    print(f"\nFound {len(candidates)} raw images to crop.")
    print("Process them in order. Press 'q' at any prompt to quit early.\n")

    for path in candidates:
        if not process_one_image(path):
            print("\nQuitting early.")
            break

    cv2.destroyAllWindows()

    # Show what was created
    all_files = sorted(INPUT_DIR.glob("*"))
    cropped = [f for f in all_files if f.name not in IMAGE_HINTS
               and f.suffix.lower() in {".jpg", ".jpeg", ".png"}
               and f.name != "README.md"]
    print(f"\n{'=' * 70}")
    print(f"Done! {len(cropped)} cropped file(s) in {INPUT_DIR}:")
    for f in cropped:
        print(f"  {f.name}")
    print("\nRun the pipeline:  python code/phase1_segmentation.py")


if __name__ == "__main__":
    main()
