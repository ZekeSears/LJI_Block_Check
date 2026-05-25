# Fix 1e — Backlit Rim + Parallelogram Cassette Anchor: Proposed Plan

> **Status:** Plan v2 — approved for implementation
> **Date:** 2026-05-25
> **Source:** Plan v1 + isolated pre-mortem review
> **Supersedes:** Fix 1d as the primary cassette anchor strategy. Fix 1d code may remain as a baseline until this plan is implemented.

---

## 1. Objective

Fix 1d improved telemetry but still produced a visually bad pilot: the ROI often covers a huge fraction of the phone image while `roi_ok=True`. The root problem is still **cassette anchoring**, not Otsu tissue segmentation inside a correct wax window.

Fix 1e changes the anchor from axis-aligned envelope detection to a composed, classical stack:

```text
dark_frame coarse candidate
  -> backlit rim signature votes
  -> rotated cassette parallelogram (`minAreaRect` / 4 corners)
  -> paraffin search inside the quad only
  -> tight area gates with no phone envelope anchor
```

**Pilot gate:** Zeke visual **>=8/10** on the frozen 10-set ROI rubric (`02, 04, 06, 11, 28, 31, 33, 35, 40, 45`). This gate is ROI framing only: wax window visible, label/grid mostly excluded, and cassette framing plausible. It does **not** claim the signal gate, matcher, or Phase 4 are fixed.

**Hardware stance:** Do not wait for the Raspberry Pi rig to start Fix 1e. The phone library is the stress test; the Pi rig should make constants easier after first captures. The PiShop box is expected Tuesday/tomorrow for bring-up; Amazon camera stack is also Tuesday; VXB gantry is not confirmed.

**Frozen APIs:** Do not change public signatures for `segment_tissue()`, `extract_contours()`, `clean_mask()`, descriptor functions, or matcher/router entry points. Extend ROI dataclasses and telemetry compatibly.

---

## 2. Proposed Architecture & Pipeline Steps

1. **Constants and capture source**
   - Approach: Continue `phase3_outputs/block_roi_constants_{phone|pi}.json`, but add Fix 1e keys for quad area, rim signature sampling, and anchor method policy. Default missing `capture_source` to `phone` with telemetry.
   - Inputs: `meta.capture_source`, constants JSON.
   - Outputs: Loaded constants, `capture_source` telemetry, testable reload behavior.

2. **Coarse dark-frame candidate**
   - Approach: Threshold dark cassette/frame material, morphology-close it, then keep contours in a plausible cassette area band. Phone initial band: candidate area **15-45% inclusive** for coarse frame blobs, with separate final quad gate below.
   - Inputs: Grayscale block silhouette.
   - Outputs: One or more candidate contours and candidate `minAreaRect`s, each with deterministic candidate telemetry.

3. **Rim signature validator**
   - Approach: For boundary samples, score the outside-to-inside profile for **bright -> dark trough -> brighter inward**. Accept candidates by vote count/fraction, not by requiring all four sides.
   - Numeric v2 default: sample along the inward normal of each ordered rectangle side at offsets `[-12, -6, 0, +6, +12]` pixels from the candidate edge, with negative offsets outside the candidate and positive offsets inside. Normalize intensities by local 5-sample median and clamp to `[0, 255]`. A sample-line vote passes when the edge/trough value is at least `20` intensity units darker than the brighter outside sample and the inward rebound is at least `12` intensity units brighter than the trough. A side passes when at least `50%` of its sample lines vote. A candidate passes the rim validator when at least `2` sides pass and side support is not concentrated on only one side/corner.
   - Inputs: Grayscale image, candidate contour/rect, cassette center.
   - Outputs: `rim_signature_votes`, `rim_signature_vote_frac`, `rim_side_votes`, `rim_side_vote_fracs`, accepted/rejected candidate reason.
   - Known exceptions: sets 06/31 may show 0/4 edge votes because tissue/lung fills the field; those should not silently fall back to full-frame envelope.

