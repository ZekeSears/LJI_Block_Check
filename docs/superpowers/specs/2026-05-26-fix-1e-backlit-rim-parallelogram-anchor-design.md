# Design: Fix 1e — Backlit rim signature + parallelogram cassette anchor

**Status:** Brainstorm approved for planning gate (2026-05-26)  
**Owner:** Zeke  
**Evidence:** `phase3_outputs/plastic_rim_clicks.json`, `phase3_outputs/plastic_rim_viability.md`, Fix 1d pilot visual 1/10, rim-signature probes (2026-05-25)  
**Supersedes:** Fix 1d as primary anchor strategy (1d code may remain until 1e lands); retains Plan C honesty (fail-closed, no envelope anchor on phone)

**Not implemented:** No `phase3_block_roi.py` changes under this document until `proposed_plan.md` v2 + pre-mortem pass.

---

## 1. Problem (why Fix 1d is not enough)

Fix 1d improved telemetry but **pilot visual framing stayed ~1/10**. Measured causes:

| Failure | Evidence |
|---------|----------|
| Wrong anchor | Phone library: `paraffin_envelope` ~98% of image when `plastic_frame` returns `None` |
| Plastic gray band alone | Pooled clicks span gray 27–115; single band 80–135 leaves largest CC ~3% on set_04 (fails 15% area gate) |
| Oversize ROI passes gates | G5 allows up to 90% image; ~76% ROI still `roi_ok=True` on 02/04/28/33 |
| Axis-aligned box | User quads ~**10%** image on set_04; code cyan ~76%; rotation not modeled |
| Slit / strip | Sets 06/31: `plastic_frame` + opposite-end strip → `roi_sliver` |

**User observation (validated):** Along a line from light box → plastic wall → wax, gray often follows **bright → dark trough → brighter inward** (backlit rim signature). Probes on pilot 10: **2–4/4 edges** show this on most sets; **0/4** on 06/31 (lung fills frame).

**Click calibration (`plastic_rim_clicks.json`, n=84):** Verdict **MIXED_PROFILE** — square sets split into darker-rim (median ~38–57) vs lighter-rim (median ~73–93) clusters. Corner quads imply cassette area **~6–33%** of image (set_04 **~9.5%**), not 76%.

---

## 2. Goal and non-goals

### Goals

1. **Cassette anchor** that matches human framing on pilot 10: wax window inside plastic, label/grid mostly out, area **~6–35%** of image (from quads).
2. **Rotated cassette support:** anchor geometry is a **parallelogram** (4 corners or `minAreaRect`), not image-axis AABB only.
3. **Classical, deterministic** pipeline on Pi 5; explainable telemetry; pytest-friendly.
4. **Pilot gate:** ≥8/10 on `phase3_outputs/pilot_roi_rubric.md` (ROI framing only) before 47-set contour regen.

### Non-goals (Fix 1e)

- Perfect green tissue mask inside crop (Phase 3 segmentation audit is separate).
- Hailo / neural deployment (Phase 5+ contingency only).
- Unlocking Tier B router or claiming signal-gate fix.
- Full-frame block threshold or center-% crop.

---

## 3. Anchor methods — alternatives and trade-offs

At least eight ways to localize the cassette. Fix 1e should **compose** a primary + fallbacks, not rely on one cue.

| # | Method | Idea | Pros | Cons | Role in Fix 1e |
|---|--------|------|------|------|----------------|
| 1 | **Backlit rim signature (B–D–B)** | Sample 1D profile outside→inside: bright pad → dark plastic → brighter wax | Matches physics; works 2–4/4 edges on most pilots; uses gradient not one gray | Breaks on label/grid side, 06/31; needs coarse center/contour | **Primary validator** on contour samples |
| 2 | **Dark frame + area band** | `gray < FRAME_THRESH`, morph close, keep blob **15–45%** image area | Simple; no plastic gray; works when blob is whole cassette | 06/31 blob ~36%; may include label; not tight wax window alone | **Coarse anchor** + fallback |
| 3 | **Plastic gray CC (calibrated)** | Mask from click-derived LOW/HIGH (+ optional max saturation) | Directly targets rim material | Fragmented CC (<15%); MIXED_PROFILE across sets | **Assist** after morph close / dual profile |
| 4 | **`minAreaRect` / 4-point quad** | Fit minimum-area rectangle or user-ordered quad to plastic contour or rim votes | **Handles rotation**; matches calibration tool | 4-point order matters; AABB from rect still wrong for gates unless warp | **Geometry output** of anchor |
| 5 | **Paraffin envelope (current)** | Largest bright-wax CC | Sometimes finds wax | **Banned on phone** as anchor — selects ~98% frame | **Disallowed** for `capture_source=phone` |
| 6 | **Hough / line fitting** | Detect cassette rectangle edges as line intersections | Rotation-aware if lines clean | Grid holes, label text, glare break Hough | **Deferred** — high false-line rate on pilots |
| 7 | **Barcode-adjacent geometry** | Use `block_barcode` pose to infer silhouette region | Strong prior when barcode captured | Block silhouette often shot without barcode in frame; extra capture step | **Out of scope** for silhouette-only path |
| 8 | **Fixed rig mechanical prior** | Gantry + fixed LED → known FOV, center, aspect | Collapses variance; best long-term | Not available on `iphone_images/` benchmark | **Pi constants** later; informs area/aspect gates |

