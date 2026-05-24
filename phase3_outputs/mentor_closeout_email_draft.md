# Draft email to Zbigniew (Step 1 — mentor gate)

**Subject:** Phase 3 closeout numbers (Option B) — parallel Phase 4?

Hi Zbigniew,

Phase 3 pipeline is wired end-to-end on the 47-set iPhone library with **metrics-only routing** (no filename tissue in the router). Closeout summary is attached / at `phase3_outputs/closeout_summary.md`.

**Set-paired top-3 TPR (Phase 3):**

| Tissue | TPR |
|--------|-----|
| lung (4 sets) | 0% |
| lungs (23 sets) | 13% |
| esophagus (18 sets, set_41 excluded pending WO check) | 5.6% |

We are keeping the **80% integration gate as xfail** (Option B) until you sign off — not claiming a pass.

**Calibration:** Geometry k=2 on slide area/dominance produced calibrated thresholds (`router_constants.json`, status `calibrated`). If overlap returns on a future library, the system writes an `overlap_unresolved` stub and falls back to module defaults.

**Questions for you:**

1. Is it acceptable to start **Phase 4 (HSV stain verification)** in parallel while ranking is below 80%, or should ranking work block Phase 4?
2. If calibration cannot separate slide metrics on a future dataset, is **documented default constants + overlap flagging** acceptable for stain-only Phase 4 work that does not depend on routing branch?

**Data notes:** `set_01` yellow-tag slide still yields zero contours after label masking (may need re-shoot). `set_41` excluded from TPR until we confirm WO7842 vs WO7482 pairing with the lab.

Thanks,  
Zeke
