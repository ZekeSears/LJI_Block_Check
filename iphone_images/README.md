# iPhone Images — LJI Histology Verification Project

These are phone images of physical samples from Work Order 7842, captured on a backlight pad for the Phase 1 testing of the automated histology verification system.

## Image Inventory

### Block-only images (multiple blocks, no slides)
- **IMG_3080.jpg** — Three esophagus blocks arranged on backlight. Tiny tissue fragments visible as dark dots through paraffin.
- **IMG_3081.jpg** — Same three esophagus blocks in vertical arrangement.

### Paired block + slide images (one block + its matching slide)
All are work order 7842, stain 01_HE (H&E):
- **IMG_3084.jpg** — Lung sample, slide labeled "WT 5 Lungs HDM". Complex multi-lobe morphology. BEST example of clean paired data.
- **IMG_3085.jpg** — Esophagus sample, slide labeled "WT 4 Esophagus 1372". Tiny tissue fragments. Challenging case.
- **IMG_3086.jpg** — Esophagus sample, slide labeled "WT 3 Esophagus 1371". Tiny tissue fragments.
- **IMG_3087.jpg** — Esophagus sample, slide labeled "WT 2 Esophagus 1370". Includes a mounting artifact (looks like a Swiss roll) — NOT actual tissue, per mentor.
- **IMG_3088.jpg** — Esophagus sample, slide labeled "WT 1 Esophagus 1369". Tiny fragments.
- **IMG_3089.jpg** — Esophagus sample, slide labeled "TWKO 5 Esophagus 1378". Single small fragment.

### Slide-only images (multiple lung slides, no blocks)
- **IMG_3091.jpeg** — Four lung slides (TWKO B1 through B4). All 02_MT (Masson's Trichrome) stained.
- **IMG_3092.jpeg** — Four lung slides: TWKO A4, TWKO A3 (both 02_MT), TWKO B4 (02_HE), HDM A5 (01_HE). Mix of stain types.

### Reference image (not for processing)
- **IMG_3090.jpg** — Photo of the block tray inventory showing all cassettes from WO 7842 with their labels (Lungs and Esophagus, WT/TWKO/NAIVE genotypes).

## Key Observations for Algorithm Testing

1. **Lung samples** have strong contrast and complex morphology — ideal for shape matching with Hu/Zernike moments.
2. **Esophagus biopsies** are tiny (2-3mm fragments) — too small for shape matching, will require constellation/spatial arrangement matching instead.
3. **Cassette lattice** is visible on block edges but should not significantly affect tissue area segmentation.
4. **Mounting artifacts** (bubbles, wrinkles, Swiss-roll-shaped artifacts in IMG_3087) need to be tolerated by the algorithm.
5. **Stain colors visible under backlight:** HE = pink/purple, MT = blue. Useful for HSV verification testing.

## Adding new slides only (orphan pairing)

1. Name files per `incoming/README.md` (e.g. `slide_lung_MT_WT1_WO7842.jpeg`).
2. Drop them in **`iphone_images/incoming/`**.
3. Run `python code/pair_orphan_slides.py` (preview), then `--apply` to create new `set_NN` files paired with an existing block silhouette (tissue + genotype match).

## Source
All images taken by Ezekiel (intern) using iPhone, on a flicker-free LED backlight pad provided by mentor Zbigniew at La Jolla Institute of Immunology Microscopy & Histology Core Facility, May 2025.
