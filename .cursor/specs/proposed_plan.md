# Fix 1d — Plastic-first paraffin ROI (post–Fix 1c audit): Proposed Plan

> **Status:** Plan v2 — approved for implementation (2026-05-25)  
> **Date:** 2026-05-25  
> **Source:** Brainstorm synthesis, isolated pre-mortem 2026-05-25, §7 defaults (parent confirmed)  
> **Supersedes:** Fix 1c cassette detection ordering; Draft v1 §10 “v2 resolved” pretense removed

---

## 1. Objective

Fix 1c regressed visual pilot to **1/10** (only set_04). Root cause is **cassette/wax localization**, not Otsu on dark tissue inside wax.

**Fix 1d:** Plastic-frame-first paraffin window, deferred `ambiguous_orientation`, gates G1–G5 (incl. slit + oversize), strict margin policy for `backlight_cc`, phone vs Pi constants, hybrid audit-only fallback.

**Pilot gate (before 47-set regen):** Zeke visual **≥8/10** on frozen pilot set list using **ROI framing rubric only** (wax window; label/grid exclusion — not tissue match-ready). Geometry pre-check must align with G4/G5 on the **same 10 set IDs**.

**Frozen:** `segment_tissue()`, `extract_contours()`, `clean_mask()`, descriptor APIs.

**Milestone scope (explicit):** Fix 1d closure means pilot + tests + telemetry. It does **not** imply Tier B router work, Phase 4 unlock, or `SIGNAL_MISSING` resolution until contour profile regen and gap histogram are reviewed post-pilot.

---

## 2. Proposed Architecture & Pipeline Steps

1. **Constants** — Load `phase3_outputs/block_roi_constants_{phone|pi}.json` by `meta.capture_source` (default `phone` only when meta omits field; see §2.13). Cache at module init; expose `reload_block_roi_constants()` for tests.

2. **Margin test (strict, data-derived)** — `has_backlight_margin` → `has_strong_margin` only if perimeter bright fraction ≥ `MARGIN_STRICT_MIN_PERIM_FRAC`. **Phone value:** derive from `contour_profile.csv` rows where `role=block_silhouette` (47-set calibration pool): compute perimeter bright-fraction per row, take **p10** of the distribution, round to 3 decimals, write to `block_roi_constants_phone.json` with JSON comment citing row count, min/median/p10. **Pi value:** same procedure when Pi batch exists; until then stub mirrors phone keys with `"_comment": "fill on first Pi batch"`. Weak glow → **no** `backlight_cc`.

3. **Cassette chain (phone)** — `plastic_frame` → `dark_frame` → `paraffin_envelope` (guarded) → `geometric_inset`. **`backlight_cc` disabled when `capture_source=phone`.** If `plastic_frame` fails, continue chain; do not assume plastic bbox for paraffin steps until a method succeeds.

4. **Cassette chain (pi)** — If `has_strong_margin` → `backlight_cc`; else same as phone (steps 3 fallback order).

5. **Fail-closed production path** — When all cassette methods fail and `allow_full_frame_fallback=False` (production default): return empty mask, `roi_ok=False`, explicit `failure_reason` (e.g. `cassette_chain_exhausted`). **Never** silent full-frame ROI in production. Audit CLI may set `allow_full_frame_fallback=True`; PNG title must include `fallback=analysis`.

6. **Inner inset** — ~6% per side (from phone JSON `INNER_INSET_FRAC`; Pi may override after calibration).

7. **Paraffin window** — Inside **successful** cassette bbox only: try row projection first; if row mask area < `PARAFFIN_ROW_MIN_FRAC` of inner area, fall back to morph; log `paraffin_method=rows|morph`. If plastic bbox was used but row and morph disagree by >20% area, set telemetry `paraffin_disagreement=True` (debug only; do not auto-fail).

8. **Opposite-end strip** — Compute short-end scores on plastic bbox. If delta > `STRIP_DELTA_MIN` (default 0.10): apply strip to lower-scoring end; `strip_method=opposite_end`. If delta ≤ threshold: `strip_method=none`. **`ambiguous_orientation`** only if aspect ratio in `[ASPECT_NEAR_SQUARE_MIN, ASPECT_NEAR_SQUARE_MAX]`, morph paraffin failed, **and** |score_a − score_b| < `AMBIGUOUS_SCORE_TIE_EPS` — defer hard fail (sets 02/33 regression). Success path for 02/33 must show `strip_method != none` when delta >10% on real/synthetic fixtures.

