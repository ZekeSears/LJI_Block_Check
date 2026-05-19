"""
phase35_id_parsing.py — DataMatrix and QR decoding from physical labels.

Parallel sub-track to the matcher work. Reads:
  - DataMatrix codes from block-barcode photos (pylibdmtx)
  - QR codes from slide labels (pyzbar)

Pre-mortem §4 critical: pylibdmtx and pyzbar require system libraries
(libdmtx and libzbar). On Windows neither is pip-installable; users must
either install wheels that bundle the DLL or place libdmtx.dll/libzbar.dll
on PATH manually. This module's imports are guarded so an undeclared
dependency surfaces as a clean, actionable failure dict — not a cryptic
mid-pipeline ImportError. The dedicated phase35_setup_check.py script
verifies imports BEFORE production use.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Guarded imports — see pre-mortem §4 critical
# ---------------------------------------------------------------------------

try:
    from pyzbar import pyzbar as _pyzbar
    _HAS_PYZBAR = True
except Exception as _exc:    # ImportError, FileNotFoundError, OSError on Win
    _pyzbar = None
    _HAS_PYZBAR = False
    log.info("pyzbar not available: %s", _exc)

try:
    from pylibdmtx import pylibdmtx as _pylibdmtx
    _HAS_PYLIBDMTX = True
except Exception as _exc:
    _pylibdmtx = None
    _HAS_PYLIBDMTX = False
    log.info("pylibdmtx not available: %s", _exc)


# Rotation angles tried by the preprocessing fallback. The non-zero entries
# are chosen to exceed pyzbar's native rotation tolerance (~20°) so the
# fallback is empirically non-tautological per pre-mortem §5 minor item.
ROTATION_FALLBACK_ANGLES_DEG: tuple[float, ...] = (
    -33.0, 33.0, -45.0, 45.0, -60.0, 60.0, 90.0, -90.0,
)


# ---------------------------------------------------------------------------
# QR payload parsing
# ---------------------------------------------------------------------------


def parse_qr_payload(payload: str) -> dict:
    """Parse the canonical payload format WorkOrder_BlockID_Slide#_Stain.

    Returns a dict with success/reason and (when success) the four named
    fields: work_order, block_id, slide_num, stain. Never raises on
    malformed input — the failure is a returned dict.
    """
    if not isinstance(payload, str) or payload == "":
        return {"success": False, "reason": "empty payload"}
    parts = payload.strip().split("_")
    if len(parts) != 4:
        return {"success": False,
                "reason": f"expected 4 _-separated fields, got {len(parts)}"}
    work_order, block_id, slide_num, stain = parts
    if not (work_order and block_id and slide_num and stain):
        return {"success": False, "reason": "empty field in payload"}
    return {
        "success": True,
        "work_order": work_order,
        "block_id": block_id,
        "slide_num": slide_num,
        "stain": stain,
    }


# ---------------------------------------------------------------------------
# QR / DataMatrix decoding
# ---------------------------------------------------------------------------


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raise ValueError(f"Unsupported image shape for decoding: {image.shape}")


def decode_qr(image: np.ndarray) -> dict:
    """Native pyzbar decode (no preprocessing). Returns
    {'success': bool, 'payload': str, 'reason': str}."""
    if not _HAS_PYZBAR:
        return {"success": False, "reason": "pyzbar unavailable; run "
                "phase35_setup_check.py for install guidance"}
    gray = _to_grayscale(image)
    try:
        results = _pyzbar.decode(gray)
    except Exception as exc:    # pylint: disable=broad-except
        return {"success": False, "reason": f"pyzbar.decode raised: {exc}"}
    if not results:
        return {"success": False, "reason": "no_barcode_found"}
    payload = results[0].data.decode("utf-8", errors="replace")
    return {"success": True, "payload": payload, "reason": "ok"}


def decode_qr_with_preprocessing(image: np.ndarray) -> dict:
    """Try native decode first; on failure iterate
    ROTATION_FALLBACK_ANGLES_DEG with CLAHE contrast normalization.

    Pre-mortem §5 minor (non-tautological): the fallback angles exceed
    pyzbar's typical native tolerance so the fallback path is genuinely
    exercised, not just a re-execution of the native path.
    """
    native = decode_qr(image)
    if native["success"]:
        native["preprocessing"] = "none"
        return native

    gray = _to_grayscale(image)
    h, w = gray.shape[:2]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast_corrected = clahe.apply(gray)
    pad = max(h, w) // 2
    padded = cv2.copyMakeBorder(contrast_corrected, pad, pad, pad, pad,
                                cv2.BORDER_CONSTANT, value=255)
    ph, pw = padded.shape[:2]
    centre = (pw / 2.0, ph / 2.0)

    for angle in ROTATION_FALLBACK_ANGLES_DEG:
        M = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rotated = cv2.warpAffine(padded, M, (pw, ph),
                                 borderValue=255)
        attempt = decode_qr(rotated)
        if attempt["success"]:
            attempt["preprocessing"] = f"rotate {angle:+.1f}°+CLAHE"
            return attempt
    return {"success": False, "reason": "no_barcode_found_after_fallback",
            "preprocessing": "rotate+CLAHE failed"}


def decode_datamatrix(image: np.ndarray) -> dict:
    """pylibdmtx decode for block-barcode photos. Same return shape as
    decode_qr()."""
    if not _HAS_PYLIBDMTX:
        return {"success": False, "reason": "pylibdmtx unavailable; run "
                "phase35_setup_check.py for install guidance"}
    gray = _to_grayscale(image)
    try:
        results = _pylibdmtx.decode(gray)
    except Exception as exc:    # pylint: disable=broad-except
        return {"success": False, "reason": f"pylibdmtx.decode raised: {exc}"}
    if not results:
        return {"success": False, "reason": "no_barcode_found"}
    payload = results[0].data.decode("utf-8", errors="replace")
    return {"success": True, "payload": payload, "reason": "ok"}


__all__ = [
    "ROTATION_FALLBACK_ANGLES_DEG",
    "parse_qr_payload",
    "decode_qr",
    "decode_qr_with_preprocessing",
    "decode_datamatrix",
]
