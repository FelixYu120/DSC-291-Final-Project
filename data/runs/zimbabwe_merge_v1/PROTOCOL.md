# Lacuna plus Zimbabwe 2024: compatibility and comparison protocol

Specified before running this experiment on November 7, 2026. Felix explicitly requested a merged dataset,
methods addressing compatibility, and a comparison against Lacuna-only training. This authorizes the pooled
development experiment; the frozen team inputs and historical fold-0 restriction remain unchanged.

## Question and comparison

Does adding cleaned 2024 observations improve prediction on the **same Lacuna 2023 fields**, compared with
training on Lacuna alone? The target population remains the 1,880 screened 2023 pure-stand rainfed records.
2024 observations are auxiliary training data, with unknown irrigation/intercropping explicitly retained.
This does not claim the two samples represent the same farm population.

The primary result is `pooled_adaptive` versus `lacuna_only`, using RMSE in t/ha. All arms predict exactly the
same held-out target observations. All listed diagnostics and sensitivity arms are reported, regardless of outcome.
No method is promoted to the primary comparison after seeing its evaluation score.

## Compatibility register

| Problem | Action in this experiment | What the action establishes / does not establish |
|---|---|---|
| Source yield units | Convert source t/ha to kg/ha once; fit/report models in t/ha. Check dry kg × 0.25 independently. | Numeric units agree; it does not prove a shared moisture basis. |
| Three inconsistent Lacuna labels | Preserve them in the raw audit, exclude them from both training alternatives. | No invented correction when actual cut area is unknown. |
| One cut vs two cuts | Retain source protocol and observed cut count. For 2024, independently average available box yields, including documented single-box cases. | Do not divide an already averaged yield by two. No assumed precision multiplier. |
| Missing moisture/grain basis | Keep physical values unchanged. The adapted model uses training-only cohort means/scales and cohort-specific slopes. | Statistical handling of source offsets/scales, not an invented physical correction. Nonlinear or field-varying measurement errors remain possible. |
| 2024 zeros | Keep all valid zeros in the primary experiment. Also run positive-only and zero-weight-0.25 sensitivity arms. | Source paper includes exact zeros; late visits do not prove missingness. Sensitivity is not proof that zeros are invalid. |
| Invalid/missing per-box data | Reject negative/nonfinite used yields or dry weights, inconsistent dry-to-yield conversion, and incompatible reported averages. Missing unused box remains missing. | Every exclusion has a row-level reason. No imputation of target labels. |
| Missing 2024 management fields | Mark unknown. Use 2024 only as an auxiliary domain with tunable contribution, and score the unchanged known-management Lacuna population. | Supports a target-specific usefulness test, not harmonization of management metadata. |
| Different harvest years | Retain source/year/season identifiers. All results are retrospective. | Does not claim 2024 data would have been available for a real-time 2023 forecast. |
| Different month coverage | Rebuild both sources' seasonal features from **December–June** only; at least four observed months. Nulls stay null before aggregation. | Removes Oct/Nov availability asymmetry. Different missingness within the common window still exists. |
| Post-harvest scenes / unknown 2024 harvest dates | Define the task as full-season retrospective estimation. Do not use photo dates as verified harvest dates. | Forecasting requires a separate cutoff-defined dataset. |
| GPS errors and cross-source proximity | Retain points, do not infer farm identities. Remove auxiliary observations within 2 km of reserved/evaluation target fields in every outer and inner split. | Prevents direct geographic leakage under this distance rule; does not correct unknown GPS displacement. |
| Duplicate identifiers/joins | Require unique source-prefixed obs_id; join by obs_id, monthly data by obs_id/month; reject duplicate keys. | Nearby records are grouped/guarded, not automatically averaged into one farmer. |
| Different cohort means, spreads, drought and collection protocol | Compare naive pooling with source intercepts and normalized shared-plus-specific slopes. Tune source weight using target training folds only. | Year and provider effects remain confounded; no causal separation or claim all differences are measurement errors. |
| Source data overwhelms the target | Adapted arms normalize total source training weight relative to target training weight; candidate ratios 0, 0.1, 0.3, 1. | Zero lets internal validation reject transfer rather than forcing a harmful merge. |
| Feature extremes / preprocessing leakage | Clip at target-training 1st/99th percentiles and scale using target-training statistics, repeated inside every inner fold. | Evaluation observations influence neither clipping nor normalization/tuning. |
| Legacy positive-only 2024 selection | Build a separately named merged table from all screened 2024 labels, ignoring the legacy zero exclusion for this experiment only. | Frozen labels and the prior handoff stay intact; no silent change of eligibility. |
| Historical test exposure | Exclude Lacuna fold 0 from every fit/score and buffer source rows away from it. Evaluate folds 1–4 with nested grouped CV. | Development results, not a new blind test. Reassigning folds would not undo history. |
| Small or misleading comparison | Same target IDs/features/folds per arm; report RMSE, MAE, bias, R², rank correlation and paired spatial-group bootstrap intervals. | Intervals are conditional on these data/models; they do not undo prior exploratory exposure or support causal claims. |
| Incomplete 2022 imagery | Leave 2022 outside this specific comparison so the addition being tested is exactly Zimbabwe 2024. | Lacuna 2022 is a separate possible extension, not secretly added to one arm. |

