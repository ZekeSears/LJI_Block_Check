# Adversarial Architecture Review: Pre-Mortem Audit

> **Status:** Critical Review Completed — Actions Required
> **Target Document:** `.cursor/specs/proposed_plan.md` (Draft v3, 2026-05-24)
> **Date:** 2026-05-24
> **Domain Detected:** Embedded CV / Data Pipeline (histology image validation closeout)

---

## 0. Plan Completeness Check

Before critiquing the plan's substance, verify its structure. The proposed plan should
contain these sections. Flag any that are missing or insufficient:

| Required Section | Present? | Notes |
|-----------------|----------|-------|
| Objective | ✅ | Clear baseline state (13% lungs / 5.3% esophagus), Option B closeout, Phase 4 gate |
| Architecture & Pipeline Steps | ✅ | Eight ordered steps; Steps 1–2 and partial 5–7 remain |
| Data Flow (Inputs/Transformations/Outputs) | ✅ | Artifact paths enumerated through Phase 4 handoff |
| Key Decisions & Rationale | ✅ | Metrics-only routing, geometry calibration, mentor gate |
| Dependencies | ✅ | Stack and dataset listed |
| Open Questions & Known Risks | ✅ | Overlap persistence, set_01, esophagus regression acknowledged |
| Testing Considerations | ✅ | Table with pass criteria; label-mask test called out as new |

The plan is structurally complete. Two substantive gaps remain in the written spec: (1) **Step 3 does not define how geometry clusters become the two scalar router thresholds** (`SLIDE_TOTAL_TISSUE_AREA_PX`, `DOMINANCE_MIN_FOR_SHAPE`), and (2) **Step 8 Phase 4 entry criteria use “measurably” without a numeric threshold** while the 80% mentor gate is explicitly not met.

## 1. Positive Architectural Notes

- **Option B closeout is the right honesty policy:** Documenting 13% / 5.3% TPR with xfail retained avoids fake green tests and matches PROJECT_CONTEXT’s ranking-only acceptance philosophy.
- **Removing filename tissue from routing is architecturally consistent:** The user requirement is explicit; keeping tissue tokens for reporting-only (`lung` / `lungs` / `esophagus` split in `closeout_summary.md` and integration tests) is the correct separation of concerns.
- **Step ordering is sound:** Data hygiene → calibration → label mask → re-run → failure analysis → targeted tweaks → docs → Phase 4 gate avoids tuning the router on poisoned or degenerate inputs.

## 2. Fatal Assumptions

- **🔴 Geometry Clustering Will Unlock Separable Router Thresholds:** Step 3 assumes that splitting the calibration pool by dominance + contour count (or k-means on `[total_area, dominance, contour_count]`) will produce non-overlapping thresholds where the **tissue-filename split failed**. On the live 47-set library, `phase3_calibration_notes.md` already records hybrid sanity **FAIL** with slide `total_tissue_area` medians of ~8,428 px (lungs) vs ~6,848 px (esophagus) — close enough that `derive_high_low_separation_threshold()` sets `overlap=True` and exits 1. Clustering on the same three features without tissue labels does not magically widen separation; it only relabels the same overlapping point cloud. **Failure scenario:** Step 3 completes, overlap persists, implementation agent writes “provisional constants” from stale `router_constants.json` (224,998 px / 0.943 dominance from a prior run), re-runs pipeline, and esophagus TPR stays near 5% — no path to Phase 4 improvement is defined.

- **🔴 Stale `router_constants.json` Serves While Calibration Fails:** `run_calibration()` skips `write_router_constants_json()` when `hybrid_overlap` is true (lines 743–746 in `phase3_contour_profile.py`), but `phase3_router.py` loads whatever JSON exists at import with no freshness or provenance check. Current artifacts are inconsistent: notes say thresholds **not derived**, yet `router_constants.json` still holds numeric values. **Failure scenario:** Step 3 exits 1; pipeline and integration tests run in fresh processes and silently use outdated constants derived under the old tissue-pool split — TPR comparisons before/after Step 3 are meaningless.

