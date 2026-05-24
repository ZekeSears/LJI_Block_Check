"""Unit tests for phase3_pipeline grouping helpers."""

from __future__ import annotations

from pathlib import Path

import phase3_pipeline as p3pl
from tests.integration.cross_modal_eval import build_set_pair_specs, set_group_key


def test_set_group_key_format():
    assert set_group_key(1) == "set_01"
    assert set_group_key(23) == "set_23"


def test_build_set_pair_specs_groups_by_set_id(tmp_path):
    stem = "set_07_block_silhouette_lung_HE_TWKO5_WO7842"
    (tmp_path / f"{stem}.jpeg").write_bytes(b"\xff\xd8\xff")
    stem2 = "set_07_slide_lung_HE_TWKO5_WO7842"
    (tmp_path / f"{stem2}.jpeg").write_bytes(b"\xff\xd8\xff")

    specs = build_set_pair_specs(tmp_path)
    assert len(specs) == 1
    assert specs[0]["group_key"] == "set_07"
    assert specs[0]["has_block"]
    assert specs[0]["has_slide"]
    assert specs[0]["tissue_class"] == "lung"


def test_select_block_prefers_silhouette():
    group = [
        {"role": "block_barcode"},
        {"role": "block_silhouette", "id": 1},
    ]
    assert p3pl._select_block_entry(group)["id"] == 1
