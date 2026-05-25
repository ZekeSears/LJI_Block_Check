# PROJECT_CONTEXT.md — LJI Histology Block-Check Pipeline

> **Last updated:** 2026-05-24 (Fix 1c design v2 — functional verification focus)
> **Purpose:** Attach this file to every new Cursor chat with `@PROJECT_CONTEXT.md`.
> It replaces the need to re-explain the project from scratch each session.
> Update it when a phase closes or a major decision changes.

---

## 1. What This Project Is

**The "Digital Gatekeeper"** — an automated computer vision system that verifies histology
tissue slides match their originating paraffin wax blocks, replacing a manual process at the
La Jolla Institute of Immunology (LJI) Microscopy & Histology Core Facility. The lab
processes ~10,000 slides/year from labs worldwide. The system uses backlit transillumination
to capture tissue silhouettes from both blocks and slides, then compares them mathematically
to detect mismatches and flag exceptions.

**People:**
- Ezekiel (Zeke) — intern (high school, strong Java background, learning Python)
- Zbigniew — supervisor/mentor at LJI
- Development environment: Windows 11, Cursor (formerly Claude Code), Python 3.10+

**Final deployment target:** Raspberry Pi 5 (8GB) + Hailo-8L AI Accelerator + Pi HQ Camera
(12MP IMX477) + 16mm C-mount lens, 300mm working distance (~100mm FOV), mounted on a
2020 aluminum gallows frame above a flicker-free LED light pad.

**Budget:** Under $1,000 total.

---

## 2. Four Technical Pillars

The full system has four capabilities. Each is a separate development track:

| Pillar | Status | Module |
|---|---|---|
| A. Motion-triggered capture (frame differencing) | ⏳ Not yet built | TBD — Phase 5+ |
| B. ID parsing (DataMatrix on blocks, QR on slides) | ✅ Built, unit-tested | `code/phase35_id_parsing.py` |
| C. Shape/constellation matching | ✅ Built, unit-tested; Phase 3 E2E wired | `code/phase2_descriptors.py`, `code/phase3_*.py`, `code/phase3_pipeline.py` |
| D. Stain verification (HSV color analysis) | ⏳ Not yet built | Phase 4 |

---

## 3. Operational Workflow

**Block enrollment phase:**
1. Technician holds block cassette with slanted edge facing camera → system reads DataMatrix
2. Technician flips block flat on backlight → system captures tissue silhouette
3. System stores `{block_id: contour_data}` in session database

**Slide verification phase:**
1. Technician places slide on backlight → system reads QR code
2. QR payload parsed: `WorkOrder_BlockID_Slide#_Stain`
3. BlockID looked up in session database
4. Shape comparison + stain verification run
5. Pass/flag decision → exception report

**Output:** CSV exception report (flagged mismatches only). Only problems surface; clean
matches are logged silently.

**Production task vs dev benchmark:** In deployment, the QR code on a slide names **one**
claimed block — the system verifies **match vs mismatch** (roughly 1-in-2), not open
retrieval across all blocks in a session. The current integration metric (**set-paired
top-3 among ~46 slides**) is a **stress test**, not the operational workflow. Low
retrieval TPR and a usable verification gate are **not contradictory**.

---

## 4. Phase Status

### Phase 1 — Segmentation Validation ✅ COMPLETE
- Otsu thresholding on backlit images. 11/17 PASS on phone images, 6 expected REVIEW.
- Key finding: lung samples segment cleanly; esophagus fragments are tiny and need special treatment.
- **Frozen functions (never modify signatures):** `segment_tissue()`, `extract_contours()` in `code/phase1_segmentation.py`