- **🟡 Metrics-Only Routing Can Recover Esophagus TPR Without New Signals:** The plan documents esophagus TPR falling from ~43% (tissue-biased router) to 5.3% (metrics-only) and treats Step 3 threshold retune as the fix. Router logic in `route_comparison_hybrid()` returns `"shape"` when **either** side hits `side_prefers_shape()` unless **both** sides hit constellation — asymmetric OR bias. Overlapping slide metrics mean many esophagus pairs route to shape matching, where constellation was designed to help. Step 5 failure analysis may confirm this, but Steps 3–6 do not authorize any routing-logic change if overlap persists — only threshold retune and data fixes. **Failure scenario:** All allowed steps complete; esophagus stays mis-routed; plan declares “improvement path documented” without actual improvement.

## 3. Algorithmic & Logic Vulnerabilities

- **🔴 Step 3 Cluster→Threshold Mapping Is Undefined:** The plan lists k-means or dominance/count split as options but never specifies: (a) how many clusters, (b) which cluster maps to “prefer shape” vs “prefer constellation”, (c) how cluster boundaries become `SLIDE_TOTAL_TISSUE_AREA_PX` and `DOMINANCE_MIN_FOR_SHAPE`, or (d) what to do when clusters overlap in the 2D (area, dominance) projection. The existing helper `derive_high_low_separation_threshold()` expects two populations with lung_median > esophagus_median — geometry clusters are not guaranteed to align with that semantics. Implementing Step 3 without this mapping is guesswork.

- **🟡 Calibration Code Still Splits on `tissue_class` (Plan/Code Drift):** Step 3 says “not by tissue filename,” but `run_calibration()` lines 693–710 still build pools with `tissue_class == "lung"` vs `"esophagus"` (with `lungs` collapsed to `lung`). An agent implementing “geometry clusters” must replace this block entirely; the plan does not name the new function, its inputs, or its overlap test. Risk of partial edit leaving tissue split in place while claiming geometry calibration.

- **🟡 Label Mask Not Wired Despite Being on the Critical Path:** Step 4 requires `detect_label_region()` → mask before `segment_tissue()` for yellow/MT slides. Today `phase3_pipeline._process_image()` calls `segment_tissue()` then `clean_mask()` only; `phase3_label_detection.py` is never imported by pipeline or unified matcher. Set 1 slide still records `contour_count=0` / `no_contours` in `contour_profile.csv`. Until Step 4 lands, set_01 and any MT slide with label-dominated segmentation are excluded from the matrix — denominator manipulation by omission, not documented miss.

- **🟡 `set_41` Work-Order Mismatch Is Evaluable Today:** `audit_set_inventory.py` records `work_order_mismatch:['WO7482', 'WO7842']` as a **warning**, not blocking; `evaluable=True` in `set_inventory_audit.csv`. Block is HE/WO7842 lineage; slide is MT/WO7482. The pair enters the 47×46 matrix under the same `set_41` key — ranking metrics measure cross-work-order mismatch, not matcher quality. Step 2 mentions this set but does not require exclude-from-eval or blocking until lab confirms.

- **🟡 MT Stain → Yellow Label Inference May Mis-Pool Calibration:** `label_type_from_meta()` treats all MT slides as yellow-tag for calibration eligibility. The expanded library has many MT sets (34–47) on white PERMASLIDE-style captures, not APEX SAS yellow adhesive. Excluding them from the white HE calibration pool is correct; mis-tagging them as yellow and excluding from threshold pool while also skipping label-mask processing conflates two different physical slide types under one enum.

- **🟢 Router Constants Loaded Once at Import:** `_load_router_constants()` runs at module import in `phase3_router.py`. Re-calibration in Step 3 updates JSON on disk; any in-process reload without a fresh interpreter serves stale globals. Fresh subprocess pipeline runs (Step 5) are safe; interactive notebook debugging is not.

## 4. Resource & Environment Constraints