4. **Candidate arbitration**
   - Approach: Score all candidates before choosing an anchor. Candidate ordering is deterministic: passing rim validator first, then higher `rim_signature_vote_frac`, then better side-support coverage, then area closer to the phone quad-area midpoint, then smaller absolute angle only as a final tie-breaker. If the top two passing candidates have scores within `0.05` or disagree by more than `20%` image area, fail closed with `failure_reason=ambiguous_candidates` rather than picking the first/largest contour.
   - Inputs: All dark-frame candidates with rim and geometry telemetry.
   - Outputs: `selected_candidate_index`, `candidate_count`, `candidate_scores`, `rejected_candidate_reasons`, `failure_reason` when ambiguous.

5. **Parallelogram anchor**
   - Approach: Fit `cv2.minAreaRect` to the rim-supported contour or passing boundary points. Convert to four ordered corners. Keep the shape as a parallelogram/rotated rectangle for gates and audit overlay; do not reduce it to an axis-aligned bbox for acceptance.
   - Quality check: a rectangle cannot pass on area/aspect alone. It must have side support on at least two non-adjacent sides or three total sides; one-side and one-corner support fail with `failure_reason=insufficient_side_support`.
   - Inputs: Accepted contour or rim-supported point cloud.
   - Outputs: `cassette_corners_original`, `cassette_angle_deg`, `cassette_area_frac`, `anchor_shape=parallelogram`.

6. **Phone envelope ban and fallback policy**
   - Approach: For `capture_source=phone`, `paraffin_envelope` cannot set the cassette anchor. If dark/rim/quad fails, production returns `roi_ok=False` with explicit `failure_reason`. Audit may draw the last failed candidate, but must label it as failed.
   - Weak-rim default: sets in the 06/31 class fail closed with `weak_rim_signature` unless a dark-frame candidate passes the same deterministic arbitration and side-support checks. There is no degraded envelope/full-frame pass in Fix 1e.
   - Inputs: Candidate failures and `allow_full_frame_fallback`.
   - Outputs: Fail-closed result; no phone `roi_ok=True` from `paraffin_envelope`.

7. **Coordinate contract, inner inset, and paraffin search**
   - Approach: Tier A is now locked. Anchor detection, candidate arbitration, gate decisions, telemetry, and final mask output are owned in original image coordinates. A bounded warp may be used only as a temporary crop workspace after a cassette quad has passed gates.
   - Coordinate fields:
     - `cassette_corners_original`: four ordered original-image points, `TL, TR, BR, BL`.
     - `paraffin_quad_original`: original-image paraffin/wax-window quad when available.
     - `paraffin_bbox_original`: axis-aligned original-image bbox enclosing the paraffin quad/crop.
     - `warp_matrix_original_to_crop` and `warp_matrix_crop_to_original`: recorded only when warp is used.
     - `mask`: always returned in original image coordinates and image shape.
   - Warp bound: crop before warping; canonical crop dimensions are capped at `640x480` for phone/Pi execution unless a later calibrated constant lowers them. Large full-image warps are forbidden for production ROI.
   - Inputs: Ordered cassette corners, BGR/gray image.
   - Outputs: `paraffin_bbox_original` or `paraffin_quad_original`, `paraffin_method`, Otsu crop coordinates/transform.

8. **Opposite-end strip policy**
   - Approach: Strip grid/label only when the anchor is confident and short-end score delta exceeds the configured threshold. `anchor_confident=True` requires a selected candidate with passing rim validator, passing side-support check, non-ambiguous arbitration, and no geometry gate failures. The short-end delta is the absolute difference between the two short-end transition/texture scores divided by the larger score; default threshold is `0.20` inclusive. Do not apply strip after a failed or low-confidence geometric fallback.
   - Inputs: Anchored quad/crop, short-end texture/transition scores.
   - Outputs: `strip_method`, strip side, `short_end_score_delta`, confidence telemetry.

