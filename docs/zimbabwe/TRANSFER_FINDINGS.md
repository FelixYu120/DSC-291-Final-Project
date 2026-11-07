# Why the Zimbabwe merge helped little, and what improved

The strongest supported explanation is **a large source/target population difference, combined with a weak initial
feature representation**. The evidence does not support blaming the result primarily on widespread random corruption
of 2024 labels. Better predictors and a stronger learner substantially improve Lacuna prediction; the incremental
benefit of adding 2024 remains small and uncertain with every tested method.

This follow-up ran 30 target evaluation arms, including controls and nested method selectors, plus six within-source
diagnostic models. All target arms evaluate the same 1,504 Lacuna development fields. Historical target fold 0 is
excluded from fitting/scoring and protected by a 2 km auxiliary buffer. Within-source diagnostics also exclude old
2024 fold 0 and its neighbours. The follow-up is exploratory and informed by the first run, not a fresh blind test.

## 1. Why naive pooling got worse

The mean recorded yield is **3.234 t/ha in the Lacuna development population** and **0.486 t/ha in 2024**. Their zero
shares are 1.60% and 43.26%. Treating these outcomes as one interchangeable response population pulls the model down
when it predicts Lacuna. The previous naive model's mean error was **−1.382 t/ha**.

The decomposition `MSE = squared mean error + centered error variance` makes the mechanism visible:

| Previous method | MSE | Squared bias | Centered error variance |
|---|---:|---:|---:|
| Lacuna-only Ridge | 3.2284 | 0.0002 | 3.2282 |
| Naive pooled Ridge | 5.1562 | 1.9094 | 3.2468 |
| Adaptive pooled Ridge | 3.2178 | 0.0004 | 3.2174 |

**99.0% of the extra MSE from naive pooling is accounted for by its increase in squared bias.** The dispersion of
errors changes much less. This accounting does not identify a causal measurement error or propose recalibrating with
held-out labels; it explains the saved predictions. Training-only source calibration already removes most of this harm.

