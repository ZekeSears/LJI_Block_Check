"""
pair_orphan_slides.py — Match incoming slide JPEGs to existing block silhouettes.

Drop files into iphone_images/incoming/ named like:
  slide_lung_MT_WT1_WO7842.jpeg
  slide_esophagus_HE_TWKO4_WO7842.jpg

Pairing key: (tissue_token, genotype) where tissue_token is `lung`, `lungs`, or
`esophagus` — stain is not used for matching.

Dry run (default):
  python code/pair_orphan_slides.py

Apply renames + block copy into iphone_images/:
  python code/pair_orphan_slides.py --apply
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from project_runtime import missing_dependency_hint, reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

try:
    import phase3_contour_profile as p3cp
except ModuleNotFoundError as exc:
    print(missing_dependency_hint(exc.name or "phase3_contour_profile"), file=sys.stderr)
    raise SystemExit(1) from exc


KNOWN_STAINS = {"HE", "MT", "PAS", "PSRFG", "SMA"}
IMAGE_GLOBS = ("*.jpeg", "*.jpg", "*.JPEG", "*.JPG")


@dataclass
class BlockRef:
    set_id: int
    path: Path
    tissue: str
    genotype: str
    stain: str
    work_order: str


@dataclass
class OrphanSlide:
    path: Path
    tissue: str
    stain: str
    genotype: str
    work_order: str
    pair_key: tuple[str, str]


@dataclass
class PairPlan:
    slide: OrphanSlide
    block: BlockRef
    new_set_id: int
    slide_dest: Path
    block_dest: Path
    barcode_dest: Optional[Path]
    barcode_source: Optional[Path]


def normalize_tissue_token(raw: str) -> Optional[str]:
    """Preserve lung vs lungs; do not collapse to a single tissue class."""
    t = raw.strip().lower()
    if t in ("lung", "lungs", "esophagus"):
        return t
    if "esoph" in t:
        return "esophagus"
    return None


def normalize_genotype(value: str) -> str:
    return value.strip().upper().replace(" ", "")


def normalize_work_order(value: str) -> str:
    v = value.strip().upper()
    if v.startswith("WO"):
        return v
    if v.isdigit():
        return f"WO{v}"
    return v


def parse_orphan_stem(stem: str) -> Optional[dict[str, str]]:
    """Parse slide_<tissue>_<stain>_<genotype>_<workorder> or same without slide_."""
    tokens = stem.split("_")
    if tokens and tokens[0].lower() == "slide":
        tokens = tokens[1:]
    if len(tokens) < 4:
        return None

    tissue_raw, stain, genotype = tokens[0], tokens[1].upper(), tokens[2]
    work_order = normalize_work_order(tokens[3])
    if stain not in KNOWN_STAINS:
        return None

    tissue_token = normalize_tissue_token(tissue_raw)
    if tissue_token is None:
        return None
    if not genotype.strip():
        return None

    return {
        "tissue_token": tissue_token,
        "stain": stain,
        "genotype": normalize_genotype(genotype),
        "work_order": work_order,
    }


def parse_orphan_slide(path: Path) -> Optional[OrphanSlide]:
    meta = parse_orphan_stem(path.stem)
    if meta is None:
        return None
    key = (meta["tissue_token"], meta["genotype"])
    return OrphanSlide(
        path=path,
        tissue=meta["tissue_token"],
        stain=meta["stain"],
        genotype=meta["genotype"],
        work_order=meta["work_order"],
        pair_key=key,
    )


def index_block_silhouettes(images_dir: Path) -> dict[tuple[str, str], list[BlockRef]]:
    index: dict[tuple[str, str], list[BlockRef]] = {}
    seen: set[Path] = set()
    for pattern in IMAGE_GLOBS:
        for path in sorted(images_dir.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen or path.parent.name == "incoming":
                continue
            seen.add(resolved)
            meta = p3cp.parse_image_filename(path.stem)
            if not meta.get("parse_ok") or meta.get("role") != "block_silhouette":
                continue
            tissue_token = normalize_tissue_token(meta.get("tissue", ""))
            genotype = normalize_genotype(meta.get("genotype", ""))
            if tissue_token is None or not genotype:
                continue
            key = (tissue_token, genotype)
            ref = BlockRef(
                set_id=int(meta["set_id"]),
                path=path,
                tissue=tissue_token,
                genotype=genotype,
                stain=(meta.get("stain") or "").upper(),
                work_order=normalize_work_order(meta.get("work_order", "")),
            )
            if ref not in index.get(key, []):
                index.setdefault(key, []).append(ref)
    return index


def next_set_id(images_dir: Path, reserved: set[int]) -> int:
    used = set(reserved)
    for pattern in IMAGE_GLOBS:
        for path in images_dir.rglob(pattern):
            meta = p3cp.parse_image_filename(path.stem)
            if meta.get("parse_ok") and meta.get("set_id") is not None:
                used.add(int(meta["set_id"]))
    n = max(used, default=0) + 1
    while n in reserved:
        n += 1
    return n


def tissue_token_for_filename(tissue_token: str, original_block_stem: str) -> str:
    """Prefer token from source block filename (lung vs lungs)."""
    parts = original_block_stem.split("_")
    for tok in parts:
        if tissue_token == "lung" and tok.lower() == "lung":
            return tok
        if tissue_token == "lungs" and tok.lower() == "lungs":
            return tok
        if tissue_token == "esophagus" and "esoph" in tok.lower():
            return tok
    return tissue_token


def build_dest_names(
        new_set_id: int,
        slide: OrphanSlide,
        block: BlockRef,
) -> tuple[Path, Path, Optional[Path], Optional[Path]]:
    images_dir = block.path.parent
    sid = f"{new_set_id:02d}"
    tissue_tok = tissue_token_for_filename(slide.tissue, block.path.stem)
    geno = slide.genotype
    wo = slide.work_order or block.work_order or "WO7842"
    stain = slide.stain

    slide_name = f"set_{sid}_slide_{tissue_tok}_{stain}_{geno}_{wo}{block.path.suffix}"
    block_name = (
        f"set_{sid}_block_silhouette_{tissue_tok}_{stain}_{geno}_{wo}{block.path.suffix}"
    )
    slide_dest = images_dir / slide_name
    block_dest = images_dir / block_name

    barcode_dest = None
    barcode_source = None
    barcode_name = block_name.replace("block_silhouette", "block_barcode")
    barcode_candidate = block.path.parent / block.path.name.replace(
        "block_silhouette", "block_barcode",
    )
    if barcode_candidate.is_file():
        barcode_source = barcode_candidate
        barcode_dest = images_dir / barcode_name

    return slide_dest, block_dest, barcode_dest, barcode_source


def plan_pairs(
        images_dir: Path,
        incoming_dir: Path,
) -> tuple[list[PairPlan], list[str]]:
    blocks = index_block_silhouettes(images_dir)
    plans: list[PairPlan] = []
    errors: list[str] = []
    reserved_sets: set[int] = set()

    incoming_files: list[Path] = []
    seen_incoming: set[Path] = set()
    for pattern in IMAGE_GLOBS:
        for path in sorted(incoming_dir.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen_incoming:
                continue
            seen_incoming.add(resolved)
            incoming_files.append(path)

    if not incoming_files:
        return plans, [f"No images found in {incoming_dir} — drop JPEGs there first."]

    for path in incoming_files:
        slide = parse_orphan_slide(path)
        if slide is None:
            errors.append(
                f"{path.name}: cannot parse — use "
                "slide_<tissue>_<stain>_<genotype>_<WO>.jpeg "
                "(e.g. slide_lung_MT_WT1_WO7842.jpeg)",
            )
            continue

        matches = blocks.get(slide.pair_key, [])
        if not matches:
            errors.append(
                f"{path.name}: no block_silhouette for "
                f"tissue={slide.pair_key[0]!r} genotype={slide.pair_key[1]!r}",
            )
            continue
        if len(matches) > 1:
            sets = ", ".join(f"set_{m.set_id:02d}" for m in matches)
            errors.append(
                f"{path.name}: ambiguous — multiple blocks ({sets}) share "
                f"tissue={slide.pair_key[0]!r} genotype={slide.pair_key[1]!r}. "
                "Use a more specific genotype (e.g. WT1 not WT).",
            )
            continue

        block = matches[0]
        new_set = next_set_id(images_dir, reserved_sets)
        reserved_sets.add(new_set)
        slide_dest, block_dest, barcode_dest, barcode_source = build_dest_names(
            new_set, slide, block,
        )
        plans.append(PairPlan(
            slide=slide,
            block=block,
            new_set_id=new_set,
            slide_dest=slide_dest,
            block_dest=block_dest,
            barcode_dest=barcode_dest,
            barcode_source=barcode_source,
        ))

    return plans, errors


def print_plan(plans: list[PairPlan], errors: list[str]) -> None:
    if errors:
        print("\n=== Issues ===")
        for line in errors:
            print(f"  - {line}")

    if not plans:
        print("\nNo pairs to apply.")
        return

    print("\n=== Pairing plan (dry run) ===")
    for p in plans:
        print(f"\n  {p.slide.path.name}")
        print(f"    match block: set_{p.block.set_id:02d}  ({p.block.path.name})")
        print(f"    new set:     set_{p.new_set_id:02d}")
        print(f"    -> slide:    {p.slide_dest.name}")
        print(f"    -> block:    {p.block_dest.name}  (copy from existing)")
        if p.barcode_dest and p.barcode_source:
            print(f"    -> barcode:  {p.barcode_dest.name}  (optional copy)")

    print(f"\n{len(plans)} set(s) ready. Re-run with --apply to write files.")


def apply_plan(plans: list[PairPlan], incoming_dir: Path) -> None:
    done_dir = incoming_dir / "processed"
    done_dir.mkdir(exist_ok=True)

    for p in plans:
        if p.slide_dest.exists() or p.block_dest.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing file for set_{p.new_set_id:02d}",
            )
        shutil.copy2(p.block.path, p.block_dest)
        shutil.move(str(p.slide.path), str(p.slide_dest))
        if p.barcode_source and p.barcode_dest:
            shutil.copy2(p.barcode_source, p.barcode_dest)
        dest_in_incoming = done_dir / p.slide.path.name
        if dest_in_incoming.exists():
            dest_in_incoming.unlink()
        print(f"Applied set_{p.new_set_id:02d}: {p.slide_dest.name}")

    print(f"\nDone. {len(plans)} set(s) added under iphone_images/.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pair incoming slides with existing block silhouettes.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy block + move slide into iphone_images/ with set_NN names",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=None,
        help="Main image folder (default: <repo>/iphone_images)",
    )
    parser.add_argument(
        "--incoming-dir",
        type=Path,
        default=None,
        help="Drop folder (default: <images-dir>/incoming)",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    images_dir = args.images_dir or (root / "iphone_images")
    incoming_dir = args.incoming_dir or (images_dir / "incoming")

    if not images_dir.is_dir():
        print(f"Images directory not found: {images_dir}", file=sys.stderr)
        return 1
    incoming_dir.mkdir(parents=True, exist_ok=True)

    plans, errors = plan_pairs(images_dir, incoming_dir)
    print_plan(plans, errors)

    if args.apply:
        if not plans:
            print("\nNothing to apply.", file=sys.stderr)
            return 1
        if errors:
            print(
                f"\nApplying {len(plans)} matched slide(s); "
                f"leaving {len(set(e.split(':')[0] for e in errors if ':' in e))} "
                f"unmatched file(s) in incoming/.",
                file=sys.stderr,
            )
        apply_plan(plans, incoming_dir)
        if errors:
            print("\n=== Still in incoming/ (rephotograph or rename) ===")
            for line in errors:
                print(f"  - {line}")
    elif plans:
        print("\nDry run only — no files changed.")

    if errors and not plans:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
