"""
phase3_score_diagnostics.py — Label-keyed score gaps and verification metrics.

Core helpers for Phase 3 signal gate (plan v2). Uses df.loc[k, k], never iloc[i, i]
on rectangular cross-modal matrices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

DEFAULT_GATE_THRESHOLD = 0.01
SENSITIVITY_THRESHOLDS = (0.0, 0.01, 0.05)


@dataclass(frozen=True)
class GapRow:
    group_key: str
    tissue_token: Optional[str]
    gap: float
    correct_score: float
    best_wrong_score: float
    wrong_top1_key: str
    top3_hit: bool
    verification_pass: bool


def evaluable_keys(sim_df: pd.DataFrame, keys: Iterable[str]) -> list[str]:
    """Keys present on both row and column axes."""
    index_set = set(sim_df.index)
    col_set = set(sim_df.columns)
    return [k for k in keys if k in index_set and k in col_set]


def compute_score_gaps(
        sim_df: pd.DataFrame,
        keys: Iterable[str],
        *,
        tissue_by_key: Optional[dict[str, str]] = None,
) -> list[GapRow]:
    """Label-keyed gap per evaluable set: sim.loc[k,k] - max(sim.loc[k,j!=k])."""
    tissue_by_key = tissue_by_key or {}
    rows: list[GapRow] = []
    for key in evaluable_keys(sim_df, keys):
        row = sim_df.loc[key]
        correct = float(row[key])
        wrong_cols = [c for c in row.index if c != key]
        if not wrong_cols:
            continue
        wrong_scores = row[wrong_cols].astype(float)
        best_wrong = float(wrong_scores.max())
        wrong_top1 = str(wrong_scores.idxmax())
        gap = correct - best_wrong
        sorted_cols = list(row.sort_values(ascending=False).index)
        top3_hit = key in sorted_cols[:3]
        rows.append(
            GapRow(
                group_key=key,
                tissue_token=tissue_by_key.get(key),
                gap=gap,
                correct_score=correct,
                best_wrong_score=best_wrong,
                wrong_top1_key=wrong_top1,
                top3_hit=top3_hit,
                verification_pass=gap > 0,
            )
        )
    return rows


def gaps_from_iloc_diagonal(
        sim_df: pd.DataFrame,
        keys: Iterable[str],
) -> list[GapRow]:
    """WRONG approach for tests: iloc[i,i] on row slice — column i is not set key i."""
    eval_keys = [k for k in keys if k in sim_df.index]
    if not eval_keys:
        return []
    sub = sim_df.loc[eval_keys]
    n = len(eval_keys)
    rows: list[GapRow] = []
    for i in range(n):
        key = sub.index[i]
        row = sub.iloc[i]
        if i >= len(row):
            continue
        correct = float(row.iloc[i])
        wrong = row.drop(row.index[i]).astype(float)
        best_wrong = float(wrong.max()) if len(wrong) else correct
        wrong_top1 = str(wrong.idxmax()) if len(wrong) else key
        gap = correct - best_wrong
        rows.append(
            GapRow(
                group_key=key,
                tissue_token=None,
                gap=gap,
                correct_score=correct,
                best_wrong_score=best_wrong,
                wrong_top1_key=wrong_top1,
                top3_hit=False,
                verification_pass=gap > 0,
            )
        )
    return rows


def gap_median(gaps: list[GapRow]) -> float:
    if not gaps:
        return float("nan")
    return float(np.median([g.gap for g in gaps]))


def gap_percentiles(gaps: list[GapRow]) -> dict[str, float]:
    if not gaps:
        return {"p10": float("nan"), "p50": float("nan"), "p90": float("nan")}
    vals = np.array([g.gap for g in gaps], dtype=float)
    return {
        "p10": float(np.percentile(vals, 10)),
        "p50": float(np.percentile(vals, 50)),
        "p90": float(np.percentile(vals, 90)),
    }


def fraction_gap_positive(gaps: list[GapRow]) -> float:
    if not gaps:
        return float("nan")
    return sum(1 for g in gaps if g.gap > 0) / len(gaps)


def sensitivity_at_thresholds(
        gaps: list[GapRow],
        thresholds: tuple[float, ...] = SENSITIVITY_THRESHOLDS,
) -> list[dict[str, Any]]:
    if not gaps:
        return [{"threshold": t, "fraction_ge": float("nan")} for t in thresholds]
    vals = [g.gap for g in gaps]
    n = len(vals)
    return [
        {
            "threshold": t,
            "fraction_ge": sum(1 for v in vals if v >= t) / n,
        }
        for t in thresholds
    ]


def gate_verdict(
        gaps: list[GapRow],
        threshold: float = DEFAULT_GATE_THRESHOLD,
) -> str:
    med = gap_median(gaps)
    if np.isnan(med) or med < threshold:
        return "GATE: SIGNAL_MISSING"
    return "GATE: RANKING_FIXABLE"


def verification_pass_rate(
        sim_df: pd.DataFrame,
        keys: Iterable[str],
) -> dict[str, Any]:
    """Fraction of evaluable sets where correct pair beats all wrong slides."""
    gaps = compute_score_gaps(sim_df, keys)
    passes = sum(1 for g in gaps if g.verification_pass)
    total = len(gaps)
    rate = passes / total if total else float("nan")
    mean_gap = float(np.mean([g.gap for g in gaps])) if gaps else float("nan")
    return {
        "passes": passes,
        "total": total,
        "rate": rate,
        "mean_gap": mean_gap,
        "gaps": gaps,
    }


def gaps_by_tissue(gaps: list[GapRow]) -> dict[str, list[GapRow]]:
    buckets: dict[str, list[GapRow]] = {}
    for g in gaps:
        tok = g.tissue_token or "unknown"
        buckets.setdefault(tok, []).append(g)
    return buckets


def warn_if_matrix_stale(
        matrix_path,
        images_dir,
) -> Optional[str]:
    """Return warning message if matrix is older than newest JPEG."""
    from pathlib import Path

    mp = Path(matrix_path)
    idir = Path(images_dir)
    if not mp.is_file() or not idir.is_dir():
        return None
    jpgs = list(idir.glob("*.jp*g"))
    if not jpgs:
        return None
    newest_img = max(p.stat().st_mtime for p in jpgs)
    if mp.stat().st_mtime < newest_img:
        return (
            f"WARNING: {mp.name} mtime is older than newest image in {idir}; "
            "run Step 0 pipeline refresh before trusting gate verdict."
        )
    return None