9. **ROI gates G1–G5** (shared functions; JSON keys) —
   - **G1** `paraffin_low` — wax signal below floor  
   - **G2** `roi_narrow` — width vs inner frame  
   - **G3** `backlight_flood` — perimeter flood heuristic  
   - **G4** `roi_sliver` — ROI height ≥ `G4_MIN_HEIGHT_FRAC` of inner height (default **0.15**; tune to 0.12 only if ≥8/10 wax framing already passes and only esophagus wide layouts fail — document in calibration notes)  
   - **G5** `roi_oversize` — ROI area ≤ `G5_MAX_AREA_FRAC` of image (default **0.90**)  
   - **G6** `empty_wax` — no paraffin signal  

10. **Otsu on crop** — Frozen `segment_tissue()` on gated crop only.

11. **Post-Otsu (production)** — `seg_empty`, `seg_flood`, `seg_blob` (esophagus only, requires reliable `tissue_class` in meta). Fail → empty mask + `reshoot_recommended=True`; no audit fallback. **`seg_blob` skipped for lung.**

12. **Hybrid** — `allow_full_frame_fallback` only audit CLI / `segmentation_audit_pack.py --analysis-fallback`; PNG title `fallback=analysis`.

13. **`capture_source` propagation** — Block silhouette paths must set `meta.capture_source` from filename prefix or inventory sidecar (`phone` for `iphone_images/` benchmark). Default `phone` when missing is **documented** in constants README comment and asserted in loader test; add pipeline inventory check that all `block_silhouette` rows in regen CSV include `capture_source`.

---

## 3. Data Flow

| Stage | Input | Output / fields |
|-------|--------|-------------------|
| Entry | BGR block silhouette, `meta.role`, `meta.tissue_class`, `meta.capture_source` | — |
| Cassette | Gray + color features | `cassette_method`, `plastic_bbox`, `failure_reason` if chain fails |
| Paraffin | Plastic or fallback bbox | `paraffin_method`, `paraffin_bbox`, `paraffin_disagreement` |
| Strip | Short-end scores | `strip_method`, `ambiguous_orientation` (bool) |
| Gates | Inner frame + ROI geom | `gate_failures[]`, `roi_ok` |
| Segment | Crop BGR | `mask`, `seg_*` flags, `reshoot_recommended` |
| Aggregate | — | `SegmentationWithRoi`: `{roi_ok, failure_reason, cassette_method, paraffin_method, strip_method, capture_source, gate_failures, mask, reshoot_recommended, ambiguous_orientation}` |

**Outputs:** Updated block rows in `contour_profile.csv` (new telemetry columns), pilot audit PNGs under `phase3_outputs/roi_crop_audit/`, geometry report `phase3_outputs/pilot_roi_geometry_report.md`. **No** full 47-set similarity matrix regen until §9 criteria 1–3 satisfied.

---

## 4. Key Decisions & Rationale

| Decision | Rationale | v2 mitigation (traceable) |
|----------|-----------|---------------------------|
| Plastic-first anchor | 44/47 audit had plastic-visible frames; wrong bbox shifts paraffin before G4/G5 | §5 plastic pilot table; fail-closed §2.5; tests §7 |
| `MARGIN_STRICT` from CSV | Avoid guessed 0.05+ that rejects dim phone edges | §2.2 p10 on `block_silhouette` rows; JSON comments |
| Phone disables `backlight_cc` | Weak perimeter glow mis-triggers full-frame | §2.3–4 + `test_phone_never_backlight_cc` |
| G4 height ≥15% | Audit slits (06, 11) | §2.9 G4; shared with geometry script |
| G5 area ≤90% | Full-frame ROI class | §2.9 G5; shared with geometry script |
| `ambiguous_orientation` deferred | 02/33 ablation | §2.8 tie rule; dedicated tests |
| ROI-only visual rubric | Tissue match-ready is segmentation audit, not Fix 1d | §6 `pilot_roi_rubric.md` |
| Signal gate unchanged | Median gap −0.305; pilot ≠ matcher fix | §1 milestone scope |
| Real JPEG policy | `iphone_images/` gitignored | §7 fixtures + skip markers |
| Constants reload | Avoid pytest stale cache | `reload_block_roi_constants()` §2.1 |

---

## 5. Plastic-frame pilot acceptance (pre-coding gate)

Before merging paraffin-window logic, validate **plastic bbox alone** on pilot 10 (visual pass/fail per set). Criteria per set: bbox covers cassette plastic rim; excludes majority of label/grid; not full-image. Record in geometry report; implementation may proceed in parallel with unit tests but **pilot PNG regen** waits until plastic step passes ≥8/10 plastic-only spot check OR documented exception with mentor note.