The releases describe different seasons and samples. Zimbabwe declared the 2023/24 cropping season a national
disaster following drought, so real environmental differences are plausible; this does not establish the cause of any
particular recorded yield. [FAO, 8 April 2024](https://www.fao.org/zimbabwe/news/detail/FAO-and-the-Government-of-Zimbabwe-review-the-food-security-situation-to-respond-to-the-El-Nino-induced-drought/en).

## 2. The populations have limited overlap

- The 2024 yield 95th percentile is **2.184 t/ha**. **64.1%** of Lacuna development observations exceed it. Source data
  are concentrated in a substantially lower-yield regime, so thousands of additional rows are not thousands of
  interchangeable examples of the target task.
- A source-versus-target classifier, evaluated with spatial groups, achieves AUC **0.824** from seasonal indices,
  **0.996** from monthly predictors, and **0.9998** from Presto. Chance AUC is 0.5. Coordinates alone give **0.654**.
  The predictor distributions are distinguishable, not merely their yields.
- These AUCs do not prove a biological cause: different missingness and acquisition patterns can also distinguish
  sources. Presto additionally uses whole-window embeddings, with October/November coverage differing across years.
  The monthly predictor comparison uses the same December–June window but still has different missingness patterns.
- For monthly relevance weighting, 4,191–4,226 available source rows have a weight-based effective sample size of only
  **114–127**, illustrating concentrated weights. This is not an independent sample count. For Presto, almost-perfect
  separation and clipping can instead leave weights near their floor; a large effective count does not establish overlap.

The sources confound year, location/sample selection, management and measurement protocol. These files cannot
separate all of those effects. The tested adaptation methods handle some offsets/scales and different relationships;
they cannot manufacture comparable examples or missing metadata.

## 3. Does the quality evidence show that 2024 is bad?

It shows some noisy or uncertain observations, but no evidence that wholesale random label corruption is the main
reason transfer is weak.

| Check | Observation | Meaning and limit |
|---|---|---|
| Missing-label provenance | 590 raw comments say “only have farm photos”; 133 say “did wet but no dry”. These are the 723 missing-label exclusions. The 4,332 retained records are marked “have average yields”. | Missing labels are identifiable separately from recorded zeros; comments do not independently verify every zero. |
| Repeated crop cuts | Correlation is **0.900** over all 4,290 paired records and **0.868** over 2,416 positive paired records. | Agreement persists without the both-zero records. It cannot detect errors shared by both cuts or prove moisture equivalence. |
| Large cut disagreement | **250/2,416**, or **10.35%**, of positive paired records have an absolute cut difference larger than their mean. | A useful noise proxy, but real within-field heterogeneity can cause disagreement too. |
| Satellite coverage | At least six common-window months exist for **99.68%** of the 2024 labels versus **84.91%** of Lacuna development rows. | The source does not have generally poorer month availability. This does not validate GPS placement, crop masks or acquisition timing. |
| Duplicate coordinates | No exactly repeated coordinate pairs among the 4,332 source labels. | Does not prove unique farms or GPS accuracy. Nearby observations remain spatially protected. |
| Learnability within 2024 | Monthly Ridge achieves spatial-CV **R² = 0.271**, RMSE 0.720 versus 0.843 for the training mean, on 3,764 protected diagnostic fields. | There is learnable source signal. Predictability alone is not ground-truth validation. |
| Geographic source signal | Coordinates alone achieve **R² = 0.264** and nonzero-ranking AUC 0.855. | Much of the learnable source structure is spatial; that does not guarantee a transferable field-level relationship with imagery. |

The [source paper](https://arxiv.org/html/2511.12999v1) treats maize yields as zero-inflated, which is consistent with
retaining recorded zeros while testing sensitivities. Neither the paper, these consistency checks, nor the drought
proves that every individual zero is correct.

Lacuna has only one crop cut per field. We cannot estimate its measurement-noise ceiling from the source's two-cut
correlation. Residual target error may include target measurement noise, unobserved management/weather and GPS/field
support mismatch. The available files do not identify each contribution.

## 4. What actually improved the model

The old model used ten seasonal statistics. The new monthly representation retains 105 month-specific band/index
values, seven missing-scene masks and the ten seasonal summaries: **122 predictors**. The frozen Presto alternative
has **128 predictors**. A boosted-tree learner also tests nonlinear relationships using the monthly predictors.

| Feature/learner family | Lacuna-only RMSE | With 2024 RMSE | Increment from 2024 |
|---|---:|---:|---:|
| Seasonal Ridge | 1.7968 | 1.7938 | −0.0030 |
| Monthly Ridge | 1.6926 | 1.6892 | −0.0034 |
| Frozen Presto + Ridge | 1.6815 | 1.6796 | −0.0018 |
| Monthly boosted trees | 1.6594 | 1.6578 | −0.0016 |

All values are t/ha; lower is better. The pooled Ridge rows use source adaptation; pooled trees use a source indicator
and internally tuned source weight. Each comparison has a paired interval crossing zero. The monthly tree's MAE
actually rises slightly with pooling, from 1.2897 to 1.2966, so its tiny RMSE change is not a consistent gain across metrics.

The lowest observed merged arm, monthly boosted trees, improves RMSE by **7.74%** over the old seasonal target-only
baseline. However, monthly trees using **only Lacuna already improve it by 7.65%**. Most of that observed improvement
comes from the representation/learner. The monthly experiment changes both temporal detail and spectral inputs, so
it does not identify which new feature component caused the gain.

Monthly trees are the lowest observed arm, not a primary method selected after seeing evaluation scores. The
pre-specified primary comparison uses two selectors, each choosing its method by inner validation:

| Selection procedure | RMSE | R² |
|---|---:|---:|
| Choose among target-only representations/learners | 1.6923 | 0.2726 |
| Also allow source-transfer methods | 1.6827 | 0.2808 |

The primary difference is **−0.00959 t/ha**, with paired 95% group-bootstrap interval **[−0.04390, +0.02262]**.
All four transfer-selector fits actually used source records. This is a modest point improvement with substantial
uncertainty, not an established benefit. The primary procedure improves by 6.35% over the old baseline; the target-only
selector already improves by 5.81%. Method selection itself is noisy; the lowest outer-scoring arm should not replace
this pre-specified comparison retroactively.

## 5. Which attempted fixes helped?

| Intervention | Result |
|---|---|
| Source quality filter | Retains 4,027 of 4,332 labels: two cuts, >=6 clear months, relative cut difference <=1. Seasonal RMSE changes from 1.793816 to 1.793812—essentially nothing. Monthly filtering slightly worsens its matched adaptive result. |
| Three matched random source subsets | Match the quality subset's zero/positive counts in each fit. Seasonal RMSE is 1.793765–1.793788, indistinguishable from the quality filter. No evidence that this filter selects more useful labels than changing sample composition. |
| Similarity/density weighting | Does not outperform unweighted adaptation in any of the three feature families. Strong distribution separation makes such weights difficult to estimate reliably. |
| Source-trained nonlinear signal | A boosted-tree source prediction added to monthly target Ridge gives 1.692620 versus 1.692594 without it. No useful gain from this transfer mechanism. |
| Five shuffled-source-label controls | RMSE 1.796434–1.797000, close to the 1.796767 target-only baseline. True-source adaptation reaches 1.793816 and beats all five point estimates. This suggests a small real signal, but every paired true-minus-shuffled interval crosses zero; five shuffles are not a formal significance test. |
| Fewer target training groups | At 25% of groups, RMSE changes 1.8096→1.8078; at 50%, 1.8019→1.8004. Both differences remain small/uncertain. These are fixed group subsamples, not exactly 25%/50% of rows: outer training counts range 231–445 and 468–724 respectively. |

The source seems to carry a small amount of relevant information, and it is clearly predictable within its own
population. The experiments do not reveal a large unused transfer benefit that is unlocked by the tested cleaning,
weighting, representation or learner changes. This does not establish that every possible transfer algorithm would fail.

## What to use and what to say

Use the richer monthly representation as a serious baseline for the team's modeling work. Report its target-only
and pooled variants side by side. Keep the harmonized 2024 observations and their quality flags available for auxiliary
training; the evidence does not justify permanently deleting uncertain but valid labels or claiming a large pooling gain.
For stronger attribution, the useful missing evidence is verified field/season alignment, management/weather inputs,
and reference measurements for questionable labels. A fresh independent season is needed for confirmatory transfer claims.

“Our first merge failed because it mixed very different yield populations and introduced a large downward bias.
Calibration fixed that. We then improved prediction substantially by retaining monthly spectral information and
testing richer models. The 2024 data is internally coherent and learnable, but contributes little additional accuracy
for the Lacuna 2023 target population under the methods we tested. Filtering noisy cuts did not change that conclusion.”

## Reproduce and inspect

- [Protocol](../ZIMBABWE_TRANSFER_DIAGNOSIS_PROTOCOL.md), specified before the follow-up models ran.
- [Generated complete results](../../data/runs/zimbabwe_transfer_diagnosis_v1/RESULTS.md), including all 30 arms and selections.
- [Runner](../../scripts/step10_diagnose_zimbabwe_transfer.py), [implementation](../../src/cropyield/experiments/zimbabwe_diagnosis.py),
  [config](../../configs/zimbabwe_transfer_diagnosis_v1.json).
- Outputs in `data/runs/zimbabwe_transfer_diagnosis_v1/`: predictors, quality flags, exact memberships/permissions,
  tuning, predictions, metrics, uncertainty, diagnostics and input/code/output hash manifest.

Run `python scripts/reproduce_zimbabwe.py diagnosis` from the repository root with the first experiment and
pinned team database present. Inputs are read-only; existing releases are immutable. The full suite passed
**162 tests, with 2 skipped**. Original seasonal baseline/adaptation predictions are reproduced independently within
the runner. Output-level checks verify source exclusions, same evaluation IDs, inner-only method selection, metrics,
bootstrap intervals and a replay of a selected outer model. Preserve `group_id` as a string when replaying seeded
bootstrap draws; numeric reordering changes the particular random draws, though not the resampling design.

The monthly predictor file is a flat regression table. Its columns name their calendar months; a sequential model
must explicitly order them December, January, February, March, April, May, June rather than using lexical column order.
