"""
test_real_images.py  --  Run composite matcher on real BIRL serial sections.

Two confirmed correct pairs:
  1. Rat Kidney: HE slide  <-> PanCytokeratin slide   (same block, adjacent cuts)
  2. Lung:      HE slide   <-> proSPC slide           (same block, adjacent cuts)

Four obvious mismatches (cross-pairings):
  3. Rat Kidney HE   <-> Lung HE            (different organ entirely)
  4. Rat Kidney HE   <-> Lung proSPC
  5. Rat Kidney PanC <-> Lung HE
  6. Rat Kidney PanC <-> Lung proSPC

Expected behavior:
  - Pairs 1,2: high composite score (above threshold)
  - Pairs 3-6: low composite score (well below threshold)

We treat each stained slide AS IF it were also a block silhouette,
because the tissue outline is what matters for shape matching, and
serial sections have the same outline geometry.
"""

import cv2
from shape_matcher import run_comparison, score_pair

PAIRS_SAME = [
    ("test_images/real/rat_kidney_HE.jpg",
     "test_images/real/rat_kidney_PanCytokeratin.jpg",
     "Rat kidney: HE vs PanCytokeratin"),
    ("test_images/real/lung_lesion_HE.jpg",
     "test_images/real/lung_lesion_proSPC.jpg",
     "Lung: HE vs proSPC"),
]

PAIRS_DIFFERENT = [
    ("test_images/real/rat_kidney_HE.jpg",
     "test_images/real/lung_lesion_HE.jpg",
     "Rat kidney HE vs Lung HE"),
    ("test_images/real/rat_kidney_HE.jpg",
     "test_images/real/lung_lesion_proSPC.jpg",
     "Rat kidney HE vs Lung proSPC"),
    ("test_images/real/rat_kidney_PanCytokeratin.jpg",
     "test_images/real/lung_lesion_HE.jpg",
     "Rat kidney PanC vs Lung HE"),
    ("test_images/real/rat_kidney_PanCytokeratin.jpg",
     "test_images/real/lung_lesion_proSPC.jpg",
     "Rat kidney PanC vs Lung proSPC"),
]


def show(result, label):
    s = result["sub_scores"]
    flag = "MATCH " if result["match"] else "REJECT"
    print(f"  [{flag}] {label}")
    print(f"           composite={result['composite']:.3f}  "
          f"hu={s['hu']:.2f} zern={s['zernike']:.2f} "
          f"four={s['fourier']:.2f} "
          f"geom={s['geometric']:.2f} iou={s['iou']:.2f}  "
          f"(block_n={result['block_contour_count']}, "
          f"slide_n={result['slide_contour_count']})")


if __name__ == "__main__":
    print("=" * 70)
    print("REAL BIRL SERIAL-SECTION PAIRS")
    print("=" * 70)

    print("\n--- SAME TISSUE (must match) ---")
    for a, b, label in PAIRS_SAME:
        res = run_comparison(a, b)
        show(res, label)

    print("\n--- DIFFERENT TISSUE (must not match) ---")
    for a, b, label in PAIRS_DIFFERENT:
        res = run_comparison(a, b)
        show(res, label)
