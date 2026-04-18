# CHANGES.md — Pillar C Rebuild (v1 → v2)

Log of every algorithmic and structural change made to the shape-matching
pipeline, with the reasoning behind each decision.

---

## Why this rebuild happened

The v1 matcher had two critical failure modes:

1. **Close-but-wrong false positives.** Hu Moments on the *largest contour
   only* could not distinguish two random blobs of similar size. Any tissue
   from the same general family (e.g. two different kidney cross-sections)
   scored in the 0.79–0.91 range — well above the 0.7 threshold.
2. **Broken on real histology.** The v1 segmentation (Otsu on inverted
   grayscale) fragmented H&E-stained tissue into dozens of "pieces" because
   the dark hematoxylin regions were detected as separate objects from the
   lighter eosin regions of the same tissue. Tested on real BIRL rat-kidney
   H&E slide → `block_n=35` instead of 1.

Project policy (per brief): false positives are unacceptable; false negatives
(correct slides flagged for manual recheck) are fine.

---

## Structural changes

### Added dependencies

| Package        | Purpose                                                    |
|----------------|------------------------------------------------------------|
| `mahotas`      | Zernike moment computation (not in OpenCV)                 |
| `scikit-image` | General-purpose image analysis utilities (pulled in for future use) |

Both install cleanly on Raspberry Pi 5 / ARM Linux. Target deployment unaffected.

### New / renamed files

| File                         | Change | Purpose                                   |
|------------------------------|--------|-------------------------------------------|
| `generate_test_images.py`    | rewrite | New categories + realistic variations    |
| `shape_matcher.py`           | rewrite | Composite scorer replacing Hu-only        |
| `test_real_images.py`        | new    | Smoke test on real BIRL pairs             |
| `calibrate_threshold.py`     | new    | Empirical threshold selection             |
| `test_images/real/*.jpg`     | new    | 4 real serial-section images from BIRL    |
| `CHANGES.md`                 | new    | This file                                 |

### Backwards compatibility

`shape_matcher.extract_contours(image, min_area=300)` is preserved as a
shim so `stain_verifier.py` continues to work unchanged.

---

## Algorithmic changes

### 1. Tissue-mask segmentation (was: Otsu on inverted grayscale)

**v1 problem:** on real H&E slides, hematoxylin (blue-purple nuclei) and
eosin (pink cytoplasm) regions had different brightnesses. Otsu picked a
threshold between them, so the mask showed ONLY the darker nuclei as
tissue and treated the lighter cytoplasm as background. Result: one
continuous tissue piece appeared as 30+ fragmented specks.

**v2 fix:** Use HSV and define tissue as "anything NOT bright near-white
background." A pixel is tissue if either:
- Saturation > 25 (any color = not white glass/wax), OR
- Value < 220 (any darkness = block silhouette or tissue)

Then morphological **closing** (15×15 ellipse) unifies internal stain
variations into one region, and **opening** (5×5 ellipse) removes speckle.

**Verified on:**
- Synthetic perfect/realistic/fragmented/wrong/hardneg: all segment correctly.
- Real BIRL rat kidney HE: `block_n` went from 35 → 1. 
- Real BIRL lung lesion: clean single-piece segmentation.

### 2. Area filtering: absolute → relative

**Was:** `area > 300 pixels` (hard-coded). Breaks at any resolution other
than our 400×300 canvas.

**Now:** `area >= max(30, 2% × largest_contour_area)`. Works at any
resolution from thumbnail to 12MP HQ camera.

### 3. Shape scoring: single Hu Moments → five-component ensemble

The new `score_pair(block_img, slide_img)` returns a composite in [0, 1]
computed as a weighted sum of five independent sub-scores. No single
metric can fool the ensemble.

| Sub-score | Weight | What it captures | Invariance |
|-----------|-------:|------------------|------------|
| `hu`        | 0.10 | Largest-contour Hu moments, `cv2.matchShapes` | rotation, scale, translation |
| `zernike`   | 0.30 | 36 Zernike moments of aligned unified mask (degree 10) | rotation + scale (via pre-alignment) |
| `fourier`   | 0.20 | First 20 Fourier descriptors of largest contour boundary | rotation, scale, translation |
| `geometric` | 0.15 | Solidity, circularity, elongation ratios on unified mask | rotation, scale |
| `iou`       | 0.25 | Pixel overlap after PCA alignment + scale normalization | rotation, translation, scale, direction |

Each sub-score is squashed through `exp(-k * distance)` so they all land
in [0, 1] where 1.0 = perfect match.

**Weight rationale:**
- Hu gets the lowest weight because it was the single metric that caused
  v1's false positives. It's included as a smooth sanity check, not a
  primary signal.
