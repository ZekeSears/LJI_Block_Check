"""
verification_metrics.py — Production-shaped 1-vs-K verification report (leaf).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

import pandas as pd

from phase3_score_diagnostics import (
    compute_score_gaps,
    gaps_by_tissue,
    verification_pass_rate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = REPO_ROOT / "phase3_outputs" / "pipeline_run" / "cross_modal_similarity.csv"
DEFAULT_ROUTING = REPO_ROOT / "phase3_outputs" / "pipeline_run" / "routing_log.csv"
DEFAULT_IMAGES = REPO_ROOT / "iphone_images"
DEFAULT_OUT = REPO_ROOT / "phase3_outputs" / "verification_metrics.md"
CLOSEOUT_MD = REPO_ROOT / "phase3_outputs" / "closeout_summary.md"


def _import_specs():
    sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
    from cross_modal_eval import build_set_pair_specs, tissue_for_spec

    return build_set_pair_specs, tissue_for_spec


def _routing_for_pair(
        routing_df: Optional[pd.DataFrame],
        block_key: str,
        slide_key: str,
) -> str:
    if routing_df is None or routing_df.empty:
        return ""
    rows = routing_df[
        (routing_df["block_group"] == block_key)
        & (routing_df["slide_group"] == slide_key)
    ]
    if rows.empty:
        return ""
    return str(rows.iloc[0].get("routing_decision", ""))


def _branch_breakdown(
        gaps: list,
        routing_df: Optional[pd.DataFrame],
) -> list[str]:
    if routing_df is None or routing_df.empty:
        return ["- (routing_log.csv not available)"]
    pass_branches: dict[str, int] = {}
    fail_branches: dict[str, int] = {}
    for g in gaps:
        branch = _routing_for_pair(routing_df, g.group_key, g.group_key) or "unknown"
        if g.verification_pass:
            pass_branches[branch] = pass_branches.get(branch, 0) + 1
        else:
            fail_branches[branch] = fail_branches.get(branch, 0) + 1
    lines = ["", "### Routing branch on correct pair", "", "**Passes:**"]
    if pass_branches:
        for b, n in sorted(pass_branches.items()):
            lines.append(f"- {b}: {n}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("**Fails:**")
    if fail_branches:
        for b, n in sorted(fail_branches.items()):
            lines.append(f"- {b}: {n}")
    else:
        lines.append("- (none)")
    return lines


def build_verification_markdown(
        sim_df: pd.DataFrame,
        stats: dict[str, Any],
        gaps: list,
        *,
        matrix_path: Path,
        routing_path: Path,
) -> str:
    by_tissue = gaps_by_tissue(gaps)
    closeout_excerpt = ""
    if CLOSEOUT_MD.is_file():
        closeout_excerpt = CLOSEOUT_MD.read_text(encoding="utf-8")

    routing_df = None
    if routing_path.is_file():
        routing_df = pd.read_csv(routing_path)

    lines = [
        "# Verification metrics (QR-claimed match detection)",
        "",
        "Production-shaped check: for each evaluable set, does the claimed block–slide "
        "pair score higher than every other slide in the matrix?",
        "",
        "> There is **no fixed pass-rate bar** for production OK. Report rates beside "
        "retrieval TPR; ~1/30 misses may be acceptable while accuracy is improved.",
        "",
        f"- Matrix: `{matrix_path}`",
        f"- Routing log: `{routing_path}`",
        "",
        "## Global verification",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Passes | {stats['passes']} / {stats['total']} |",
        f"| Pass rate | {stats['rate']:.1%} |",
        f"| Mean gap | {stats['mean_gap']:.4f} |",
        "",
        "## Retrieval TPR (46-way stress test)",
        "",
        "From latest closeout summary:",
        "",
    ]
    for line in closeout_excerpt.splitlines():
        if line.startswith("|") and ("lung" in line or "esophagus" in line or "Tissue" in line):
            lines.append(line)
        if line.startswith("|--------------"):
            lines.append(line)

    lines.extend(["", "## Per-tissue verification", ""])
    for tissue in sorted(by_tissue.keys()):
        tg = by_tissue[tissue]
        p = sum(1 for g in tg if g.verification_pass)
        lines.append(
            f"- **{tissue}**: {p}/{len(tg)} pass ({(p / len(tg) if tg else 0):.1%}), "
            f"mean gap {float(sum(g.gap for g in tg) / len(tg)):.4f}"
        )

    lines.extend(_branch_breakdown(gaps, routing_df))
    lines.append("")
    return "\n".join(lines)


def write_verification_metrics(
        matrix_path: Path = DEFAULT_MATRIX,
        images_dir: Path = DEFAULT_IMAGES,
        out_path: Path = DEFAULT_OUT,
        routing_path: Path = DEFAULT_ROUTING,
) -> Path:
    sim_df = pd.read_csv(matrix_path, index_col=0)
    build_set_pair_specs, tissue_for_spec = _import_specs()
    specs = build_set_pair_specs(images_dir)
    tissue_map = {
        s["group_key"]: tissue_for_spec(s) or "unknown"
        for s in specs
    }
    keys = [s["group_key"] for s in specs]
    stats = verification_pass_rate(sim_df, keys)
    gaps = compute_score_gaps(sim_df, keys, tissue_by_key=tissue_map)
    md = build_verification_markdown(
        sim_df, stats, gaps, matrix_path=matrix_path, routing_path=routing_path,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    return out_path


def main() -> int:
    if not DEFAULT_MATRIX.is_file():
        print(f"Missing matrix: {DEFAULT_MATRIX}", file=sys.stderr)
        return 1
    out = write_verification_metrics()
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