### Phase 2 — Shape Matching ✅ COMPLETE AND VALIDATED
- Hu moments + Zernike moments + geometric properties. Set-to-set matching via Hungarian algorithm.
- Integration test: 3/3 evaluable lung blocks ranked their correct slide in top-3 (100% TPR).
- Key calibration: `SOLIDITY_MAX` = 0.998 (lung paraffin is nearly convex; 0.95 dropped valid contours).
- Key finding: score separation only +0.012σ — ranking works, absolute thresholds do NOT.
- `set_01_slide` failed segmentation (tissue_fraction = 0.999, label dominated) → addressed in Phase 3.
- Esophagus matching weak as predicted → addressed in Phase 3.
- **Frozen functions (never modify signatures):** `clean_mask()`, `match_features_hungarian()`, all descriptor functions in `code/phase2_descriptors.py`

### Phase 3 — Constellation Matching + Label Detection + ID Parsing
**Sub-status:**
- ✅ All modules implemented; unit + geometry calibration tests (`test_phase3_geometry_calibration.py`, `test_phase3_router_constants.py`)
- ✅ `phase3_contour_profile.py` on `iphone_images/` (140 files, 94 measured); geometry k=2 calibration **exit 0**
- ✅ **Metrics-only router** — no filename tissue in routing; tissue tokens for TPR reporting only
- ✅ End-to-end: `phase3_pipeline.py` → 47×46 matrix; yellow-tag label mask wired (`set_01` still degenerate — re-shoot candidate)
- ✅ Option B closeout: `closeout_summary.md`, `ranking_failure_notes.md`; integration structural tests pass; 80% gate **xfail** by design
- ✅ **Signal gate v2** (2026-05-24): label-keyed gaps, verification metrics, segmentation audit, failure census, fragment probe — see `phase3_outputs/score_separation_report.md`
- ✅ **Fix 1b — structural cassette ROI** (2026-05-24): 2D paraffin mask + morph close + semantic validation; HSV fallback when Otsu crop fails; **14/47** blocks `roi_detection_ok` (honest, not 100%); audit PNGs in `phase3_outputs/roi_crop_audit/` — set_04 ROI now frames paraffin window
- 📋 **Fix 1c design v2** (brainstorm, not implemented): layered ROI — detection-based cassette (no primary central-% crop), grid/label on **opposite short ends**, **3** ROI geometry gates with `roi_fail_reason` logging, **Otsu-only** on blocks (reshoot if inadequate; no block HSV), pilot **≥7/10 visual** pass before 47-set regen. Spec: `docs/superpowers/specs/2026-05-24-block-capture-roi-design.md`; decisions: `phase3_outputs/mentor_questions.md`
- ⏳ Formal cycle: synthesizer → `proposed_plan.md` v1 → pre-mortem → plan v2 → implement Fix 1c
- ⏳ **Success bar:** functional verification **most of the time** on Pi captures — not mask perfection on full phone library
- ⏳ Mentor alignment optional; Zeke policy in `mentor_questions.md`

**47-set retrieval TPR (2026-05-24 post-refresh; stress-test metric):**

| Tissue | TPR | Notes |
|--------|-----|-------|
| lung (4) | 0% | small N |
| lungs (23) | 13% | 3/23 top-3 hits |
| esophagus (19) | 5.3% | `set_41` re-included in denominator |

**Signal gate verdict:** `GATE: SIGNAL_MISSING` — median gap **−0.305** (46 evaluable sets); 4.3% with gap &gt; 0. Provisional threshold 0.01 is Zeke’s working default, not mentor-approved. **Do not start Tier B** (z-score/router experiments) until gap distribution improves.

**Verification (QR-claimed match):** 2/46 pass (4.3%) — production-shaped 1-vs-K; reported beside retrieval TPR in `verification_metrics.md`. No fixed “production OK” pass rate; ~1/30 misses tolerable while improving accuracy.

**Strategic hypotheses (unvalidated):**
- Block silhouette (~340k px) vs slide section (~8k px) may be **different geometry**, not scale — boundary Hu/Zernike may be the wrong cross-modal feature class.
- Esophagus may be driven more by **fragment count** than constellation layout (test before heavy constellation tuning).
- **Segmentation mask quality** may cap all matchers (audit overlays before algorithm churn).
- Wrong top-1 may often be **same genotype + tissue** (biological siblings) — document as acceptable confound, not pure matcher failure.

