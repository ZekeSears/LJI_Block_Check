"""Unit tests for label-keyed score-gap diagnostics (plan v2)."""

from __future__ import annotations

import pandas as pd
import pytest

from phase3_score_diagnostics import (
    GapRow,
    compute_score_gaps,
    evaluable_keys,
    gate_verdict,
    gap_median,
    gaps_from_iloc_diagonal,
    verification_pass_rate,
)


def _misaligned_3x3() -> pd.DataFrame:
    """set_01 row exists but no set_01 column (47x46 pattern); iloc[i,i] is wrong."""
    return pd.DataFrame(
        [
            [0.9, 0.1],
            [0.3, 0.8],
            [0.2, 0.3],
        ],
        index=["set_01", "set_02", "set_03"],
        columns=["set_02", "set_03"],
    )


def test_evaluable_keys_requires_both_axes():
    df = _misaligned_3x3()
    assert evaluable_keys(df, ["set_01", "set_02", "set_03"]) == ["set_02", "set_03"]


def test_compute_score_gaps_label_keyed():
    df = pd.DataFrame(
        [
            [0.9, 0.4, 0.3],
            [0.2, 0.85, 0.5],
            [0.1, 0.6, 0.95],
        ],
        index=["set_01", "set_02", "set_03"],
        columns=["set_01", "set_02", "set_03"],
    )
    gaps = compute_score_gaps(df, ["set_01", "set_02", "set_03"])
    assert len(gaps) == 3
    by_key = {g.group_key: g for g in gaps}
    assert by_key["set_01"].gap == pytest.approx(0.9 - 0.4)
    assert by_key["set_01"].correct_score == pytest.approx(0.9)
    assert by_key["set_01"].best_wrong_score == pytest.approx(0.4)
    assert by_key["set_01"].wrong_top1_key == "set_02"
    assert by_key["set_01"].verification_pass is True


def test_iloc_diagonal_differs_from_label_gaps_on_misaligned_matrix():
    df = pd.DataFrame(
        [
            [0.9, 0.1, 0.2],
            [0.3, 0.8, 0.1],
            [0.2, 0.3, 0.7],
        ],
        index=["set_01", "set_02", "set_03"],
        columns=["set_02", "set_03", "set_01"],
    )
    label_gaps = compute_score_gaps(df, ["set_01", "set_02", "set_03"])
    iloc_gaps = gaps_from_iloc_diagonal(df, ["set_01", "set_02", "set_03"])
    label_by_key = {g.group_key: g.gap for g in label_gaps}
    iloc_by_key = {g.group_key: g.gap for g in iloc_gaps}
    assert label_by_key["set_02"] != iloc_by_key["set_02"]


def test_missing_column_excluded_not_nan_median():
    df = pd.DataFrame(
        [[0.5, 0.9], [0.8, 0.7]],
        index=["set_01", "set_02"],
        columns=["set_02", "set_03"],
    )
    gaps = compute_score_gaps(df, ["set_01", "set_02", "set_03"])
    assert [g.group_key for g in gaps] == ["set_02"]
    assert gap_median(gaps) == pytest.approx(gaps[0].gap)


def test_gate_verdict_threshold():
    rows = [
        GapRow("set_01", None, 0.02, 0.9, 0.88, "set_02", True, True),
        GapRow("set_02", None, 0.03, 0.8, 0.77, "set_01", True, True),
    ]
    assert gate_verdict(rows, threshold=0.01) == "GATE: RANKING_FIXABLE"
    rows[0] = GapRow("set_01", None, -0.1, 0.5, 0.6, "set_02", False, False)
    rows[1] = GapRow("set_02", None, -0.2, 0.4, 0.6, "set_01", False, False)
    assert gate_verdict(rows, threshold=0.01) == "GATE: SIGNAL_MISSING"


def test_verification_pass_rate_synthetic():
    df = pd.DataFrame(
        [
            [0.9, 0.4],
            [0.3, 0.85],
        ],
        index=["set_01", "set_02"],
        columns=["set_01", "set_02"],
    )
    stats = verification_pass_rate(df, ["set_01", "set_02"])
    assert stats["passes"] == 2
    assert stats["total"] == 2
    assert stats["rate"] == pytest.approx(1.0)
