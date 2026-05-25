# Adversarial Architecture Review: Pre-Mortem Audit

> **Status:** Critical Review Completed — Actions Required
> **Target Document:** `c:\Users\zekes\lji_blockcheck\.cursor\specs\proposed_plan.md`
> **Date:** 2026-05-25
> **Domain Detected:** Embedded CV

---

## 0. Plan Completeness Check

| Required Section | Present? | Notes |
|-----------------|----------|-------|
| Objective | ✅ | Clear ROI-specific target: replace Fix 1d cassette anchoring and require Zeke visual >=8/10 on the frozen 10-set pilot. |
| Architecture & Pipeline Steps | ✅ | The staged dark-frame -> rim signature -> parallelogram -> paraffin search flow is explicit. Several acceptance details remain underspecified. |
| Data Flow (Inputs/Transformations/Outputs) | ✅ | Inputs, transformations, and telemetry outputs are listed. Coordinate-system ownership needs tightening before implementation. |
| Key Decisions & Rationale | ✅ | Major alternatives are rejected with useful rationale, especially phone envelope fallback and ML deferral. |
| Dependencies | ✅ | Dependencies are limited to existing OpenCV, NumPy, pytest, and audit scripts. |
| Open Questions & Known Risks | ✅ | The plan names the main risks, but some of them are severe enough to require v2 design decisions rather than implementation-time choices. |
| Testing Considerations | ✅ | Good unit-test categories are listed. Missing tests around multi-candidate arbitration, coordinate mapping, and audit failure semantics should be added. |

The plan is complete enough for critique. It should not move to implementation until the critical checklist items below are resolved in plan v2.

## 1. Positive Architectural Notes

- The plan correctly separates ROI framing from matcher/signal-gate claims. That prevents a local ROI improvement from being oversold as Phase 4 readiness.
- The phone `paraffin_envelope` ban is the right safety posture. A false `roi_ok=True` is more dangerous than an honest failure in a histology block-check pipeline.
- Moving from axis-aligned boxes to ordered four-corner geometry matches the rotated cassette problem better than Fix 1d's envelope behavior.

## 2. Fatal Assumptions

- **🔴 Deterministic candidate selection will emerge from the dark/rim stages:** The plan says dark-frame thresholding may produce "one or more" candidates, then rim votes accept candidates, but it does not define how to rank multiple passing candidates, how to break ties, or when conflicting signals must fail closed. In phone images with labels, grids, tissue shadows, and cassette edges, multiple dark blobs can plausibly satisfy partial bright-dark-bright votes. If implementation picks the largest or first contour by accident, the system can recreate Fix 1d's false `roi_ok=True` failure while appearing to use the new anchor.

- **🔴 Coordinate transforms will stay correct without a single contract:** The plan allows either quad-mask processing or optional `warpPerspective` for the Otsu crop, while outputs may be `paraffin_bbox` or `paraffin_quad` and masks must return to original image coordinates. That is a silent-corruption risk: a mask can look reasonable in warped space but be shifted, mirrored, or clipped when mapped back. In this project, downstream matching trusts the contour geometry, so a coordinate bug becomes a false shape signal rather than a visible crash.

- **🔴 "About" thresholds are not implementation-ready gates:** The plan uses draft bands like cassette quad area "about 6-45%" and final ROI area "6-55%" without naming exact constants, inclusive/exclusive boundaries, or calibration provenance required by the implementation. Gate code and tests need exact values. If the implementation fills in these constants ad hoc, Fix 1e can pass the 10-set pilot by tuning to visible examples while still failing determinism on the Pi or full phone library.

## 3. Algorithmic & Logic Vulnerabilities

- **🔴 Rim signature scoring is underdefined:** The plan names the bright -> dark trough -> brighter inward profile but does not specify sample normal direction, sampling distances, intensity normalization, trough depth, minimum inward rebound, or how votes are aggregated across long and short edges. Without these details, a glare band, label border, or dark tissue boundary can pass as a cassette rim. A v2 plan should define the profile feature numerically enough that synthetic 1D tests can be written before source edits.