9. **Tight ROI gates**
   - Approach: Replace oversized G5=0.90 behavior with quad-aware gates. Exact v2 draft constants live in JSON and tests assert boundary behavior:
     - `coarse_candidate_area_frac_min=0.15`, `coarse_candidate_area_frac_max=0.45`, inclusive.
     - `cassette_quad_area_frac_min=0.06`, `cassette_quad_area_frac_max=0.35`, inclusive.
     - `final_roi_area_frac_min=0.06`, `final_roi_area_frac_max=0.55`, inclusive.
     - `min_roi_short_side_frac_of_cassette_short_side=0.25`, inclusive lower bound.
     - `cassette_aspect_ratio_min=1.20`, `cassette_aspect_ratio_max=3.80`, inclusive.
   - Provenance: these are Fix 1e draft constants from the plan context's clicked-quad/phone-pilot ranges. Implementation may later replace them only through a calibration script/report, not ad hoc tuning inside ROI code.
   - Inputs: Quad geometry, final ROI geometry, image shape.
   - Outputs: `gate_failures`, `roi_ok`, `failure_reason`.

10. **Segmentation inside accepted crop only**
   - Approach: Run frozen `segment_tissue()` only after the ROI gates pass. Post-Otsu production guards (`seg_empty`, `seg_flood`, `seg_blob` where appropriate) remain fail-closed.
   - Inputs: Gated crop/warp.
   - Outputs: Mask in original image coordinates, ROI telemetry fields.

11. **Audit overlays and reports**
    - Approach: Audit PNGs draw the parallelogram, the final crop/ROI, and the last failed candidate when applicable. Titles include `anchor_method`, `anchor_shape`, `area_frac`, `rim_votes`, `roi_ok`, and failure reason.
    - Failure semantics: successful anchors and failed candidates must use distinct title text and overlay styling. Failed candidate overlays must include `roi_ok=False` and `failure_reason` in both the report row and the PNG title/caption.
    - Visualization invariants: preserve BGR->RGB conversion before matplotlib, create output directories with `parents=True, exist_ok=True`, and close every figure with `plt.close(fig)`.
    - Inputs: ROI result object.
    - Outputs: `phase3_outputs/roi_crop_audit/*.png`, `phase3_outputs/pilot_roi_geometry_report.md`, updated CSV telemetry.

12. **Pi calibration path**
    - Approach: After the Pi/camera rig captures first usable images, fill `block_roi_constants_pi.json` from Pi photos rather than copying phone thresholds blindly. First Pi work is bring-up and capture calibration, not a blocker for phone pilot.
    - Guard: Pi constants include `pi_constants_calibrated=false` until real rig stills produce thresholds. Unknown capture sources and uncalibrated Pi constants may load for audit/bring-up telemetry, but cannot silently produce `roi_ok=True` production passes.
    - Inputs: Pi stills, fixed exposure/FOV notes.
    - Outputs: Pi constants update and comparison note; no Hailo/ML dependency.

---

## 3. Data Flow

### Inputs

- BGR block silhouette image.
- Metadata: `role`, `tissue_class`, `capture_source`, `set_id`.
- Constants: `block_roi_constants_phone.json`, `block_roi_constants_pi.json`.
- Evidence/calibration:
  - `phase3_outputs/plastic_rim_clicks.json`
  - `phase3_outputs/plastic_rim_viability.md`
  - `phase3_outputs/fix1d_roi_audit_report.md`
  - `phase3_outputs/pilot_roi_rubric.md`
  - `docs/superpowers/specs/2026-05-26-fix-1e-backlit-rim-parallelogram-anchor-design.md`
  - `docs/superpowers/specs/2026-05-26-pi-bringup-and-classical-strategy.md`

### Transformations

