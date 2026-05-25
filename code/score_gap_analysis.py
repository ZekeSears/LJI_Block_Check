"""
score_gap_analysis.py — Score-gap gate report and calibration histograms (leaf).

Reads pipeline similarity matrix; writes score_separation_report.md and PNGs.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from project_runtime import reexec_if_project_venv_available

reexec_if_project_venv_available(__file__)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd

from phase3_score_diagnostics import (
    DEFAULT_GATE_THRESHOLD,
    SENSITIVITY_THRESHOLDS,
    compute_score_gaps,
    fraction_gap_positive,
    gap_median,
    gap_percentiles,
    gate_verdict,
    gaps_by_tissue,
    sensitivity_at_thresholds,
    warn_if_matrix_stale,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = REPO_ROOT / "phase3_outputs" / "pipeline_run" / "cross_modal_similarity.csv"
DEFAULT_IMAGES = REPO_ROOT / "iphone_images"
DEFAULT_OUT = REPO_ROOT / "phase3_outputs" / "score_separation_report.md"
HIST_DIR = REPO_ROOT / "phase3_outputs" / "calibration_histograms"
AUDIT_CSV = REPO_ROOT / "phase3_outputs" / "set_inventory_audit.csv"
CLOSEOUT_MD = REPO_ROOT / "phase3_outputs" / "closeout_summary.md"


def _import_specs():
    sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
    from cross_modal_eval import build_set_pair_specs, tissue_for_spec

    return build_set_pair_specs, tissue_for_spec


def tissue_map_from_specs(specs: list[dict]) -> dict[str, str]:
    _, tissue_for_spec = _import_specs()
    return {
        s["group_key"]: tissue_for_spec(s) or "unknown"
        for s in specs
        if s.get("group_key")
    }


def _read_sets_scanned() -> Optional[int]:
    if not AUDIT_CSV.is_file():
        return None
    try:
        df = pd.read_csv(AUDIT_CSV)
        return len(df)
    except (OSError, pd.errors.EmptyDataError):
        return None


def _closeout_tpr_lines() -> list[str]:
    if not CLOSEOUT_MD.is_file():
        return ["- (closeout_summary.md not found — run closeout_report.py)"]
    text = CLOSEOUT_MD.read_text(encoding="utf-8")
    lines = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| lung"):
            in_table = True
        if in_table and line.startswith("|"):
            lines.append(line)
        if in_table and line.strip() == "" and lines:
            break
    return lines or ["- (TPR table not found in closeout summary)"]


def build_score_separation_markdown(
        sim_df: pd.DataFrame,
        gaps: list,
        *,
        matrix_path: Path,
        images_dir: Path,
        threshold: float = DEFAULT_GATE_THRESHOLD,
) -> str:
    verdict = gate_verdict(gaps, threshold=threshold)
    pct = gap_percentiles(gaps)
    med = gap_median(gaps)
    pos_frac = fraction_gap_positive(gaps)
    sens = sensitivity_at_thresholds(gaps, SENSITIVITY_THRESHOLDS)
    by_tissue = gaps_by_tissue(gaps)

    mtime = datetime.fromtimestamp(
        matrix_path.stat().st_mtime, tz=timezone.utc,
    ).strftime("%Y-%m-%d %H:%M UTC")
    sets_scanned = _read_sets_scanned()

    lines = [
        "# Score separation report (Phase 3 signal gate)",
        "",
        "## Provenance",
        "",
        f"- Matrix: `{matrix_path}`",
        f"- Matrix mtime: {mtime}",
        f"- Shape: {sim_df.shape[0]} blocks × {sim_df.shape[1]} slides",
        f"- Images: `{images_dir}`",
        f"- Sets scanned (audit): {sets_scanned if sets_scanned is not None else 'unknown'}",
        f"- Evaluable sets (label-keyed gaps): {len(gaps)}",
        f"- Gate threshold (provisional): **{threshold}** on `raw_similarity`",
        "",
        "## Retrieval TPR (stress test; from closeout)",
        "",
        *_closeout_tpr_lines(),
        "",
        "## Global gap statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Median gap | {med:.4f} |",
        f"| p10 | {pct['p10']:.4f} |",
        f"| p50 | {pct['p50']:.4f} |",
        f"| p90 | {pct['p90']:.4f} |",
        f"| % sets with gap > 0 | {pos_frac:.1%} |",
        "",
        "## Gate verdict",
        "",
        f"**{verdict}**",
        "",
        "> 0.01 is Zeke's working default for automation, not mentor-approved. "
        "Current library is expected to show SIGNAL_MISSING until signal improves. "
        "Mentor may choose a data-driven cutoff from the sensitivity table below.",
        "",
        "## Sensitivity (fraction of sets with gap ≥ threshold)",
        "",
        "| Threshold | Fraction ≥ |",
        "|-----------|------------|",
    ]
    for row in sens:
        lines.append(f"| {row['threshold']:.2f} | {row['fraction_ge']:.1%} |")

    lines.extend(["", "## Per-tissue gap statistics", ""])
    for tissue in sorted(by_tissue.keys()):
        tg = by_tissue[tissue]
        tp = gap_percentiles(tg)
        lines.extend([
            f"### {tissue} (n={len(tg)})",
            "",
            f"- Median gap: {gap_median(tg):.4f}",
            f"- p10 / p50 / p90: {tp['p10']:.4f} / {tp['p50']:.4f} / {tp['p90']:.4f}",
            f"- % gap > 0: {fraction_gap_positive(tg):.1%}",
            "",
        ])

    lines.extend([
        "## Histograms",
        "",
        f"- `{HIST_DIR / 'score_gap_by_tissue.png'}`",
        f"- `{HIST_DIR / 'correct_vs_wrong_score_scatter.png'}`",
        "",
    ])
    return "\n".join(lines)


def write_gap_histograms(gaps: list, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    by_tissue = gaps_by_tissue(gaps)
    if not gaps:
        return paths

    fig, axes = plt.subplots(1, max(1, len(by_tissue)), figsize=(4 * max(1, len(by_tissue)), 3))
    if len(by_tissue) == 1:
        axes = [axes]
    for ax, (tissue, rows) in zip(axes, sorted(by_tissue.items())):
        vals = [r.gap for r in rows]
        ax.hist(vals, bins=min(15, max(5, len(vals))), edgecolor="black", alpha=0.7)
        ax.set_title(f"gap — {tissue} (n={len(vals)})")
        ax.axvline(0, color="red", linestyle="--", linewidth=1)
        ax.axvline(DEFAULT_GATE_THRESHOLD, color="green", linestyle=":", linewidth=1)
    fig.tight_layout()
    p1 = out_dir / "score_gap_by_tissue.png"
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    paths.append(p1)

    fig2, ax2 = plt.subplots(figsize=(5, 5))
    correct = [g.correct_score for g in gaps]
    wrong = [g.best_wrong_score for g in gaps]
    ax2.scatter(wrong, correct, alpha=0.6, s=30)
    lims = [0, 1]
    ax2.plot(lims, lims, "r--", label="y=x")
    ax2.set_xlabel("best wrong score")
    ax2.set_ylabel("correct pair score")
    ax2.set_title("correct vs best-wrong")
    ax2.legend()
    fig2.tight_layout()
    p2 = out_dir / "correct_vs_wrong_score_scatter.png"
    fig2.savefig(p2, dpi=120)
    plt.close(fig2)
    paths.append(p2)
    return paths


def run_score_gap_analysis(
        matrix_path: Path = DEFAULT_MATRIX,
        images_dir: Path = DEFAULT_IMAGES,
        out_path: Path = DEFAULT_OUT,
        *,
        threshold: float = DEFAULT_GATE_THRESHOLD,
) -> dict[str, Any]:
    if not matrix_path.is_file():
        raise FileNotFoundError(f"Missing similarity matrix: {matrix_path}")

    stale = warn_if_matrix_stale(matrix_path, images_dir)
    if stale:
        print(stale, file=sys.stderr)

    sim_df = pd.read_csv(matrix_path, index_col=0)
    build_set_pair_specs, _ = _import_specs()
    specs = build_set_pair_specs(images_dir)
    tissue_map = tissue_map_from_specs(specs)
    all_keys = [s["group_key"] for s in specs]
    gaps = compute_score_gaps(sim_df, all_keys, tissue_by_key=tissue_map)

    HIST_DIR.mkdir(parents=True, exist_ok=True)
    write_gap_histograms(gaps, HIST_DIR)

    md = build_score_separation_markdown(
        sim_df, gaps, matrix_path=matrix_path, images_dir=images_dir, threshold=threshold,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    verdict = gate_verdict(gaps, threshold=threshold)
    print(verdict)
    return {"verdict": verdict, "gaps": gaps, "report_path": out_path}


def main() -> int:
    try:
        run_score_gap_analysis()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
