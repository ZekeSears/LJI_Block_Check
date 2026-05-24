"""Unit tests for orphan slide filename parsing and pairing keys."""

from __future__ import annotations

import sys
from pathlib import Path

_CODE = Path(__file__).resolve().parents[1] / "code"
if str(_CODE) not in sys.path:
    sys.path.insert(0, str(_CODE))

import pair_orphan_slides as pos  # noqa: E402


def test_parse_orphan_stem_lung_mt():
    meta = pos.parse_orphan_stem("slide_lung_MT_WT1_WO7842")
    assert meta is not None
    assert meta["tissue_token"] == "lung"
    assert meta["stain"] == "MT"
    assert meta["genotype"] == "WT1"


def test_parse_orphan_stem_lungs_distinct_from_lung():
    lungs = pos.parse_orphan_stem("slide_lungs_MT_WT1_WO7842")
    lung = pos.parse_orphan_stem("slide_lung_MT_WT1_WO7842")
    assert lungs is not None and lung is not None
    assert lungs["tissue_token"] == "lungs"
    assert lung["tissue_token"] == "lung"


def test_parse_orphan_stem_without_slide_prefix():
    meta = pos.parse_orphan_stem("esophagus_HE_TWKO4_7842")
    assert meta is not None
    assert meta["tissue_token"] == "esophagus"
    assert meta["genotype"] == "TWKO4"


def test_parse_orphan_stem_rejects_too_few_tokens():
    assert pos.parse_orphan_stem("slide_lung_MT") is None


def test_pair_key_from_path(tmp_path):
    p = tmp_path / "slide_lung_HE_WT2_WO7842.jpeg"
    p.write_bytes(b"x")
    slide = pos.parse_orphan_slide(p)
    assert slide is not None
    assert slide.pair_key == ("lung", "WT2")
