# Independent checks of the monthly-band gain (7 Nov 2026)

Four audits ran in parallel, each followed by a skeptic that re-ran the evidence and tried to refute it. Scripts and logs
are in the session scratchpad (`audit2/<lens>/`). Folds 1-4 of `s1_cc2km` only; fold 0 was never scored. Read with
`README.md` (the ladder) in this folder.

## 1. Reproduction: the numbers are right

- Two independent rebuilds (no shared code with `time_features.py`) match A1, the GCVI peak, M2 and M2-pre in Lacuna,
  Malawi 2022, Kenya and Malawi 2023 to about 1e-15.
- Model rows equal `load_xy`; no group in two folds; fold 0 never scored; clipping and scaling are fit on training rows
  only (scaling the other test rows by 1,000 changes no prediction); gap-filling uses only the field's own months
  (7-10 % of cells filled).
- Caveat: "pre-harvest" is a calendar rule. 11 % of the clear photos in the Lacuna and Kenya pre-harvest window are after
  the field's cut date (Malawi: 0 %).

## 2. Leakage and where the gain comes from

No leak: the minimum distance between folds is at least 2.003 km, no coordinates appear in two folds, and neither the
cloud pattern nor `months_with_data` predicts yield. But the gain of the monthly band curve (M2) over A1 is not clean
field-level crop signal in any cohort:

| Cohort | Reading | Key numbers |
|---|---|---|
| Lacuna | real, but at village level | 86 % of the error reduction is between villages; R2 between 0.30 -> 0.50, within 0.055 -> 0.096 (gain not significant); new regions +0.087 (CI -0.029 to +0.169); photos before the cut only: R2 0.310 (full 0.322); red-edge bands alone give most of the gain |
| Malawi 2022 | signal + place + post-cut photos | pre-cut M2-pre vs pre-cut A1: +0.093 on s1 (CI +0.021 to +0.162), +0.081 on new regions (CI -0.011 to +0.177); the rank gain inside villages needs the May-June photos after the cut |
| Malawi 2023 | no signal beyond A1 | M2 overfits (70 features, 253 fields): R2 0.084 vs A1 0.154, also worse in new regions |
| Kenya | place + harvest timing | the cut date alone gives R2 0.124 (M2 0.134); M2 predicts the cut date with R2 0.53; inside villages M2 is significantly worse (within R2 -0.096); all the gain is in 2019 |

The band curve is a location fingerprint: it predicts latitude with R2 0.70 (Lacuna), 0.79 (Malawi 2022), 0.54 (Kenya).

## 3. Why Presto does not improve

- Its frozen embedding is 81-84 % a linear function of the same 99 monthly inputs; the non-linear rest predicts nothing
  (R2 -0.01 to -0.09).
- Adding it to the bands adds nothing: Lacuna RMSE -0.010 (CI -0.035 to +0.018), rank +0.017 (CI -0.001 to +0.034); same
  in both Malawi cohorts.
- Not overfitting: fine-tuning plateaus at train R2 0.49 / validation 0.34; Ridge on the bands shows the same gap (0.45 /
  0.32). Both hit the same ceiling.
- The Level-1C vs Level-2A shift is real (Presto expects blue 1.6-1.8x brighter) but not the limit: fine-tuning could absorb
  it and scores the same.
- Exception: in Malawi 2023 fine-tuned Presto beats M2 on RMSE (-0.058, CI -0.114 to -0.005), but A1 beats both there.

## 4. More data

- More labels: A1 is close to saturated (Lacuna +0.018 R2 over the last doubling; 2x labels about +0.01 to +0.02). M2 is
  still label-limited in Malawi 2022 (2x labels about +0.04 R2, +0.05 rank). Kenya M2 stays below 0 inside villages at
  every size.
- Pooling other cohorts (z-scored yield, equal weights): no help after correction; R2 falls in all four cohorts; Malawi
  2023 gets no help in 8 variants. Malawi 2022 rank +0.053 (CI +0.010 to +0.094, Holm 0.16).
- Leave one cohort out keeps most of the within-village rank (Lacuna 0.285 vs own 0.299; Malawi 2022 0.361 vs 0.299):
  the ranking transfers across countries, the level does not.

## What this means

1. Most of the R2 comes from predicting which villages yield more. Inside a village, A1 ranks fields about as well as
   anything tried (Lacuna 0.30).
2. The monthly bands are the real source of the extra R2, and Presto cannot add information that is not in its inputs.
3. In Kenya and partly Malawi 2022, harvest timing and post-cut photos carry yield information: fine for an end-of-season
   estimate, never call it a forecast.
4. Candidates to pre-register for one fold-0 test: M2 built from photos before the cut (Lacuna), and the GCVI monthly
   curve (rank +0.059 vs A1 in Lacuna, CI +0.014 to +0.109, not significant after Holm).
