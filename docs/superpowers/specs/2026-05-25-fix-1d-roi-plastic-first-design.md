# Design: Fix 1d — Plastic-first paraffin ROI (post–Fix 1c audit)

**Status:** Approved for synthesis (2026-05-25)  
**Owner:** Zeke  
**Evidence:** `phase3_outputs/fix1d_roi_audit_report.md`, pilot visual 1/10, iPhone JPEG ablations  
**Supersedes:** Fix 1c detection-chain ordering for phone library; retains production honesty + hybrid calibration

---

## Problem

Fix 1c regressed visual pilot (**1/10**, only set_04) despite improving telemetry. Root causes on real iPhone images:

1. `backlight_cc` / `paraffin_envelope` select wrong objects on fill-frame shots.
2. `ambiguous_orientation` fails before paraffin morph succeeds (sets 02, 33).
3. Gate G2 allows horizontal **slit** ROIs (sets 06, 11).
4. No seg sanity tie to visual rubric (set 28 flood while `roi_ok=True`).

## Goals

- **Approach A:** Wax window via **plastic-frame-first** + row/morph paraffin (Fix 1b core), refined gates.
- **Hybrid:** Production `allow_full_frame_fallback=False`; calibration audit may opt in with flag on PNG title.
- **Pi-ready:** No center-crop hacks; constants keyed by `capture_source=phone|pi`.
- **Pilot:** ≥8/10 visual on same 10 sets before 47-set regen.

## Non-goals

- Full-frame block dark threshold.
- Center-% crop (rejected).
- Block HSV in production.
- Verification gap / Tier B until pilot passes.

## Architecture

See `proposed_plan.md` (Fix 1d) for pipeline steps, gates G1–G5, and constants files.

## Phone vs Pi

| | Phone library | Pi rig |
|---|---------------|--------|
| Role | Stress test | Production target |
| `backlight_cc` | Only if margin strength ≥ strict threshold | Enabled when pad reliable |
| Constants | `block_roi_constants_phone.json` | `block_roi_constants_pi.json` (first batch) |