**Router (geometry calibration):** k=2 on slide `(area, dominance)`; provenance-gated `router_constants.json`.

**Yellow-tag policy:** Only `YELLOW_TAG_SET_IDS` (set 1) → yellow; MT white PERMASLIDE slides in calibration pool.

**What is built:**

| Module | Purpose |
|---|---|
| `code/phase3_constellation.py` | 55-element canonical signature, no PCA, 90th-percentile normalization |
| `code/phase3_label_detection.py` | Rectangularity + aspect ratio + border edge density (NO uniformity criterion) |
| `code/phase3_router.py` | Hybrid routing + explicit `shape_partial` for 1-vs-N |
| `code/phase3_unified_matcher.py` | Per-branch z-score, routing_uncertain flag; passes tissue/role to router |
| `code/phase3_contour_profile.py` | Calibration script → CSV, histograms, notes, router_constants.json |
| `code/phase3_pipeline.py` | E2E cross-modal matrix via `unified_compare`, grouped by `set_NN` |
| `code/phase35_id_parsing.py` | DataMatrix + QR decoding with rotation/CLAHE fallback |
| `code/phase35_setup_check.py` | Pre-flight platform DLL verification (Windows/macOS/Linux) |

**Generated outputs (`phase3_outputs/`):**

| File | Purpose |
|---|---|
| `contour_profile.csv` | Per-image contour metrics + metadata |
| `calibration_histograms/*.png` | Distributions (including slide area + dominance) |
| `phase3_calibration_notes.md` | Human-readable threshold derivation |
| `router_constants.json` | Machine-readable constants for the router |

**Phase 3 closeout artifacts:** `closeout_summary.md`, `ranking_failure_notes.md`, `pipeline_run/cross_modal_similarity.csv`, `router_constants.json`.

**Active engineering plan:** `.cursor/specs/proposed_plan.md` — refresh for **Fix 1c** after design sign-off. Brainstorm (not the plan): `docs/superpowers/specs/2026-05-24-block-capture-roi-design.md`.

**Phase 4 entry:** Gated on signal-gate outcome **and** mentor criteria (retrieval vs verification). Do not treat 46-way top-3 TPR as the only pass/fail definition of “working.”

### Phase 4 — End-to-End Integration ⏳ NOT YET STARTED
Goals: HSV stain verification, two-phase batch workflow orchestration, exception report
generation, false-positive/false-negative analysis. See Section 10.

### Phases 5–7 — Hardware Integration ⏳ NOT YET STARTED
Motion detection, production camera, Pi deployment.

---

## 5. Frozen Interfaces — NEVER MODIFY THESE SIGNATURES

These function signatures are called by other modules. Changing them breaks the pipeline.
If you need to extend them, add a new function; do not change the existing one.

```python
# phase1_segmentation.py
def segment_tissue(bgr_image: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Returns (grayscale_inverted, binary_mask, otsu_threshold_value)."""

def extract_contours(binary_mask: np.ndarray, min_area: int) -> tuple[list, list]:
    """Returns (all_contours, filtered_contours_above_min_area)."""

# phase2_descriptors.py
def clean_mask(mask: np.ndarray, role: str) -> np.ndarray:
    """Role-aware mask cleanup. 'slide' gets label detection; 'block' does not."""

def match_features_hungarian(descriptors_a: list, descriptors_b: list) -> dict:
    """Set-to-set matching via Hungarian assignment. Returns match result dict."""
```

---

## 6. Key Technical Decisions (Do Not Revisit Without Strong Evidence)

