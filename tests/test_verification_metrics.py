"""Unit tests for verification_pass_rate (shared with score-gap core)."""

from __future__ import annotations

import pandas as pd

from phase3_score_diagnostics import verification_pass_rate


def test_verification_one_fail():
    df = pd.DataFrame(
        [
            [0.5, 0.9],
            [0.3, 0.85],
        ],
        index=["set_01", "set_02"],
        columns=["set_01", "set_02"],
    )
    stats = verification_pass_rate(df, ["set_01", "set_02"])
    assert stats["passes"] == 1
    assert stats["total"] == 2
    assert stats["rate"] == 0.5
