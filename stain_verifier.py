"""
stain_verifier.py  --  Pillar D: Stain Verification (Color Check)
-----------------------------------------------------------------
Verifies that the stain color on a slide matches what the label says.

For example: if a slide's QR code says "HE" (Hematoxylin & Eosin),
the tissue should look pink/purple. If it looks red/green instead,
it might actually be a PSR (Picrosirius Red) slide -- wrong stain!

HOW IT WORKS:
1. Convert the image from BGR to HSV color space
2. Use the tissue mask (from shape_matcher) to look ONLY at tissue pixels
3. Calculate the average Hue of those tissue pixels
4. Check if that Hue falls in the expected range for the labeled stain

WHAT IS HSV?
  BGR (Blue, Green, Red) is how computers store color but it's hard
  to reason about. HSV separates color into three intuitive parts:
    - Hue (H): The "pure color" -- red, orange, yellow, green, blue, purple
              Ranges 0-179 in OpenCV (not 0-360 like in art class)
    - Saturation (S): How vivid/intense the color is (0 = gray, 255 = pure color)
    - Value (V): How bright/dark it is (0 = black, 255 = bright)

  By checking just the Hue, we can identify stain type regardless of
  how bright or dark the tissue happens to be.

JAVA ANALOGY:
  If BGR is like storing a date as "milliseconds since epoch" (accurate
  but hard to read), HSV is like storing it as year/month/day (intuitive).
"""

import cv2
import numpy as np

# Hue ranges for each stain type (OpenCV Hue: 0-179)
# These are approximate and WILL need calibration with real images!
#
# Color wheel in OpenCV Hue:
#   0-10   = Red
#   10-25  = Orange
#   25-35  = Yellow
#   35-85  = Green
#   85-130 = Blue
#   130-170 = Purple/Pink
#   170-179 = Red (wraps around)
#
STAIN_PROFILES = {
    "HE": {
        "name": "Hematoxylin & Eosin",
        "hue_min": 120,
        "hue_max": 175,
        "description": "Pink/Purple",
    },
    "PAS": {
        "name": "Periodic Acid-Schiff",
        "hue_min": 130,
        "hue_max": 179,
        "description": "Intense Magenta",
    },
    "PSR": {
        "name": "Picrosirius Red / Fast Green",
        "hue_min": 0,
        "hue_max": 15,
        "description": "Red",
        # PSR also has green component -- we check red for now
    },
}


def verify_stain(image, mask, expected_stain):
    """
    Checks if the tissue color matches the expected stain.

    Parameters
    ----------
    image : numpy array (BGR)
        The slide image.
    mask : numpy array (single channel, 0/255)
        Binary mask where tissue pixels = 255. Get this from
        shape_matcher.extract_contours().
    expected_stain : str
        The stain label from the QR code ("HE", "PAS", or "PSR").

    Returns
    -------
    dict with keys:
        valid : bool -- does the color match the expected stain?
        expected_stain : str -- what we expected
        detected_hue : float -- the average hue we measured
        expected_range : tuple -- (min_hue, max_hue) for this stain
        message : str -- human-readable result
    """
    if expected_stain not in STAIN_PROFILES:
        return {
            "valid": False,
            "expected_stain": expected_stain,
            "detected_hue": None,
            "expected_range": None,
            "message": f"Unknown stain type: '{expected_stain}'",
        }

    profile = STAIN_PROFILES[expected_stain]

    # Step 1: Convert BGR -> HSV
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Step 2: Calculate mean color ONLY within the tissue mask
    # cv2.mean() returns (H_mean, S_mean, V_mean, 0)
    # The mask parameter tells it to ignore background pixels
    mean_hsv = cv2.mean(hsv, mask=mask)
    mean_hue = mean_hsv[0]
    mean_sat = mean_hsv[1]

    # Step 3: Check if the measured hue falls in the expected range
    hue_min = profile["hue_min"]
    hue_max = profile["hue_max"]
    hue_ok = hue_min <= mean_hue <= hue_max

    # Also check that saturation is high enough (tissue should be colorful)
    # Low saturation means grayish -- could indicate unstained tissue or bad image
    sat_ok = mean_sat > 30

    is_valid = hue_ok and sat_ok

    # Build a human-readable message
    if is_valid:
        message = (f"Stain OK: expected {expected_stain} ({profile['description']}), "
                   f"measured hue={mean_hue:.1f} (range {hue_min}-{hue_max})")
    elif not sat_ok:
        message = (f"WARNING: Low saturation ({mean_sat:.1f}). "
                   f"Tissue may be unstained or image too dark.")
    else:
        # Try to guess what stain it actually is
        detected = identify_stain(mean_hue)
        message = (f"STAIN MISMATCH: labeled as {expected_stain} "
                   f"({profile['description']}), but hue={mean_hue:.1f} "
                   f"looks like {detected}")

    return {
        "valid": is_valid,
        "expected_stain": expected_stain,
        "detected_hue": round(mean_hue, 1),
        "mean_saturation": round(mean_sat, 1),
        "expected_range": (hue_min, hue_max),
        "message": message,
    }


def identify_stain(hue):
    """
    Given a hue value, guess which stain it most likely is.
    This is a simple lookup -- real-world would need more sophistication.
    """
    for name, profile in STAIN_PROFILES.items():
        if profile["hue_min"] <= hue <= profile["hue_max"]:
            return f"{name} ({profile['description']})"
    return f"Unknown (hue={hue:.1f})"


# ---- Run it directly to test ----
if __name__ == "__main__":
    from shape_matcher import extract_contours
    import glob

    print("=" * 50)
    print("PILLAR D: Stain Verification Test")
    print("=" * 50)

    # Test correctly-labeled slides
    print("\n--- Correctly Labeled Slides ---")
    slide_files = sorted(glob.glob("test_images/slide_match_*_*.png"))
    for slide_path in slide_files:
        # Extract stain from filename: slide_match_0_HE.png -> HE
        stain = slide_path.split("_")[-1].replace(".png", "")

        slide_img = cv2.imread(slide_path)
        _, mask = extract_contours(slide_img)

        result = verify_stain(slide_img, mask, stain)
        status = "PASS" if result["valid"] else "FAIL"
        print(f"  [{status}] {slide_path}")
        print(f"         {result['message']}")

    # Test wrong-stain slide
    print("\n--- Wrong Stain Test ---")
    slide_path = "test_images/slide_wrongstain_0_HE.png"
    slide_img = cv2.imread(slide_path)
    if slide_img is not None:
        _, mask = extract_contours(slide_img)
        # The file is labeled HE but was actually drawn with PSR colors
        result = verify_stain(slide_img, mask, "HE")
        status = "PASS" if not result["valid"] else "FAIL"
        print(f"  [{status}] {slide_path}")
        print(f"         {result['message']}")
