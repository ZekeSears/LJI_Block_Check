"""Integration: verification metrics on live iphone library (explicit invocation only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
MATRIX = REPO / "phase3_outputs" / "pipeline_run" / "cross_modal_similarity.csv"
IMAGES = REPO / "iphone_images"


@pytest.mark.skipif(not MATRIX.is_file(), reason="pipeline matrix not built")
@pytest.mark.skipif(not IMAGES.is_dir(), reason="iphone_images missing")
def test_verification_pass_rate_on_library():
    import sys

    sys.path.insert(0, str(REPO / "code"))
    sys.path.insert(0, str(REPO / "tests" / "integration"))
    from cross_modal_eval import build_set_pair_specs
    from phase3_score_diagnostics import verification_pass_rate

    sim_df = pd.read_csv(MATRIX, index_col=0)
    specs = build_set_pair_specs(IMAGES)
    keys = [s["group_key"] for s in specs]
    stats = verification_pass_rate(sim_df, keys)
    assert stats["total"] >= 40
    assert 0.0 <= stats["rate"] <= 1.0