**Recommendation:** **(2) coarse dark_frame → (1) rim scoring on boundary → (4) parallelogram fit → paraffin inside quad → Plan C gates.** Plastic gray (3) only as tie-breaker with morphology, not sole anchor.

---

## 4. Parallelogram vs axis-aligned bounding box (AABB)

### When AABB is enough

- Cassette **upright within ~5°** and audit only needs rough framing.
- Pi rig with mechanical square-up (Phase 5) may make AABB sufficient again.

### When parallelogram is required

- Phone bench photos with **visible rotation** (user corner quads are trapezoids, not rectangles aligned to image axes).
- Any anchor that uses `cv2.boundingRect` on a rotated contour **over-includes** corners of the image (same failure mode as 76% cyan box, smaller degree).

### Proposed geometry model

```text
Image
  └─ CassetteAnchor (parallelogram)
        corners: 4 x (x,y) ordered TL→TR→BR→BL (cassette frame)
        OR minAreaRect(center, size, angle) from rim-supported contour
  └─ Inner inset (offset ~6% along local normal or shrink toward center)
  └─ Paraffin ROI (rows/morph inside inset, axis-aligned in **warped** crop optional)
  └─ Final ROI for Otsu (may stay AABB in warped space)
```

**Two implementation tiers (pick in plan v2):**

| Tier | Approach | Paraffin / strip | Otsu | Complexity |
|------|----------|------------------|------|------------|
| **A (MVP)** | `minAreaRect` on plastic/dark contour; store 4 corners; **gates use rect area vs image**; audit draws `cv2.polylines` | Run in full image with mask inside quad | Crop via `warpPerspective` to axis-aligned tile OR mask-only Otsu | Medium |
| **B** | Full perspective warp to canonical cassette aspect; all downstream in warped patch | Same as Fix 1b/1d logic in warped space | Clean axis-aligned pipeline | Higher; memory on Pi |

**Recommendation for plan v2:** **Tier A** — `minAreaRect` + quad telemetry + optional warp only for Otsu crop. Avoid full-file warp until profiling on Pi.

### Telemetry fields (extend `roi_fields_from_result` / CSV)

| Field | Type | Meaning |
|-------|------|---------|
| `anchor_shape` | `parallelogram` \| `aabb_fallback` | What was stored |
| `cassette_corners` | 8 floats or JSON | TL,TR,BR,BL x,y |
| `cassette_angle_deg` | float | From `minAreaRect` |
| `cassette_area_frac` | float | Quad area / image area |
| `rim_signature_votes` | int | Boundary samples passing B–D–B |
| `anchor_method` | str | `rim+dark_frame`, `dark_frame`, `fail` |

### Gate changes

- **G5 (oversize):** Use **quad area / image area ≤ 0.55** (from click calibration), not 0.90.
- **G4 (sliver):** Min height relative to **short side of minAreaRect**, not image height.
- **New G7 (optional):** Max aspect ratio of minAreaRect vs expected cassette aspect band.

---

## 5. Rim signature algorithm (sketch)

**Inputs:** grayscale image, coarse dark blob contour (or quad center).

**Per boundary sample** (N points on contour or per edge at M steps):

1. Unit normal **outward** from cassette center through boundary point.
2. Sample gray along ray: `s = +35…-95` (outside positive).
3. Score: `outside_mean ≥ 170`, `trough ≤ 85`, `inner_mean ≥ trough + 10`.
4. Point passes if all hold.

**Aggregate:** If ≥ K% of samples pass (e.g. 40% of perimeter), accept contour as plastic boundary; fit `minAreaRect` to passing points or full contour.

**Edge failures:** Label side and grid side often fail B–D–B — use **median vote** and reject outliers; require min 2 of 4 sides on quad-based sampling.

**Known hard sets:** 06, 31 — skip rim-primary; use dark_frame area + lung-specific strip policy (no opposite-end strip unless plastic anchor confident).

---

## 6. Plan C rules (retained, tightened)

1. **Phone:** `paraffin_envelope` **cannot** set cassette anchor.
2. **Cassette area** (quad or minAreaRect): **6–45%** image (tune from `plastic_rim_clicks.json` quads).
3. **Final ROI area:** **6–55%**; fail closed otherwise.
4. **Strip:** Only if `anchor_method` includes confident plastic/rim and short-end delta > 10%.
5. **Production:** `allow_full_frame_fallback=False`; audit PNG shows last candidate quad + `fallback=production`.

---

## 7. ML vs classical — decision framework

