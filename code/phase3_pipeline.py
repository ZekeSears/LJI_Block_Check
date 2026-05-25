"""
phase3_pipeline.py — End-to-end cross-modal matching with Phase 3 routing.

Groups images by set_NN (canonical pairing), compares each block silhouette to
each slide via unified_compare. Routing uses contour metrics only (not filename
tissue). Yellow-tag slides get label masking before segmentation.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

from project_runtime import missing_dependency_hint, reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError as exc:
    name = exc.name or "numpy"
    print(missing_dependency_hint(name), file=sys.stderr)
    raise SystemExit(1) from exc

import phase2_descriptors as p2
import phase3_constellation as p3c
import phase3_contour_profile as p3cp
import phase3_label_detection as p3ld
import phase3_unified_matcher as p3u
from phase1_segmentation import load_image
import phase3_block_roi as p3roi


log = logging.getLogger(__name__)


def set_group_key(set_id: int) -> str:
    """Canonical group label for a matched image set."""
    return f"set_{set_id:02d}"


def _select_block_entry(group: list[dict]) -> Optional[dict]:
    sil = [g for g in group if g.get("role") == "block_silhouette"]
    if sil:
        return sil[0]
    blocks = [g for g in group if g.get("role", "").startswith("block")]
    return blocks[0] if blocks else None


def _select_slide_entry(group: list[dict]) -> Optional[dict]:
    slides = [g for g in group if g.get("role") == "slide"]
    return slides[0] if slides else None


def _process_image(path: Path, meta: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not meta.get("parse_ok"):
        return None
    if meta.get("role") == "block_barcode":
        return None

    img = load_image(path)
    if img is None:
        return None

    p3cp.enrich_tissue_fields(meta)
    if meta.get("label_type") == "yellow":
        img = p3ld.apply_label_mask(img)

    seg = p3roi.segment_with_block_roi(img, meta, p2.clean_mask)
    cleaned = seg.cleaned_mask
    contours = seg.contours
    if not contours:
        log.warning("No usable contours after cleaning: %s", path.name)
        return None

    p3cp.enrich_tissue_fields(meta)
    tissue_class = meta.get("tissue_class")
    tissue_token = meta.get("tissue_token")
    set_id = meta.get("set_id")
    if set_id is None:
        return None

    descriptor_rows: list[dict[str, Any]] = []
    for ci, c in enumerate(contours):
        d = p2.compute_descriptors(c)
        d["contour_index"] = ci
        descriptor_rows.append(d)

    sig, sig_meta = p3c.extract_constellation_signature(contours)

    return {
        "path": path,
        "filename": path.name,
        "set_id": int(set_id),
        "group_key": set_group_key(int(set_id)),
        "role": meta.get("role"),
        "tissue_class": tissue_class,
        "tissue_token": tissue_token,
        "tissue_raw": meta.get("tissue", ""),
        "contours": contours,
        "descriptor_rows": descriptor_rows,
        "signature": sig,
        "signature_meta": sig_meta,
        "image": img,
        "cleaned_mask": cleaned,
        **p3roi.roi_fields_from_result(seg, meta=meta),
    }


def run_phase3_pipeline(
        input_dir: Path,
        output_dir: Path,
) -> dict[str, Any]:
    """Build cross-modal similarity matrix using unified_compare."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "visualizations").mkdir(parents=True, exist_ok=True)

    per_image: list[dict[str, Any]] = []
    flat_descriptor_rows: list[dict[str, Any]] = []

    for path in sorted(input_dir.glob("*.jp*g")):
        meta = p3cp.parse_image_filename(path.stem)
        rec = _process_image(path, meta)
        if rec is None:
            continue
        per_image.append(rec)
        for row in rec["descriptor_rows"]:
            flat = dict(row)
            flat["filename"] = rec["filename"]
            flat["group_key"] = rec["group_key"]
            flat["role"] = rec["role"]
            flat["tissue_class"] = rec["tissue_class"]
            flat["tissue_token"] = rec.get("tissue_token")
            flat_descriptor_rows.append(flat)

    if not per_image:
        return {"cross_modal": None, "reason": "no processed images"}

    df = pd.DataFrame(flat_descriptor_rows)
    df.to_csv(output_dir / "descriptors.csv", index=False)

    feature_cols = [c for c in df.columns if c.startswith(("hu_", "zernike_"))
                    or c in {"area", "perimeter", "aspect_ratio",
                             "solidity", "eccentricity"}]
    X = df[feature_cols].to_numpy(dtype=float)
    X_std = p2.standardize_feature_matrix(X)
    df["_row"] = np.arange(len(df))

    by_file: dict[str, np.ndarray] = {}
    for fname, sub in df.groupby("filename"):
        by_file[fname] = X_std[sub["_row"].to_numpy()]

    groups: dict[str, list[dict[str, Any]]] = {}
    for rec in per_image:
        groups.setdefault(rec["group_key"], []).append(rec)

    block_entries: list[dict[str, Any]] = []
    slide_entries: list[dict[str, Any]] = []
    set_records: list[dict[str, Any]] = []

    for group_key, group in sorted(groups.items()):
        block = _select_block_entry(group)
        slide = _select_slide_entry(group)
        tissue_class = None
        tissue_token = None
        for g in group:
            if g.get("tissue_token"):
                tissue_token = g["tissue_token"]
            if g.get("tissue_class"):
                tissue_class = g["tissue_class"]
        set_records.append({
            "group_key": group_key,
            "set_id": group[0]["set_id"],
            "tissue_class": tissue_class,
            "tissue_token": tissue_token,
            "has_block": block is not None,
            "has_slide": slide is not None,
        })
        if block is not None:
            block_entries.append(block)
        if slide is not None:
            slide_entries.append(slide)

    block_labels = [b["group_key"] for b in block_entries]
    slide_labels = [s["group_key"] for s in slide_entries]
    n, m = len(block_entries), len(slide_entries)
    sim = np.zeros((n, m), dtype=float)
    routing_rows: list[dict[str, Any]] = []

    for i, block in enumerate(block_entries):
        bf = by_file.get(block["filename"])
        for j, slide in enumerate(slide_entries):
            sf = by_file.get(slide["filename"])
            if bf is None or sf is None:
                continue
            result = p3u.unified_compare(
                block["contours"],
                slide["contours"],
                bf,
                sf,
                block["signature"],
                slide["signature"],
                role_a="block_silhouette",
                role_b="slide",
            )
            sim[i, j] = result.raw_similarity
            routing_rows.append({
                "block_group": block["group_key"],
                "slide_group": slide["group_key"],
                "routing_decision": result.routing_decision,
                "raw_similarity": result.raw_similarity,
                "routing_uncertain": result.routing_uncertain,
                "notes": result.notes,
            })

    sim_df = pd.DataFrame(sim, index=block_labels, columns=slide_labels)
    sim_df.to_csv(output_dir / "cross_modal_similarity.csv")
    pd.DataFrame(routing_rows).to_csv(output_dir / "routing_log.csv", index=False)
    pd.DataFrame(set_records).to_csv(output_dir / "set_inventory.csv", index=False)

    vis_dir = output_dir / "visualizations"
    for i, block in enumerate(block_entries):
        if m == 0:
            continue
        j_best = int(np.argmax(sim[i]))
        slide = slide_entries[j_best]
        out = vis_dir / f"{block['group_key']}__match__{slide['group_key']}.png"
        try:
            p2.create_pair_visualization(
                block["image"], block["contours"],
                slide["image"], slide["contours"],
                matched_pairs=[],
                out_path=out,
            )
        except Exception as exc:
            log.warning("Visualization failed for %s: %s",
                        block["group_key"], exc)

    for rec in per_image:
        rec.pop("image", None)
        rec.pop("cleaned_mask", None)

    return {
        "cross_modal": (sim_df, block_labels, slide_labels),
        "set_records": set_records,
        "descriptors": df,
    }


def main() -> None:
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(__file__).resolve().parent.parent
    code = run_phase3_pipeline(
        root / "iphone_images",
        root / "phase3_outputs" / "pipeline_run",
    )
    if code.get("cross_modal") is None:
        log.error("Pipeline failed: %s", code.get("reason"))
        sys.exit(1)
    log.info("Phase 3 pipeline complete.")


if __name__ == "__main__":
    main()


__all__ = [
    "set_group_key",
    "run_phase3_pipeline",
]
