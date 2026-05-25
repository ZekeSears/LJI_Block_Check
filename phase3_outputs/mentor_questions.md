# Mentor & project decisions — LJI blockcheck (consolidated)

**For:** Zbigniew (supervisor) — optional review  
**Owner:** Zeke  
**Last updated:** 2026-05-24  
**Purpose:** Single place for open questions, recorded answers, and policy decisions. Many items below are **Zeke’s working decisions** when mentor input is unavailable; update when the lab responds.

Related: [mentor_closeout_email_draft.md](mentor_closeout_email_draft.md) (signal gate v2), [.cursor/specs/pre_mortem.md](../.cursor/specs/pre_mortem.md) §7.

---

## Zeke’s decisions (current policy)

### Imaging / Pi rig

| Topic | Decision |
|--------|----------|
| **Framing** | Usually **fill the frame**; white backlight border often **not visible**. Pipeline should work **with or without** a border — detect border if present, else use in-cassette geometry. |
| **Failed auto-crop** | Prefer **automatic re-shoot**, not silent full-frame segmentation. Long-term: **motion-triggered capture** (hand in → wait → hand out → settle → snap). Manual ROI rectangle only as **last resort**; re-shoot is simpler. |
| **Camera pose** | **Fixed overhead**; blocks may be placed in **any orientation** (180° rotation possible). |
| **FOV / lens** | Ordered for ~100 mm FOV per project description; **validate when Pi + camera arrive**. |
| **Exposure** | Assume **fixed exposure** unless Pi testing shows otherwise; open to change. |
| **Vignetting** | *Darkening toward image corners* from lens/light pad — can look like false edges; watch for on Pi captures. |

### Cassette / ROI / segmentation

| Topic | Decision |
|--------|----------|
| **Grid band** | Same end relative to **barcode on cassette**, but barcode **not always visible from top** (scanned in separate ID step). |
| **Block cassettes** | **White only** (as far as known). |
| **Slides / labels** | Yellow-tag slides: **mask label rectangle** same idea as white-tag; geometry, not stain color. |
| **Mask quality target** | Aim **100%**; acceptable to proceed after **~80%** while Pi access pending; keep improving. |
| **Border detection** | Worth implementing: **test if white border exists** and branch logic — low cost, improves robustness. |
| **Regeneration after ROI fix** | Re-run **~10 representative sets** first; if same failure mode, full 47-set regen has little value. |
| **Set 01 slide** | **Exclude** from slide metrics for now (zero contours after label mask). |
| **Benchmark library** | Current 47-set phone library is **not fully representative**; **prioritize new Pi captures** when available. |

### Metrics / phases

| Topic | Decision |
|--------|----------|
| **Production metric** | **Verification** (QR names one block; beat wrong slides) over 46-way retrieval TPR. |
| **Verification rate** | No fixed % bar yet; **maximize accuracy** before Phase 4; iterate. |
| **Score gap cutoff** | **Do not assume 0.01** as lab truth — iterate from data after masks are fixed. |
| **Phase 4 (HSV stain)** | **Fix block masks first**; Phase 4 in parallel has **little benefit** if shape input is still cassette plastic. Stain path should still **exclude label** like slides. |
| **Deliberate mismatches** | Timing **TBD** (false-positive testing). |

---

## Open questions for mentor (if available)

### A. Pi rig, camera, and framing

1. For Pi deployment, is **fill-frame** capture acceptable, or should we enforce a minimum white margin?
2. Confirm **fixed exposure** vs auto-exposure for wax/tissue stability.
3. Any expected **vignetting** or edge artifacts from the chosen lens + pad?

### B. Cassette geometry and ROI

4. Confirm grid band is always on the **barcode end** of the cassette (even when barcode not visible from top).
5. Preferred **mentor sign-off** rule: 80% vs 100% of block silhouettes on audit PNGs?
6. When auto ROI fails, exclude those sets from **signal-gap** stats or keep them (pessimistic)?

### C. Yellow vs white

7. Any production **yellow block** cassettes? (Zeke assumes white only.)
8. Phase 4: does yellow sticker material affect **HSV stain** thresholds on slides?

### D. Metrics and phase order

9. Agree **verification** is the primary production metric vs retrieval TPR?
10. Data-driven rule for **score gap** before investing in router tuning?
11. OK to gate Phase 4 on **block mask quality** from Pi sample batch?

### E. Data

12. Confirm **set_01 slide** re-shoot vs exclude from benchmarks.
13. When to add **deliberate mismatch** pairs to the test library?

---

## Prior email thread (signal gate v2) — still relevant

From [mentor_closeout_email_draft.md](mentor_closeout_email_draft.md):

1. Verification pass rate vs 46-way top-3 TPR for production success?
2. What gap cutoff (or data-driven rule) for ranking tweaks vs new features?
3. Phase 4 in parallel while shape signal weak, or blocked?

Zeke’s current answers: verification primary (#15 above); gap must be iterated, not 0.01; **block masks first**, Phase 4 parallel low value until masks fixed.

---

## Pre-mortem §7 items (ROI Fix 1) — status

| Item | Status |
|------|--------|
| Visual pass threshold | Zeke: aim 100%, proceed ~80% until Pi |
| Close-frame fallback in gap stats | **Open** for mentor; default: report **roi_ok** and **roi_failed** cohorts separately |
| Grid orientation | Zeke: same end as barcode; algorithm must handle **rotation** |
| Full artifact regeneration | Zeke: **10-set pilot** first, then full regen if improved |

---

## Glossary (plain language)

- **Verification:** Slide QR says “this block”; software checks that block scores higher than every other slide in the session (production-shaped).
- **Retrieval TPR:** Harder stress test — correct slide in top 3 among ~46 slides (not how the bench works day-to-day).
- **Score gap:** How much higher the true match scores than the best wrong match (negative = wrong slide wins).
- **roi_detection_ok:** Software found a trustworthy paraffin-window crop before Otsu/HSV.
- **Vignetting:** Corners of photo darker than center — can confuse edge detection.

---

## Design v2 notes (2026-05-24)

- **Not perfection:** masks good enough for verification **most of the time** on Pi captures.
- **No primary central-% crop;** geometric inset last resort + `cassette_method` logged.
- **3 ROI gates** + `roi_fail_reason`; no block HSV — reshoot if Otsu inadequate.
- **Grid/label:** opposite short ends (rotation-aware).
- **Pilot:** ≥7/10 visual on 10 named sets before full regen.

Full spec: [docs/superpowers/specs/2026-05-24-block-capture-roi-design.md](../docs/superpowers/specs/2026-05-24-block-capture-roi-design.md)

## Next engineering doc

Brainstorm → synthesizer → `proposed_plan.md` v1 → pre-mortem → plan v2 → implement (this file is **not** the plan).
