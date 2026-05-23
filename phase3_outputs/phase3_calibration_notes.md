# Phase 3 calibration notes

**Date:** 2026-05-23

## Provenance

- **Dataset:** `iphone_images/` — iPhone backlit captures, single shooting session
- **Re-calibration:** Required if images are re-shot or lighting changes materially

## Recommended router thresholds (hybrid v2)

Primary routing uses **tissue in filename** when available, then **slide**
`total_tissue_area` and **dominance** (max contour area / sum of areas).
Contour-count thresholds are legacy fallback only.

| Constant | Value | Derivation |
|----------|-------|------------|
| `SLIDE_TOTAL_TISSUE_AREA_PX` | 224998 | median_midpoint on slide total tissue area (lung median 301964, esophagus median 148033) |
| `DOMINANCE_MIN_FOR_SHAPE` | 0.943 | median_midpoint on slide dominance (lung median 0.985, esophagus median 0.900) |

- Contour-count calibration **overlapped** (expected on this dataset); do not use count for primary routing.

**Sanity check:** PASS

## Per-(tissue, role) statistics

| tissue | role | n | contour_count median | median_area median |
|--------|------|---|----------------------|---------------------|
| esophagus | block_silhouette | 7 | 3.0 | 333372 |
| esophagus | slide | 7 | 4.0 | 6848 |
| lung | block_silhouette | 14 | 3.0 | 356570 |
| lung | slide | 14 | 2.0 | 20465 |

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

## Low sample-size warnings

- lung slide calibration pool n=13 (<15); percentiles are unstable.
- esophagus slide calibration pool n=7 (<15); percentiles are unstable.
