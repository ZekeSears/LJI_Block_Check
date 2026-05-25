# Phase 3 ranking failure notes

Generated from pipeline_run after plan v2 implementation (label-keyed gaps).

Router source: geometry_k2 calibrated JSON (see router_constants.json).
set_01 slide excluded from matrix (zero contours after label mask).
set_41 included in TPR denominator (plan v2 re-inclusion).

## esophagus

| set | result | gap | routing (correct pair) | routing (wrong top1) | same genotype | failure class | top1 |
|-----|--------|-----|--------------------------|----------------------|---------------|---------------|------|
| set_03 | miss | -0.030 | constellation | constellation | no | wrong_score | top1=set_42 |
| set_04 | miss | -0.332 | shape | constellation | no | wrong_score | top1=set_13 |
| set_07 | miss | -0.305 | shape | constellation | no | wrong_score | top1=set_42 |
| set_09 | miss | -0.775 | shape | constellation | no | wrong_score | top1=set_13 |
| set_10 | miss | -0.074 | constellation | constellation | no | wrong_score | top1=set_42 |
| set_11 | miss | -0.096 | constellation | constellation | no | wrong_score | top1=set_42 |
| set_12 | miss | -0.070 | constellation | constellation | no | wrong_score | top1=set_42 |
| set_23 | miss | -0.257 | shape | constellation | no | wrong_score | top1=set_42 |
| set_24 | miss | -0.396 | shape_partial | constellation | no | wrong_score | top1=set_42 |
| set_25 | miss | -0.326 | shape | constellation | no | wrong_score | top1=set_42 |
| set_26 | miss | -0.569 | constellation | constellation | no | wrong_score | top1=set_13 |
| set_27 | miss | -0.310 | shape_partial | constellation | no | wrong_score | top1=set_42 |
| set_28 | miss | -0.337 | shape | constellation | no | wrong_score | top1=set_13 |
| set_40 | miss | -0.774 | shape_partial | constellation | yes | wrong_score | top1=set_14 |
| set_41 | miss | -0.301 | shape | constellation | no | wrong_score | top1=set_42 |
| set_42 | hit | -0.101 | constellation | constellation | no | — | top1=set_19 |
| set_43 | miss | -0.270 | constellation | constellation | no | wrong_score | top1=set_19 |
| set_44 | miss | -0.849 | shape_partial | constellation | yes | wrong_score | top1=set_13 |
| set_45 | miss | -0.319 | shape | constellation | no | wrong_score | top1=set_38 |

## lung

| set | result | gap | routing (correct pair) | routing (wrong top1) | same genotype | failure class | top1 |
|-----|--------|-----|--------------------------|----------------------|---------------|---------------|------|
| set_21 | miss | -0.305 | shape | constellation | no | wrong_score | top1=set_42 |
| set_22 | miss | -0.328 | shape | constellation | no | wrong_score | top1=set_19 |
| set_29 | miss | -0.311 | shape | constellation | no | wrong_score | top1=set_19 |
| set_30 | miss | -0.321 | shape | constellation | no | wrong_score | top1=set_42 |

## lungs

| set | result | gap | routing (correct pair) | routing (wrong top1) | same genotype | failure class | top1 |
|-----|--------|-----|--------------------------|----------------------|---------------|---------------|------|
| set_02 | miss | -0.824 | shape | constellation | no | wrong_score | top1=set_14 |
| set_05 | miss | -0.543 | shape | constellation | no | wrong_score | top1=set_31 |
| set_06 | hit | 0.002 | shape | shape | no | — | top1=set_16 |
| set_08 | miss | -0.281 | shape | constellation | no | wrong_score | top1=set_19 |
| set_13 | hit | 0.024 | constellation | constellation | no | — | top1=set_19 |
| set_14 | miss | -0.014 | constellation | constellation | no | wrong_score | top1=set_19 |
| set_15 | miss | -0.302 | shape | constellation | no | wrong_score | top1=set_19 |
| set_16 | miss | -0.324 | shape_partial | constellation | no | wrong_score | top1=set_19 |
| set_17 | miss | -0.210 | constellation | constellation | no | wrong_score | top1=set_42 |
| set_18 | miss | -0.266 | shape | constellation | no | wrong_score | top1=set_42 |
| set_19 | hit | -0.002 | constellation | constellation | no | — | top1=set_42 |
| set_20 | miss | -0.614 | shape_partial | constellation | no | wrong_score | top1=set_33 |
| set_31 | miss | -0.041 | shape_partial | shape | yes | wrong_score | top1=set_06 |
| set_32 | miss | -0.534 | constellation | constellation | no | wrong_score | top1=set_31 |
| set_33 | miss | -0.712 | constellation | constellation | no | wrong_score | top1=set_14 |
| set_34 | miss | -0.562 | shape | constellation | no | wrong_score | top1=set_33 |
| set_35 | miss | -0.290 | shape | constellation | no | wrong_score | top1=set_42 |
| set_36 | miss | -0.044 | constellation | constellation | no | wrong_score | top1=set_42 |
| set_37 | miss | -0.211 | constellation | constellation | no | wrong_score | top1=set_42 |
| set_38 | miss | -0.155 | constellation | constellation | no | wrong_score | top1=set_19 |
| set_39 | miss | -0.026 | constellation | constellation | no | wrong_score | top1=set_19 |
| set_46 | miss | -0.824 | constellation | constellation | no | wrong_score | top1=set_43 |
| set_47 | miss | -0.801 | shape | constellation | no | wrong_score | top1=set_42 |
