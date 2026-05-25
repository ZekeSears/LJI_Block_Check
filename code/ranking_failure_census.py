"""
ranking_failure_census.py — Full ranking failure table with genotype confound (leaf).
"""

from __future__ import annotations

import sys
from pathlib import Path

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

import pandas as pd

from audit_set_inventory import normalize_genotype
from phase3_score_diagnostics import compute_score_gaps

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = REPO_ROOT / "phase3_outputs" / "pipeline_run" / "cross_modal_similarity.csv"
DEFAULT_ROUTING = REPO_ROOT / "phase3_outputs" / "pipeline_run" / "routing_log.csv"
DEFAULT_IMAGES = REPO_ROOT / "iphone_images"
DEFAULT_OUT = REPO_ROOT / "phase3_outputs" / "ranking_failure_notes.md"

import phase3_contour_profile as p3cp


def build_genotype_cache(images_dir: Path) -> dict[int, str]:
    cache: dict[int, str] = {}
    for path in p3cp.list_jpeg_paths(images_dir):
        meta = p3cp.parse_image_filename(path.stem)
        if not meta.get("parse_ok") or meta.get("set_id") is None:
            continue
        sid = int(meta["set_id"])
        if sid in cache:
            continue
        g = meta.get("genotype", "")
        if g:
            cache[sid] = normalize_genotype(g)
    return cache


def _routing_for_pair(routing_df: pd.DataFrame, block_key: str, slide_key: str) -> str:
    rows = routing_df[
        (routing_df["block_group"] == block_key)
        & (routing_df["slide_group"] == slide_key)
    ]
    if rows.empty:
        return ""
    return str(rows.iloc[0].get("routing_decision", ""))


def failure_class(gap_row) -> str:
    if gap_row.top3_hit:
        return "—"
    if gap_row.gap > 0:
        return "rank_miss"
    return "wrong_score"


def build_failure_notes_markdown(
        gaps: list,
        *,
        routing_df: pd.DataFrame,
        images_dir: Path,
        genotype_cache: dict[int, str],
) -> str:
    by_tissue: dict[str, list] = {}
    for g in gaps:
        tok = g.tissue_token or "unknown"
        by_tissue.setdefault(tok, []).append(g)

    lines = [
        "# Phase 3 ranking failure notes",
        "",
        "Generated from pipeline_run after plan v2 implementation (label-keyed gaps).",
        "",
        "Router source: geometry_k2 calibrated JSON (see router_constants.json).",
        "set_01 slide excluded from matrix (zero contours after label mask).",
        "set_41 included in TPR denominator (plan v2 re-inclusion).",
        "",
    ]

    for tissue in sorted(by_tissue.keys()):
        rows = sorted(by_tissue[tissue], key=lambda g: g.group_key)
        lines.extend([
            f"## {tissue}",
            "",
            "| set | result | gap | routing (correct pair) | routing (wrong top1) | "
            "same genotype | failure class | top1 |",
            "|-----|--------|-----|--------------------------|----------------------|"
            "---------------|---------------|------|",
        ])
        for g in rows:
            sid = int(g.group_key.split("_")[1])
            true_geno = genotype_cache.get(sid, "")
            wrong_sid = int(g.wrong_top1_key.split("_")[1]) if g.wrong_top1_key.startswith("set_") else 0
            wrong_geno = genotype_cache.get(wrong_sid, "") if wrong_sid else ""
            same_geno = (
                true_geno and wrong_geno and true_geno == wrong_geno
            )
            route_ok = _routing_for_pair(routing_df, g.group_key, g.group_key)
            route_wrong = _routing_for_pair(routing_df, g.group_key, g.wrong_top1_key)
            result = "hit" if g.top3_hit else "miss"
            lines.append(
                f"| {g.group_key} | {result} | {g.gap:.3f} | {route_ok} | {route_wrong} | "
                f"{'yes' if same_geno else 'no'} | {failure_class(g)} | top1={g.wrong_top1_key} |"
            )
        lines.append("")

    return "\n".join(lines)


def write_ranking_failure_notes(
        matrix_path: Path = DEFAULT_MATRIX,
        images_dir: Path = DEFAULT_IMAGES,
        out_path: Path = DEFAULT_OUT,
        routing_path: Path = DEFAULT_ROUTING,
) -> Path:
    sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
    from cross_modal_eval import build_set_pair_specs, tissue_for_spec

    sim_df = pd.read_csv(matrix_path, index_col=0)
    specs = build_set_pair_specs(images_dir)
    tissue_map = {s["group_key"]: tissue_for_spec(s) or "unknown" for s in specs}
    keys = [s["group_key"] for s in specs]
    gaps = compute_score_gaps(sim_df, keys, tissue_by_key=tissue_map)
    routing_df = pd.read_csv(routing_path) if routing_path.is_file() else pd.DataFrame()
    geno_cache = build_genotype_cache(images_dir)
    md = build_failure_notes_markdown(
        gaps, routing_df=routing_df, images_dir=images_dir, genotype_cache=geno_cache,
    )
    out_path.write_text(md, encoding="utf-8")
    return out_path


def main() -> int:
    if not DEFAULT_MATRIX.is_file():
        print(f"Missing matrix: {DEFAULT_MATRIX}", file=sys.stderr)
        return 1
    out = write_ranking_failure_notes()
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
