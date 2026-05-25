# Adversarial Architecture Review: Pre-Mortem Audit

> **Status:** Critical Review Completed — Actions Required
> **Target Document:** `.cursor/specs/proposed_plan.md`
> **Date:** 2026-05-25
> **Domain Detected:** Embedded CV (OpenCV block ROI on phone/Pi backlit histology captures)

---

## 0. Plan Completeness Check

Before critiquing the plan's substance, verify its structure. The proposed plan should
contain these sections. Flag any that are missing or insufficient:

| Required Section | Present? | Notes |
|-----------------|----------|-------|
| Objective | ✅ | Clear failure mode (1/10 pilot), Fix 1d scope, ≥8/10 gate, no 47-set regen until pilot |
| Architecture & Pipeline Steps | ✅ | 12 ordered steps; phone vs Pi chain divergence documented |
| Data Flow (Inputs/Transformations/Outputs) | ✅ | Present but thin — no explicit `SegmentationWithRoi` field list or failure enum |
| Key Decisions & Rationale | ✅ | Table present; several cells reference "v2 mitigation" before this pre-mortem exists |
| Dependencies | ✅ | Minimal (opencv, numpy, pytest) — omits pandas/CSV consumers if contour profile regen is in scope |
| Open Questions & Known Risks | 🟡 | Only two bullets; understates meta/calibration and signal-gate coupling |
| Testing Considerations | ✅ | Named tests + pilot geometry script + visual rubric |

**Structural concern:** §10 "Pre-mortem checklist (v2 resolved)" embeds resolved 🔴 items inside a **Draft v1** plan pending pre-mortem. That creates false confidence — downstream agents may skip checklist items assuming they are already mitigated. Plan v2 must either remove §10 or re-derive mitigations from this audit.

---

## 1. Positive Architectural Notes

- **Pilot-before-regen discipline** is correct and aligned with PROJECT_CONTEXT: ROI quality must not be judged by 46-way retrieval TPR or verification gap while `SIGNAL_MISSING` persists.
- **Phone disables `backlight_cc`** directly targets the audit finding that weak perimeter glow mis-triggers full-frame paths on iPhone JPEGs — a concrete, testable policy split by `capture_source`.
- **Production vs audit fallback separation** (`allow_full_frame_fallback` audit-only, PNG title `fallback=analysis`) preserves the Fix 1c safety posture and avoids silent full-frame production passes.

---

## 2. Fatal Assumptions

- **🔴 Plastic bbox is the right spatial anchor:** The plan chains paraffin row/morph logic inside a **plastic_frame** detection bbox, citing audit coverage "44/47" without reproducing detection criteria in the plan. If `plastic_frame` false-positives on glare, label plastic, or partial cassette visibility (common on phone JPEGs), the paraffin window is shifted before G4/G5 ever run — identical failure class to Fix 1c's cassette localization regression. **When it breaks:** set_02/set_33 tests pass on one frame but pilot fails on adjacent captures; geometry script flags slit/flood on sets that passed unit tests.

- **🔴 Strict margin threshold generalizes across the 47-set phone library:** Step 2 requires `MARGIN_STRICT_MIN_PERIM_FRAC` (phone "high; e.g. 0.05+") but the plan does not bind this to measured perimeter statistics from `contour_profile.csv` or a calibration script output. **When it breaks:** unstained blocks with dim edges never reach `has_strong_margin` on Pi (acceptable) but phone chain also loses valid frames if perimeter metric is computed on downscaled or JPEG-compressed edges — `plastic_frame` runs on crops that still include label/grid clutter.

- **🔴 ROI correction unlocks downstream matching without touching segmentation:** Steps 9–10 keep frozen `segment_tissue()` and only add post-Otsu `seg_*` gates. PROJECT_CONTEXT already states median score gap is **−0.305** and verification pass is **4.3%**. A tighter ROI that passes visual rubric may still yield masks with tiny tissue fraction or label bleed — ranking and verification will remain `SIGNAL_MISSING` unless audit overlays improve. **When it breaks:** pilot ≥8/10 achieved, 47-set regen run, gap histogram unchanged → wasted regen cycle and false milestone closure.

---

## 3. Algorithmic & Logic Vulnerabilities

- **🔴 Opposite-end strip + deferred `ambiguous_orientation`:** Step 7 applies strip only when short-end score delta >10%; otherwise `strip_method=none`, and `ambiguous_orientation` triggers only when aspect is near-square **and** morph failed **and** scores tied. Sets 02/33 are explicit regression targets — tie-breaking without strip can leave grid/label energy on one short end, failing plastic-first intent. Conversely, a marginal >10% delta on noisy phone JPEGs can strip the wrong end on square-ish cassettes.

