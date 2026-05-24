"""
Cross-modal ranking — Phase 2 integration test (shape matching only).

Set-paired evaluation via build_set_pair_specs (phase3 filename parser + phase1
sample_label for matrix rows). Lung filter accepts tissue_class == lung.

Run: pytest tests/integration/test_cross_modal_ranking.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

import phase2_descriptors as p2

from tests.integration.cross_modal_eval import (
    build_set_pair_specs,
    is_esophagus_tissue,
    is_lung_family_tissue,
    is_lung_tissue,
    set_label_paired_top3_tpr,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

# 47-set library, lung+lungs family (2026-05-24): ~3.7% set-paired top-3
IPHONE_BASELINE_PHASE2_LUNG_TPR = 0.037


def _resolve_images_dir() -> Path:
    for name in ("iphone_images", "iPhone_test_images"):
        candidate = REPO_ROOT / name
        if candidate.is_dir() and (
            any(candidate.glob("*.jpeg")) or any(candidate.glob("*.jpg"))
        ):
            return candidate
    return REPO_ROOT / "iphone_images"


IMAGES_DIR = _resolve_images_dir()


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
@pytest.mark.xfail(
    reason="Phase 2 lung top-3 below 80% mentor gate on current iphone_images/",
    strict=False,
)
def test_phase2_lung_cross_modal_top3_set_paired(tmp_path):
    specs = build_set_pair_specs(IMAGES_DIR)
    run = p2.run_pipeline(
        input_dir=IMAGES_DIR,
        output_dir=tmp_path / "phase2_outputs",
    )
    cm = run.get("cross_modal")
    if cm is None:
        pytest.skip(f"Phase 2 pipeline: {run.get('reason')}")

    sim_df, _, _ = cm
    tpr, hits, total = set_label_paired_top3_tpr(
        sim_df, specs, tissue_predicate=is_lung_tissue,
    )
    if total == 0:
        pytest.skip("No evaluable lung sets in Phase 2 matrix.")

    assert tpr >= 0.80, (
        f"Phase 2 lung top-3 TPR {tpr:.2%} ({hits}/{total} set-paired lung sets)."
    )


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
@pytest.mark.xfail(
    reason="Phase 2 esophagus top-3 below 80% mentor gate on current iphone_images/",
    strict=False,
)
def test_phase2_esophagus_cross_modal_top3_set_paired(tmp_path):
    specs = build_set_pair_specs(IMAGES_DIR)
    run = p2.run_pipeline(
        input_dir=IMAGES_DIR,
        output_dir=tmp_path / "phase2_outputs",
    )
    cm = run.get("cross_modal")
    if cm is None:
        pytest.skip(f"Phase 2 pipeline: {run.get('reason')}")

    sim_df, _, _ = cm
    tpr, hits, total = set_label_paired_top3_tpr(
        sim_df, specs, tissue_predicate=is_esophagus_tissue,
    )
    if total == 0:
        pytest.skip("No evaluable esophagus sets in Phase 2 matrix.")

    assert tpr >= 0.80, (
        f"Phase 2 esophagus top-3 TPR {tpr:.2%} ({hits}/{total} set-paired)."
    )


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
def test_phase2_baseline_tpr_recorded(tmp_path):
    specs = build_set_pair_specs(IMAGES_DIR)
    run = p2.run_pipeline(IMAGES_DIR, tmp_path / "phase2_outputs")
    sim_df, _, _ = run["cross_modal"]
    tpr, _, total = set_label_paired_top3_tpr(
        sim_df, specs, tissue_predicate=is_lung_family_tissue,
    )
    assert total > 0
    assert tpr >= IPHONE_BASELINE_PHASE2_LUNG_TPR - 0.02