| Set ID | Tissue (reporting) | Plastic bbox expectation |
|--------|-------------------|---------------------------|
| 02 | lung | Strip end clears grid; plastic visible |
| 04 | esophagus | Golden regression — must remain pass |
| 06 | lung | No vertical slit — G4 target |
| 11 | esophagus | No slit; wax band centered |
| 28 | esophagus | Post-Otsu flood class guarded |
| 31 | lungs | Standard cassette |
| 33 | lung | Same strip policy as 02 |
| 35 | lungs | Standard cassette |
| 40 | esophagus | Pi-like aspect; phone constants |
| 45 | esophagus | Standard cassette |

---

## 6. Pilot visual rubric (ROI framing only)

**Artifact:** `phase3_outputs/pilot_roi_rubric.md` (created at implementation start; this section is authoritative content).

**Sets:** `02, 04, 06, 11, 28, 31, 33, 35, 40, 45` — same as Fix 1c audit.

**Pass per set (1 point each dimension, max 3 → set pass if ≥2/3):**

| Dimension | Pass | Fail |
|-----------|------|------|
| Wax window | Paraffin window visible; not full-frame; not extreme slit | Full frame, sliver, or wax missing |
| Label/grid exclusion | Label and grid mostly outside ROI | Label or grid dominates crop |
| Cassette framing | Plastic/cassette context plausible | Obvious wrong cassette region |

**Set pass:** ≥2/3 dimensions pass. **Pilot pass:** ≥8/10 sets pass. **Out of scope:** tissue silhouette match-ready, constellation score, verification gap.

**Geometry pre-check (same 10 IDs):** `code/pilot_roi_geometry_check.py` calls **same** `evaluate_roi_gates()` (or shared module) and reads `G4_MIN_HEIGHT_FRAC`, `G5_MAX_AREA_FRAC` from phone JSON — no duplicate thresholds. Report `slit`/`flood` flags; Zeke visual only on sets with zero flags OR documented override in rubric notes.

---

## 7. Testing Considerations

| Test / check | Success criterion | Pre-mortem §6 item |
|--------------|-------------------|-------------------|
| `test_margin_strict_from_json` | Loader reads `MARGIN_STRICT_MIN_PERIM_FRAC`; value matches calibration script output | Margin data-derived |
| `test_load_phone_constants` / `test_load_pi_constants_stub` | Phone + Pi JSON load; Pi null/sentinel keys accepted | Pi stub schema |
| `test_phone_never_backlight_cc` | `capture_source=phone` → method ≠ `backlight_cc` | Phone policy |
| `test_pi_may_use_backlight_cc_with_margin` | `capture_source=pi` + synthetic strong margin → `backlight_cc` allowed | Inverse guard |
| `test_cassette_chain_fail_closed` | All methods fail, production flag → empty mask, `failure_reason` set | Fail-closed |
| `test_plastic_absent_falls_through` | No plastic → dark_frame or envelope or inset or fail; never silent full frame | Plastic-first fail closed |
| `test_roi_sliver_rejects_set06_class` | Real JPEG or `tests/fixtures/roi/set_06_sliver.jpg`; not `roi_ok` | G4 + geometry align |
| `test_set02_set33_roi_ok_plastic` | Real JPEG or committed fixture; `ambiguous_orientation` false; `strip_method != none` when delta>10% | Opposite-end strip |
| `test_set04_golden_regression` | Still passes | Golden |
| `test_seg_flood_set28_class` | mask frac >0.85 → production fail, no audit fallback | Post-Otsu |
| `test_geometry_script_matches_g4_g5` | Synthetic slit triggers both geometry report and pytest G4 | Align geometry |
| `test_reload_block_roi_constants` | Mutate JSON → reload → new value | Stale cache |
| `test_capture_source_default_documented` | Missing meta → phone + warning telemetry | Default policy |
| Real JPEG policy | `@pytest.mark.skipif(not path.exists(...))` with reason `iphone_images missing` | Real-image policy |
| `pytest tests/` (non-integration) | All pass | Regression |
| Visual pilot | ≥8/10 per §6 | Pilot rubric |

**Fixtures:** Commit minimal `tests/fixtures/roi/` (set_04 golden, set_06 slit class, set_02/33 strip cases) so CI is green without gitignored library.

---

## 8. Implementation Files

