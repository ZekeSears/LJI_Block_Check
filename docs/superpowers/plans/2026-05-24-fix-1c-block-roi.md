# Fix 1c — Block paraffin ROI implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement design v2 in `phase3_block_roi.py` so block silhouettes get detection-based cassette → opposite-end grid/label strip → Otsu-only tissue on wax, with reshoot flags instead of silent full-frame fallback.

**Architecture:** Extend Fix 1b module with `cassette_method`, `roi_fail_reason`, `seg_fail_reason`; three geometry gates; remove block HSV path; production mode skips contours when ROI/seg fails. Pilot 10 sets, ≥7/10 visual pass before 47-set regen.

**Tech stack:** Python 3.10+, OpenCV, numpy, pytest, existing `segment_tissue()` (frozen).

**Spec:** `docs/superpowers/specs/2026-05-24-block-capture-roi-design.md`

**Workflow before code:** Session synthesizer → `.cursor/specs/proposed_plan.md` v1 → pre-mortem → plan v2 (project gate). This file is the execution checklist after plan v2.

---

## File map

| File | Action |
|------|--------|
| `code/phase3_block_roi.py` | Core ROI + seg changes |
| `tests/test_phase3_block_roi.py` | New synthetics + gate tests |
| `tests/test_segment_tissue_integration.py` | Update if HSV path removed from blocks |
| `code/phase3_contour_profile.py` | CSV columns: `roi_fail_reason`, `cassette_method`, `seg_fail_reason` |
| `code/phase3_pipeline.py` | Respect production no-contour on fail |
| `code/segmentation_audit_pack.py` | Regen pilot audit only |
| `.cursor/docs/PROJECT_CONTEXT.md` | After pilot pass |

---

### Task 1: Synthetics — opposite-end grid/label (180°)

**Files:**
- Modify: `tests/test_phase3_block_roi.py`

- [ ] **Step 1: Add failing test `test_rotated_grid_label_opposite_ends`**

Build synthetic BGR: dark cassette frame, bright paraffin center band, grid transitions on **left** short end, dark label band on **right** short end. Call `detect_cassette_interior_roi`. Assert ROI excludes both ends and `roi_detection_ok` is True.

- [ ] **Step 2: Add failing test `test_rotated_180_swaps_ends`**

Same layout rotated 180° in image; grid now on right, label on left. Assert same pass.

Run: `pytest tests/test_phase3_block_roi.py::test_rotated_grid_label_opposite_ends -v`  
Expected: FAIL until Task 3.

---

### Task 2: Synthetics — no-border cassette detection

**Files:**
- Modify: `tests/test_phase3_block_roi.py`

- [ ] **Step 1: Add `test_no_border_plastic_frame_detects_cassette`**

Fill-frame image: no white pad; gray plastic rim contour encloses paraffin. Assert `cassette_method != "geometric_inset"` and paraffin ROI found.

- [ ] **Step 2: Add `test_geometric_inset_only_when_detection_fails`**

Blank/uniform image → `cassette_method == "geometric_inset"` and `roi_detection_ok` is False (or `low_confidence`).

---

### Task 3: Opposite-end grid/label in `detect_cassette_interior_roi`

**Files:**
- Modify: `code/phase3_block_roi.py` — replace bottom-only grid trim and top-N% label logic

- [ ] **Step 1: Implement `_short_end_transition_scores(inner_bbox)`**

Return scores for both short ends.

- [ ] **Step 2: `_strip_grid_and_label(paraffin_bbox, inner_bbox)`**

Grid end = argmax score; strip band; label end = opposite short end; strip 15–22% band. Fallback `dark_band_fallback` only if scores within 10%.

- [ ] **Step 3: Run Task 1 tests**

`pytest tests/test_phase3_block_roi.py -k rotated -v` → PASS

---

### Task 4: Cassette detection chain (no primary central %)

**Files:**
- Modify: `code/phase3_block_roi.py`

- [ ] **Step 1: Add `detect_cassette_bbox(gray, has_backlight_margin) -> (bbox, cassette_method)`**

Order: backlight CC → `_cassette_bbox_from_frame` (existing) → paraffin envelope CC → `geometric_inset` last.

- [ ] **Step 2: Wire into `detect_cassette_interior_roi`**

Remove any central 70–85% primary path.

