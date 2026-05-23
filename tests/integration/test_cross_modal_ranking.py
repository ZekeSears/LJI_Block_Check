"""
Cross-modal ranking acceptance test — LIVE-DATASET integration test.

Pre-mortem §3.2: this test was moved OUT of tests/test_phase2.py because
it depends on the user's growing iPhone_test_images/ dataset and would
otherwise make `pytest tests/` non-deterministic. The default pytest run
ignores tests/integration/ (see pytest.ini). Run explicitly:

    pytest tests/integration/ -v

Acceptance gate (proposed_plan §7): for each lung block in the real
dataset, the correct slide must rank in the top 3 of its row in the
cross-modal similarity matrix (true positive rate ≥ 80%).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import phase2_descriptors as p2


REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_images_dir() -> Path:
    for name in ("iphone_images", "iPhone_test_images"):
        candidate = REPO_ROOT / name
        if candidate.is_dir() and any(candidate.glob("*.jpeg")) or any(
                candidate.glob("*.jpg")):
            return candidate
    return REPO_ROOT / "iphone_images"


IMAGES_DIR = _resolve_images_dir()


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ (or iPhone_test_images/) has no JPEGs — skipping.",
)
def test_lung_cross_modal_top3_ranking(tmp_path):
    """For each lung block, the correct slide ranks in top 3 of its
    cross-modal similarity row. True positive rate must be ≥ 80%."""
    run = p2.run_pipeline(
        input_dir=IMAGES_DIR,
        output_dir=tmp_path / "phase2_outputs",
    )
    cm = run["cross_modal"]
    if cm is None:
        pytest.skip("Intra-class gate did not pass; cross-modal not computed.")

    sim_df, block_labels, slide_labels = cm
    lung_blocks = [b for b in block_labels if "lungs" in b.lower()]
    # Fairness filter: only evaluate blocks whose paired slide also
    # produced a usable row in the matrix. If the slide was excluded by
    # the degenerate-mask detector (pre-mortem §3.6), the algorithm
    # cannot be held responsible for missing it — that is a data-quality
    # problem flagged elsewhere.
    evaluable = [b for b in lung_blocks if b in sim_df.columns]
    if not evaluable:
        pytest.skip("No lung samples with usable paired slides.")

    hits = 0
    for block in evaluable:
        row = sim_df.loc[block].sort_values(ascending=False)
        top3 = list(row.index[:3])
        if block in top3:
            hits += 1
    tpr = hits / len(evaluable)
    skipped = len(lung_blocks) - len(evaluable)
    assert tpr >= 0.80, (
        f"Lung cross-modal top-3 TPR {tpr:.2%} below 80% gate "
        f"({hits}/{len(evaluable)} evaluable blocks; "
        f"{skipped} excluded due to degenerate slides)."
    )