| File | Change |
|------|--------|
| `code/phase3_block_roi.py` | Fix 1d logic; shared gate helpers; `reload_block_roi_constants()` |
| `code/calibrate_margin_strict.py` | One-off: read `contour_profile.csv` block_silhouette rows → emit p10 + stats for JSON comment |
| `phase3_outputs/block_roi_constants_phone.json` | Thresholds incl. `MARGIN_STRICT_MIN_PERIM_FRAC` with derivation comment |
| `phase3_outputs/block_roi_constants_pi.json` | Stub mirrors phone keys |
| `phase3_outputs/pilot_roi_rubric.md` | Frozen checklist (content from §6) |
| `code/pilot_roi_geometry_check.py` | Leaf: imports shared gates; writes `pilot_roi_geometry_report.md` |
| `tests/test_phase3_block_roi.py` | Extended per §7 |
| `tests/fixtures/roi/` | Minimal committed JPEGs/PNGs |
| `code/segmentation_audit_pack.py` | `--analysis-fallback` |
| `docs/superpowers/specs/2026-05-25-fix-1d-roi-plastic-first-design.md` | Design cross-ref |
| `.cursor/docs/PROJECT_CONTEXT.md` | §4 Fix 1d implemented / pilot result (after work) |

**Contour profile regen (post-pilot only):** Document new columns (`strip_method`, `capture_source`, `paraffin_method`, `paraffin_disagreement`) in `phase3_calibration_notes.md`; router ignores unknown columns by default.

---

## 9. Acceptance Criteria

1. All §7 tests pass (including skip markers documented).  
2. `calibrate_margin_strict.py` run once; phone JSON field matches script output.  
3. Geometry report on pilot 10: ≥8 sets with zero slit/flood flags (same gate functions as production).  
4. Zeke visual **≥8/10** per `pilot_roi_rubric.md` (ROI framing only).  
5. **Then** contour profile regen on 47 sets; **then** review gap histogram — do not claim signal-gate fix until reviewed.  
6. No full pipeline similarity regen until 1–4 met.

---

## 10. Pre-mortem §6 critical checklist — mitigations (not pre-resolved in v1)

| §6 critical item | Plan v2 mitigation | Verification |
|------------------|-------------------|--------------|
| Remove §10 pretense | This section replaces v1 §10 | v2 status header |
| `MARGIN_STRICT` from data | §2.2, `calibrate_margin_strict.py`, JSON comments | `test_margin_strict_from_json` |
| Plastic-frame pilot acceptance | §5 table + geometry report | Manual + ≥8 plastic spot check |
| Fail-closed cassette chain | §2.5, §2.3–4 | `test_cassette_chain_fail_closed`, `test_plastic_absent_falls_through` |
| Freeze pilot IDs + rubric | §6, `pilot_roi_rubric.md` | Visual ≥8/10 |
| Align geometry with G4/G5 | §6, shared `evaluate_roi_gates()` | `test_geometry_script_matches_g4_g5` |
| Real-image test policy | §7 fixtures + skipif | CI docs in plan §7 |

**Moderate items (during implementation, not v2 blockers):** `capture_source` inventory audit (§2.13); post-Otsu production path tests; constants reload (§2.1); PROJECT_CONTEXT signal-gate note (§1).

---

## 11. Open Questions & Residual Risks

- Pi constants: filled on first hardware batch; phone thresholds may mismatch FOV until recalibrated.  
- G4 at 12%: only if §9 step 4 already ≥8/10 and esophagus wide layouts fail wax framing only.  
- Plastic false positives (glare/label plastic): mitigated by §5 per-set table and fail-closed chain, not single global threshold.

---

### Asynchronous Execution Macro

Independent test/JSON work — run before `phase3_block_roi.py` implementation:

```
/multitask
1. tests/test_phase3_block_roi.py — Add failing tests: fail-closed chain, plastic absent fall-through, G4 set_06 class, set_02/set_33 strip (fixtures under tests/fixtures/roi/), phone never backlight_cc, pi may backlight_cc, geometry/G4 alignment synthetic. No implementation in phase3_block_roi.py yet.
2. code/calibrate_margin_strict.py + phase3_outputs/block_roi_constants_phone.json — Run script on contour_profile.csv block_silhouette rows; write p10 MARGIN_STRICT with stats comment; test_load_phone_constants + test_margin_strict_from_json only.
3. phase3_outputs/pilot_roi_rubric.md + tests/fixtures/roi/README.md — Write rubric artifact from plan §6; add fixture README and placeholder paths; stub code/pilot_roi_geometry_check.py with docstring contract only (import gate helpers after they exist).
```

**Sequential after macro:** Implement `phase3_block_roi.py` → `pytest tests/` → pilot PNG regen → Zeke rubric → geometry report → visual ≥8/10 → contour profile regen.
