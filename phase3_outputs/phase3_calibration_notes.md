# Phase 3 calibration notes

**Date:** 2026-05-23

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
| esophagus | block_silhouette | 19 | 3.0 | 341234 |
| esophagus | slide | 19 | 2.0 | 6848 |
| lung | block_silhouette | 5 | 3.0 | 349691 |
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