| Decision | What Was Chosen | Why |
|---|---|---|
| Constellation representation | Single 55-element padded vector: sorted pairwise centroid distances (45) + sorted area ratios (10) | Pre-mortem ruled out PCA (unstable for symmetric esophagus arrangements) and dual representation (incomparable score scales). Single canonical form, single L2 metric. |
| Rotation invariance | Intrinsic via sorted pairwise distances — NO PCA | Pairwise distances are rotation-invariant by construction; PCA has sign/axis ambiguity on symmetric point clouds. |
| Mirror invariance | Accepted as desired behavior | Slides physically flip during mounting; mirrored arrangements are legitimate matches. |
| Normalization reference | 90th-percentile distance (not max) | Max is an extreme-value statistic vulnerable to a single spurious contour; 90th-percentile is robust. |
| Label detection criterion | Rectangularity + aspect ratio + Canny border edge density | Uniformity criterion was BACKWARDS — real labels have HIGH interior variance from printed barcodes/text. |
| Router strategy | Hard switch (not soft blend) | Mixing scores from algorithms measuring different things on different scales makes debugging impossible. |
| 1-vs-N routing | Explicit `shape_partial` branch with `routing_uncertain` flag | Silent partial alignment was flagged as a defect in pre-mortem. |
| Score combination | Per-row ranking within a single routing branch only | Absolute cross-branch scores are not comparable. Phase 2's tiny score separation (+0.012σ) confirmed ranking is the only valid approach. |
| Stain verification | Deferred to Phase 4 | Secondary failure mode catcher; not core to shape matching. |
| False-positive safety | System should err toward flagging uncertainty rather than passing a mismatch | A missed mismatch (false negative) is more dangerous than a false alarm in histology. |
| Block ROI (Fix 1c) | Detection-based cassette; grid/label opposite ends; 3 geometry gates; Otsu-only blocks; geometric inset last resort flagged | Avoid fixed central-% crop and stacked AND gates that reject good frames; HSV weak on unstained silhouettes |
| Fix 1c pilot gate | ≥7/10 visual audit on named pilot sets vs Fix 1b baseline | Do not use verification/gap to judge ROI pilot; regen 47 only after pilot passes |

---

## 7. Dataset

**Location:** `phase1_dataset/` (phone images, 23 matched sets)

**Filename convention:**
```
set_NN_<role>_<subtype>_<tissue>_<stain>_<genotype>_<workorder>.<ext>
```