1. Validate BGR image and load constants for capture source.
2. Convert to grayscale and generate dark-frame candidate contours.
3. Score candidate boundaries with rim profile samples.
4. Fit and order a parallelogram anchor from the accepted candidate.
5. Apply area/aspect/sliver gates on quad geometry.
6. Search for paraffin inside the quad/inset only.
7. Optionally warp the accepted crop for Otsu while preserving original-image telemetry.
8. Run frozen segmentation and post-segmentation guards.
9. Emit mask, telemetry, CSV fields, and audit overlay.

### Outputs

- `SegmentationWithRoi` extended with:
  - `anchor_method`
  - `anchor_shape`
  - `cassette_corners_original`
  - `cassette_angle_deg`
  - `cassette_area_frac`
  - `selected_candidate_index`
  - `candidate_count`
  - `candidate_scores`
  - `rejected_candidate_reasons`
  - `rim_signature_votes`
  - `rim_signature_vote_frac`
  - `rim_side_votes`
  - `rim_side_vote_fracs`
  - `paraffin_quad_original`
  - `paraffin_bbox_original`
  - `warp_matrix_original_to_crop`
  - `warp_matrix_crop_to_original`
  - `gate_failures`
  - `failure_reason`
- Updated `roi_fields_from_result()` CSV fields.
- Pilot audit PNGs with parallelogram overlay.
- Pilot geometry report for the frozen 10 sets.
- Updated phone constants and Pi stub/constants if needed.

---

## 4. Key Decisions & Rationale

| Decision | Chosen Approach | Alternatives Considered | Rationale |
|----------|----------------|--------------------------|-----------|
| Anchor model | Dark-frame candidate + rim signature + parallelogram | Global plastic gray, paraffin envelope, center crop, Hough lines | Global gray is mixed-profile; envelope selects ~98% frame; center crop is a hack; Hough likely breaks on grid/label. |
| Geometry | `minAreaRect` / ordered corners | Axis-aligned bbox only | User calibration quads are rotated; AABB over-includes image corners and repeats the huge-ROI failure class. |
| Phone fallback | Fail closed; draw last candidate in audit only | `paraffin_envelope`, full-frame, geometric inset pass | False `roi_ok=True` is worse than honest failure. |
| Gate area | Quad/final ROI area around 6-55% | G5 <= 90% image | Fix 1d allowed ~76% ROI to pass; user corner quads are far smaller. |
| Pi timing | Implement/test now on phone, recalibrate when rig arrives | Wait for hardware before code | Phone validates robust logic; Pi improves constants but should not block planning or tests. |
| ML/Hailo | Defer; classical first | Train ML immediately | Current PO lacks Hailo; labels do not exist; classical is explainable and likely easier under fixed lighting/FOV. |
| Warp tier | Tier A: quad telemetry, optional crop warp only | Full canonical warp for entire ROI pipeline | Lower implementation and memory risk on Pi; still supports rotated cassette. |

---

## 5. Dependencies

| Library/Tool | Purpose | Version Constraint |
|--------------|---------|--------------------|
| OpenCV (`cv2`) | Thresholding, morphology, contour extraction, `minAreaRect`, `boxPoints`, optional `warpPerspective` | Existing project dependency |
| NumPy | Masks, profiles, geometry math | Existing project dependency |
| pytest | Deterministic unit/integration checks | Existing project dependency |
| Existing audit scripts | Pilot PNG generation and geometry reporting | Keep CLI-compatible where possible |

No ML dependencies are part of Fix 1e. If ML is later approved, it gets a separate spec and plan.

---

## 6. V2 Resolutions, Open Risks, and Implementation Defaults

The isolated pre-mortem found no user blockers. Plan v2 resolves every critical item as implementation text:

- **Candidate arbitration resolved:** all candidates are scored before selection, deterministic tie-breakers are defined, ambiguous top candidates fail closed, and rejected-candidate telemetry is required.
- **Coordinate contract resolved:** all accepted geometry, telemetry, and final masks are in original image coordinates; warp is a bounded temporary workspace only; every transform field is named.
- **Gate constants resolved:** draft thresholds are exact JSON keys with inclusive boundary behavior; future changes require calibration output rather than implementation guesses.
- **Rim profile math resolved:** sample direction, offsets, normalization, trough/rebound thresholds, side votes, and candidate acceptance are specified for TDD.

