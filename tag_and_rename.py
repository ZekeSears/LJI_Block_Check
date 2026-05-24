#!/usr/bin/env python3
"""
LJI Histology Image Tagger & Renamer  (v2)
===========================================
Run from the folder containing your images:
    python tag_and_rename.py

Or point it at a specific folder:
    python tag_and_rename.py --folder "C:/path/to/iCloud Photos"

What's new in v2:
  - Metadata (tissue, stain, genotype/animal#, work order) is asked ONCE per set,
    not per image. You only enter the ROLE for each image.
  - Images open in a small windowed viewer (top-right of screen) so the terminal
    stays visible. The previous image auto-closes when the next one opens.
  - Stain is written onto every filename in the set (slide + both block images)
    for consistency with existing sets 01-06.

Workflow per set:
  Image 1 of set -> asks role + full metadata (tissue/stain/genotype/WO)
  Image 2,3      -> asks role only; reuses the set's metadata
  Role repeats   -> new set begins, asks full metadata again

Set numbering starts at 07 (continuing from existing sets 01-06).

Naming convention:
  set_XX_<role>_<tissue>_<stain>_<genotype><animal#>_WO<order>.jpeg
  Optional fields (stain, genotype/animal, work order) omitted if left blank.

Requirements: Python 3.8+, Pillow (pip install pillow). tkinter ships with
standard Python on Windows. If either is missing, the script falls back to the
system default image viewer (no auto-close / no sizing).
"""

import argparse
import csv
import os
import platform
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
START_SET = 7
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG", ".heic", ".HEIC"}

ROLES = ["slide", "block_silhouette", "block_barcode"]
ROLE_SHORTCUTS = {"s": "slide", "bs": "block_silhouette", "bb": "block_barcode",
                  "1": "slide", "2": "block_silhouette", "3": "block_barcode"}

VIEWER_HEIGHT = 750   # pixels — windowed image height; lower this on a small screen


# ── Windowed image viewer ─────────────────────────────────────────────────────
class ImageViewer:
    """Reusable windowed viewer. Call .show(path) per image; .close() at the end.

    Shows each image in a small always-on-top window at the top-right of the
    screen so the terminal stays usable. Reusing one window means the previous
    image is replaced (effectively auto-closed) when a new one is shown.
    Falls back to the OS default viewer if tkinter or Pillow is unavailable.
    """

    def __init__(self):
        self._ok = False
        self._root = None
        self._label = None
        self._photo = None
        try:
            import tkinter as tk
            from PIL import Image, ImageTk
            self._tk = tk
            self._Image = Image
            self._ImageTk = ImageTk
            self._ok = True
        except Exception as e:
            print(f"  [Windowed viewer unavailable ({e}); using system viewer.]")
            self._ok = False

    def show(self, path: Path):
        if not self._ok:
            _open_with_system(path)
            return
        try:
            if self._root is None:
                self._root = self._tk.Tk()
                self._root.title("LJI Image Tagger")
                self._root.attributes("-topmost", True)
                self._label = self._tk.Label(self._root)
                self._label.pack()

            img = self._Image.open(str(path))
            w, h = img.size
            scale = VIEWER_HEIGHT / h
            new_size = (max(1, int(w * scale)), VIEWER_HEIGHT)
            img = img.resize(new_size, self._Image.LANCZOS)

            self._photo = self._ImageTk.PhotoImage(img)
            self._label.configure(image=self._photo)

            self._root.update_idletasks()
            screen_w = self._root.winfo_screenwidth()
            x = max(0, screen_w - new_size[0] - 20)
            self._root.geometry(f"{new_size[0]}x{VIEWER_HEIGHT}+{x}+20")
            self._root.title(f"LJI Image Tagger — {path.name}")
            self._root.update()   # render now, hand control back to the terminal
        except Exception as e:
            print(f"  [Viewer error ({e}); opening with system viewer.]")
            _open_with_system(path)

    def close(self):
        if self._root is not None:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None


def _open_with_system(path: Path):
    """Fallback: open in OS default viewer (cannot auto-close or resize)."""
    try:
        if platform.system() == "Windows":
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"  [Could not open image: {e}]  Open manually: {path}")


# ── Input prompt ──────────────────────────────────────────────────────────────
def prompt(label: str, required: bool = True, options: list = None,
           shortcuts: dict = None, default: str = None) -> str:
    """Prompt for input. Returns '' if optional+skipped, 'q' if user quits."""
    hint_parts = []
    if options:
        hint_parts.append("/".join(options))
    if shortcuts:
        hint_parts.append("shortcuts: " + ", ".join(f"{k}={v}" for k, v in list(shortcuts.items())[:3]))
    if default:
        hint_parts.append(f"default: {default}")
    if not required:
        hint_parts.append("Enter to skip")
    hint = f"  [{', '.join(hint_parts)}]" if hint_parts else ""
    req = " *" if required else "  "

    while True:
        raw = input(f"{req} {label}{hint}: ").strip()
        if raw.lower() == "q":
            return "q"
        if shortcuts and raw.lower() in shortcuts:
            raw = shortcuts[raw.lower()]
        if not raw and default is not None:
            if options:
                match = next((o for o in options if o.lower() == default.lower()), None)
                return match if match else default
            return default
        if not raw and not required:
            return ""
        if options and raw:
            match = next((o for o in options if o.lower() == raw.lower()), None)
            if match:
                return match
            print(f"  -> Enter one of: {', '.join(options)}")
            continue
        if required and not raw:
            print("  -> This field is required.")
            continue
        return raw