**Role tokens:** `block_silhouette`, `block_barcode`, `slide`
**Tissue:** `lung`, `esophagus`
**Stain:** `HE`, `MT`, `PAS`, `PSRFG` (blocks carry the paired slide's stain as metadata)
**Genotype:** `WT`, `TWKO`, `NAIVE`, `N1`, `N2` (no internal underscore — use `TWKO1` not `TWKO_1`)
**Work order:** e.g., `WO7842`

**Pairing ground truth:** Set number is the canonical link. `set_20_block_*` matches `set_20_slide_*`.
Dataset currently has NO deliberate mismatches — integration test measures ranking only.
False-positive testing moves to Phase 4.

**Known exceptions:**
- **Set 1** — yellow-tag slide (different slide type: APEX SAS label vs. white PERMASLIDE Plus).
  Has no `block_barcode` image and no work-order token in the filename.
  Label detection must be validated against yellow-tag labels separately.
  Only one yellow-tag set exists; more recommended before Phase 4.
- All other sets: white-tag PERMASLIDE Plus slides, 8-token filenames.

**Tissue types observed:**
- Lung: large, complex multi-lobe morphology, excellent backlight contrast. Shape matching works well.
- Esophagus biopsies: tiny fragments (2–3 mm, 3–4 dots per block). Shape matching fails; constellation matching required.

---

## 8. Engineering Rules (From CLAUDE.md / Cursor Rules)

**TDD — refined rule:**
- Mandatory for any function that is called by another function (has dependents). Tests written BEFORE implementation.
- Optional for leaf functions that only produce human-readable output (visualizations, diagnostic PNGs, CSVs for human review).
- Promotion rule: if a leaf function gains logic or is later called by another function, it is immediately promoted to core and requires tests retroactively.

**Pre-mortem before implementation:**
- Every phase plan is audited by an adversarial pre-mortem before Claude Code writes any code.
- Pre-mortem runs in a fresh chat (to avoid anchoring on its own plan).
- Critical blockers from pre-mortem MUST be resolved in a v2 plan before implementation starts.

**Calibration before threshold-locking:**
- Router thresholds and configurable constants must be derived from measured data, not guesses.
- Calibration script runs first; thresholds are documented in calibration notes with the data they came from.

**Recall from Phase 2 testing:**
- The "1 - avg_cost/5.0" similarity mapping was caught and fixed during TDD. Always use bounded `1/(1+d)` mapping.
- Absolute thresholds do not work; validate with ranking tests only.
- Test pairing correctness (did Hungarian pick the right pairs?), not absolute score magnitude.

**Memory and visualization:**
- Always `plt.close(fig)` after `fig.savefig()`. Memory leak otherwise (confirmed Phase 1).
- Always `cv2.cvtColor(img, cv2.COLOR_BGR2RGB)` before passing color images to matplotlib. Silent channel swap otherwise (confirmed Phase 1).
- Always create output directories with `parents=True, exist_ok=True` at the top of `main()`.

**Code style (Zeke is learning Python from Java):**
- Type hints on all function signatures.
- Docstrings on every function with purpose, params, returns.
- Descriptive variable names; no single-letter variables except loop counters.
- Comment non-obvious OpenCV calls explaining what they do and why.
- No clever one-liners; favor readability.

---

## 9. File Structure

```
LJI_blockcheck/
├── .cursor/
│   └── rules/
│       ├── project-conventions.md      # TDD, frozen interfaces, code style
│       └── planning-workflow.md        # Session-synthesizer + pre-mortem templates
├── docs/
│   ├── PROJECT_CONTEXT.md              # ← This file
│   ├── proposed_plan.md                # Current phase plan (overwritten each phase)
│   └── pre_mortem.md                   # Current phase audit (overwritten each phase)
├── .claude/
│   └── specs/
│       └── proposed_plan.md            # Claude Code backward compatibility copy
├── CLAUDE.md                           # Claude Code behavioral rules
├── code/
│   ├── phase1_segmentation.py          # FROZEN
│   ├── phase2_descriptors.py           # FROZEN
│   ├── phase3_constellation.py
│   ├── phase3_label_detection.py
│   ├── phase3_router.py
│   ├── phase3_unified_matcher.py
│   ├── phase35_id_parsing.py
│   ├── phase35_setup_check.py
│   └── phase3_contour_profile.py       # Calibration script
├── tests/
│   ├── conftest.py                     # Pytest fixtures (synthetic images)
│   ├── test_phase1.py                  # MUST ALWAYS PASS (regression)
│   ├── test_phase2.py                  # MUST ALWAYS PASS (regression)
│   ├── test_phase3.py
│   ├── test_phase3_contour_profile.py
│   ├── test_phase35_id_parsing.py
│   └── integration/
│       └── test_cross_modal_ranking.py # Gated — run explicitly only
├── pytest.ini                          # Excludes tests/integration/ from default run
├── requirements.txt
├── iphone_images/                      # 23 matched iPhone image sets (gitignored JPEGs)
├── phase1_outputs/
├── phase2_outputs/
│   ├── descriptors.csv
│   ├── cross_modal_similarity.csv
│   └── visualizations/
├── phase2_calibration_notes.md         # Tuned values: SOLIDITY_MAX=0.998, etc.
└── phase3_outputs/                     # Created by calibration script
    ├── contour_profile.csv
    ├── calibration_histograms/
    ├── phase3_calibration_notes.md
    └── router_constants.json
```

---

## 10. What Comes Next

### Immediate — Post signal gate (SIGNAL_MISSING)

**Completed (plan v2):** pipeline refresh (47 sets), score-gap report + histograms, verification metrics, segmentation audit overlays (`phase3_outputs/segmentation_audit/`), ranking failure census with genotype confound, esophagus fragment-count probe.

**Next (signal / data, not router tuning):**
1. Human REVIEW of segmentation audit overlays (`segmentation_audit/review.csv`).
2. Pi rig / re-shoot candidates (`set_01` slide ceiling; any flagged masks).
3. Feature-class experiments if masks look OK (block vs slide geometry hypothesis).
4. Mentor email: median gaps, verification 4.3% vs retrieval 13% lungs — ask for data-driven gap cutoff.

**Defer until median gap ≥ 0.01 (provisional):** z-scored matrix ranking, asymmetric router experiments, Tier C matcher work.

### Phase 4 — End-to-End Integration (gated)

Goals:
- **HSV stain verification** — confirm slide color matches QR-claimed stain type (HE=pink/purple, MT=blue)
- **Two-phase batch orchestrator** — block enrollment pass then slide verification pass as single entry point
- **Exception report generation** — CSV with work order, block ID, slide number, ID match, shape score, routing branch, stain validity; flagged exceptions only
- **False-positive testing** — add deliberate mismatch image pairs to dataset; measure how often system wrongly passes a bad pair

---

## 11. Dependencies Reference

| Library | Purpose | Version |
|---|---|---|
| opencv-python | Core CV: segmentation, contours, label detection | >=4.5 |
| numpy | Array operations | >=1.24 |
| scipy | Hungarian assignment | >=1.12 (hard pin) |
| pandas | CSV I/O, grouping | >=2.0 |
| matplotlib | Diagnostic visualizations | >=3.7 |
| mahotas | Zernike moments | >=1.4 |
| pylibdmtx | DataMatrix decoding | >=0.1.10 + system DLL |
| pyzbar | QR decoding | >=0.1.9 + system DLL |
| pytest | Test runner | >=7.4 |
| pytest-mock | Mocking in tests | >=3.10 |

**Windows DLL note:** `pylibdmtx` and `pyzbar` require system libraries not installed by pip.
Run `python code/phase35_setup_check.py` first — it prints platform-specific install steps
if the imports fail.

---

## 12. Commands Reference

```bash
# Standard test run (all phases, no integration)
pytest tests/ -v

# Integration test against real dataset (run explicitly after calibration)
pytest tests/integration/ -v

# Full run including integration
pytest tests/ tests/integration/ -v

# Run calibration script (produces contour_profile.csv and phase3_calibration_notes.md)
python code/phase3_contour_profile.py

# Verify Windows DLL setup for barcode reading
python code/phase35_setup_check.py

# Lint check
flake8 code/ tests/
```

---

## 13. Things That Must Not Be Redone or Forgotten

- **Do not modify Phase 1 or Phase 2 frozen function signatures.** Other code depends on them.
- **Do not use PCA for rotation invariance.** Pre-mortem ruled this out — unstable for symmetric arrangements.
- **Do not use uniformity as a label-detection criterion.** Real labels have HIGH variance (printed barcodes/text).
- **Do not use EMD (scipy.stats.wasserstein_distance).** Eliminated in Phase 3 v2. Single L2 metric throughout.
- **Do not use absolute similarity thresholds for pass/fail.** Score separation is +0.012σ — ranking only.
- **Do not set router thresholds before running the calibration script.** Thresholds from data, not guesses.
- **Do not skip the pre-mortem step.** Both Phase 1 and Phase 3 pre-mortems caught real bugs before implementation.
- **Do not run integration tests by default.** `pytest.ini` excludes `tests/integration/` intentionally.
- **Do not forget BGR→RGB conversion before matplotlib.** Silent wrong colors (Phase 1 regression).
- **Do not forget `plt.close(fig)` after `fig.savefig()`.** Memory leak (Phase 1 regression).
- **Do not move to Phase 4 until signal gate + mentor criteria are met.** High retrieval TPR is not the same as production verification.
- **Do not invest in router/threshold tuning before score-gap histograms.** Gap &lt; ~0.01 means optimize data/features, not ranking.
- **Dataset has no deliberate mismatches yet.** False-positive testing moves to Phase 4.
- **Set 1 is a yellow-tag slide (APEX SAS).** Different label type; report its metrics separately from white-tag sets.
