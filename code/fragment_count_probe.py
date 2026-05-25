"""
fragment_count_probe.py — Esophagus block vs slide contour_count delta vs hit/miss (leaf).
"""

from __future__ import annotations

import sys
from pathlib import Path

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

import numpy as np
import pandas as pd

from phase3_score_diagnostics import compute_score_gaps

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTOUR_CSV = REPO_ROOT / "phase3_outputs" / "contour_profile.csv"
DEFAULT_MATRIX = REPO_ROOT / "phase3_outputs" / "pipeline_run" / "cross_modal_similarity.csv"
DEFAULT_IMAGES = REPO_ROOT / "iphone_images"
DEFAULT_OUT = REPO_ROOT / "phase3_outputs" / "fragment_count_probe.md"


def _contour_counts_by_set(contour_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Map set_XX -> {block: count, slide: count}."""
    out: dict[str, dict[str, float]] = {}
    for _, row in contour_df.iterrows():
        stem = str(row.get("filename_stem", ""))
        if not stem.startswith("set_"):
            continue
        parts = stem.split("_")
        if len(parts) < 2:
            continue
        key = f"set_{int(parts[1]):02d}"
        role = str(row.get("role", ""))
        if not row.get("measured", False):
            continue
        cnt = row.get("contour_count")
        if pd.isna(cnt):
            continue
        bucket = out.setdefault(key, {})
        if role == "slide":
            bucket["slide"] = float(cnt)
        elif role.startswith("block_"):
            bucket["block"] = float(cnt)
    return out


def write_fragment_count_probe(
        contour_path: Path = CONTOUR_CSV,
        matrix_path: Path = DEFAULT_MATRIX,
        images_dir: Path = DEFAULT_IMAGES,
        out_path: Path = DEFAULT_OUT,
) -> Path:
    sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
    from cross_modal_eval import build_set_pair_specs, tissue_for_spec

    contour_df = pd.read_csv(contour_path)
    counts = _contour_counts_by_set(contour_df)
    sim_df = pd.read_csv(matrix_path, index_col=0)
    specs = build_set_pair_specs(images_dir)
    eso_keys = [
        s["group_key"] for s in specs
        if tissue_for_spec(s) == "esophagus"
    ]
    gaps = {g.group_key: g for g in compute_score_gaps(sim_df, eso_keys)}

    deltas_hit: list[float] = []
    deltas_miss: list[float] = []
    rows_md: list[str] = []

    for key in sorted(eso_keys):
        if key not in gaps:
            continue
        c = counts.get(key, {})
        if "block" not in c or "slide" not in c:
            continue
        delta = abs(c["block"] - c["slide"])
        g = gaps[key]
        hit = g.top3_hit
        if hit:
            deltas_hit.append(delta)
        else:
            deltas_miss.append(delta)
        rows_md.append(
            f"| {key} | {c['block']:.0f} | {c['slide']:.0f} | {delta:.0f} | "
            f"{'hit' if hit else 'miss'} | {g.gap:.3f} |"
        )

    n = len(deltas_hit) + len(deltas_miss)
    corr_note = (
        "Sample size too small for stable correlation; treat as exploratory."
        if n < 10
        else "Compare hit vs miss delta distributions below."
    )

    lines = [
        "# Fragment count probe (esophagus)",
        "",
        "Hypothesis: block vs slide `contour_count` delta may explain esophagus hits.",
        "",
        f"**Note:** {corr_note}",
        "",
        f"- Esophagus evaluable rows: {len(rows_md)}",
        f"- Mean |delta| hits: {np.mean(deltas_hit) if deltas_hit else float('nan'):.1f}",
        f"- Mean |delta| misses: {np.mean(deltas_miss) if deltas_miss else float('nan'):.1f}",
        "",
        "| set | block_count | slide_count | |delta| | top3 | gap |",
        "|-----|-------------|-------------|--------|------|-----|",
        *rows_md,
        "",
        "## Interpretation",
        "",
        "Contour counts use different `clean_mask` roles for block vs slide; large delta "
        "may reflect protocol rather than mismatch. Do not treat count alone as 80% signal "
        "without mentor validation.",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> int:
    if not CONTOUR_CSV.is_file():
        print(f"Missing {CONTOUR_CSV}", file=sys.stderr)
        return 1
    out = write_fragment_count_probe()
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
