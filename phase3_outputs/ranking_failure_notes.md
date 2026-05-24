# Phase 3 ranking failure notes

Generated from pipeline_run after plan v2 implementation.

Router source: geometry_k2 calibrated JSON (208044 px / 0.912 dominance).
set_01 slide excluded from matrix (zero contours after label mask).
set_41 excluded from TPR denominator (work-order mismatch).

## lung

| set | result | routing (paired compare) | failure class |
|-----|--------|--------------------------|---------------|
| set_21 | miss | shape | wrong_score | top1=set_42 |
| set_22 | miss | shape | wrong_score | top1=set_19 |
| set_29 | miss | shape | wrong_score | top1=set_19 |

## lungs

| set | result | routing (paired compare) | failure class |
|-----|--------|--------------------------|---------------|
| set_06 | hit | shape | — |
| set_13 | hit | constellation | — |
| set_19 | hit | constellation | — |
| set_02 | miss | shape | wrong_score | top1=set_14 |
| set_05 | miss | shape | wrong_score | top1=set_31 |
| set_08 | miss | shape | wrong_score | top1=set_19 |

## esophagus

| set | result | routing (paired compare) | failure class |
|-----|--------|--------------------------|---------------|
| set_42 | hit | constellation | — |
| set_03 | miss | constellation | wrong_score | top1=set_42 |
| set_04 | miss | shape | wrong_score | top1=set_13 |
| set_07 | miss | shape | wrong_score | top1=set_42 |
