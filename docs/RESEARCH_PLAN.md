# Research plan: geospatial foundation models for maize-yield estimation

## Goal and research question

Test whether pretrained geospatial representations improve maize-yield estimation when labels are scarce and evaluation fields come from locations withheld during training. The primary setting is smallholder Africa, where the current repository has field-level crop-cut or reported-yield candidates from One Acre Fund (multiple countries), Malawi, and Zimbabwe. The primary outcome is yield in kg/ha after source-unit checks. Treat every current row as a *screened candidate*, not as a verified field-level label: audit eligibility does not prove that a GPS point or polygon identifies the maize field.

The framing follows Burke and Lobell (2017): satellite-yield relationships depend on precise plot area, field size, and the quality of field measurements. Their western Kenya study used 1 m imagery and intensive field sampling over two years, and reported its strongest agreement at R² up to 0.4 with precise field measures. Our study asks whether modern pretrained representations help under small labels and spatial transfer, while explicitly measuring the effect of location and label quality. The coauthor's name is David **Lobell**.

### Questions and hypotheses

1. Does a pretrained representation improve out-of-location yield prediction over a yield-mean baseline, regularized regression, and tree-based models using the same labels and spatial folds?
2. Does Presto fine-tuning beat using its frozen encoder as a feature extractor, especially with only 10%, 25%, or 50% of the training labels?
3. Do AlphaEarth annual embeddings improve retrospective yield estimation over seasonal Sentinel-2 features, and how much does performance fall when spatial clusters or countries are held out?
4. How sensitive are results to field-location confidence, area measurement, crop-cut protocol, mixed cropping, year, and yield-unit interpretation?

Hypotheses: pretrained features will help most at low label fractions; spatially separated performance will be lower than random-split performance; and label/location uncertainty will limit observed performance even when image representations are strong.

## Define two prediction settings before training

The requested datasets mix survey, crop-cut, and multi-season observations, and the satellite products have different temporal coverage. Report two distinct tasks instead of treating every feature as an equivalent yield forecast:

| Task | Features allowed | Claim supported |
|---|---|---|
| **Completed-season estimation (primary)** | Imagery/embeddings from the full crop season, including harvest time if available | Retrospective field-level yield estimation after the season. Same-year AlphaEarth is allowed, but is not an in-season forecast. |
| **Pre-harvest prediction (secondary)** | Sentinel-2 / Presto sequence truncated to a stated forecast cutoff; no observations after that date | Forecasting yield before harvest. AlphaEarth's published annual embedding summarizes the annual observation period, so use only a prior-year embedding as a historical-feature baseline; do not use the same-year embedding here. |

Google publishes AlphaEarth as a 64-band, 10 m annual embedding collection for 2017–2024 in Earth Engine. These are pretrained embeddings for downstream regression; this project should not describe them as an encoder that we fine-tune. The annual composite is useful for completed-season mapping, but it does not provide a within-year time cutoff. Include the attribution “The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind,” and confirm Earth Engine access/terms before bulk export.

## Data and geographic scope

**Primary Africa field-level benchmark.** Start with Malawi 2022/2023 because field polygons and crop-cut measurements are available. Add Zimbabwe and One Acre Fund observations only after confirming yield units, location provenance, field identity, and whether same-season imagery can reasonably be matched. Do not silently pool reported yields and crop-cut yields. Keep dataset, season, protocol, unit conversion, crop status (sole/intercropped), field area, location geometry, coordinate confidence, and source row in each modeling table. Use zero-yield records, but report metrics both with and without them as a sensitivity analysis.

**U.S. extension.** USDA NASS Quick Stats provides published state/county aggregate corn yields, not public field-level yields or farm locations. The optional downloader saves county estimates under `data/raw/USA/USDA_NASS/`. This is a separate county-scale benchmark: join by state and county FIPS to county polygons and compare county-aggregated predictions with estimates. Never convert a county row to a field point, concatenate it as a field label, or use it to claim field-level transfer. NASS county coverage and availability vary by year and disclosure rules.

**OAF curated file.** Keep its rows traceable and flagged separately: the release mixes field, nearby-town, and district coordinates without a public row-level precision flag. Do not use it in the primary location-valid experiment unless the team obtains that provenance.

### Data checks before extracting features

- Resolve source units and yield protocol with provider documentation; retain original and converted values side by side.
- Check geometry over a basemap and within the stated country; verify field-vs-home/site precision and CRS transformation.
- Confirm planted/harvested dates and crop year. Keep Malawi nested cuts and repeated observations on the same field in one group; do not count nested cuts as independent fields.
- Exclude or sensitivity-test uncertain, intercropped, damaged, mixed-crop, and low-precision records; report each exclusion.
- Record satellite product, scene IDs, dates, processing level, cloud/valid-pixel coverage, extraction geometry, and any resampling. A point sample is not a field mean.

The repository's current 2019+ count is **18,939 screened candidates**, not 18,939 verified field labels. The older One Acre Fund 2016–2020 rows may still be useful for retrospective experiments but cannot satisfy the 2019+ Sentinel-2 window across all observations. Keep time coverage explicit per dataset.

## Model comparison

Use identical eligible observations, target definition, forecast cutoff, country/source strata, and spatial folds wherever the feature products allow it.

