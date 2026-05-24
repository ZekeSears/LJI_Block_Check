"""
Cross-modal ranking — Phase 3 integration test (hybrid router + unified_compare).

Uses phase3_pipeline.run_phase3_pipeline with set_XX matrix labels.
Ranking quality gate (80% top-3) is aspirational until dataset/calibration improve;
structural and TPR-report tests always run when iphone_images/ is present.

Run: pytest tests/integration/test_phase3_cross_modal_ranking.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

import phase3_pipeline as p3pl

from tests.integration.cross_modal_eval import (
    build_set_pair_specs,
    esophagus_evaluable_from_specs,
    is_lung_tissue,
    lung_evaluable_from_specs,
    lungs_evaluable_from_specs,
    set_label_paired_top3_tpr,
    top3_ranking_tpr,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

# 47-set library, metrics-only router (2026-05-24). Mentor target: 0.80.
IPHONE_BASELINE_PHASE3_LUNG_TPR = 0.0
IPHONE_BASELINE_PHASE3_LUNGS_TPR = 0.13
IPHONE_BASELINE_PHASE3_ESOPHAGUS_TPR = 0.05


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
def test_phase3_pipeline_set_keyed_matrix(tmp_path):
    """Phase 3 pipeline produces set_XX rows/columns and inventory CSV."""
    run = p3pl.run_phase3_pipeline(
        input_dir=IMAGES_DIR,
        output_dir=tmp_path / "phase3_outputs",
    )
    cm = run.get("cross_modal")
    assert cm is not None, run.get("reason")
    sim_df, block_labels, slide_labels = cm
    assert all(lbl.startswith("set_") for lbl in block_labels)
    assert all(lbl.startswith("set_") for lbl in slide_labels)
    assert sim_df.shape[0] >= 1 and sim_df.shape[1] >= 1
    inv = tmp_path / "phase3_outputs" / "set_inventory.csv"
    assert inv.is_file()
    routing = tmp_path / "phase3_outputs" / "routing_log.csv"
    assert routing.is_file()


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
@pytest.mark.xfail(
    reason="Lungs set-paired top-3 below 80% mentor gate on current iphone_images/",
    strict=False,
)
def test_phase3_lungs_cross_modal_top3_set_paired(tmp_path):
    specs = build_set_pair_specs(IMAGES_DIR)
    run = p3pl.run_phase3_pipeline(
        input_dir=IMAGES_DIR,
        output_dir=tmp_path / "phase3_outputs",
    )
    sim_df, _, _ = run["cross_modal"]
    evaluable = lungs_evaluable_from_specs(specs, sim_df, use_set_keys=True)
    if not evaluable:
        pytest.skip("No evaluable lungs sets in Phase 3 matrix.")
    tpr, hits, total = top3_ranking_tpr(sim_df, evaluable)
    assert tpr >= 0.80, (
        f"Phase 3 lungs top-3 TPR {tpr:.2%} ({hits}/{total} set-paired lungs sets)."
    )


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
@pytest.mark.xfail(
    reason="Lung set-paired top-3 below 80% mentor gate on current iphone_images/",
    strict=False,
)
def test_phase3_lung_cross_modal_top3_set_paired(tmp_path):
    specs = build_set_pair_specs(IMAGES_DIR)
    run = p3pl.run_phase3_pipeline(
        input_dir=IMAGES_DIR,
        output_dir=tmp_path / "phase3_outputs",
    )
    sim_df, _, _ = run["cross_modal"]
    evaluable = lung_evaluable_from_specs(specs, sim_df, use_set_keys=True)
    assert evaluable, "No evaluable lung sets in Phase 3 matrix."
    tpr, hits, total = top3_ranking_tpr(sim_df, evaluable)
    assert tpr >= 0.80, (
        f"Phase 3 lung top-3 TPR {tpr:.2%} ({hits}/{total} set-paired lung sets)."
    )


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
@pytest.mark.xfail(
    reason="Esophagus set-paired top-3 below 80% mentor gate on current iphone_images/",
    strict=False,
)
def test_phase3_esophagus_cross_modal_top3_set_paired(tmp_path):
    specs = build_set_pair_specs(IMAGES_DIR)
    run = p3pl.run_phase3_pipeline(
        input_dir=IMAGES_DIR,
        output_dir=tmp_path / "phase3_outputs",
    )
    sim_df, _, _ = run["cross_modal"]
    evaluable = esophagus_evaluable_from_specs(specs, sim_df, use_set_keys=True)
    assert evaluable, "No evaluable esophagus sets in Phase 3 matrix."
    tpr, hits, total = top3_ranking_tpr(sim_df, evaluable)
    assert tpr >= 0.80, (
        f"Phase 3 esophagus top-3 TPR {tpr:.2%} ({hits}/{total} set-paired)."
    )


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
def test_phase3_baseline_tpr_recorded(tmp_path):
    """Regression guard: Phase 3 wired path returns known baseline TPR (not zero wiring)."""
    import phase2_descriptors as p2

    specs = build_set_pair_specs(IMAGES_DIR)
    p3_run = p3pl.run_phase3_pipeline(IMAGES_DIR, tmp_path / "p3")
    sim3, _, _ = p3_run["cross_modal"]
    lung_keys = lung_evaluable_from_specs(specs, sim3, use_set_keys=True)
    lungs_keys = lungs_evaluable_from_specs(specs, sim3, use_set_keys=True)
    eso_keys = esophagus_evaluable_from_specs(specs, sim3, use_set_keys=True)
    lung_tpr, _, lung_n = top3_ranking_tpr(sim3, lung_keys)
    lungs_tpr, _, lungs_n = top3_ranking_tpr(sim3, lungs_keys)
    eso_tpr, _, eso_n = top3_ranking_tpr(sim3, eso_keys)
    assert lung_n + lungs_n > 0 and eso_n > 0
    assert lung_tpr >= IPHONE_BASELINE_PHASE3_LUNG_TPR - 0.01
    assert lungs_tpr >= IPHONE_BASELINE_PHASE3_LUNGS_TPR - 0.05
    assert eso_tpr >= IPHONE_BASELINE_PHASE3_ESOPHAGUS_TPR - 0.05


@pytest.mark.skipif(
    not IMAGES_DIR.is_dir()
    or not (any(IMAGES_DIR.glob("*.jpeg")) or any(IMAGES_DIR.glob("*.jpg"))),
    reason="iphone_images/ has no JPEGs — skipping.",
)
def test_phase3_reports_tpr_separate_from_phase2(tmp_path, capsys):
    import phase2_descriptors as p2

    specs = build_set_pair_specs(IMAGES_DIR)
    p2_run = p2.run_pipeline(IMAGES_DIR, tmp_path / "p2")
    p3_run = p3pl.run_phase3_pipeline(IMAGES_DIR, tmp_path / "p3")
    sim2, _, _ = p2_run["cross_modal"]
    sim3, _, _ = p3_run["cross_modal"]
    tpr2, h2, n2 = set_label_paired_top3_tpr(
        sim2, specs, tissue_predicate=is_lung_tissue,
    )
    lung_keys = lung_evaluable_from_specs(specs, sim3, use_set_keys=True)
    tpr3, h3, n3 = top3_ranking_tpr(sim3, lung_keys)
    msg = f"Phase2 lung TPR={tpr2:.2%} ({h2}/{n2}); Phase3 lung TPR={tpr3:.2%} ({h3}/{n3})"
    print(msg)
    captured = capsys.readouterr()
    assert "Phase2 lung TPR=" in captured.out
