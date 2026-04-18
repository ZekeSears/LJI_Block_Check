"""
calibrate_threshold.py
----------------------
Sweep composite-score thresholds and find the one that maximizes
separation between "must pass" and "must reject" cases.

A case is "must pass" if it's a true match (synthetic perfect/realistic/
fragmented, or real serial-section pair).
A case is "must reject" if it's a non-match (synthetic wrong, real cross-
organ, or synthetic hard-negative).

Per the project brief: false positives are worse than false negatives.
A mismatched slide slipping through is a data-integrity failure; a
flagged correct slide just means a human eyeballs it.

So the scoring rule we pick the threshold by:
    PRIMARY   : reject every "must reject" case (zero false positives)
    SECONDARY : pass as many "must pass" cases as possible

We then report:
    - The highest threshold that achieves zero false positives
    - Which true matches (if any) fall below that threshold
    - Per-category pass rates
"""

import glob
import os
import cv2

from shape_matcher import score_pair


# ---------------- Test-case collection ----------------

def collect_synthetic_pairs():
    pairs = []
    for cat in ["perfect", "realistic", "fragmented", "wrong", "hardneg"]:
        block_files = sorted(glob.glob(f"test_images/{cat}_*_block.png"))
        for bp in block_files:
            idx = os.path.basename(bp).split("_")[1]
            slide_matches = glob.glob(f"test_images/{cat}_{idx}_slide_*.png")
            if slide_matches:
                pairs.append((bp, slide_matches[0], cat, f"{cat}_{idx}"))
    return pairs


REAL_PAIRS = [
    ("test_images/real/rat_kidney_HE.jpg",
     "test_images/real/rat_kidney_PanCytokeratin.jpg",
     "real_match", "rat_kidney_HE_vs_PanC"),
    ("test_images/real/lung_lesion_HE.jpg",
     "test_images/real/lung_lesion_proSPC.jpg",
     "real_match", "lung_HE_vs_proSPC"),
    ("test_images/real/rat_kidney_HE.jpg",
     "test_images/real/lung_lesion_HE.jpg",
     "real_mismatch", "ratK_HE_vs_lung_HE"),
    ("test_images/real/rat_kidney_HE.jpg",
     "test_images/real/lung_lesion_proSPC.jpg",
     "real_mismatch", "ratK_HE_vs_lung_proSPC"),
    ("test_images/real/rat_kidney_PanCytokeratin.jpg",
     "test_images/real/lung_lesion_HE.jpg",
     "real_mismatch", "ratK_PanC_vs_lung_HE"),
    ("test_images/real/rat_kidney_PanCytokeratin.jpg",
     "test_images/real/lung_lesion_proSPC.jpg",
     "real_mismatch", "ratK_PanC_vs_lung_proSPC"),
]


MUST_PASS_CATS  = {"perfect", "realistic", "fragmented", "real_match"}
MUST_REJECT_CATS = {"wrong", "hardneg", "real_mismatch"}


# ---------------- Scoring ----------------

def score_all_pairs():
    results = []
    all_pairs = collect_synthetic_pairs() + REAL_PAIRS
    for bp, sp, cat, label in all_pairs:
        block_img = cv2.imread(bp)
        slide_img = cv2.imread(sp)
        r = score_pair(block_img, slide_img)
        results.append({
            "category": cat,
            "label":    label,
            "score":    r["composite"],
            "subs":     r["sub_scores"],
        })
    return results


# ---------------- Threshold selection ----------------

def find_best_threshold(results):
    """Highest threshold that rejects ALL must-reject cases.

    Returns (threshold, report_dict). If no threshold separates perfectly,
    returns the one that minimizes false positives + false negatives.
    """
    rejects = [r["score"] for r in results if r["category"] in MUST_REJECT_CATS]
    passes  = [r["score"] for r in results if r["category"] in MUST_PASS_CATS]

    max_reject = max(rejects) if rejects else 0.0
    min_pass   = min(passes)  if passes  else 1.0

    if max_reject < min_pass:
        # Clean separation exists -- pick midpoint
        threshold = (max_reject + min_pass) / 2
        strategy = "clean-separation midpoint"
    else:
        # No clean separation. Pick threshold that prioritizes zero
        # false positives (reject max + epsilon).
        threshold = max_reject + 1e-6
        strategy = "zero-FP (false negatives possible)"

    return threshold, {
        "max_reject_score": max_reject,
        "min_pass_score":   min_pass,
        "gap":              min_pass - max_reject,
        "strategy":         strategy,
    }


def apply_threshold(results, threshold):
    """Compute per-category pass rate and enumerate errors."""
    errors = []
    per_cat = {}

    for r in results:
        cat = r["category"]
        per_cat.setdefault(cat, {"total": 0, "correct": 0})
        per_cat[cat]["total"] += 1

        is_match = r["score"] >= threshold
        should_match = cat in MUST_PASS_CATS

        if is_match == should_match:
            per_cat[cat]["correct"] += 1
        else:
            errors.append({
                "label": r["label"],
                "category": cat,
                "score": r["score"],
                "expected": "match" if should_match else "reject",
                "got":      "match" if is_match else "reject",
                "subs": r["subs"],
            })

    return errors, per_cat


# ---------------- Main ----------------

if __name__ == "__main__":
    print("Scoring all test pairs...")
    results = score_all_pairs()

    threshold, report = find_best_threshold(results)

    print()
    print("=" * 70)
    print("CALIBRATION REPORT")
    print("=" * 70)
    print(f"  Max score among MUST-REJECT pairs: {report['max_reject_score']:.3f}")
    print(f"  Min score among MUST-PASS pairs  : {report['min_pass_score']:.3f}")
    print(f"  Gap                              : {report['gap']:+.3f}")
    print(f"  Strategy                         : {report['strategy']}")
    print(f"  SELECTED THRESHOLD               : {threshold:.3f}")

    errors, per_cat = apply_threshold(results, threshold)

    print()
    print("--- Per-category pass rate ---")
    for cat in sorted(per_cat):
        info = per_cat[cat]
        pct = 100 * info["correct"] / info["total"]
        print(f"  {cat:15s}  {info['correct']:2d}/{info['total']:2d}  ({pct:5.1f}%)")

    if errors:
        print()
        print("--- ERRORS (expected vs actual) ---")
        for e in errors:
            tag = "FALSE-POS" if e["expected"] == "reject" else "FALSE-NEG"
            print(f"  [{tag}] {e['label']:30s}  score={e['score']:.3f}  "
                  f"(expected {e['expected']})")
            s = e["subs"]
            print(f"              hu={s['hu']:.2f} zern={s['zernike']:.2f} "
                  f"four={s['fourier']:.2f} "
                  f"geom={s['geometric']:.2f} iou={s['iou']:.2f}")
    else:
        print()
        print("All cases classified correctly at this threshold.")
