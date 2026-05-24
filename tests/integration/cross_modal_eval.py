"""
Shared cross-modal ranking metrics for integration tests.

Set pairing: ground truth is block silhouette + slide from the same set_NN.
Phase 3 matrices use set_XX row/column labels; Phase 2 uses sample_label
strings — use set_label_paired_top3_tpr for Phase 2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional


def is_lung_tissue(tissue: str | None) -> bool:
    """Single-lobe lung token only (not lungs)."""
    return tissue == "lung"


def is_lungs_tissue(tissue: str | None) -> bool:
    return tissue == "lungs"


def is_lung_family_tissue(tissue: str | None) -> bool:
    """lung or lungs token (Phase 2 historical baselines used collapsed 'lung')."""
    return tissue in ("lung", "lungs")


def is_esophagus_tissue(tissue: str | None) -> bool:
    if not tissue:
        return False
    return tissue == "esophagus"


def tissue_for_spec(spec: dict) -> str | None:
    """Prefer raw tissue_token; fall back to collapsed tissue_class."""
    tok = spec.get("tissue_token")
    if tok:
        return tok
    return spec.get("tissue_class")


def set_group_key(set_id: int) -> str:
    return f"set_{set_id:02d}"


def build_set_pair_specs(images_dir: Path) -> list[dict]:
    """Inventory of sets with block/slide sample_labels and tissue tokens."""
    from phase1_segmentation import parse_filename
    import phase3_contour_profile as p3cp

    groups: dict[str, dict] = {}
    for path in sorted(Path(images_dir).glob("*.jp*g")):
        try:
            meta1 = parse_filename(path)
        except ValueError:
            continue
        meta3 = p3cp.parse_image_filename(path.stem)
        if not meta3.get("parse_ok") or meta3.get("set_id") is None:
            continue
        p3cp.enrich_tissue_fields(meta3)
        key = set_group_key(int(meta3["set_id"]))
        entry = groups.setdefault(key, {
            "group_key": key,
            "set_id": int(meta3["set_id"]),
            "tissue_class": None,
            "tissue_token": None,
            "has_block": False,
            "has_slide": False,
            "block_label": None,
            "slide_label": None,
        })
        if meta3.get("tissue_token"):
            entry["tissue_token"] = meta3["tissue_token"]
        if meta3.get("tissue_class"):
            entry["tissue_class"] = meta3["tissue_class"]
        role = meta3.get("role")
        if role == "block_silhouette":
            entry["has_block"] = True
            entry["block_label"] = meta1["sample_label"]
        elif role == "slide":
            entry["has_slide"] = True
            entry["slide_label"] = meta1["sample_label"]

    return [groups[k] for k in sorted(groups)]


def evaluable_set_specs(
        specs: list[dict],
        sim_df,
        *,
        tissue_predicate=None,
        use_set_keys: bool = False,
) -> list[dict]:
    """Specs whose block and slide both appear in the similarity matrix."""
    out: list[dict] = []
    for s in specs:
        if not s.get("has_block") or not s.get("has_slide"):
            continue
        if tissue_predicate is not None and not tissue_predicate(tissue_for_spec(s)):
            continue
        if use_set_keys:
            key = s["group_key"]
            if key not in sim_df.index or key not in sim_df.columns:
                continue
        else:
            if (s.get("block_label") not in sim_df.index
                    or s.get("slide_label") not in sim_df.columns):
                continue
        out.append(s)
    return out


def set_label_paired_top3_tpr(
        sim_df,
        specs: list[dict],
        *,
        tissue_predicate=None,
) -> tuple[float, int, int]:
    """Top-3 TPR when matrix rows/cols are Phase 2 sample_label strings."""
    evaluable = evaluable_set_specs(
        specs, sim_df, tissue_predicate=tissue_predicate, use_set_keys=False,
    )
    if not evaluable:
        return 0.0, 0, 0

    hits = 0
    for spec in evaluable:
        row = sim_df.loc[spec["block_label"]].sort_values(ascending=False)
        if spec["slide_label"] in list(row.index[:3]):
            hits += 1
    total = len(evaluable)
    return hits / total, hits, total


def top3_ranking_tpr(
        sim_df,
        evaluable_groups: Iterable[str],
) -> tuple[float, int, int]:
    """Top-3 TPR when row/column labels are the same set_XX key."""
    evaluable = [
        key for key in evaluable_groups
        if key in sim_df.index and key in sim_df.columns
    ]
    if not evaluable:
        return 0.0, 0, 0

    hits = 0
    for key in evaluable:
        row = sim_df.loc[key].sort_values(ascending=False)
        if key in list(row.index[:3]):
            hits += 1
    total = len(evaluable)
    return hits / total, hits, total


def lung_evaluable_from_specs(
        specs: list[dict],
        sim_df,
        *,
        use_set_keys: bool,
) -> list[str]:
    rows = evaluable_set_specs(
        specs, sim_df, tissue_predicate=is_lung_tissue, use_set_keys=use_set_keys,
    )
    if use_set_keys:
        return [r["group_key"] for r in rows]
    return rows


def lungs_evaluable_from_specs(
        specs: list[dict],
        sim_df,
        *,
        use_set_keys: bool,
) -> list[str]:
    rows = evaluable_set_specs(
        specs, sim_df, tissue_predicate=is_lungs_tissue, use_set_keys=use_set_keys,
    )
    if use_set_keys:
        return [r["group_key"] for r in rows]
    return rows


def esophagus_evaluable_from_specs(
        specs: list[dict],
        sim_df,
        *,
        use_set_keys: bool,
) -> list[str]:
    rows = evaluable_set_specs(
        specs, sim_df,
        tissue_predicate=is_esophagus_tissue,
        use_set_keys=use_set_keys,
    )
    if use_set_keys:
        return [r["group_key"] for r in rows]
    return rows