- **🟡 G4 (`roi_sliver`, h ≥15% inner) vs G5 (`roi_oversize`, area ≤90%):** Gates are directionally right for audit failures (06/11 slits, full-frame class) but 15% height is a single scalar across lung and esophagus layouts. Esophagus blocks with wide shallow wax pools may fail G4 while still looking correct to a human; lung sets with legitimate tall wax may pass G4 yet still flood Otsu. Plan allows 12% tune "only if wax visually correct" — that defers a **classification** decision to post-hoc pilot, not a measured rule.

- **🟡 `capture_source` default `phone`:** Step 1 loads JSON by meta with default `phone`. Any pipeline path that omits `capture_source` on Pi captures will permanently disable `backlight_cc` and apply phone margins on production hardware — wrong chain with no runtime error.

- **🟡 Post-Otsu `seg_blob` (esophagus only):** Tissue-class gating assumes `tissue_class` in meta is reliable and consistent with filename tokens used only for reporting elsewhere. Mis-labeled meta routes lung floods through without `seg_blob`, or esophagus through with false blob fails.

- **🟢 Row projection vs morph paraffin (`paraffin_method=rows|morph`):** Logging method is good for telemetry; plan does not specify selection order or failure handoff when both disagree inside the same plastic bbox — debugging will require manual PNG review per set.

- **🟢 Constants cache at module init:** Tests that mutate JSON or env must call an explicit reload hook; plan mentions reload for tests but does not require a public `reload_block_roi_constants()` — risk of order-dependent pytest flakes.

---

## 4. Resource & Environment Constraints

- **🟡 Real JPEG integration tests:** Plan mandates `test_set02_set33_roi_ok_plastic`, `test_roi_sliver_rejects_set06_class`, etc. on "real JPEG 06 or synthetic." `iphone_images/` is gitignored — CI and fresh clones may run **synthetic-only**, giving false green while pilot fails on compression/white-balance artifacts. **Done when:** tests skip with explicit reason if assets missing, or minimal committed fixtures under `tests/fixtures/roi/`.

- **🟡 Pilot geometry leaf script:** `pilot_roi_geometry_check.py` is pre-visual and audit-only — acceptable as leaf, but if slit/flood heuristics diverge from G4/G5 thresholds, Zeke reviews two conflicting signals. Align geometry script thresholds with JSON constants or generate flags from the same functions.

- **🟢 Pi 5 / Arducam path not exercised:** `block_roi_constants_pi.json` stub until hardware batch — memory and timing are non-issues for offline pytest; **runtime** risk is first-field mismatch between phone-tuned plastic thresholds and Pi FOV/exposure (300mm WD, ~100mm FOV per PROJECT_CONTEXT).

- **🟢 OpenCV matrix lifecycle:** Plan does not repeat Fix 1c explicit `del`/`release` discipline; multiple morph + projection passes per frame on Pi remain bounded for single-frame capture but should not leak across batch regen loops.

---

## 5. Testing Gaps

- **🔴 No test that plastic-first chain fails closed when `plastic_frame` is absent:** Cassette chain lists `plastic_frame → dark_frame → paraffin_envelope → geometric_inset` but tests name golden set_04 and slit/oversize — not "all methods failed → empty ROI + telemetry reason."

- **🟡 No test for wrong `capture_source` on Pi-bound image:** Only `test_phone_never_backlight_cc`; missing inverse guard that `capture_source=pi` **may** use `backlight_cc` when `has_strong_margin`.

- **🟡 Pilot set list and rubric not in plan:** Acceptance requires Zeke visual ≥8/10 but plan does not enumerate the 10 pilot set IDs or per-set pass criteria (wax window vs tissue visibility vs label exclusion). Regression to 1/10 is undetectable without a frozen checklist file.

- **🟡 Geometry script vs visual gate:** §9 requires geometry script "no slit/flood flags on ≥8 sets" before visual — no definition of which ≥8 sets (same as pilot 10? subset?). Mismatch allows visual work on sets geometry already flagged.

- **🟡 Contour profile regen after pilot:** Listed as acceptance #4 but no test that new telemetry columns (`strip_method`, `capture_source`, `paraffin_method`) round-trip into `contour_profile.csv` without breaking router consumers.

- **🟢 `test_seg_flood_set28_class`:** Good production-path guard; ensure synthetic mask frac >0.85 matches set_28 failure mode from audit narrative, not an arbitrary threshold.

---

## 6. Pre-Implementation Checklist

### 🔴 Critical (must resolve before writing any code)

- [ ] **Remove or rewrite plan §10 "v2 resolved" pretense:** Plan v2 must map each 🔴 below to an explicit step/constant/test — not claim pre-resolution. **Done when:** `proposed_plan.md` v2 §10 is deleted or replaced with pointers to this §6 checklist items marked mitigated.

