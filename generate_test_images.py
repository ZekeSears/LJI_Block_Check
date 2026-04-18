"""
generate_test_images.py  --  Synthetic test image generator (v2)
----------------------------------------------------------------
Creates synthetic tissue images that realistically simulate the
variation seen between a paraffin BLOCK (viewed via transillumination)
and its corresponding SLIDE (a 5um section stained and mounted).

REAL-WORLD VARIATIONS we simulate:
  1. Rotation            -- block placed at any angle, slide at any other angle
  2. Translation         -- tissue centered differently in each frame
  3. Scale / shrinkage   -- tissue shrinks ~5-15% during dehydration
  4. Fragmentation       -- one piece in the block can appear as 2-3 on the slide
  5. Piece loss          -- an edge can chip off during cutting
  6. Minor deformation   -- slight warping between adjacent sections

We also generate TEST CATEGORIES:
  - perfect   : identical shapes, no variation (sanity baseline)
  - realistic : a correct match with all variation types layered in
  - fragmented: tissue broke apart between block and slide
  - wrong     : completely different shape type (obvious mismatch)
  - hard_neg  : SAME shape family but DIFFERENT random sample
                (the adversarial case -- must NOT match)
"""

import cv2
import numpy as np
import os

OUTPUT_DIR = "test_images"
W, H = 400, 300  # canvas size


# -------------------- Shape generation --------------------

def make_tissue_blob(center_x, center_y, size, num_points=8, rng=None,
                     shape_type="random"):
    """Generate a single tissue-like closed contour.

    shape_type in {"random", "elongated", "crescent", "spiral", "swiss_roll"}
    """
    if rng is None:
        rng = np.random.default_rng()

    points = []

    if shape_type == "elongated":
        for i in range(num_points):
            angle = 2 * np.pi * i / num_points
            rx = size * rng.uniform(0.8, 1.0)
            ry = size * rng.uniform(0.2, 0.4)
            points.append([
                int(center_x + rx * np.cos(angle)),
                int(center_y + ry * np.sin(angle)),
            ])

    elif shape_type == "crescent":
        arc_points = num_points // 2
        for i in range(arc_points):
            angle = np.pi * 0.2 + (np.pi * 1.6) * i / (arc_points - 1)
            r = size * rng.uniform(0.85, 1.0)
            points.append([
                int(center_x + r * np.cos(angle)),
                int(center_y + r * np.sin(angle)),
            ])
        for i in range(arc_points - 1, -1, -1):
            angle = np.pi * 0.2 + (np.pi * 1.6) * i / (arc_points - 1)
            r = size * rng.uniform(0.35, 0.55)
            points.append([
                int(center_x + r * np.cos(angle)),
                int(center_y + r * np.sin(angle)),
            ])

    elif shape_type in ("spiral", "swiss_roll"):
        total = max(num_points, 24)
        for i in range(total):
            t = i / total
            angle = t * 4 * np.pi
            r = size * (0.2 + 0.7 * t) + rng.uniform(-3, 3)
            points.append([
                int(center_x + r * np.cos(angle)),
                int(center_y + r * np.sin(angle)),
            ])

    else:  # "random"
        angles = np.linspace(0, 2 * np.pi, num_points, endpoint=False)
        radii = rng.uniform(0.5, 1.0, size=num_points) * size
        for angle, radius in zip(angles, radii):
            points.append([
                int(center_x + radius * np.cos(angle)),
                int(center_y + radius * np.sin(angle)),
            ])

    return np.array(points, dtype=np.int32).reshape(-1, 1, 2)


# -------------------- Variation operators --------------------
#
# Each of these takes a list of contours and returns a transformed list.
# They are designed to be stacked ("compose") to simulate realistic drift.