### What classical Fix 1e does

- Hand-crafted features (gray profiles, area, morphology).
- Fixed constants in JSON per `capture_source`.
- Fails closed with explicit `failure_reason`.
- Runs on Pi 5 CPU in deterministic time (target: <<1 s per block silhouette).

### What ML would do (if added later)

| Approach | Train on | Inference | Output |
|----------|----------|-----------|--------|
| Segmentation CNN / U-Net | Pixel labels: plastic, wax, tissue, background | Per-pixel class map | Mask → contour → quad |
| Hailo-8L compiled model | Same, exported HEf/ONNX | NPU on Pi | Mask at reduced resolution |
| Windows GPU training | `iphone_images/` + label tool | Offline only | Weights → export to Pi |

**What ML does not automatically fix**

- Wrong training labels on grid/label regions.
- Need for 50–200+ annotated block images for stable generalization.
- Mentor review scope and intern timeline.
- Deterministic pytest (needs golden masks or mock inference).

### Decision matrix

| Trigger | Action |
|---------|--------|
| Fix 1e classical pilot **≥8/10** | Stay classical; calibrate Pi JSON on rig captures |
| Fix 1e pilot **fails twice** after rim+quad+area law | **Spike:** 20-image mask labeling + small U-Net on Windows GPU |
| Pi latency > budget with CPU warp | Consider Hailo for seg only (Phase 5+), not Phase 3 gate |
| Mentor mandates interpretability | Stay classical until Phase 5 review |

**PROJECT_CONTEXT alignment:** Hailo-8L is **Phase 5+ optional** (not on current PO). Phase 4 gated on signal gate + mentor criteria — **not** on ML ROI. **Do not block Phase 4** on Hailo.

### Pipeline impact if ML is added later

```text
Today:  block JPEG → phase3_block_roi (classical) → mask → phase2/3 descriptors
ML:     block JPEG → roi_segmentation_hailo.py → mask → same downstream

Training path (offline, Windows):
  iphone_images/ + label masks → train → export → block_roi_model_hailo.hef

Tests:
  Classical: synthetic geometry + fixture JPEGs (keep)
  ML: separate test_mocks with fixed mask PNGs; optional integration @pytest.mark.gpu
```

**Deferral recommendation:** **Classical Fix 1e first.** ML only after second classical pilot failure or explicit mentor request.

---

## 8. Feasibility summary (probes)

| Probe | Result |
|-------|--------|
| Auto plastic 80–135, 15% CC | set_04 largest CC **3.1%** — explains plastic `None` |
| Click quads area | set_04 **9.5%**, 02/33/11 **~10%**, 06/31 **~33%** |
| Rim B–D–B (outside→inside) | 02,11,33,35: 3–4/4 edges; 04,28: 1/4; 06,31: 0/4 |
| Pooled click gray | **MIXED_PROFILE**; dual profile or rim-first, not 26–99 alone |
| Inward brighten (edge→center) | Strong on square esophagus sets; weak on 06/31 |

**Conclusion:** Approach is **viable** as **composed classical** anchor, not as single global threshold. **Not inviable** due to lighting — volatile for one band, stable for rim+area+quad.

**Consistent Pi rig:** Expect narrower gray spread, higher rim vote rate, optional return to simpler plastic CC — recalibrate `block_roi_constants_pi.json` on first batch.

---

## 9. Recommended path (for planning gate)

1. **Brainstorm / design** — this document (done).
2. **Session synthesizer** → `proposed_plan.md` v1 (Fix 1e).
3. **Pre-mortem** → `pre_mortem.md` (parallelogram warp memory, rim false positives, telemetry CSV columns).
4. **Plan v2** → implement `phase3_block_roi.py` + `calibrate_plastic_rim.py` export to JSON + pilot regen.
5. **Success:** ≥8/10 visual; zero `roi_ok=True` with `cassette_method=paraffin_envelope` on phone; quad area in 6–45% for passes.
6. **If fail twice:** ML spike doc only — not default.

---

## 10. Open questions for plan v2

1. **Tier A vs B warp:** Warp for Otsu only, or mask-in-quad without warp?
2. **Dual plastic profiles:** Explicit `phone_plastic_dark` / `phone_plastic_light` vs rim-only?
3. **06/31 policy:** Separate `tissue_class=lung` anchor path (no strip) in same PR or follow-up?
4. **Audit overlay:** Draw parallelogram + failed candidate vs full-frame on fail?

---

## 11. References

- `phase3_outputs/plastic_rim_clicks.json` — user clicks, corner quads, MIXED_PROFILE
- `phase3_outputs/plastic_rim_viability.md` — auto probe table
- `docs/superpowers/specs/2026-05-25-fix-1d-roi-plastic-first-design.md` — prior design
- `.cursor/docs/PROJECT_CONTEXT.md` — § Fix 1e brainstorming
- `code/calibrate_plastic_rim.py` — calibration UI (quad draw, click stats)
