#!/usr/bin/env python3
"""
One-shot rename for iphone_images/ sets 01-06.
Run from the project root:  python rename_existing.py --dry-run
Then without --dry-run to execute.

If set_06 stain should not be 'IF', edit the RENAMES list below before running.
"""
import argparse
import os
import shutil
from pathlib import Path

# Each tuple: (current_name, new_name)
# Convention: set_XX_<role>_<tissue>_<stain>_<genotype><animal#>_WO<order>.jpeg
#   role     : slide | block_silhouette | block_barcode
#   tissue   : lung | esophagus
#   stain    : HE | MT | IF (placeholder — edit if needed)
#   genotype : WT | TWKO
#   animal#  : numeric (1-5) or alphanumeric (B4)
#   WO#      : omitted only when not visible in image

RENAMES = [
    # --- SET 01 — lung, MT, TWKO B4 (no WO# visible on slide label) ---
    ("set_01_slide_lung_MT.jpeg",
     "set_01_slide_lung_MT_TWKOB4.jpeg"),
    ("set_01_block_silhouette_lung_MT.jpeg",
     "set_01_block_silhouette_lung_MT_TWKOB4.jpeg"),
    # set_01 has no block_barcode image — that's OK, not every set needs all three

    # --- SET 02 — lung, HE, WT 3, WO7842 ---
    ("set_02_slide_lung_HE_WT_WO7842.jpeg",
     "set_02_slide_lung_HE_WT3_WO7842.jpeg"),
    ("set_02_block_silhouette_lung_HE_WT_WO7842.jpeg",
     "set_02_block_silhouette_lung_HE_WT3_WO7842.jpeg"),
    ("set_02_block_barcode_lung2_HE_WT_WO7842.jpeg",    # fix "lung2" typo
     "set_02_block_barcode_lung_HE_WT3_WO7842.jpeg"),

    # --- SET 03 — esophagus, HE, TWKO 4, WO7842 ---
    ("set_03_slide_esophagus_HE_TWKO_WO7842.jpeg",
     "set_03_slide_esophagus_HE_TWKO4_WO7842.jpeg"),
    ("set_03_block_silhouette_esophagus_HE_TWKO_WO7842.jpeg",
     "set_03_block_silhouette_esophagus_HE_TWKO4_WO7842.jpeg"),
    ("set_03_block_barcode_esophagus_HE_TWKO_WO7842.jpeg",
     "set_03_block_barcode_esophagus_HE_TWKO4_WO7842.jpeg"),

    # --- SET 04 — lung, HE, WT 2, WO7842 ---
    ("set_04_slide_lungs_HE_WT_WO7842.jpeg",           # fix "lungs"→"lung"
     "set_04_slide_lung_HE_WT2_WO7842.jpeg"),
    ("set_04_block_silhouette_lungs_HE_WT_WO7842.jpeg",
     "set_04_block_silhouette_lung_HE_WT2_WO7842.jpeg"),
    ("set_04_block_barcode_lungs_HE_WT_WO7842.jpeg",   # correct barcode for set_04
     "set_04_block_barcode_lung_HE_WT2_WO7842.jpeg"),
    # MISFILED: this esophagus barcode belongs to set_05 — move it
    ("set_04_block_barcode_esophagus_HE_WT_WO7842.jpeg",
     "set_05_block_barcode_esophagus_HE_WT5_WO7842.jpeg"),

    # --- SET 05 — esophagus, HE, WT 5, WO7842 ---
    ("set_05_slide.jpeg",
     "set_05_slide_esophagus_HE_WT5_WO7842.jpeg"),
    ("set_05_block_silhouette.jpeg",
     "set_05_block_silhouette_esophagus_HE_WT5_WO7842.jpeg"),
    # set_05_block_barcode comes from the misfiled set_04 entry above

    # --- SET 06 — lung, IF (AF647/SMA), TWKO 5, WO7842 ---
    # NOTE: stain is 'IF' (immunofluorescence). Edit to e.g. 'AF647-SMA' if preferred.
    ("set_06_slide.jpeg",
     "set_06_slide_lung_IF_TWKO5_WO7842.jpeg"),
    ("set_06_block_silhouette.jpeg",
     "set_06_block_silhouette_lung_IF_TWKO5_WO7842.jpeg"),
    ("set_06_block_barcode.jpeg",
     "set_06_block_barcode_lung_IF_TWKO5_WO7842.jpeg"),
]


def run(img_dir: Path, dry_run: bool) -> None:
    errors = []
    renames = []

    for old_name, new_name in RENAMES:
        src = img_dir / old_name
        dst = img_dir / new_name

        if not src.exists():
            errors.append(f"  MISSING source: {old_name}")
            continue
        if dst.exists() and src != dst:
            errors.append(f"  CONFLICT — destination already exists: {new_name}")
            continue

        renames.append((src, dst))

    if errors:
        print("ERRORS — fix these before running:")
        for e in errors:
            print(e)
        return

    print(f"{'DRY RUN — ' if dry_run else ''}Renaming {len(renames)} files in {img_dir}\n")
    for src, dst in renames:
        arrow = "→" if src.name != dst.name else "  (unchanged)"
        print(f"  {src.name}")
        if src.name != dst.name:
            print(f"    → {dst.name}")
        if not dry_run and src.name != dst.name:
            shutil.move(str(src), str(dst))

    if dry_run:
        print("\nDry run complete — no files changed. Run without --dry-run to apply.")
    else:
        print(f"\nDone. {len(renames)} files renamed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("iphone_images"),
                        help="Path to iphone_images folder (default: ./iphone_images)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without changing anything")
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(f"ERROR: directory not found: {args.dir}")
    else:
        run(args.dir, args.dry_run)
