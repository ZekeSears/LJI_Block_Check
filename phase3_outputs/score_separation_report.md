# Score separation report (Phase 3 signal gate)

## Provenance

- Matrix: `C:\Users\zekes\lji_blockcheck\phase3_outputs\pipeline_run\cross_modal_similarity.csv`
- Matrix mtime: 2026-05-24 14:30 UTC
- Shape: 43 blocks × 46 slides
- Images: `C:\Users\zekes\lji_blockcheck\iphone_images`
- Sets scanned (audit): 47
- Evaluable sets (label-keyed gaps): 42
- Gate threshold (provisional): **0.01** on `raw_similarity`

## Retrieval TPR (stress test; from closeout)

| lung | 0 | 4 | 0.0% |
| lungs | 3 | 23 | 13.0% |
| esophagus | 1 | 19 | 5.3% |

## Global gap statistics

| Metric | Value |
|--------|-------|
| Median gap | -0.2704 |
| p10 | -0.7485 |
| p50 | -0.2704 |
| p90 | -0.0273 |
| % sets with gap > 0 | 4.8% |

## Gate verdict

**GATE: SIGNAL_MISSING**

> 0.01 is Zeke's working default for automation, not mentor-approved. Current library is expected to show SIGNAL_MISSING until signal improves. Mentor may choose a data-driven cutoff from the sensitivity table below.

## Sensitivity (fraction of sets with gap ≥ threshold)

| Threshold | Fraction ≥ |
|-----------|------------|
| 0.00 | 4.8% |
| 0.01 | 2.4% |
| 0.05 | 0.0% |

## Per-tissue gap statistics

### esophagus (n=15)

- Median gap: -0.3171
- p10 / p50 / p90: -0.7687 / -0.3171 / -0.0850
- % gap > 0: 0.0%

### lung (n=4)

- Median gap: -0.2303
- p10 / p50 / p90: -0.3124 / -0.2303 / -0.1285
- % gap > 0: 0.0%

### lungs (n=23)

- Median gap: -0.2107
- p10 / p50 / p90: -0.5394 / -0.2107 / -0.0048
- % gap > 0: 8.7%

## Histograms

- `C:\Users\zekes\lji_blockcheck\phase3_outputs\calibration_histograms\score_gap_by_tissue.png`
- `C:\Users\zekes\lji_blockcheck\phase3_outputs\calibration_histograms\correct_vs_wrong_score_scatter.png`
