# Fragment count probe (esophagus)

Hypothesis: block vs slide `contour_count` delta may explain esophagus hits.

**Note:** Compare hit vs miss delta distributions below.

- Esophagus evaluable rows: 19
- Mean |delta| hits: 0.0
- Mean |delta| misses: 1.2

| set | block_count | slide_count | |delta| | top3 | gap |
|-----|-------------|-------------|--------|------|-----|
| set_03 | 3 | 4 | 1 | miss | -0.030 |
| set_04 | 3 | 7 | 4 | miss | -0.332 |
| set_07 | 3 | 2 | 1 | miss | -0.305 |
| set_09 | 2 | 2 | 0 | miss | -0.775 |
| set_10 | 3 | 4 | 1 | miss | -0.074 |
| set_11 | 3 | 4 | 1 | miss | -0.096 |
| set_12 | 3 | 4 | 1 | miss | -0.070 |
| set_23 | 3 | 4 | 1 | miss | -0.257 |
| set_24 | 3 | 1 | 2 | miss | -0.396 |
| set_25 | 3 | 3 | 0 | miss | -0.326 |
| set_26 | 2 | 4 | 2 | miss | -0.569 |
| set_27 | 3 | 1 | 2 | miss | -0.310 |
| set_28 | 3 | 2 | 1 | miss | -0.337 |
| set_40 | 2 | 1 | 1 | miss | -0.774 |
| set_41 | 3 | 3 | 0 | miss | -0.301 |
| set_42 | 2 | 2 | 0 | hit | -0.101 |
| set_43 | 2 | 2 | 0 | miss | -0.270 |
| set_44 | 2 | 1 | 1 | miss | -0.849 |
| set_45 | 5 | 2 | 3 | miss | -0.319 |

## Interpretation

Contour counts use different `clean_mask` roles for block vs slide; large delta may reflect protocol rather than mismatch. Do not treat count alone as 80% signal without mentor validation.