def rotate_contours(contours, angle_deg, pivot=(W // 2, H // 2)):
    """Rotate every point in every contour around `pivot` by `angle_deg`."""
    angle = np.deg2rad(angle_deg)
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    cx, cy = pivot
    out = []
    for c in contours:
        pts = c.reshape(-1, 2).astype(np.float32)
        pts[:, 0] -= cx
        pts[:, 1] -= cy
        x_new = pts[:, 0] * cos_a - pts[:, 1] * sin_a
        y_new = pts[:, 0] * sin_a + pts[:, 1] * cos_a
        pts[:, 0] = x_new + cx
        pts[:, 1] = y_new + cy
        out.append(pts.astype(np.int32).reshape(-1, 1, 2))
    return out


def translate_contours(contours, dx, dy):
    """Shift all contours by (dx, dy)."""
    return [c + np.array([dx, dy], dtype=np.int32).reshape(1, 1, 2) for c in contours]


def scale_contours(contours, factor, pivot=(W // 2, H // 2)):
    """Scale around pivot (uniform shrinkage or expansion)."""
    cx, cy = pivot
    out = []
    for c in contours:
        pts = c.reshape(-1, 2).astype(np.float32)
        pts[:, 0] = (pts[:, 0] - cx) * factor + cx
        pts[:, 1] = (pts[:, 1] - cy) * factor + cy
        out.append(pts.astype(np.int32).reshape(-1, 1, 2))
    return out


def fragment_contour(contour, rng, num_pieces=2):
    """Split one contour into `num_pieces` by cutting along a random chord.

    Implementation: rasterize the contour into a mask, cut a thin line
    through it, then re-extract contours. Realistic because that's
    essentially what happens when tissue tears during sectioning.
    """
    # Rasterize this contour
    mask = np.zeros((H, W), dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)

    # Pick two random points on the bounding box to define the cut line
    x, y, w, h = cv2.boundingRect(contour)
    for _ in range(num_pieces - 1):
        # Cut near the center with a random angle
        cx, cy = x + w // 2, y + h // 2
        theta = rng.uniform(0, np.pi)
        dx, dy = int(200 * np.cos(theta)), int(200 * np.sin(theta))
        cv2.line(mask, (cx - dx, cy - dy), (cx + dx, cy + dy),
                 color=0, thickness=6)

    new_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
    # Filter tiny shards
    return [c for c in new_contours if cv2.contourArea(c) > 100]


def chip_off_edge(contour, rng):
    """Remove a small chunk from one edge (simulates a cutting artifact)."""
    mask = np.zeros((H, W), dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)

    x, y, w, h = cv2.boundingRect(contour)
    # Pick a random spot along the boundary and remove a circular chunk
    # whose radius is ~15-25% of the tissue's bounding box diagonal.
    edge_theta = rng.uniform(0, 2 * np.pi)
    r_chunk = int(0.20 * max(w, h))
    px = int(x + w / 2 + 0.45 * w * np.cos(edge_theta))
    py = int(y + h / 2 + 0.45 * h * np.sin(edge_theta))
    cv2.circle(mask, (px, py), r_chunk, color=0, thickness=-1)

    new_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
    return [c for c in new_contours if cv2.contourArea(c) > 100]


def deform_contour(contour, rng, amplitude=3):
    """Add small random jitter to every contour point (tissue warping)."""
    pts = contour.reshape(-1, 2).astype(np.float32)
    pts += rng.uniform(-amplitude, amplitude, size=pts.shape)
    return pts.astype(np.int32).reshape(-1, 1, 2)


def apply_realistic_variation(contours, rng):
    """Compose a realistic block->slide transformation.

    - random rotation (-30, 30 deg)
    - random translation (+-30 px)
    - mild shrinkage (0.85-0.98)
    - per-point jitter
    """
    angle = rng.uniform(-30, 30)
    dx = int(rng.uniform(-30, 30))
    dy = int(rng.uniform(-30, 30))
    scale = rng.uniform(0.85, 0.98)

    out = rotate_contours(contours, angle)
    out = translate_contours(out, dx, dy)
    out = scale_contours(out, scale)
    out = [deform_contour(c, rng, amplitude=2) for c in out]
    return out


# -------------------- Rendering --------------------

def draw_block_image(contours):
    """Transillumination view: white background, dark tissue silhouettes."""
    image = np.ones((H, W, 3), dtype=np.uint8) * 240
    for c in contours:
        cv2.fillPoly(image, [c], color=(60, 50, 45))
    return image


def draw_slide_image(contours, stain="HE"):
    image = np.ones((H, W, 3), dtype=np.uint8) * 245
    stain_colors = {
        "HE":  (180, 100, 200),
        "PAS": (180,  80, 210),
        "PSR": ( 80, 100, 200),
    }
    color = stain_colors.get(stain, (180, 100, 200))
    for c in contours:
        cv2.fillPoly(image, [c], color=color)
    return image


# -------------------- Tissue family generator --------------------
#
# A "family" = a parametric recipe that always produces tissue with the
# same general character (e.g. "two-piece random blob" vs "single crescent").
# Hard negatives pull from the SAME family but with a different random seed,
# so they look statistically similar but are not the same tissue.

FAMILIES = [
    {"name": "single_blob",     "n": 1, "type": "random"},
    {"name": "two_blobs",       "n": 2, "type": "random"},
    {"name": "three_blobs",     "n": 3, "type": "random"},
    {"name": "crescent",        "n": 1, "type": "crescent"},
    {"name": "elongated_strip", "n": 1, "type": "elongated"},
    {"name": "swiss_roll",      "n": 1, "type": "swiss_roll"},
]


def build_family(family, rng):
    """Construct a fresh tissue instance from a family recipe."""
    contours = []
    n = family["n"]
    for i in range(n):
        cx = int(W / 2 + (i - (n - 1) / 2) * 110)
        cy = H // 2 + rng.integers(-15, 15)
        size = int(rng.integers(45, 70))
        contours.append(
            make_tissue_blob(cx, cy, size, rng=rng, shape_type=family["type"])
        )
    return contours


# -------------------- Test-case emitters --------------------

def emit_perfect(idx, rng):
    """Perfect match: identical contours on both images."""
    family = FAMILIES[idx % len(FAMILIES)]
    contours = build_family(family, rng)
    stain = ["HE", "PAS", "PSR"][idx % 3]
    return {
        "block": draw_block_image(contours),
        "slide": draw_slide_image(contours, stain=stain),
        "stain": stain,
        "family": family["name"],
    }


def emit_realistic(idx, rng):
    """Correct match with realistic rotation/translation/scale/jitter."""
    family = FAMILIES[idx % len(FAMILIES)]
    block_contours = build_family(family, rng)
    slide_contours = apply_realistic_variation(block_contours, rng)
    stain = ["HE", "PAS", "PSR"][idx % 3]
    return {
        "block": draw_block_image(block_contours),
        "slide": draw_slide_image(slide_contours, stain=stain),
        "stain": stain,
        "family": family["name"],
    }


def emit_fragmented(idx, rng):
    """Correct match but tissue fragmented between block and slide."""
    # Prefer families with larger single pieces that can plausibly fragment
    candidates = [f for f in FAMILIES if f["n"] == 1]
    family = candidates[idx % len(candidates)]
    block_contours = build_family(family, rng)

    # Apply realistic variation THEN fragment the largest piece
    slide_contours = apply_realistic_variation(block_contours, rng)
    if slide_contours:
        largest = max(slide_contours, key=cv2.contourArea)
        fragmented = fragment_contour(largest, rng, num_pieces=2)
        slide_contours = [c for c in slide_contours if not np.array_equal(c, largest)]
        slide_contours.extend(fragmented)

    # Also chip an edge on one piece for extra realism
    if slide_contours and rng.random() < 0.5:
        c = slide_contours[0]
        slide_contours = chip_off_edge(c, rng) + slide_contours[1:]

    stain = "HE"
    return {
        "block": draw_block_image(block_contours),
        "slide": draw_slide_image(slide_contours, stain=stain),
        "stain": stain,
        "family": family["name"],
    }


def emit_wrong(idx, rng):
    """Obvious mismatch: two different shape families."""
    block_fam = FAMILIES[idx % len(FAMILIES)]
    slide_fam = FAMILIES[(idx + 3) % len(FAMILIES)]
    block_contours = build_family(block_fam, rng)
    slide_contours = build_family(slide_fam, rng)
    stain = "HE"
    return {
        "block": draw_block_image(block_contours),
        "slide": draw_slide_image(slide_contours, stain=stain),
        "stain": stain,
        "family": f"{block_fam['name']}_vs_{slide_fam['name']}",
    }


def emit_hard_negative(idx, rng):
    """Adversarial: SAME family, two DIFFERENT random samples.

    These are the critical false-positive test cases. The shapes will be
    statistically similar (same family) but geometrically different.
    They MUST score below the match threshold.
    """
    family = FAMILIES[idx % len(FAMILIES)]
    block_contours = build_family(family, rng)
    slide_contours = build_family(family, rng)  # new draw, different result
    stain = "HE"
    return {
        "block": draw_block_image(block_contours),
        "slide": draw_slide_image(slide_contours, stain=stain),
        "stain": stain,
        "family": family["name"] + "_hardneg",
    }


# -------------------- Main --------------------

def save_pair(case, category, idx):
    """Write block and slide images to disk with standardized naming."""
    block_path = f"{OUTPUT_DIR}/{category}_{idx}_block.png"
    slide_path = f"{OUTPUT_DIR}/{category}_{idx}_slide_{case['stain']}.png"
    cv2.imwrite(block_path, case["block"])
    cv2.imwrite(slide_path, case["slide"])
    return block_path, slide_path


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    rng = np.random.default_rng(seed=42)

    categories = [
        ("perfect",   emit_perfect,      5),
        ("realistic", emit_realistic,    6),
        ("fragmented", emit_fragmented,  4),
        ("wrong",     emit_wrong,        5),
        ("hardneg",   emit_hard_negative, 6),
    ]

    for cat_name, emitter, count in categories:
        print(f"\n[{cat_name}] generating {count} pairs...")
        for i in range(count):
            case = emitter(i, rng)
            block_p, slide_p = save_pair(case, cat_name, i)
            print(f"  {cat_name}_{i}  family={case['family']}  stain={case['stain']}")

    total = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png")])
    print(f"\nDone. {total} synthetic images in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
