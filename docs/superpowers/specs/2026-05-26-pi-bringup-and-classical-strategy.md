# Pi bring-up timeline and classical-first strategy

**Status:** Notes from 2026-05-26 brainstorming (Z shipping update)  
**Related:** `2026-05-26-fix-1e-backlit-rim-parallelogram-anchor-design.md`

## Hardware arrival (Z update)

| Source | ETA | Notes |
|--------|-----|--------|
| PiShop (USPS) | Tomorrow | Tracking `9405551902256084013980`, postal 92037 |
| Amazon (camera stack) | Tuesday | Arducam module, 16mm lens, FPC adapter — no tracking in thread yet |
| VXB gantry | TBD | No shipping info yet |
| LED light pad | Not on PO | Still needed for production backlight |

**Tomorrow:** Pi 5 bring-up (flash SD, boot, SSH, repo clone, `pytest`) even without camera.  
**Tuesday:** Camera stills; desk backlight OK for first `pi_rig` captures before gantry/pad.

## Classical Fix 1e — test on phone before rig

The anchor stack does **not** require Pi hardware to implement or pilot:

```text
dark_frame (15–45%) → rim B–D–B votes → parallelogram → paraffin inside quad → gates (6–55%, no envelope on phone)
```

| Prove now (iPhone pilot 10) | Re-tune after Pi captures |
|-----------------------------|---------------------------|
| Ban paraffin_envelope anchor | `block_roi_constants_pi.json` |
| Quad area gates | Narrower gray / higher rim votes |
| Fail-closed oversize ROI | FOV + exposure repeatability |

**Do not defer Fix 1e implementation until rig is assembled.** Pi simplifies calibration; phone library is the stress test (≥8/10 rubric).

## ML / Hailo

Stay classical for Fix 1e. Consider ML spike only if classical pilot fails twice after Pi JSON calibration. Train on Windows GPU offline; Hailo remains Phase 5+ optional.
