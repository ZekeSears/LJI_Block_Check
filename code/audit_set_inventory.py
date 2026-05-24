"""
audit_set_inventory.py — Per-set consistency audit for iphone_images/.

Blocks are unstained; stain tokens on block/barcode filenames are not validated.
Requires agreement on tissue_token, genotype, and work_order across roles.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

import phase3_contour_profile as p3cp

SKIP_DIR_NAMES = frozenset({"incoming", "on_hold"})


def normalize_genotype(value: str) -> str:
    return value.strip().upper().replace(" ", "")


def normalize_work_order(value: str) -> str:
    v = value.strip().upper()
    if v.startswith("WO"):
        return v
    if v.isdigit():
        return f"WO{v}"
    return v


@dataclass
class RoleRecord:
    path: Path
    role: str
    tissue_token: Optional[str]
    genotype: str
    work_order: str
    stain: str
    label_type: str


@dataclass
class SetAudit:
    set_id: int
    roles: list[RoleRecord] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def group_key(self) -> str:
        return f"set_{self.set_id:02d}"


def _skip_path(path: Path, images_root: Path) -> bool:
    try:
        rel = path.relative_to(images_root)
    except ValueError:
        return True
    return any(part in SKIP_DIR_NAMES for part in rel.parts)


def collect_image_paths(images_dir: Path) -> list[Path]:
    root = Path(images_dir)
    paths: list[Path] = []
    for path in p3cp.list_jpeg_paths(root):
        if not _skip_path(path, root):
            paths.append(path)
    return paths


def build_set_audits(images_dir: Path) -> list[SetAudit]:
    by_set: dict[int, SetAudit] = {}
    for path in collect_image_paths(images_dir):
        meta = p3cp.parse_image_filename(path.stem)
        if not meta.get("parse_ok") or meta.get("set_id") is None:
            sid = meta.get("set_id")
            audit = by_set.setdefault(sid or -1, SetAudit(set_id=sid or -1))
            audit.blocking.append(f"parse_fail:{path.name}:{meta.get('parse_error', '')}")
            continue
        p3cp.enrich_tissue_fields(meta)
        sid = int(meta["set_id"])
        audit = by_set.setdefault(sid, SetAudit(set_id=sid))
        audit.roles.append(RoleRecord(
            path=path,
            role=str(meta.get("role", "")),
            tissue_token=meta.get("tissue_token"),
            genotype=normalize_genotype(meta.get("genotype", "")),
            work_order=normalize_work_order(meta.get("work_order", "")),
            stain=str(meta.get("stain", "")),
            label_type=str(meta.get("label_type", "")),
        ))
    return sorted(by_set.values(), key=lambda a: a.set_id)


def audit_set(set_audit: SetAudit) -> None:
    roles = set_audit.roles
    sil = [r for r in roles if r.role == "block_silhouette"]
    slides = [r for r in roles if r.role == "slide"]
    barcodes = [r for r in roles if r.role == "block_barcode"]

    if len(sil) > 1:
        set_audit.blocking.append(f"duplicate_block_silhouette:{len(sil)}")
    if len(slides) > 1:
        set_audit.blocking.append(f"duplicate_slide:{len(slides)}")
    if not sil:
        set_audit.warnings.append("missing_block_silhouette")
    if not slides:
        set_audit.warnings.append("missing_slide")

    tissues = {r.tissue_token for r in roles if r.tissue_token}
    if len(tissues) > 1:
        set_audit.blocking.append(f"tissue_mismatch:{sorted(tissues)}")
    elif roles and not tissues:
        set_audit.warnings.append("missing_tissue_token")

    genotypes = {r.genotype for r in roles if r.genotype}
    if len(genotypes) > 1:
        set_audit.blocking.append(f"genotype_mismatch:{sorted(genotypes)}")

    work_orders = {r.work_order for r in roles if r.work_order}
    if len(work_orders) > 1:
        set_audit.warnings.append(f"work_order_mismatch:{sorted(work_orders)}")

    slide_stains = {r.stain.upper() for r in slides if r.stain}
    if "MT" in slide_stains and "HE" in slide_stains:
        set_audit.warnings.append("mixed_slide_stain:HE_and_MT")


def audit_library(images_dir: Path) -> list[SetAudit]:
    audits = build_set_audits(images_dir)
    for audit in audits:
        audit_set(audit)
    return audits


def audits_to_rows(audits: list[SetAudit]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for audit in audits:
        tissue = ""
        genotype = ""
        work_order = ""
        for r in audit.roles:
            if r.tissue_token:
                tissue = r.tissue_token
            if r.genotype:
                genotype = r.genotype
            if r.work_order:
                work_order = r.work_order
        rows.append({
            "set_id": audit.set_id,
            "group_key": audit.group_key,
            "n_files": len(audit.roles),
            "has_block": any(r.role == "block_silhouette" for r in audit.roles),
            "has_slide": any(r.role == "slide" for r in audit.roles),
            "tissue_token": tissue,
            "genotype": genotype,
            "work_order": work_order,
            "blocking": ";".join(audit.blocking),
            "warnings": ";".join(audit.warnings),
            "evaluable": not audit.blocking and audit.roles
            and any(r.role == "block_silhouette" for r in audit.roles)
            and any(r.role == "slide" for r in audit.roles),
        })
    return rows


def write_audit_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        out_path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(audits: list[SetAudit]) -> None:
    blocking = [a for a in audits if a.blocking]
    warn = [a for a in audits if a.warnings and not a.blocking]
    print(f"Sets scanned: {len(audits)}")
    print(f"Blocking failures: {len(blocking)}")
    for a in blocking[:20]:
        print(f"  {a.group_key}: {', '.join(a.blocking)}")
    if len(blocking) > 20:
        print(f"  ... and {len(blocking) - 20} more")
    print(f"Sets with warnings only: {len(warn)}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit iphone_images set consistency")
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path("iphone_images"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("phase3_outputs/set_inventory_audit.csv"),
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Write CSV (default is summary only)",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    images_dir = root / args.images_dir if not args.images_dir.is_absolute() else args.images_dir
    out_path = root / args.out if not args.out.is_absolute() else args.out

    if not images_dir.is_dir():
        print(f"Missing images dir: {images_dir}", file=sys.stderr)
        return 1

    audits = audit_library(images_dir)
    rows = audits_to_rows(audits)
    print_summary(audits)
    if args.write_csv:
        write_audit_csv(rows, out_path)
        print(f"Wrote {out_path}")
    blocking_n = sum(1 for a in audits if a.blocking)
    return 1 if blocking_n else 0


if __name__ == "__main__":
    sys.exit(main())