- **🟡 Full 47×46 Pipeline Re-Run Required After Each Step 3/4 Change:** Each calibration or label-mask iteration re-segments ~140 JPEGs and runs ~2,150 cross-modal comparisons (segmentation + routing + branch-specific matching). Step 5’s “sample 3 hits and 3 misses” still assumes a fresh matrix exists. Plan mentions 7–15 min integration runs but no artifact-reuse policy — three Step 3 retune attempts ≈ 30–45 min of laptop time with no parallelization on Pi 5 target.

- **🟡 Manual Step 5 Does Not Scale to 47 Sets:** `ranking_failure_notes.md` from 18 manual samples (3×3 per tissue bucket × 2 buckets, plus lung’s 4 sets) may miss systematic failure modes affecting the 13% lungs figure. Acceptable for closeout documentation, not for threshold derivation.

- **🟢 Windows Dev vs Pi 5 Deployment:** Current library is iPhone JPEGs at ~3024×3024; memory per image is manageable on dev hardware. No Pi-specific memory release audit is required for this plan’s scope (batch offline, not live capture).

## 5. Testing Gaps

- **🔴 No Test for Geometry-Based Threshold Derivation (Step 3 Core):** Plan says “TDD for new threshold derivation helper first,” but no test file or fixture is specified. Required: synthetic slide-metric rows where clusters are separable → helper returns two thresholds + exit 0; overlapping rows → overlap flag + no JSON write + explicit stale-json invalidation policy.

- **🔴 No Test for Label-Mask-Before-Segmentation Path (Step 4):** Testing table lists “synthetic yellow-slide fixture → contours > 0 after mask.” `detect_label_region()` has unit tests, but nothing asserts pipeline wiring. Without it, Step 4 can be “implemented” in label_detection only while pipeline still skips it.

- **🟡 Stale JSON / Overlap Exit-Code Policy Untested:** When calibration exits 1, nothing verifies that router does **not** load unproven constants, or that `phase3_calibration_notes.md` and JSON provenance stay in sync. A regression test should assert: overlap run → JSON absent or marked `"provenance": "provisional_overlap"` → router falls back to documented defaults only.

- **🟡 Phase 4 Entry Gate Not Encoded in Tests:** Step 8 criteria (mentor parallel OR lungs TPR improvement vs 13%) have no pytest or script guard. An agent could start Phase 4 HSV work while integration xfail still reflects sub-baseline ranking.

- **🟡 `set_41`-Class Metadata Warnings Not Gating TPR:** Audit detects work-order mismatch; integration/closeout do not exclude warned sets unless manually filtered. Need test or closeout rule: “warned-but-evaluable sets listed separately in TPR table.”

- **🟢 Separate `lung` / `lungs` / `esophagus` TPR Tests Exist:** `test_phase3_cross_modal_ranking.py` and `closeout_report.py` already split tokens — prior v2 gap is resolved.

## 6. Pre-Implementation Checklist

### 🔴 Critical (must resolve before writing any code)

- [ ] **Define cluster→threshold algorithm for Step 3:** Specify how geometry clusters (or dominance/count split) produce `SLIDE_TOTAL_TISSUE_AREA_PX` and `DOMINANCE_MIN_FOR_SHAPE`, including overlap detection and fallback when k-means clusters interleave in (area, dominance) space. **Done when:** `proposed_plan.md` Step 3 has a numbered sub-algorithm; unit test passes on separable synthetic data and fails overlap on known 47-set statistics.

- [ ] **Stale JSON invalidation on calibration failure:** When `hybrid_overlap` is true, either delete `router_constants.json`, write a explicit `"status": "overlap_unresolved"` stub, or force router to ignore JSON unless `"calibration_exit": 0`. **Done when:** test confirms overlap run does not load prior numeric thresholds; pipeline logs which constants are active.

- [ ] **Remove tissue-class split from calibration implementation:** Replace lines 693–710 pool logic in `phase3_contour_profile.py` with the Step 3 geometry helper — no `tissue_class == "lung"` gate for threshold derivation. **Done when:** calibration notes no longer say “Primary routing uses tissue in filename”; code grep shows zero tissue-class use in threshold derivation path.