## Models

- `train_mean`: target-training mean reference.
- `lacuna_only`: Ridge on the ten common-window spectral statistics, alpha tuned internally.
- `pooled_naive`: same Ridge, all valid source rows, equal weight per row, no cohort adjustment.
- `pooled_intercept`: common feature slopes, separate unpenalized cohort means, tunable source weight.
- `pooled_adaptive` (**primary**): standardize each cohort's training targets separately, center features within each
  training cohort, then fit a Ridge model with shared, target-specific and source-specific feature blocks. Restore
  predictions to the target training mean/standard deviation. A positive affine change of source labels cancels
  under this normalization. Candidate source weight zero falls back exactly to target-only Ridge.
- `pooled_positive_sensitivity`: same adaptive procedure, removing source zeros only as a sensitivity.
- `pooled_zero_weight_sensitivity`: same adaptive procedure, giving source zeros one-quarter of the weight of
  positive source records, only as a sensitivity. Weighted means/scales use the same row weights.
- `lacuna_tree` and `pooled_tree`: a second learner (histogram gradient boosting) checks model dependence. The
  pooled tree receives a cohort indicator and tunable source weight; no physical-label rescaling is assumed.

Shared/domain-specific feature augmentation follows the general idea in
[Daumé, 2007](https://aclanthology.org/P07-1033/). Cohort target normalization and source weighting here are explicit
adaptations for this regression problem. They are not a claim that all domain differences have disappeared.

## Evaluation and tuning

Use immutable `s1_cc2km` target folds. Never score fold 0. Each of folds 1–4 is held out once; train on the other
three development folds (1,128 target records per outer fit), giving 1,504 paired out-of-fold predictions per arm.
For every outer split, exclude auxiliary points within 2 km of the outer evaluation fields and fold-0 fields.
During each 3-fold grouped inner CV, additionally exclude auxiliary points within 2 km of inner validation fields.
The same spatial group never straddles target training/validation. Purging uses coordinates, not target yields.

Select alpha/source weight or tree leaf count on pooled inner validation squared errors, not outer scores.
Source policies and candidate grids are frozen in `configs/zimbabwe_merge_v1.json` before the run. No external
evaluation target means or variances are used for normalization. Preprocessing sees only the current training set.
Source-specific centering/normalization sees only the source rows allowed in that training split.

All predictions are clipped to nonnegative yield for every arm. The primary paired uncertainty interval resamples
target spatial groups 2,000 times, using identical draws for both methods. Report the fraction of bootstrap draws
favoring each method as descriptive only, not a probability the hypothesis is true. Other arm intervals are
exploratory and are not adjusted for multiple comparisons. No pooled cross-source R² is used.

## Deliverables and decision rule

The full screened label catalog includes Lacuna 2022 and non-primary management groups, with explicit
`comparison_candidate` flags. The comparison feature table uses the target population above; a catalog row
being retained does not imply it trains a model. The season label is an alignment convention inferred from the
harvest/collection year, not verified planting/harvest dates for 2024.

The runner exports the harmonized combined table, source row audit, per-fold source exclusions, inner-CV tuning
scores, selected parameters, out-of-fold predictions, metrics, paired differences, plot and provenance manifest.
The source database is read-only and all code/config/input hashes are recorded. Outputs are written to a new
experiment directory and identical reruns can verify reproducibility. Exact target memberships and source
distance permissions are exported for every inner and outer fit, allowing independent leakage checks.

If adaptive pooling lowers RMSE consistently and its paired interval excludes zero, describe evidence of benefit
**for this retrospective target population and protocol**. If the interval includes zero, describe uncertainty.
If pooling hurts, keep the harmonized dataset and report that added observations did not improve this task.
An inner-CV source weight of zero means that fold rejected auxiliary training, not that its model used all merged rows.

Sources: [Lacuna provider](https://doi.org/10.5281/zenodo.10060610),
[2024 source paper](https://arxiv.org/html/2511.12999v1), local provider metadata and the recorded handoff audit.