Remaining risks are implementation risks, not plan blockers:

- **Constants drift:** Phone constants must not be treated as Pi constants after rig captures arrive. Pi JSON must be recalibrated from first rig stills and remains `pi_constants_calibrated=false` until then.
- **Quad ordering bugs:** Misordered corners can mirror or rotate the warp incorrectly. Tests must lock TL/TR/BR/BL ordering and area computation.
- **Telemetry compatibility:** New fields must not break existing CSV consumers; old fields remain present, and downstream readers must ignore unknown columns.
- **Audit illusion risk:** Failed candidates must be visually and machine-readably distinct from successful anchors.
- **Signal gate risk:** Better ROI may improve masks, but the current median gap is still `SIGNAL_MISSING`; do not claim matcher success until post-pilot regen and histograms are reviewed.

---

## 7. Testing Considerations

| What to Test | Method | Success Criteria | Related Phase |
|--------------|--------|------------------|---------------|
| Dark-frame candidate area | Synthetic frames + fixture images | Candidate area in configured band; oversize/undersize rejected | Fix 1e ROI |
| Rim signature scoring | Synthetic 1D profiles and small image patches | Bright-dark-bright profiles pass; flat, glare-only, and dark-tissue profiles fail under the numeric v2 thresholds | Fix 1e ROI |
| Multi-candidate arbitration | Synthetic image with true rotated cassette plus larger label/grid-like dark blob | Selected candidate is the rim-supported cassette, or the result fails closed with `ambiguous_candidates`; never first/largest by accident | Fix 1e ROI |
| Parallelogram area and corner ordering | Rotated synthetic rectangles | Ordered TL/TR/BR/BL corners; area stable under rotation; one-side/one-corner support fails | Fix 1e ROI |
| Coordinate round-trip | Synthetic rotated wax patch with optional crop warp | Original-image mask/quad overlaps expected patch within documented tolerance; mirrored/rotated corner mistakes fail | Fix 1e ROI |
| Phone envelope ban | Unit test with phone source and envelope-like image | `cassette_method != paraffin_envelope`; failure if no better anchor | Fix 1e ROI |
| Gate boundaries | Synthetic geometry at below/equal/above exact JSON constants | Inclusive bounds pass at equality and fail just outside each gate | Fix 1e ROI |
| G5 tightening | Synthetic huge ROI (~76%) | Rejected with `roi_oversize` | Fix 1e ROI |
| Sliver gate | Synthetic short-height ROI and set_06-class fixture | Rejected with `roi_sliver` | Fix 1e ROI |
| Optional warp crop | Synthetic rotated wax patch | Otsu crop maps mask back to original coordinates | Fix 1e ROI |
| Telemetry serialization and consumers | `roi_fields_from_result()` plus downstream CSV/audit reader tests | New fields present, old fields preserved, unknown columns ignored | Phase 3 pipeline |
| Failure audit semantics | Report/title assertions for failed candidates | `roi_ok=False`, `failure_reason`, and failed-candidate label are visible in CSV/report/title | Fix 1e audit |
| Pilot 10 audit | Regenerate PNGs and rubric review | Each set records pass/fail, reason, reviewer/date, and audit PNG filename; Zeke visual >=8/10 | Pilot gate |
| Pi constants stub | Loader test | Pi source loads with explicit uncalibrated status; uncalibrated Pi constants cannot silently pass production ROI gates | Hardware bring-up |

**TDD rule:** Core helpers used by segmentation flow require tests before implementation. Leaf audit/report changes may be implemented with lighter tests but must not become hidden decision logic.

---

## 8. Implementation Files