- [ ] **Lock phone `MARGIN_STRICT_MIN_PERIM_FRAC` from data:** Measure perimeter bright fraction on block silhouettes in calibration CSV or a one-off script; document value in `block_roi_constants_phone.json` with source row stats. **Done when:** JSON field exists, loader test asserts value, and notes cite min/median of measured distribution — not "e.g. 0.05+".

- [ ] **Define plastic_frame acceptance on pilot 10 sets:** Document detection rule (color/edge thresholds) and expected bbox IoU or visual pass per set before coding paraffin window. **Done when:** design spec subsection or plan v2 table lists pass/fail per pilot set ID for plastic bbox alone.

- [ ] **Fail-closed cassette chain test:** When all cassette methods fail, ROI returns empty/`roi_ok=False` with `failure_reason` — never silent full frame in production. **Done when:** pytest asserts production path with `allow_full_frame_fallback=False` yields empty mask and explicit reason string.

- [ ] **Freeze pilot set IDs + rubric artifact:** Enumerate 10 (or N) set IDs, rubric dimensions (wax framing, label/grid exclusion, tissue visible), and fail policy. **Done when:** `phase3_outputs/pilot_roi_rubric.md` or equivalent exists and is referenced in plan v2 §9.

- [ ] **Align geometry pre-check with G4/G5:** `pilot_roi_geometry_check.py` must call shared gate functions or read same JSON keys. **Done when:** one set_06-class synthetic triggers both geometry script flag and `test_roi_sliver_rejects_set06_class` failure.

- [ ] **Real-image test policy:** Committed minimal fixtures OR skip-if-missing with `pytest.mark` and CI documentation. **Done when:** `pytest tests/test_phase3_block_roi.py` behavior documented in plan v2; no silent synthetic substitution without marker.

### 🟡 Moderate (must resolve during implementation)

- [ ] **`capture_source` propagation audit:** Every block silhouette entry point sets meta from filename or sidecar; default documented. **Done when:** grep-backed checklist in plan v2 or test that pipeline inventory CSV includes `capture_source` for all block rows.

- [ ] **Opposite-end strip regression:** set_02 and set_33 real/synthetic tests assert `strip_method != none` when delta >10%, and `ambiguous_orientation` not set on success path. **Done when:** named tests pass and telemetry columns populated.

- [ ] **Constants loader + reload:** `test_load_phone_constants` and test-only reload after JSON edit. **Done when:** two tests green; flake8 clean.

- [ ] **Post-Otsu production fail path:** `seg_flood` / `seg_empty` / esophagus `seg_blob` set `reshoot_recommended` without invoking audit fallback. **Done when:** pytest on production flag path; PNG title never `fallback=analysis`.

- [ ] **Signal-gate expectation documented in milestone:** Closing Fix 1d does not imply Tier B or Phase 4 unlock. **Done when:** PROJECT_CONTEXT §4 update states pilot pass ≠ gap improvement until regen + histogram reviewed.

### 🟢 Minor (address as encountered)

- [ ] **Public `reload_block_roi_constants()` for tests:** Avoid module-level stale cache. **Done when:** function exists and used in at least one test.

- [ ] **Contour profile column contract:** Document new CSV columns and router ignore list. **Done when:** `phase3_calibration_notes.md` snippet in same PR as regen.

- [ ] **Pi JSON stub schema:** Pi file mirrors phone keys with `null` or sentinel + comment "fill on first batch." **Done when:** loader accepts pi file without crash.

---

## 7. Clarifications required before plan v2

- **[Pending]:** Which **exact set IDs** constitute the visual pilot (same 10 as Fix 1c audit, or revised list after set_04-only pass)? **Who:** User (Zeke). **If not answered:** Plan v2 must not claim ≥8/10 acceptance — use placeholder `PILOT_SET_IDS` in constants JSON commented "TBD" and block milestone sign-off.

- **[Pending]:** Is **≥8/10** judged on wax/ROI framing only, or must tissue silhouette also look match-ready inside the crop? **Who:** User / Zbigniew. **If not answered:** Safe default for plan v2 — **ROI framing only** (label/grid exclusion + paraffin window); tissue quality tracked separately in segmentation audit, not gating Fix 1d closure.

- **[Pending]:** For **phone** `MARGIN_STRICT_MIN_PERIM_FRAC`, should the value be derived from the existing 47-set `contour_profile.csv` perimeter stats, or from a fresh measurement pass on block silhouettes only? **Who:** User. **If not answered:** Safe default — derive from block `block_silhouette` rows in existing calibration CSV; document percentile used (e.g. p10 bright perimeter) in constants JSON comments.

> **§7 blocks plan v2:** **Partially.** Plan v2 can proceed with safe defaults for margin derivation and ROI-only rubric, but **pilot set ID enumeration** should be confirmed before locking acceptance criteria and geometry-script set lists. Pi hardware constants remain stubbed per plan — not a v2 blocker.