- **🟡 `minAreaRect` can fit the wrong rectangle even when a contour is valid:** `minAreaRect` returns the minimum-area rotated rectangle around the supplied points, not a semantic cassette boundary. If rim-supported points cover only two sides, are biased toward the label end, or include tissue shadows, the fitted parallelogram can have plausible area but wrong placement. The plan needs a quality check beyond area and aspect ratio, such as side-support coverage or vote distribution across at least two non-adjacent edges.

- **🟡 The known 06/31 weak-rim cases are named but not converted into behavior:** The plan correctly says sets 06/31 may show 0/4 edge votes and must not silently become envelope/full-frame passes. It does not say whether those cases should fail closed, use a specific dark-frame-only degraded mode, or be excluded from the >=8/10 pilot expectation. Leaving that open creates implementation pressure to add an unreviewed fallback when the pilot score is low.

- **🟡 Opposite-end stripping depends on an undefined confidence model:** The strip rule only applies when the anchor is confident and short-end score delta exceeds a threshold, but neither "confident" nor the delta metric is specified. A wrong strip can remove wax/tissue from one end or leave label/grid material inside the ROI. This should be a bounded, telemetry-backed operation, not an implementation guess.

- **🟡 `capture_source` defaulting to `phone` may hide metadata defects:** Defaulting missing `capture_source` to phone with telemetry keeps current data moving, but it can also route new Pi captures through phone constants if metadata is absent. Because Pi constants must be calibrated separately, the loader should make the default behavior explicit and testable, with a visible warning field and no silent promotion to `roi_ok=True` on unknown capture sources.

## 4. Resource & Environment Constraints

- **🟡 Warp and mask allocation must be bounded for Raspberry Pi 5:** The plan prefers optional warp only for the Otsu crop, which is good, but it does not require crop-before-warp or cap canonical tile dimensions. Full-resolution `warpPerspective` plus masks and audit overlays can create unnecessary memory pressure on the Pi, especially when batch processing 47 sets. The v2 plan should specify a bounded crop/warp size and release or avoid large temporaries where practical.

- **🟡 Audit artifact generation can become the bottleneck or leak memory:** The plan adds parallelogram overlays, failed candidates, titles, CSV telemetry, and a geometry report. The project context already flags `plt.close(fig)` and BGR->RGB as known visualization hazards. The audit plan should explicitly preserve those invariants so pilot regeneration does not create misleading color overlays or memory growth during batch runs.

- **🟢 Pi bring-up is intentionally deferred, but Pi constants need a hard guard:** Phone-first work is reasonable, but the Pi JSON stub can become accidental production configuration. The loader should surface `pi_constants_calibrated=false` or equivalent until first rig stills produce real thresholds, and tests should verify that stub constants cannot silently pass production ROI gates.

## 5. Testing Gaps

- **🔴 Multi-candidate arbitration tests are missing:** Current testing considerations cover candidate area and rim scoring separately, but not the combined case where two plausible candidates exist. A proper test should build a synthetic image with a true rotated cassette and a larger label/grid-like dark blob, then verify the selected candidate is the rim-supported cassette or the result fails closed with a deterministic reason.

- **🔴 Coordinate round-trip tests are incomplete:** The optional warp crop test says the mask maps back to original coordinates, but the plan also needs tests for ordered corner inputs, mirrored/rotated corner mistakes, and area preservation after inverse mapping. Success should verify that a known synthetic wax patch returns a mask whose original-image bounding quad overlaps the expected patch within a documented tolerance.

- **🟡 Failure audit semantics need tests:** The plan warns that drawing a nice parallelogram on failure can look like a pass, but the test list does not include color/title/CSV assertions that failed candidates are visibly and machine-readably failed. At minimum, report rows and overlay titles should expose `roi_ok=False`, `failure_reason`, and a distinct failed-candidate label.

- **🟡 Acceptance depends on a human visual score without a frozen scoring record format:** Zeke visual >=8/10 is a valid pilot gate, but the plan should define where the 10 per-set scores are recorded, what counts as pass/fail per set, and how disagreements or re-runs are handled. Otherwise the pilot result can become hard to audit later.