- [ ] **Step 3: Run Task 2 tests**

`pytest tests/test_phase3_block_roi.py -k no_border -v` → PASS

---

### Task 5: Three geometry gates + `roi_fail_reason`

**Files:**
- Modify: `code/phase3_block_roi.py` — `validate_paraffin_roi` or equivalent

- [ ] **Step 1: Replace multi-gate AND with G1/G2/G3 + `empty_wax`**

Return `(ok: bool, reason: str)`.

- [ ] **Step 2: Tests for each fail code**

`test_roi_fail_paraffin_low`, `test_roi_fail_roi_narrow`, `test_roi_fail_backlight_flood`, `test_roi_fail_empty_wax`.

- [ ] **Step 3: Run**

`pytest tests/test_phase3_block_roi.py -k roi_fail -v` → PASS

---

### Task 6: Remove block HSV; post-Otsu reshoot gates

**Files:**
- Modify: `code/phase3_block_roi.py` — `segment_with_block_roi`

- [ ] **Step 1: Delete or bypass `_hsv_tissue_mask` for `role=="block"`**

`segmentation_method` always `"otsu"` or `"failed"`.

- [ ] **Step 2: Add `_validate_block_segmentation(mask, crop, roi_area) -> (ok, seg_fail_reason)`**

Rules: empty, >85% crop, >55% roi with ≤2 contours.

- [ ] **Step 3: On fail return empty contours, `roi_detection_ok` may be True but `reshoot_recommended=True`**

- [ ] **Step 4: Test `test_block_no_hsv_fallback` and `test_seg_flood_returns_empty`**

- [ ] **Step 5: Update `tests/test_segment_tissue_integration.py` if it asserted `hsv_fallback`**

`pytest tests/test_phase3_block_roi.py tests/test_segment_tissue_integration.py -v`

---

### Task 7: Production mode — no full-frame fallback

**Files:**
- Modify: `code/phase3_block_roi.py`, `code/phase3_pipeline.py`, `code/phase2_descriptors.py` (batch path if any)

- [ ] **Step 1: Add parameter `allow_full_frame_fallback: bool = False`**

When False and ROI fail → empty mask, zero contours.

- [ ] **Step 2: Pipeline uses `allow_full_frame_fallback=False` for blocks**

Analysis scripts may pass True for debug.

- [ ] **Step 3: Integration test one failing-set synthetic**

`pytest tests/test_segment_tissue_integration.py -v`

---

### Task 8: CSV telemetry

**Files:**
- Modify: `code/phase3_contour_profile.py`

- [ ] **Step 1: Extend row dict with `cassette_method`, `roi_fail_reason`, `seg_fail_reason`, `reshoot_recommended`**

- [ ] **Step 2: Smoke run on one image path in test or manual**

Document column names in `phase3_calibration_notes.md` appendix (one paragraph).

---

### Task 9: Pilot regen + visual gate

**Files:**
- Run: `code/segmentation_audit_pack.py` or existing roi audit script for sets 02,04,06,11,28,31,33,35,40,45

- [ ] **Step 1: Generate `phase3_outputs/roi_crop_audit/` for pilot 10 only**

- [ ] **Step 2: Zeke visual score — record N/10 in `phase3_outputs/phase3_calibration_notes.md`**

Pass if ≥7/10. If not, histogram `roi_fail_reason` from CSV and tune one gate.

- [ ] **Step 3: Update PROJECT_CONTEXT.md with pilot result**

Do **not** regen full 47 until pass.

---

### Task 10: Lint + full test suite

- [ ] **Step 1:** `python -m flake8 code/phase3_block_roi.py code/phase3_contour_profile.py`

- [ ] **Step 2:** `pytest tests/`

- [ ] **Step 3: Commit (if Zeke says commit milestone)** — `feat: Fix 1c block ROI detection and Otsu-only block seg`

---

## Self-review (plan vs spec)

| Spec section | Task |
|--------------|------|
| 5.1–5.2 detection cassette | 4 |
| 5.3 opposite ends | 3 |
| 5.4 three gates + reasons | 5 |
| 5.5 Otsu only + post gates | 6 |
| 5.6 production mode | 7 |
| 8 pilot ≥7/10 | 9 |
| No block HSV | 6 |

No TBD placeholders in task list.
