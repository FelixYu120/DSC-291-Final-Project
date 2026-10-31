# Related work and the CNN question

Literature check of 29 October 2026, for the feedback "Have other papers used foundation models for crop
yield? Cite and differentiate" and "MOSAIKS + Ridge vs CNN vs foundation model?". Every entry was opened on
its own page; entries marked (*) could only be checked through search listings.

## Papers

| Paper | What they did | Main result | How we differ |
|---|---|---|---|
| **Adjei 2026**, arXiv:[2605.08113](https://arxiv.org/abs/2605.08113) | 6,404 maize points, Kenya, Malawi, Nigeria, Rwanda, Tanzania 2017–22 (GROW-Africa surveys and trials). Frozen Prithvi-EO-1.0 and an ImageNet ViT vs 23 Sentinel-2 + rainfall features; Ridge, RF, XGB heads; one season-median image | pooled random-CV R² 0.17–0.30 (Prithvi+XGB 0.30 vs spectral+XGB 0.29); leave-one-country-out R² negative for all | one image date, one FM, no MOSAIKS/Presto/AlphaEarth, labels not crop cuts, no held-out season, countries pooled |
| **Ma, Shen, Swatantran, Lobell 2026**, "Harvesting AlphaEarth…", arXiv:[2601.00857](https://arxiv.org/abs/2601.00857) | AlphaEarth vs hand-built remote-sensing features (RF/XGB); US county and field yields; year, county-to-field and ecoregion transfer | county R² ~0.78, field R² 0.13–0.46, both about equal to hand-built features; AlphaEarth clearly worse under county-to-field and ecoregion transfer | US commercial fields; we have smallholder crop cuts and add MOSAIKS and Presto |
| **Kamangir, Yun, Earles 2026**, NeurIPS REO workshop ([page](https://neurips.cc/virtual/2026/157097)) | AlphaEarth, OlmoEarth, Presto, AnySat vs a from-scratch fusion model; 140 corn and 197 wheat field-years | OlmoEarth with a ConvLSTM head best | intra-field yield maps in few fields; we have thousands of fields, one label each |
| **Nejadshamsi et al. 2025**, FARM, arXiv:[2510.26609](https://arxiv.org/abs/2510.26609) | fine-tunes Prithvi-EO-2.0-600M for 30 m canola yield maps, Canada | R² 0.81; beats from-scratch, 3D-CNN, DeepYield | large commercial fields, full fine-tuning; we use frozen embeddings |
| **Nedungadi, Xiong, Rußwurm, Athanasiadis 2026**, arXiv:[2608.30392](https://arxiv.org/abs/2608.30392) | Galileo, CropFM (on Presto), TabPFN vs RF, LSTM, Transformer; CY-Bench (US, Germany, Senegal) and YieldSAT | no Earth-observation FM wins; from-scratch LSTM/Transformer at or below RF | admin-level or pixel labels |
| **Nedungadi et al. 2025**, ICCV SEA workshop, arXiv:[2507.05390](https://arxiv.org/abs/2507.05390) | Presto+RF, Galileo+RF vs RF; CY-Bench maize, Spain, leave-one-year-out | Presto+RF worse than RF (NRMSE 31.1 vs 14.3) | weather inputs, regional scale |
| **Halder et al. 2025**, *Sci. Remote Sens.*, doi:10.1016/j.srs.2025.100344 (*) | maize yield maps for 42 African countries at 250 m from FAO yields spread to pixels; XGB, LightGBM, NN, TabPFN | XGB temporal R² 0.78 | synthetic labels; tabular FM |
| **Brown et al. 2025**, AlphaEarth Foundations, arXiv:[2507.22291](https://arxiv.org/abs/2507.22291) | annual 10 m 64-d embeddings, 15 tasks | no yield task; MOSAIKS often second | we test AlphaEarth on yield |
| **Rolf et al. 2021**, *Nat. Commun.* 12:4392, doi:10.1038/s41467-021-24638-z | MOSAIKS + Ridge vs end-to-end ResNet-18 vs pretrained ResNet-152 features; 7 US tasks, 80k images | MOSAIKS on average 0.04 R² below the trained CNN, 250–10,000× cheaper | no yield task |
| **Molitor et al. 2025**, *Remote Sens.* 17:3641, doi:10.3390/rs17213641 | MOSAIKS (Landsat + Sentinel-2) + Ridge, Zambia, 72 districts, 2016–21 | out-of-sample R² 0.83 | district level, no CNN or FM arm |
| **Corley et al. 2024**, CVPRW, arXiv:[2305.13456](https://arxiv.org/abs/2305.13456) | re-tests pretrained remote-sensing models | always include simple baselines, including random convolutional features | classification only |
| **Burke & Lobell 2017**, *PNAS* 114:2189, doi:10.1073/pnas.1616919114 | 1 m imagery, western Kenya maize, self-reported yields | R² up to ~0.4 with precise ground data | index regression |
| **Jin et al. 2017**, *Remote Sens.* 9:931, doi:10.3390/rs9090931 | SkySat, RapidEye, Sentinel-2 in western Kenya (with One Acre Fund) | red-edge MTCI best; small fields, intercropping, clouds limit accuracy | index regression |
| **Jin et al. 2019**, *RSE* 228:115 | Sentinel-1/2 maize maps + SCYM yields, Kenya and Tanzania | ~50 % of district yield variation | checked only at district level |
| **Lobell et al. 2020**, *AJAE* 102:202, doi:10.1093/ajae/aaz051 | Uganda: self-reports vs sub-plot cuts vs full-plot cuts vs Sentinel-2 | satellite at least as good as self-reports and sub-plot cuts against full-plot cuts | label-quality background for our crop cuts |
| **Li et al. 2026**, AAAI, arXiv:[2511.12999](https://arxiv.org/abs/2511.12999) | ~20k crop cuts + field photos; prediction-powered inference | maize effective sample size +12–23 % | source of Zimbabwe 2024; photos, zone averages |
| **You et al. 2017**, AAAI, doi:10.1609/aaai.v31i1.11172 | CNN/LSTM on MODIS histograms + Gaussian process, US county soybean | ~30 % lower RMSE than baselines | county level, many labels |
| **Jere & Munthali 2026**, ISPRS Archives, doi:10.5194/isprs-archives-XLVIII-4-W20-2025-33-2026 | Sentinel-2 series, 8 fields in Malawi; CNN-LSTM, ViT-LSTM | recurrent models best | 8 fields only |

Not used: Fang et al. 2025 (TechRxiv, AlphaEarth county corn) could not be opened.

## Related-work paragraph (draft for the midterm)

> Foundation models for crop yield are recent and mostly tested in North America at county or within-field
> scale, with administrative or yield-monitor labels. AlphaEarth embeddings match purpose-built
> remote-sensing features within a region but transfer poorly across regions and scales (Ma et al., 2026).
> Fine-tuned Prithvi-EO-2.0 beats training from scratch on canola yield maps (Nejadshamsi et al., 2025), and
> OlmoEarth with a temporal head leads a probe that also includes Presto and AlphaEarth (Kamangir et al.,
> 2026). On CY-Bench, no Earth-observation foundation model beats a tabular baseline (Nedungadi et al.,
> 2026). In sub-Saharan Africa, the one direct test we found uses frozen Prithvi-EO on single-season
> composites with survey and trial labels; it finds no gain over spectral features and negative
> cross-country R² (Adjei, 2026). MOSAIKS predicts district maize yields in Zambia well (Molitor et al.,
> 2025) but has not been compared with foundation models. We address this narrower gap: field-level crop-cut
> labels from smallholder cohorts, MOSAIKS vs multi-temporal (Presto) and annual (AlphaEarth) embeddings
> under the same head, evaluated within each cohort with spatially blocked and held-out-season splits.

What we must **not** claim: "the first foundation-model yield study in sub-Saharan Africa" (Adjei 2026),
or unseen-country transfer as a headline (Adjei 2026 already found it fails).

## The CNN question

Emily reads RQ1 as MOSAIKS + Ridge vs an end-to-end CNN vs a foundation model. Our answer keeps the
three-way comparison but places the "CNN" honestly:

1. **Random convolutional features: MOSAIKS (arm A2).** Rolf et al. (2021) describe MOSAIKS as a CNN whose
   one convolutional layer has random, untrained filters; with 80k labels it was on average only 0.04 R²
   below a trained ResNet-18.
2. **A deep model trained from scratch: a small GRU or 1D CNN on the monthly band series (arm A4).** Same
   input Presto receives, no pretraining. This is where the yield signal lives (the seasonal course of
   greenness), and it fits our label counts.
3. **Pretrained foundation models: Presto frozen (A3) and AlphaEarth (A5).** Stretch: Presto fine-tuned vs
   the same architecture with random weights, which isolates the effect of pretraining.

Why no trained 2D CNN in the core:

- Most labels are GPS points (one 10 m pixel); Malawi polygons are 0.4–0.6 ha (about 40–60 pixels). A
  64×64 chip is 640 m wide, so a 2D CNN mostly sees neighbours' land and learns landscape, which spatial
  splits then punish (Kattenborn et al. 2022 report up to 28 % inflation from autocorrelated validation).
- We have a few thousand noisy labels per cohort. Where deep models win on yield they are pretrained and
  trained on dense yield-monitor labels (Kamangir et al. 2026; Nejadshamsi et al. 2025); from-scratch
  sequence models scored at or below random forests on CY-Bench (Nedungadi et al. 2026).
- If time is left after G3, one small 2D CNN on the Kenya chip stack is the stretch item that answers the
  question literally.
