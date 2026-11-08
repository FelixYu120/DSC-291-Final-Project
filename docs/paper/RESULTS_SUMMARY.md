# Zimbabwe data preparation and results

We assembled **6,598 screened field-season records**: 2,266 Lacuna observations from 2022–2023 and 4,332 Zimbabwe 2024 observations. Preparation reconciled identifiers, coordinates, crop-cut arithmetic and yield units; excluded three inconsistent Lacuna records and 723 missing 2024 labels; and retained 1,874 recorded 2024 zeros. The two sources were aligned to a common December–June satellite window. Unknown moisture basis remains unresolved.

All target results below evaluate the **same 1,504 Lacuna 2023 fields**, using four spatial outer folds and inner model selection. Another 376 fields were excluded from current fitting and scoring. Added training observations were buffered by 2 km from protected fields. RMSE is in t/ha; R² is calculated from pooled held-out predictions.

| Model and training pool | RMSE ↓ | R² ↑ |
|---|---:|---:|
| Basic index Ridge, Lacuna | 1.7968 | 0.1800 |
| Basic index Ridge, naive pooling | 2.2707 | −0.3096 |
| Basic index Ridge, adaptive pooling | 1.7938 | 0.1827 |
| Monthly imagery Ridge, Lacuna | 1.6926 | 0.2723 |
| Monthly imagery trees, merged | 1.6578 | 0.3020 |
| Monthly + 46 weather features, merged trees | 1.7221 | 0.2467 |
| Monthly + 2 weather features, merged trees | 1.6740 | 0.2882 |
| Monthly + 4 weather features, shared merged Ridge | 1.6554 | 0.3040 |
| Preharvest bands, expanded Lacuna | 1.7480 | 0.2239 |
| Preharvest bands, expanded Lacuna + 2024 | 1.7490 | 0.2231 |

**What the experiments show.** Naive pooling harmed prediction. Source adjustment removed most of that penalty, but the basic adaptive merge improved RMSE by only 0.0030 t/ha; its 95% spatial-group interval included zero. Monthly imagery was more useful than simple seasonal index summaries. Adding all 46 NASA POWER weather features worsened performance; smaller weather sets partly recovered accuracy. Four-feature shared Ridge had the lowest observed RMSE, but its advantage over imagery-only merged trees was only 0.0023 t/ha, with interval [−0.0548, +0.0529]. It is a candidate for validation, not a confirmed overall winner. Internal 2024 prediction showed learnable signal, so weak transfer does not establish that the source labels are unusable.

**Seasonal aggregation and data availability.** Original preharvest-band means improved RMSE from 1.7984 to 1.7503 and R² from 0.1785 to 0.2219; median and modal summaries performed worse. The expanded experiment added 217 eligible 2023 fields before spatial buffering. All 169 Lacuna 2022 fields had only one or two common-window months, so none entered the models; two 2024 fields were also excluded. The latest aggregate models filled no missing imagery predictors. Adding 2024 still gave no clear gain.

**Team handoff.** Use the accompanying manuscript section for data sources and preparation. The results appendix contains all 149 target-arm rows and six separate source-diagnostic rows, with repeated controls identified. These are exploratory, retrospective comparisons; unknown moisture, single-pixel satellite support, coarse weather cells and provider/year confounding limit generalization.
