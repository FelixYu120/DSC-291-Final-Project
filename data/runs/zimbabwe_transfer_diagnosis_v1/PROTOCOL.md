# Why did Zimbabwe pooling add little? Follow-up diagnostic protocol

This follow-up was specified after seeing the first experiment, before running these new models. Felix requested
diagnosis of source quality versus information content/model limitations, and tests of improved pooling methods.
All results are exploratory; new methods and hypotheses are informed by previously examined development data.
No new blind evaluation is claimed, no fold 0 is scored, and no existing release is modified.

## Questions and falsifiable checks

1. **What caused naive pooling to worsen?** Decompose saved errors as MSE = squared mean error + centered error variance.
   This is an accounting identity, not a deployable correction using evaluation labels. Compare source/target label
   distributions and missingness; report rank correlation alongside level accuracy.
2. **Is 2024 internally inconsistent?** Recheck the two independent crop cuts, positive-only as well as all-row
   correlations, relative disagreement, single-cut cases, missing imagery, and duplicate coordinates. Agreement
   does not verify a shared moisture basis or rule out a shared recording error. Both-zero agreement is uninformative.
3. **Is 2024 learnable within its own domain?** Run grouped spatial CV using all eligible source labels except the
   old 2024 fold-0 fields and points within 2 km of them, also protecting Lacuna fold 0. Recompute 2 km components on
   the remaining source population and use four diagnostic folds. Report source mean, Ridge on seasonal/monthly/Presto
   features, monthly boosted trees, and a coordinates-only baseline. These are descriptive models, not a fresh source
   test. Source R² cannot establish physical label validity or be read as the same task difficulty as target R².
4. **Does the true source feature-label relationship help?** Repeat seasonal adaptive transfer with five fixed
   shuffled-source-label controls, each retuned inside the same folds. Preserve source labels' distribution, counts
   and coordinates; permute only allowed training labels, separately in each fit. Compare true and shuffled outcomes
   without choosing a favorable seed. Five permutations are a diagnostic, not a formal permutation significance test.
5. **Does source quality filtering help more than changing sample size/composition?** Keep source records with two
   cuts, at least six clear common-window months, and relative cut disagreement <=1 (larger cut no more than 3× smaller;
   both-zero rows pass but remain unverified). Compare adaptive fitting against all source data and three random subsets
   with the same zero/positive counts as the quality subset in each fit. These flags are proxies, not truth labels for
   good/bad records. Excluded records remain in the underlying catalog.
6. **Does source relevance matter?** Fit a source-versus-target logistic classifier on allowed training features,
   estimate target/source density ratios, clip to [0.05,20], and use them as source weights in adaptive regression.
   This weights similarity, not measurement quality. It assumes useful relationship overlap, which can fail.
7. **Are our representations/learners too restrictive?** Compare target-only and adaptive Ridge on three matched
   feature families: ten seasonal statistics; December–June monthly bands/indices plus masks and seasonal statistics;
   and 128 frozen Presto embeddings. Also compare monthly boosted trees with/without a source indicator and tunable
   source weight; test a source-trained nonlinear prediction as an additional target Ridge feature.
   Presto uses the existing whole-window embeddings (Oct–June), so its window/mask conventions differ from the two
   common-window families. A Presto gain alone is not proof of a benefit from adding 2024.
8. **Is source information redundant when target labels are plentiful?** At 25% and 50% of target training spatial
   groups, compare seasonal target-only and adaptive training with identical selected groups and unchanged evaluation
   fields. This is a fixed-seed learning-curve diagnostic, not an estimate averaged across all possible subsamples.

## Evaluation and primary comparison

Reuse the 1,504 target development fields and immutable Lacuna folds 1–4. Never fit/score target fold 0. Reuse all
per-fit target memberships and auxiliary spatial permissions from the first experiment, including the extra inner
validation buffer. Validate their hashes first. Source outcome permutations, quality screening, density weighting,
imputation, winsorization, scaling, calibration and model selection see only each fit's permitted observations.

Numeric missing values are imputed from target training medians; 1st/99th percentile clipping and scaling also use
target training only. Monthly missing-scene masks are explicit. Every arm predicts the same target evaluation fields.
All predictions are clipped nonnegative. Same-family target-only comparisons separate representation gains from
gains due to the extra source. The source-only predictability diagnostic fits preprocessing on source training rows.

The **primary** comparison is `transfer_selector` versus `target_selector`. Within each outer training set, the latter
chooses a feature family/Ridge alpha or monthly tree leaf count from inner validation; the former can additionally
choose true-label adaptive transfer, quality filtering, density weighting, nonlinear source-signal transfer or pooled
monthly trees. It may choose target-only. Shuffles, random subsets, coordinates-only and learning curves are excluded
from selection. Select using pooled inner squared error, never the outer score. Export the selected family and actual
source contribution; a target-only selection is not described as a successful use of 2024.

Report all arms, paired spatial-group bootstrap intervals (2,000 draws), per-fold scores, source subset sizes and
chosen parameters. Pair each adaptation with its corresponding target-only feature/learner baseline. Additionally
report the primary selectors and their contrast with the original seasonal baseline. Bootstrap intervals condition on
the saved predictions; secondary intervals have no multiplicity adjustment. Do not promote the best outer-scoring
arm to a pre-specified primary result or keep searching until something looks significant.

## Deliverables and interpretation limits

New immutable output directory: `data/runs/zimbabwe_transfer_diagnosis_v1/`. Include error decomposition,
quality/shift diagnostics, source predictability, all target predictions/metrics/tuning, learning curves, shuffled
controls, exact source access inherited from v1, selected models, plots, report and a hash manifest.

A lack of transfer gain can coexist with learnable, internally consistent source data: the two source-year populations
may have different predictors/outcome relationships, or source information may duplicate what target labels already
teach. Conversely, improving with richer target-only features does not show source labels helped. Without matched
reference measurements, this study cannot identify a field's true measurement error, separate provider effects from
the 2024 season, or declare source zeros invalid. Conclusions must distinguish these explanations explicitly.