def ask_set_metadata(set_num: int) -> dict:
    """Ask the four per-set metadata fields. Returns dict; {'quit': True} if user quits."""
    print(f"\n  --- Metadata for set_{set_num:02d} (applies to all images in this set) ---")

    tissue = prompt("Tissue", required=True, options=["lung", "esophagus"])
    if tissue == "q":
        return {"quit": True}

    stain = prompt("Stain", required=False, options=["HE", "MT", "IF"])
    if stain == "q":
        return {"quit": True}

    print("  (examples: WT3, TWKO5, TWKOB4, NAIVE2)")
    genotype = prompt("Genotype+Animal#", required=False)
    if genotype == "q":
        return {"quit": True}
    genotype = genotype.replace(" ", "").upper()

    work_order = prompt("Work Order", required=False)
    if work_order == "q":
        return {"quit": True}

    return {"tissue": tissue, "stain": stain,
            "genotype_animal": genotype, "work_order": work_order, "quit": False}


def fill_missing_set_metadata(set_num: int, meta: dict) -> dict:
    """Re-prompt only for set-level fields still blank. Returns updated meta or {'quit': True}.

    Tissue is required at set creation and never blank here. Optional fields
    (stain, genotype_animal, work_order) can be supplied later by a downstream
    image in the same set; callers should rebuild prior filenames after this.
    """
    missing = [k for k in ("stain", "genotype_animal", "work_order") if not meta.get(k)]
    if not missing:
        return meta

    print(f"\n  --- Fill in missing metadata for set_{set_num:02d} (Enter to keep blank) ---")
    updated = dict(meta)

    if "stain" in missing:
        v = prompt("Stain", required=False, options=["HE", "MT", "IF"])
        if v == "q":
            return {"quit": True}
        if v:
            updated["stain"] = v

    if "genotype_animal" in missing:
        print("  (examples: WT3, TWKO5, TWKOB4, NAIVE2)")
        v = prompt("Genotype+Animal#", required=False)
        if v == "q":
            return {"quit": True}
        if v:
            updated["genotype_animal"] = v.replace(" ", "").upper()

    if "work_order" in missing:
        v = prompt("Work Order", required=False)
        if v == "q":
            return {"quit": True}
        if v:
            updated["work_order"] = v

    return updated


