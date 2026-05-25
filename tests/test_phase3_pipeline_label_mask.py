"""Pipeline wiring: yellow-tag slides mask label before segmentation (plan v2 Step 4)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import phase3_block_roi as p3roi
import phase3_label_detection as p3ld
import phase3_pipeline as p3pl
from phase3_block_roi import SegmentationWithRoi


def test_process_image_calls_label_mask_before_segmentation(monkeypatch, tmp_path):
    order: list[str] = []

    def fake_mask(img: np.ndarray) -> np.ndarray:
        order.append("mask")
        return img

    def fake_seg(img: np.ndarray, meta, clean_mask_fn):
        order.append("seg")
        mask = np.zeros((100, 100), dtype=np.uint8)
        cv2 = pytest.importorskip("cv2")
        cv2.circle(mask, (50, 70), 25, 255, -1)
        c = np.array([[45, 65], [55, 65], [55, 75], [45, 75]], dtype=np.int32)
        return SegmentationWithRoi(
            cleaned_mask=mask,
            contours=[c.reshape(-1, 1, 2)],
            otsu_threshold=128,
            roi_detection_ok=True,
            roi_bbox=(0, 0, 100, 100),
            crop_origin=(0, 0),
        )

    def fake_load(_path: Path):
        img = np.full((100, 100, 3), 240, dtype=np.uint8)
        cv2 = pytest.importorskip("cv2")
        cv2.rectangle(img, (10, 5), (90, 25), (20, 20, 20), -1)
        cv2.circle(img, (50, 70), 25, (30, 30, 30), -1)
        return img

    import phase2_descriptors as p2

    monkeypatch.setattr(p3ld, "apply_label_mask", fake_mask)
    monkeypatch.setattr(p3roi, "segment_with_block_roi", fake_seg)
    monkeypatch.setattr(p3pl, "load_image", fake_load)
    monkeypatch.setattr(
        p2,
        "clean_mask",
        lambda mask, role: (mask, [np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.int32)]),
    )

    path = tmp_path / "set_01_slide_lung_MT_TWKOB4.jpeg"
    path.write_bytes(b"\xff\xd8\xff")
    meta = {
        "parse_ok": True,
        "role": "slide",
        "set_id": 1,
        "label_type": "yellow",
        "tissue_class": "lung",
        "tissue_token": "lung",
    }
    out = p3pl._process_image(path, meta)
    assert order[:2] == ["mask", "seg"]
    assert out is not None
    assert len(out["contours"]) == 1
