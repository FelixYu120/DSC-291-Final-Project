# Compact Zimbabwe weather experiment

Specified before compact-model scoring, following the requested check for overfitting in the 46-feature weather experiment.
The earlier weather results inform this follow-up; all new results are exploratory on already examined development fields.
Do not change the original data, weather cache, code, manifests, or memberships/permissions of prior releases.

## Fixed features

Keep the 122 December–June imagery features unchanged. Add either:

- **compact2:** January–March rain as percent of its 1991–2020 normal, and January–March temperature anomaly in °C.
- **compact4 (primary):** the same two predictors plus October–December rainfall percent of normal and temperature anomaly.

These are two corresponding seasonal windows in different harvest years, not farmer-specific crop stages.
Select these summaries before running models, without feature selection using held-out yields. Do not search month subsets.
Use the existing NASA POWER cache and derived cell-month data; no new download is required. October–December belongs to
the prior calendar year. Rain percent = 100 × sum(actual monthly rain mm) / sum(normal rain rate × actual calendar days).
Temperature anomaly is the day-weighted mean of the monthly deviations from the 1991–2020 normals.
Retain full weather data; the compact sets are model feature policies, not permanent column deletions.

The reduction changes both dimensionality and temporal encoding/window coverage. An improvement supports the practical
value of simplification but cannot by itself prove that dimensionality alone caused the original failure.

## Models and evaluation

For each fixed set, run target Ridge, cohort-adaptive Ridge, physical shared-label weighted Ridge, target boosted trees
and pooled boosted trees: ten new arms. Use the exact prior outer/inner target memberships and source distance permissions.
Every arm evaluates the same 1,504 Lacuna 2023 fields; each outer fit uses 1,128 target fields. Fold 0 is neither fit nor scored.
Source fields are excluded within 2 km of reserved/evaluation/inner-validation target fields. No new split is generated.

Reuse the prior preprocessing: imagery gets target-training-only imputation, 1st/99th percentile clipping and scaling;
weather gets target-training-only imputation/scaling without percentile clipping. Adaptive target calibration is estimated
only on the allowed training rows. All predictions are clipped nonnegative. No raw year, coordinate or grid ID predictor.

Use the unchanged Ridge alpha grid [0.01,0.1,1,10,100,1000], source/target total-weight ratios [0,0.1,0.3,1], tree leaf counts
[7,15], 120 iterations, learning rate 0.05, minimum leaf size 20, L2=1, early stopping off, seed 20261108. Inner target-validation
MSE chooses parameters; do not pick them using outer scores. Ratio zero is a target-only fallback and is reported honestly.

Controls are hash-verified saved predictions: no-weather target/adaptive Ridge and target/pooled trees; 46-weather target,
adaptive/shared Ridge and target/pooled trees. Their predictions remain unchanged; no retrospective retuning of controls.
The primary comparison is compact4 pooled trees versus compact4 target trees. Report compact-versus-46 and compact-versus-zero
weather contrasts for each matching learner/population, all ten arms, fold metrics and selected source counts. Secondary
contrasts are exploratory and not multiplicity-adjusted. Include the paired change in merging benefit from zero to four features.

## Overfitting diagnostics

For each selected new fit, predict its target-training rows as well as the outer evaluation fields. Training predictions
are used only after inner selection, never for parameter choice. Record training RMSE and outer RMSE; their difference is
descriptive, not a statistical test. Replay selected no-weather and full-weather tree models to obtain the same training
diagnostic, verifying that their outer predictions reproduce the saved controls within 1e-9 t/ha. Preserve original controls.

Describe unique weather profiles, numerical rank of standardized weather predictors, and strongly correlated predictor pairs
(absolute Pearson correlation >=0.95) across the 30 unique target weather cells, without labels. These are descriptive checks,
not a feature-selection procedure. Summarize squared bias versus centered error dispersion from saved out-of-fold errors.

Use 2,000 paired spatial-group bootstrap draws, preserving group IDs as strings, with the same seed and draw order as before.
Also report a weather-cell bootstrap sensitivity with 30 cells; it reflects coarser dependence but cannot fix historical data
reuse or establish generalization to new years. No model is selected by either bootstrap. Keep primary group intervals labeled.

## Deliverables and interpretation

Write a new immutable `data/runs/zimbabwe_weather_compact_v1/` release with matrices, compact weather table, dictionary,
exact split files, predictions, tuning, selected parameters, training/outer diagnostics, feature-structure diagnostics,
metrics, paired intervals and complete input/code/config/output hash manifest. Shorten the existing methods Page so the
conclusion, small comparison table, explanation and recommendation come first; place reproducibility and full methods at the end.

If simpler features reduce outer error while full-weather fits have lower training error, describe that as evidence consistent
with overfitting, not causal proof. If compact sets do not help, report it. Weather remains coarse, target observations cover
one year, and climate/year/provider/management effects are confounded. The same required 2 km splits allow shared weather
cells; this is retrospective spatial development evaluation, not a new-cell or future-season blind test.
