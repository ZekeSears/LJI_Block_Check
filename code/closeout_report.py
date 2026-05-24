"""
closeout_report.py — Option B closeout summary from pipeline similarity matrix.

Leaf script: reads phase3_outputs/pipeline_run/cross_modal_similarity.csv when present.
"""

from __future__ import annotations

import sys
from pathlib import Path
from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

try:
    import pandas as pd
except ModuleNotFoundError:
    print("pandas required", file=sys.stderr)
    raise SystemExit(1) from None

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = REPO_ROOT / "phase3_outputs" / "pipeline_run" / "cross_modal_similarity.csv"
DEFAULT_IMAGES = REPO_ROOT / "iphone_images"
DEFAULT_OUT = REPO_ROOT / "phase3_outputs" / "closeout_summary.md"

# Excluded from TPR denominator until lab confirms pairing (plan v2 set_41 default).
TPR_EXCLUDED_SET_IDS: frozenset[int] = frozenset({41})


def _import_eval():
    sys.path.insert(0, str(REPO_ROOT / "code"))
    sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
    from cross_modal_eval import (
        build_set_pair_specs,
        esophagus_evaluable_from_specs,
        lung_evaluable_from_specs,
        lungs_evaluable_from_specs,
        top3_ranking_tpr,
    )
    return (
        build_set_pair_specs,
        lung_evaluable_from_specs,
        lungs_evaluable_from_specs,
        esophagus_evaluable_from_specs,
        top3_ranking_tpr,
    )


def build_closeout_markdown(
        sim_df: pd.DataFrame,
        images_dir: Path,
        *,
        closeout_option: str = "B",
) -> str:
    (
        build_set_pair_specs,
        lung_evaluable_from_specs,
        lungs_evaluable_from_specs,
        esophagus_evaluable_from_specs,
        top3_ranking_tpr,
    ) = _import_eval()

    specs = build_set_pair_specs(images_dir)
    tpr_specs = [
        s for s in specs
        if s.get("set_id") not in TPR_EXCLUDED_SET_IDS
    ]
    excluded = sorted(
        s["group_key"] for s in specs
        if s.get("set_id") in TPR_EXCLUDED_SET_IDS
    )
    lung_keys = lung_evaluable_from_specs(tpr_specs, sim_df, use_set_keys=True)
    lungs_keys = lungs_evaluable_from_specs(tpr_specs, sim_df, use_set_keys=True)
    eso_keys = esophagus_evaluable_from_specs(tpr_specs, sim_df, use_set_keys=True)

    lung_tpr, lung_h, lung_n = top3_ranking_tpr(sim_df, lung_keys)
    lungs_tpr, lungs_h, lungs_n = top3_ranking_tpr(sim_df, lungs_keys)
    eso_tpr, eso_h, eso_n = top3_ranking_tpr(sim_df, eso_keys)

    lines = [
        "# Phase 3 closeout summary (Option B — measurement)",
        "",
        f"Closeout policy: **Option {closeout_option}** — documented TPR; "
        "80% mentor gate remains xfail in integration tests until sign-off.",
        "",
        f"Images: `{images_dir}`",
        f"Matrix shape: {sim_df.shape[0]} blocks × {sim_df.shape[1]} slides",
        "",
        "## Set-paired top-3 TPR (Phase 3)",
        "",
        "| Tissue token | Hits | Total | TPR |",
        "|--------------|------|-------|-----|",
        f"| lung | {lung_h} | {lung_n} | {lung_tpr:.1%} |",
        f"| lungs | {lungs_h} | {lungs_n} | {lungs_tpr:.1%} |",
        f"| esophagus | {eso_h} | {eso_n} | {eso_tpr:.1%} |",
        "",
        "## Notes",
        "",
        "- Sets with zero post-clean contours are excluded when absent from the matrix.",
        "- `lung` and `lungs` are reported separately.",
        "- Yellow-tag slides: APEX SAS adhesive (set 1 only); label mask before segmentation.",
    ]
    if excluded:
        lines.append(
            f"- **TPR excluded sets** (metadata warning): {', '.join(excluded)} "
            "(work-order mismatch pending lab confirmation)."
        )
    lines.append("")
    return "\n".join(lines)


def write_closeout_summary(
        images_dir: Path = DEFAULT_IMAGES,
        matrix_path: Path = DEFAULT_MATRIX,
        out_path: Path = DEFAULT_OUT,
        *,
        closeout_option: str = "B",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not matrix_path.is_file():
        placeholder = (
            "# Phase 3 closeout summary (Option B — measurement)\n\n"
            f"No similarity matrix at `{matrix_path}`.\n\n"
            "Run `python code/phase3_pipeline.py` then re-run this script.\n"
        )
        out_path.write_text(placeholder, encoding="utf-8")
        return out_path

    sim_df = pd.read_csv(matrix_path, index_col=0)
    md = build_closeout_markdown(sim_df, images_dir, closeout_option=closeout_option)
    out_path.write_text(md, encoding="utf-8")
    return out_path


def main() -> int:
    out = write_closeout_summary()
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
