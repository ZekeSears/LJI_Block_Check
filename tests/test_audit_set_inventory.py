"""Tests for audit_set_inventory.py."""

from __future__ import annotations

from pathlib import Path

import pytest

import audit_set_inventory as audit


def test_normalize_tissue_token_distinct_lung_lungs():
    import phase3_contour_profile as p3cp

    assert p3cp.normalize_tissue_token("lung") == "lung"
    assert p3cp.normalize_tissue_token("lungs") == "lungs"
    assert p3cp.normalize_tissue_class("lungs") == "lung"


def test_consistent_set_passes_audit(tmp_path):
    d = tmp_path / "iphone_images"
    d.mkdir()
    stem = "set_10_block_silhouette_lung_HE_WT1_WO7842"
    (d / f"{stem}.jpeg").write_bytes(b"x")
    (d / "set_10_slide_lung_HE_WT1_WO7842.jpeg").write_bytes(b"x")

    audits = audit.audit_library(d)
    a = next(x for x in audits if x.set_id == 10)
    assert not a.blocking


def test_genotype_mismatch_blocks(tmp_path):
    d = tmp_path / "iphone_images"
    d.mkdir()
    (d / "set_02_block_silhouette_lung_HE_WT1_WO7842.jpeg").write_bytes(b"x")
    (d / "set_02_slide_lung_HE_WT2_WO7842.jpeg").write_bytes(b"x")

    audits = audit.audit_library(d)
    a = next(x for x in audits if x.set_id == 2)
    assert any("genotype_mismatch" in b for b in a.blocking)


def test_he_block_mt_slide_not_blocking(tmp_path):
    d = tmp_path / "iphone_images"
    d.mkdir()
    (d / "set_41_block_silhouette_esophagus_HE_TWKO4_WO7842.jpeg").write_bytes(b"x")
    (d / "set_41_slide_esophagus_MT_TWKO4_WO7482.jpeg").write_bytes(b"x")

    audits = audit.audit_library(d)
    a = next(x for x in audits if x.set_id == 41)
    assert not any("stain" in b for b in a.blocking)
    assert not a.blocking or all("stain" not in b for b in a.blocking)


def test_list_jpeg_paths_includes_uppercase_extension(tmp_path):
    import phase3_contour_profile as p3cp

    (tmp_path / "a.jpeg").write_bytes(b"x")
    (tmp_path / "b.JPEG").write_bytes(b"x")
    paths = p3cp.list_jpeg_paths(tmp_path)
    names = {p.name for p in paths}
    assert names == {"a.jpeg", "b.JPEG"}