| File | Planned change |
|------|----------------|
| `code/phase3_block_roi.py` | Add dark/rim/parallelogram anchor helpers, quad-aware gates, phone envelope ban, telemetry fields, optional warp crop path. |
| `phase3_outputs/block_roi_constants_phone.json` | Add exact Fix 1e constants: rim sample offsets `[-12,-6,0,6,12]`, trough depth `20`, rebound `12`, side pass fraction `0.50`, candidate ambiguity delta `0.05`, area/aspect/sliver gates, warp cap, and method policy. |
| `phase3_outputs/block_roi_constants_pi.json` | Keep schema-compatible stub with `pi_constants_calibrated=false`; fill after first Pi capture batch. |
| `tests/test_phase3_block_roi.py` | Add TDD coverage for rim scoring, multi-candidate arbitration, coordinate round-trip, quad geometry, phone envelope ban, sliver/oversize gates, gate boundaries, Pi stub guard, and telemetry serialization/consumer compatibility. |
| `phase3_outputs/pilot_roi_rubric.md` | Reuse frozen pilot rubric; update title if needed from Fix 1d to Fix 1e. |
| `code/pilot_roi_geometry_check.py` | Ensure report uses the same quad-aware gates as production. |
| `code/segmentation_audit_pack.py` or audit CLI | Draw parallelogram and failed candidate overlays while preserving BGR->RGB, `plt.close(fig)`, distinct failure styling, and output-directory creation invariants. |
| `.cursor/docs/PROJECT_CONTEXT.md` | Update after pilot result and/or Pi bring-up milestone. |

---

## 9. Acceptance Criteria

1. Tests for core Fix 1e helpers are written before source implementation.
2. `pytest tests/` passes, or any skipped real-image tests are explicitly marked with missing-fixture reasons.
3. Multi-candidate images are resolved by deterministic score/tie-break rules or fail closed with `ambiguous_candidates`.
4. All ROI output geometry has declared original-image coordinate ownership, and coordinate round-trip tests pass.
5. Exact JSON gate constants are present and boundary-tested.
6. Rim-profile tests cover bright-dark-bright, flat, glare-only, and dark-tissue profiles.
7. For `capture_source=phone`, no successful ROI may use `cassette_method=paraffin_envelope`.
8. Oversize phone ROI class (~76% of image) fails G5 or equivalent quad-aware gate.
9. Pilot 10 audit PNGs draw the parallelogram and final ROI clearly, with failed candidates visibly distinct.
10. Zeke visual score is **>=8/10** using `phase3_outputs/pilot_roi_rubric.md`, with per-set pass/fail, reason, reviewer/date, and PNG filename recorded.
11. Full 47-set contour/profile regen occurs only after pilot pass.
12. Signal-gate or Phase 4 claims require post-regen histogram review; Fix 1e alone does not unlock Tier B router tuning.

---

## 10. Asynchronous Execution Macro

Implementation-time tasks that can run in parallel after this plan v2 approval:

```text
/multitask
1. Add TDD tests for Fix 1e core behavior in tests/test_phase3_block_roi.py: numeric rim profile scoring, multi-candidate arbitration, rotated quad ordering/area, coordinate round-trip, phone envelope ban, exact gate boundaries, oversize/sliver gates, Pi stub guard, and telemetry compatibility. Do not edit source implementation.
2. Draft constants schema updates for phase3_outputs/block_roi_constants_phone.json and block_roi_constants_pi.json: rim sample offsets, trough/rebound thresholds, side vote thresholds, candidate arbitration deltas, exact quad/ROI/aspect/sliver gates, warp cap, capture-source policy, and Pi calibration status. Add loader tests only.
3. Update audit/rubric artifacts: rename pilot rubric title to Fix 1e where appropriate, define the 10-set score record format, and prepare failure-semantics expectations for geometry reports and overlays; avoid changing ROI logic.
```

Sequential after macro: print file-by-file pre-mortem mitigations -> implement `phase3_block_roi.py` core helpers -> run tests -> regenerate pilot audit PNGs -> Zeke rubric -> only then 47-set regen.