- **🟡 Telemetry compatibility tests should include downstream consumers, not just serialization:** The plan lists `roi_fields_from_result()` but should also verify that existing pipeline CSV readers, router/matcher paths, or audit scripts ignore unknown columns and still see old fields. New telemetry must not break Phase 3 outputs.

## 6. Pre-Implementation Checklist

### 🔴 Critical (must resolve before writing any code)

- [ ] **Define candidate arbitration:** Add a v2 design section for ranking, tie-breaking, and fail-closed behavior when multiple dark/rim candidates exist. **Done when:** the plan names the candidate score formula or ordering rules, lists required telemetry for rejected candidates, and includes a unit test scenario with two plausible candidates.

- [ ] **Lock the coordinate contract:** Choose the Tier A geometry path precisely: which operations run in original image space, which may run in warped space, and how masks/boxes/quads map back. **Done when:** every ROI output field has a declared coordinate space and a coordinate round-trip test can be written from the plan alone.

- [ ] **Replace approximate gates with exact constants or a calibration-first rule:** Convert "about 6-45%" and "6-55%" into named JSON keys with exact draft values, boundary behavior, and provenance, or require a calibration script to write them before implementation. **Done when:** tests can assert pass/fail at, below, and above every gate boundary without guessing.

- [ ] **Specify rim profile math:** Define sampling direction, sample offsets, intensity normalization, trough/rebound thresholds, per-side vote criteria, and candidate-level vote acceptance. **Done when:** synthetic bright-dark-bright, flat, glare-only, and dark-tissue profiles have expected pass/fail outcomes in the testing plan.

### 🟡 Moderate (must resolve during implementation)

- [ ] **Add side-support quality checks for `minAreaRect`:** Prevent a rectangle fitted from partial or biased points from passing on area alone. **Done when:** a candidate with support on only one side or one corner fails with a specific `failure_reason`.

- [ ] **Decide 06/31 degraded behavior:** State whether weak-rim lung-heavy cases fail closed, use a named degraded anchor, or are expected pilot failures. **Done when:** set-like synthetic tests cannot pass via envelope/full-frame behavior and the pilot report labels weak-rim failures explicitly.

- [ ] **Make capture-source fallback visible:** Preserve the phone default only if the telemetry and loader behavior make missing metadata obvious. **Done when:** tests show missing `capture_source` records a warning/default field and unknown/Pi-stub constants cannot silently pass production gates.

- [ ] **Bound warp memory usage:** Crop before warping and cap canonical tile size for Pi execution. **Done when:** the implementation documents maximum warp dimensions and tests or code assertions prevent full-image warps where not required.

- [ ] **Protect audit generation invariants:** Ensure overlays use correct color conversion and close matplotlib figures. **Done when:** audit code retains BGR->RGB conversion, calls `plt.close(fig)`, and output directories are created with `parents=True, exist_ok=True`.

- [ ] **Test downstream telemetry compatibility:** Verify old ROI fields remain present and new columns do not break existing consumers. **Done when:** `pytest tests/` includes a serialization/consumer test that passes with the extended `SegmentationWithRoi`.

### 🟢 Minor (address as encountered)

- [ ] **Standardize pilot score recording:** Create or update a small report format for the 10-set visual rubric. **Done when:** each pilot set has pass/fail, reason, reviewer/date, and link or filename for its audit PNG.

- [ ] **Keep failed overlays visually distinct:** Use title text and color conventions that prevent failed candidates from looking successful. **Done when:** failed-candidate audit PNGs include `roi_ok=False` and `failure_reason` in the title or caption.

- [ ] **Mark Pi constants as uncalibrated until real stills exist:** Avoid accidental reuse of phone thresholds on the rig. **Done when:** Pi stub JSON has an explicit calibration status and loader/report telemetry exposes it.

## 7. Clarifications Required Before Plan v2

No user clarification required before plan v2.

The v2 author can resolve the blockers from the existing plan context by making design choices explicit. The most important v2 changes are deterministic candidate arbitration, a single coordinate-space contract, exact gate constants or calibration-first generation, and numeric rim-profile scoring rules.
