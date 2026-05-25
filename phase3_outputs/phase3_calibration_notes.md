# Phase 3 calibration notes

**Date:** 2026-05-24

## Provenance

- **Dataset:** `iphone_images/` — iPhone backlit captures, single shooting session
- **Re-calibration:** Required if images are re-shot or lighting changes materially

## Recommended router thresholds (geometry calibration)

Primary routing uses **slide** `total_tissue_area` and **dominance** only
(metrics-only; no filename tissue). Thresholds derive from geometry k=2
clusters on white-tag HE slides. Contour-count thresholds are legacy fallback.

| Constant | Value | Derivation |
|----------|-------|------------|
| `SLIDE_TOTAL_TISSUE_AREA_PX` | 208044 | median_midpoint on slide total tissue area (shape_like median 309841, constellation_like median 106248) |
| `DOMINANCE_MIN_FOR_SHAPE` | 0.912 | median_midpoint on slide dominance (shape_like median 0.986, constellation_like median 0.839) |

- Contour-count calibration **overlapped** (expected on this dataset); do not use count for primary routing.

**Sanity check:** PASS

## Per-(tissue, role) statistics

| tissue | role | n | contour_count median | median_area median |
|--------|------|---|----------------------|---------------------|
| esophagus | block_silhouette | 19 | 3.0 | 321380 |
| esophagus | slide | 19 | 2.0 | 6848 |
| lung | block_silhouette | 5 | 2.0 | 349691 |
| lung | slide | 5 | 3.0 | 8968 |
| lungs | block_silhouette | 23 | 3.0 | 383003 |
| lungs | slide | 23 | 4.0 | 8428 |

## Yellow-tag (Set 1) separate findings

Measured yellow-tag images: 2 (excluded from white-tag threshold pool).

## Parse warnings

- (none)

## Yellow-tag recommendation

Only one yellow-tag set exists (Set 1). Add more yellow-tag samples before Phase 4 if Set 1 metrics diverge from white-tag norms.

## Histograms

- `phase3_outputs/calibration_histograms/contour_count_by_tissue.png`
- `phase3_outputs/calibration_histograms/slide_total_tissue_area_by_tissue.png`
- `phase3_outputs/calibration_histograms/slide_dominance_by_tissue.png`
- `phase3_outputs/calibration_histograms/contour_count_white_vs_yellow.png`

## Block cassette ROI (Fix 1)

- **`tissue_fraction`:** `(full_mask > 0).sum() / (image_height * image_width)` with mask pasted into full-frame coordinates.
- **Paraffin interior (Fix 1b):** row-projection tallest bright band (row mean ≥ 165) inside frame mask; semantic `validate_paraffin_roi()` required for `roi_detection_ok`.
- **Segmentation:** Otsu on crop; HSV fallback when Otsu mask inadequate.
- **Signal-gap reporting:** use `roi_detection_ok=True` cohort separately from fallback rows when interpreting regenerated gaps.

- Block silhouettes measured: **47**
- `roi_detection_ok=True`: **14** (29.8%)
- Fallback (full frame): **33**

- Fallback set IDs: `set_01, set_05, set_06, set_07, set_08, set_09, set_10, set_12, set_14, set_15, set_16, set_17, set_18, set_19, set_21, set_23, set_25, set_26, set_27, set_30, set_31, set_32, set_35, set_36, set_37, set_38, set_39, set_40, set_42, set_44, set_45, set_46, set_47`

## Fix 1c pilot visual rubric (≥8/10 gate)

**Sets:** 02, 04, 06, 11, 28, 31, 33, 35, 40, 45 — audit PNGs in `phase3_outputs/roi_crop_audit/`.

**Pass rule:** ≥8/10 sets pass all four checks (at most one failure allowed on n=10).

| Set | ROI excludes grid | ROI excludes label stripe | Tissue mask inside wax | No plastic flood | Pass? |
|-----|-------------------|---------------------------|------------------------|------------------|-------|
| 02 | N | N | N | Y | N |
| 04 | Y | Y | Y | Y | Y |
| 06 | N | N | N | N | N |
| 11 | N | N | N | N | N |
| 28 | N | N | N | N | N |
| 31 | N | N | N | N | N |
| 33 | N | N | N | N | N |
| 35 | N | N | N | N | N |
| 40 | N | N | N | N | N |
| 45 | N | N | N | N | N |

**Score:** 1 / 10 — pilot **FAIL** (need ≥8). Do **not** regen full 47-set library yet.

### Zeke visual notes (2026-05-25)

- **02:** Cyan ROI = full frame; no green tissue mask (`ambiguous_orientation` / failed seg).
- **04:** Only set that looked correct — grid/label excluded, tissue on wax; tiny green in filleted paraffin corners acceptable.
- **06:** Tiny horizontal slit under paraffin; wrong window (no visible backlight border).
- **11:** Small horizontal slit at bottom; misses cassette.
- **28:** Huge ROI over cassette; green masks whole cassette (flood).
- **31:** Tiny horizontal slit; ROI and mask both wrong (no backlight border).
- **33, 35, 40:** Cyan ROI = full image.
- **45:** Tiny slit at bottom.
- **Overall:** Fix 1c regressed vs Fix 1b on most close-frame / no-pad images; tune from `roi_fail_reason` histogram before second pilot.

**Telemetry:** Re-run `phase3_contour_profile.py` after ROI fixes to refresh `cassette_method`, `roi_fail_reason`, `seg_fail_reason`, `reshoot_recommended` columns.