- [ ] **Wire label mask in pipeline (Step 4):** For `label_type == "yellow"` slides, call `apply_label_mask()` (or equivalent) on BGR **before** `segment_tissue()` in `_process_image()`. **Done when:** set_01 slide produces contours > 0 in contour_profile re-run OR is documented excluded with mentor sign-off; synthetic yellow fixture test passes through pipeline path.

- [ ] **`set_41` eval policy:** Resolve WO7842 vs WO7482 with lab; until resolved, exclude `set_41` from TPR denominator with documented reason or mark audit warning as blocking. **Done when:** `set_inventory_audit.csv` shows `evaluable=False` for set_41 OR closeout table has footnote excluding it.

### 🟡 Moderate (must resolve during implementation)

- [ ] **Define “measurably” for Phase 4 entry (Step 8):** e.g. lungs TPR ≥ 13% + 10 pp, or any esophagus improvement with mentor sign-off. **Done when:** numeric threshold or explicit “mentor letter only” path in plan §8.

- [ ] **MT vs yellow-tag visual confirmation:** Do not rely on stain token alone for `label_type`; spot-check MT sets 34–47 slide photos against APEX SAS vs PERMASLIDE. **Done when:** `YELLOW_TAG_SET_IDS` or `label_type_from_meta()` rules updated; calibration notes list yellow vs white MT counts.

- [ ] **Degenerate-set denominator rule (documented):** Closeout already says zero-contour sets excluded when absent from matrix — extend to label-mask failures. **Done when:** `closeout_summary.md` lists excluded set IDs and whether exclusion counts as miss or omit.

- [ ] **Post-calibration fresh-process rule:** Document that Step 5 pipeline and integration must run in new Python process after Step 3/4. **Done when:** execution order in plan §8 mentions process restart.

- [ ] **Update stale artifacts:** `phase3_calibration_notes.md` and `PROJECT_CONTEXT.md` §4 still describe tissue-metadata routing and 23-set baselines. **Done when:** Step 7 complete with 47-set metrics-only numbers.

- [ ] **Ranking failure analysis deliverable:** Step 5 output `ranking_failure_notes.md` should classify at least: wrong route vs wrong score vs degenerate segmentation, with set IDs. **Done when:** file exists and references `routing_log.csv` decisions for sampled sets.

### 🟢 Minor (address as encountered)

- [ ] **Fix `phase3_pipeline.py` module docstring:** Still says routing uses “tissue metadata” — misleading for metrics-only v3. **Done when:** docstring matches router behavior.

- [ ] **Integration artifact reuse (optional):** Document whether Step 5 reuses `phase3_outputs/pipeline_run/` or always runs fresh. **Done when:** one-line policy in plan or test docstring.

- [ ] **Router reload helper (optional):** Expose `_load_router_constants()` for REPL/notebook use after calibration. **Done when:** function callable without process restart, or documented as unsupported.

## 7. Clarifications required before plan v2

- **Pending (Zbigniew):** Proceed to Phase 4 (HSV stain verification) in parallel while ranking is 13% lungs / 5.3% esophagus, or block Phase 4 until ranking improves? **Who:** Zbigniew. **If not answered:** Plan v2 retains Step 1 as gate; default recommendation is **parallel documentation-only Phase 4 planning** but no HSV implementation until mentor reply.

- **Pending (Lab / Zeke):** Is `set_41` block (WO7842 / HE) genuinely paired with slide (WO7482 / MT), or is one filename wrong? **Who:** User + lab. **If not answered:** Exclude set_41 from TPR denominator in plan v2 with documented assumption; do not treat its ranking as matcher signal.

- **Pending (Zbigniew):** If Step 3 geometry calibration still exits 1 on overlap after implementation, is it acceptable to proceed with **documented provisional constants + routing_uncertain flagging** rather than blocking Phase 4 indefinitely? **Who:** Zbigniew. **If not answered:** Plan v2 default is keep Option B xfail, document overlap in calibration notes, and **do not** claim router is calibrated — Phase 4 may start only for stain layer that does not depend on routing branch.

> **No user clarification required before plan v2.** Steps 3–4 algorithm specs and stale-JSON policy can be written into plan v2 with repo-derived defaults. Mentor items above are **pending decisions** with documented fallbacks, not blockers to revising the spec.
