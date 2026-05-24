# Phase 3 closeout summary (Option B — measurement)

Closeout policy: **Option B** — documented TPR; 80% mentor gate remains xfail in integration tests until sign-off.

Images: `C:\Users\zekes\lji_blockcheck\iphone_images`
Matrix shape: 47 blocks × 46 slides

## Set-paired top-3 TPR (Phase 3)

| Tissue token | Hits | Total | TPR |
|--------------|------|-------|-----|
| lung | 0 | 4 | 0.0% |
| lungs | 3 | 23 | 13.0% |
| esophagus | 1 | 18 | 5.6% |

## Notes

- Sets with zero post-clean contours are excluded when absent from the matrix.
- `lung` and `lungs` are reported separately.
- Yellow-tag slides: APEX SAS adhesive (set 1 only); label mask before segmentation.
- **TPR excluded sets** (metadata warning): set_41 (work-order mismatch pending lab confirmation).
