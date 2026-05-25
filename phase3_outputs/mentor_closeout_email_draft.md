# Draft email to Zbigniew (signal gate v2)

**Subject:** Phase 3 signal gate — verification vs retrieval

Hi Zbigniew,

Phase 3 pipeline is refreshed on the **47-set** library (WO7842 filenames, `set_41` back in TPR). Closeout TPR is in `phase3_outputs/closeout_summary.md`.

**Stress-test retrieval (46-way top-3):**

| Tissue | TPR |
|--------|-----|
| lung (4) | 0% |
| lungs (23) | 13% |
| esophagus (19) | 5.3% |

**Production-shaped verification** (claimed block must beat all wrong slides): **2/46 pass (4.3%)**. Same matrix as retrieval; low rates are consistent, not contradictory. Details: `phase3_outputs/verification_metrics.md`.

**Score separation (ranking vs signal):** Median gap (correct − best wrong) = **−0.305** on `raw_similarity`. Automated gate: **SIGNAL_MISSING** at provisional cutoff 0.01 (my working default, not lab-approved). Full distribution + sensitivity table: `phase3_outputs/score_separation_report.md`.

**Questions for you:**

1. For production, is **verification pass rate** the right success metric (QR names one block), rather than 46-way top-3 TPR? We are not claiming a fixed pass-rate bar yet.
2. What **gap cutoff** (or data-driven rule) would you use to decide ranking tweaks are worth trying vs new imaging/features?
3. OK to start **Phase 4 (HSV stain)** in parallel while shape signal is weak, or should we block on separation?

**Data notes:** `set_01` slide still zero contours after label mask (re-shoot candidate). Segmentation audit overlays: `phase3_outputs/segmentation_audit/`.

Thanks,  
Zeke