1. **Reference baselines:** training-fold yield mean/median; Ridge regression on a small, fixed set of seasonal spectral indices or band summaries; Random Forest and HistGradientBoosting on those same summaries. Fit all scaling, imputation, feature selection, and tuning using training folds only.
2. **AlphaEarth downstream model:** extract the 64 annual `A00`–`A63` values over the field polygon; use the robust pixel median as the main vector and record valid-pixel share. For point-only rows, use a fixed small neighborhood and a point-pixel sensitivity analysis. Fit Ridge as the low-capacity benchmark and a tree model as a nonlinear comparator. Do not tune embeddings using test labels. If polygon labels and only point geolocation are available, label the feature extraction as a proxy and analyze it separately.
3. **Presto transfer:** load the released pretrained checkpoint and build a one-output regression head using the official downstream interface `construct_finetuning_model(num_outputs=1, regression=True)`. Presto accepts `[batch, time, bands]` sequences of 1–24 steps, with band masks, optional Dynamic World labels, coordinates, and a starting month. Use the package's input-construction helpers and normalization rather than passing raw reflectance in an assumed scale. Compare: (a) frozen encoder features + Ridge/tree head; (b) train only the regression head; (c) unfreeze the full encoder and jointly fine-tune the head. Add partial unfreezing (last encoder block) if compute permits. Use a single Sentinel-2-only input ablation where possible so the comparison does not hinge on unshared modalities.
4. **Optional fusion:** compare AlphaEarth and Presto feature concatenation only after individual models are evaluated. Feature fusion is secondary because the temporal semantics and observation windows differ.

The official Presto config uses encoder embedding size 128, depth 2, 8 attention heads, MLP ratio 4, and month/channel embedding ratios 0.25; these are the released architecture defaults, not yield-task hyperparameters. Start the fine-tuning search conservatively: AdamW learning rate in `{1e-5, 3e-5, 1e-4}` for unfrozen Presto weights, head learning rate in `{1e-4, 3e-4, 1e-3}`, weight decay `{0, 1e-4, 1e-2}`, batch size 16 or 32 subject to accelerator memory, and up to 50 epochs with early stopping on spatial validation MAE (patience 5–8). Search/selection must occur only within the training geography. Log the exact checkpoint, library commit, seed, hyperparameters, trainable parameter count, feature date range, and stopping epoch. These values are a proposed student-project search space, not official Presto defaults; refine it after a small pilot.

## Evaluation design

- **Primary split:** spatially grouped folds. Cluster fields by farm/site or a prespecified distance-based spatial block; all repeated field IDs and nearby repeated coordinates stay together. A random field split is only an optimistic diagnostic.
- **Location transfer:** reserve one or more sites/districts entirely for testing; if sample sizes allow, report leave-one-country-out transfer separately from within-country unseen-location validation. Country and dataset effects are distinct and must not be hidden in a single pooled score.
- **Low-label curve:** within each training fold, subsample 10%, 25%, 50%, and 100% of training groups, stratified by country/source/year where feasible. Repeat the subsampling seeds and use the same subsets across models.
- **Temporal transfer:** where repeated years exist, train on earlier years and test on a later year. Do not use the later year's yield data to tune the model.
- **Metrics:** MAE and RMSE in kg/ha, R², and bias; report fold-level values and uncertainty across spatial folds/seeds. Report both pooled and per-dataset/country values. Do not compare U.S. county metrics directly with Africa field metrics as though they were the same task.
- **Ablations:** frozen vs fine-tuned Presto; AlphaEarth vs seasonal optical summaries; feature-window cutoff; field polygon vs point-buffer extraction; high-confidence-only labels vs all candidates; single-crop vs intercropped; and inclusion/exclusion of zero yields.

Keep a locked spatial test set out of all feature/model/hyperparameter choices. Fit normalization and transformations on training only. Preserve source IDs for auditability but do not pass identifiers, exact location-derived shortcuts, or post-harvest information into a purported pre-harvest model. For geospatial embeddings, carefully distinguish spatially transferable signal from memorizing location/context.

## Recommended order of work

1. Confirm field counts, location quality, crop dates, yield protocol, and usage conditions with data providers; request additional later-season field labels if available.
2. Create a reviewed analysis manifest per country and fix the train/test grouping rules before training.
3. Validate imagery alignment and make a small extraction batch; freeze documented input schemas for AlphaEarth and Presto.
4. Establish baseline results and a spatial-split protocol.
5. Run the low-label comparisons and fine-tuning ablations, then repeat on the held-out geography.
6. Add the U.S. county benchmark only as a scale-separated extension. First verify NASS years, units, and county boundaries for the exact target query.
7. Publish data/model attribution, licenses, counts at each filter stage, code/configs, and limitations with the results.

## Core references

- Burke, M., & Lobell, D. B. (2017). “Satellite-based assessment of yield variation and its determinants in smallholder African systems.” *Proceedings of the National Academy of Sciences*, 114(9), 2189–2194. [doi:10.1073/pnas.1616919114](https://doi.org/10.1073/pnas.1616919114).
- Tseng, G., Cartuyvels, R., Zvonkov, I., Purohit, M., Rolnick, D., & Kerner, H. (2023; revised 2024). “Lightweight, Pre-trained Transformers for Remote Sensing Timeseries.” [arXiv:2304.14065](https://arxiv.org/abs/2304.14065) ([PDF](https://arxiv.org/pdf/2304.14065)). See the [Presto code and downstream demo](https://github.com/nasaharvest/presto).
- Brown, C. F., et al. (2025). “AlphaEarth Foundations: An embedding field model for accurate and efficient global mapping from sparse label data.” [arXiv:2507.22291](https://arxiv.org/abs/2507.22291). See the [Earth Engine dataset catalog](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL).
- USDA National Agricultural Statistics Service, [Quick Stats database and API](https://quickstats.nass.usda.gov/api).