# ── Filename builder ──────────────────────────────────────────────────────────
def build_filename(set_num: int, role: str, meta: dict, original_ext: str) -> str:
    parts = [f"set_{set_num:02d}", role, meta["tissue"].lower()]
    if meta["stain"]:
        parts.append(meta["stain"].upper())
    if meta["genotype_animal"]:
        parts.append(meta["genotype_animal"].replace(" ", ""))
    if meta["work_order"]:
        wo = meta["work_order"].strip()
        if not wo.upper().startswith("WO"):
            wo = f"WO{wo}"
        parts.append(wo.upper())
    ext = ".jpeg" if original_ext.lower() in (".jpg", ".jpeg") else original_ext.lower()
    return "_".join(parts) + ext


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="LJI Image Tagger & Renamer v2")
    parser.add_argument("--folder", type=Path, default=Path("."),
                        help="Folder with images (default: current directory)")
    parser.add_argument("--start-set", type=int, default=START_SET,
                        help=f"Starting set number (default: {START_SET})")
    parser.add_argument("--no-rename", action="store_true",
                        help="Write CSV only, skip renaming")
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        print(f"ERROR: folder not found: {folder}")
        sys.exit(1)

    images = sorted(
        [f for f in folder.iterdir() if f.suffix in IMAGE_EXTENSIONS],
        key=lambda f: f.name
    )
    if not images:
        print(f"No image files found in {folder}")
        sys.exit(1)

    print(f"\nFound {len(images)} images in {folder}")
    print("\nControls:")
    print("  Role: s=slide, bs=block_silhouette, bb=block_barcode  (or 1/2/3)")
    print("  Enter = skip optional field   |   q = quit and save progress")
    print("  Metadata is asked once per set; role is asked per image.")
    print("  Skipped optional fields can be filled in later from any image in the set.\n")

    start_raw = prompt("Starting set number", required=False,
                       default=str(args.start_set))
    if start_raw == "q":
        print("Quit before starting.")
        return
    try:
        start_set = int(start_raw)
        if start_set < 1:
            raise ValueError
    except ValueError:
        print(f"Invalid set number '{start_raw}'; falling back to {args.start_set:02d}.")
        start_set = args.start_set
    print(f"Starting at set_{start_set:02d}\n")

    viewer = ImageViewer()
    current_set = start_set
    roles_in_set = set()
    set_meta = None
    rows = []
    quit_early = False

    for i, img_path in enumerate(images):
        print(f"\n{'-' * 65}")
        print(f"Image {i+1}/{len(images)}: {img_path.name}   [Set {current_set:02d}]")
        print(f"  Roles in this set so far: {', '.join(sorted(roles_in_set)) or 'none'}")

        viewer.show(img_path)   # replaces (auto-closes) the previous image

        role = prompt("Role", required=True, options=ROLES, shortcuts=ROLE_SHORTCUTS)
        if role == "q":
            quit_early = True
            break

        if role in roles_in_set:
            print(f"  -> '{role}' already in set_{current_set:02d}. Starting set_{current_set+1:02d}.")
            current_set += 1
            roles_in_set = set()
            set_meta = None
        roles_in_set.add(role)

        if set_meta is None:
            set_meta = ask_set_metadata(current_set)
            if set_meta.get("quit"):
                quit_early = True
                break
        else:
            print(f"  (reusing set_{current_set:02d} metadata: "
                  f"{set_meta['tissue']}, {set_meta['stain'] or '-'}, "
                  f"{set_meta['genotype_animal'] or '-'}, {set_meta['work_order'] or '-'})")
            before = (set_meta.get("stain"), set_meta.get("genotype_animal"),
                      set_meta.get("work_order"))
            updated = fill_missing_set_metadata(current_set, set_meta)
            if updated.get("quit"):
                quit_early = True
                break
            after = (updated.get("stain"), updated.get("genotype_animal"),
                     updated.get("work_order"))
            if after != before:
                set_meta = updated
                set_tag = f"{current_set:02d}"
                for r in rows:
                    if r["set"] == set_tag:
                        r["stain"] = set_meta["stain"]
                        r["genotype_animal"] = set_meta["genotype_animal"]
                        r["work_order"] = set_meta["work_order"]
                        orig_ext = Path(r["original_filename"]).suffix
                        new_for_prior = build_filename(current_set, r["role"],
                                                       set_meta, orig_ext)
                        if new_for_prior != r["new_filename"]:
                            print(f"  updated prior: {r['new_filename']} -> {new_for_prior}")
                            r["new_filename"] = new_for_prior

        new_name = build_filename(current_set, role, set_meta, img_path.suffix)
        rows.append({
            "original_filename": img_path.name,
            "set": f"{current_set:02d}",
            "role": role,
            "tissue": set_meta["tissue"],
            "stain": set_meta["stain"],
            "genotype_animal": set_meta["genotype_animal"],
            "work_order": set_meta["work_order"],
            "new_filename": new_name,
        })
        print(f"  OK -> {new_name}")

    viewer.close()

    if not rows:
        print("\nNo images tagged. Nothing to write.")
        return
    if quit_early:
        print(f"\nStopped early — {len(rows)} images tagged so far will still be saved.")

    # Write CSV
    csv_path = folder / "metadata.csv"
    fieldnames = ["original_filename", "set", "role", "tissue", "stain",
                  "genotype_animal", "work_order", "new_filename"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV written: {csv_path}")

    if args.no_rename:
        print("--no-rename set. Done.")
        return

    # Rename preview + confirm
    print("\n" + "=" * 65)
    print("RENAME PREVIEW")
    print("=" * 65)
    for r in rows:
        print(f"  {r['original_filename']}  ->  {r['new_filename']}")
    if input("\nRename all files? [y/N]: ").strip().lower() != "y":
        print("Rename cancelled. CSV saved — review and rename manually if you like.")
        return

    # Collision check
    collisions = [r["new_filename"] for r in rows
                  if (folder / r["new_filename"]).exists()
                  and (folder / r["new_filename"]) != (folder / r["original_filename"])]
    if collisions:
        print("\nWARNING — these target filenames already exist:")
        for c in collisions:
            print(f"  {c}")
        if input("Overwrite them? [y/N]: ").strip().lower() != "y":
            print("Rename cancelled.")
            return

    renamed, errors = 0, []
    for r in rows:
        src = folder / r["original_filename"]
        dst = folder / r["new_filename"]
        try:
            src.rename(dst)
            renamed += 1
        except Exception as e:
            errors.append(f"  {r['original_filename']}: {e}")

    print(f"\nRenamed {renamed}/{len(rows)} files.")
    if errors:
        print("Errors:")
        for e in errors:
            print(e)
    print(f"metadata.csv saved to {csv_path}")
    print("Import metadata.csv to Google Sheets for your records.")


if __name__ == "__main__":
    main()