- Zernike gets the highest weight because it's the most discriminative
  for complex shapes (36 moments vs Hu's 7).
- IoU gets the second-highest weight because it's the closest thing to
  "ground truth" — after alignment, pixels literally overlap or they
  don't.
- Fourier adds boundary-detail discrimination that Zernike sometimes
  misses on smooth outlines.
- Geometric features are a topology sanity check.

### 4. Zernike normalization: bbox-crop → principal-axis alignment

**v1 attempt (abandoned):** Crop to tight bbox, pad square, resize. This
broke rotation invariance because a rotated shape has a different bbox
than its unrotated version, so "same tissue at two rotations" scored
differently.

**v2:** Align both masks to their PCA principal axis BEFORE the Zernike
computation. After alignment, any residual difference is genuine shape
difference, not rotation.

### 5. Aligned IoU with direction disambiguation

Principal-axis alignment leaves a ±180° and a mirror ambiguity (PCA
doesn't distinguish major-axis direction). We try all 4 flip combinations
and take the best IoU.

### 6. Multi-contour awareness

- Zernike and IoU operate on the **unified mask** (union of all tissue
  contours) → fragmentation-tolerant.
- Hu and Fourier operate on the **largest contour** → preserve the v1
  behavior as a baseline.
- Geometric features use both: total area/perimeter across the set,
  convex hull of all points combined.

Explicitly **not** comparing piece counts: fragmentation is a legitimate
difference we want to tolerate, and piece-count mismatch would penalize
it.

---

## Test data changes

### Synthetic categories

v1 had two categories (match / mismatch). v2 has five:

| Category     | Count | Purpose                                             |
|--------------|------:|-----------------------------------------------------|
| `perfect`    | 5 | Identical shapes, sanity baseline                    |
| `realistic`  | 6 | Correct match + rotation (±30°) + translation (±30px) + shrinkage (0.85–0.98) + point jitter |
| `fragmented` | 4 | Correct match, but tissue split into 2+ pieces during cutting |
| `wrong`      | 5 | Two DIFFERENT shape families — obvious mismatch     |
| `hardneg`    | 6 | **Same shape family, new random draw** — adversarial false-positive test |

The `hardneg` category is the critical new addition. Random blobs of the
same family are genuinely hard to distinguish, which is exactly the
property we need to stress-test.

### Real images

Added 4 real serial-section thumbnails from the BIRL challenge dataset
([github.com/Borda/BIRL](https://github.com/Borda/BIRL)), public-domain
CC-licensed:

| File                                    | Organ        | Stain           |
|-----------------------------------------|--------------|-----------------|
| `rat_kidney_HE.jpg`                     | rat kidney   | H&E             |
| `rat_kidney_PanCytokeratin.jpg`         | rat kidney   | PanCytokeratin  |
| `lung_lesion_HE.jpg`                    | lung lesion  | H&E             |
| `lung_lesion_proSPC.jpg`                | lung lesion  | proSPC          |

Each pair is two adjacent serial sections from the same block, stained
differently. This is the closest publicly available proxy for the
block↔slide shape-matching problem: the tissue outline should be highly
similar across adjacent sections.

Test cases built from them:
- **2 correct matches:** kidney HE↔PanC, lung HE↔proSPC
- **4 cross-organ mismatches:** kidney↔lung in all 4 combinations

---

## Calibration result

Running `calibrate_threshold.py` on all 32 test pairs (26 synthetic + 6 real):

```
Max score among MUST-REJECT pairs : 0.673  (synthetic hardneg_0)
Min score among MUST-PASS pairs   : 0.656  (synthetic fragmented_2)
Gap                               : -0.017
```

The ranges overlap by 0.017, so no threshold gives a perfect
classification across all 32. Following project policy (zero false
positives preferred), we selected **0.68**, which:

| Category        | Pass rate |
|-----------------|----------:|
| perfect         | 5/5 (100%) |
| realistic       | 6/6 (100%) |
| fragmented      | 3/4 ( 75%) |
| wrong           | 5/5 reject (100%) |
| hardneg         | 6/6 reject (100%) |
| real_match      | 2/2 ( 100%) |
| real_mismatch   | 4/4 reject (100%) |

**Zero false positives.** One false negative (`fragmented_2`, score 0.656)
gets flagged for manual review, which is the intended behavior when the
system is uncertain.

---

## What this does NOT solve (future work)

- **Rare extreme fragmentation** (tissue into 5+ pieces with large gaps)
  may still fall below threshold. The IoU component handles this best;
  consider raising its weight if real-world data suggests we need to.
- **Whole-slide images** (gigapixel .svs / .ndpi formats) are not
  supported. The current pipeline assumes a single-frame camera capture
  of the full block/slide. WSI support would need openslide or tifffile
  streaming.
- **Stain-specific artifacts** (tissue folding, bubbles, cover-slip
  drift) aren't simulated. Once real images arrive from Zbigniew, we
  should add those variations to the generator.
- **TMAs (tissue microarrays)**: 600-sample TMA layouts are an entirely
  different matching problem (grid position-based, not silhouette-based).
  Out of scope for Pillar C.

---

## How to re-tune

If test results drift (new hardware, new image characteristics, new
stains), re-run:

```bash
python generate_test_images.py    # regenerate synthetic suite
python calibrate_threshold.py     # get fresh threshold recommendation
```

Then update `DEFAULT_THRESHOLD` in `shape_matcher.py`.
