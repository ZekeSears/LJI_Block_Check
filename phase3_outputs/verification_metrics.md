# Verification metrics (QR-claimed match detection)

Production-shaped check: for each evaluable set, does the claimed block–slide pair score higher than every other slide in the matrix?

> There is **no fixed pass-rate bar** for production OK. Report rates beside retrieval TPR; ~1/30 misses may be acceptable while accuracy is improved.

- Matrix: `C:\Users\zekes\lji_blockcheck\phase3_outputs\pipeline_run\cross_modal_similarity.csv`
- Routing log: `C:\Users\zekes\lji_blockcheck\phase3_outputs\pipeline_run\routing_log.csv`

## Global verification

| Metric | Value |
|--------|-------|
| Passes | 2 / 42 |
| Pass rate | 4.8% |
| Mean gap | -0.2918 |

## Retrieval TPR (46-way stress test)

From latest closeout summary:

| Tissue token | Hits | Total | TPR |
|--------------|------|-------|-----|
| lung | 0 | 4 | 0.0% |
| lungs | 3 | 23 | 13.0% |
| esophagus | 1 | 19 | 5.3% |

## Per-tissue verification

- **esophagus**: 0/15 pass (0.0%), mean gap -0.3716
- **lung**: 0/4 pass (0.0%), mean gap -0.2233
- **lungs**: 2/23 pass (8.7%), mean gap -0.2516

### Routing branch on correct pair

**Passes:**
- shape: 2

**Fails:**
- constellation: 15
- shape: 16
- shape_partial: 9
