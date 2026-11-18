# Zimbabwe maize yield atlas

The notebook opens with measured maize yield, followed by prediction error, seasonal greenness and weather. All four maps use actual Sentinel-2 imagery as their geographic backdrop. Full-resolution figures and captions are available below. [Open the executed notebook](../../notebooks/zimbabwe_visual_atlas.ipynb).

![Measured maize yield over Zimbabwe with Guruve and Shurugwi close-ups and three harvest years](yield_map.png)

## Map captions

**Measured maize yield, 2022–2024.** Each circle marks the recorded location of a crop cut. Color gives measured yield in tonnes per hectare, from blue for lower yield to red for higher yield. Coincident records share one mean for that harvest. The national views contain 169 plotted locations in 2022, 2,089 in 2023 and 4,280 in 2024. Nearby locations can overlap at national scale. The 60 km × 30 km close-ups enlarge two densely sampled regions. Guruve has 107 records at 107 locations and Shurugwi has 288 records at 284 locations. The screened 2024 catalog includes 1,874 recorded zeros. Of its 4,332 records, 52 fall outside the generalized border. [Full-size yield figure](yield_map.png) · [Coverage and zoom windows](map_data_summary.json).

**Measured yield, estimated yield and error.** The first two columns compare crop cuts and held-out A1 Ridge estimates in t/ha at the same recorded coordinates. In the third column, red means overprediction and blue means underprediction. Values at or beyond ±4 t/ha share the end colors. The top row covers 1,504 held-out fields at 1,497 locations. The second row enlarges Shurugwi, where 170 fields occupy 167 locations. Repeated coordinates are averaged for display. [Full-size prediction figure](prediction_map.png) · [Saved field predictions](../../experiments/presto_finetune/runs/zimbabwe_lacuna_2022_2023/).

**Seasonal greenness.** Each month shows GCVI at the same 1,046 locations with usable Sentinel-2 observations for all three months in 2023. The 1,050 matched fields have a median across plotted locations of 2.48 in January, 2.80 in February and 2.50 in March. Yellow-green marks higher greenness, with values at or above 6 sharing the upper color. The bottom row follows 163 Shurugwi locations in the same geographic window as the yield and prediction maps. [Full-size greenness figure](greenness_map.png) · [Imagery handoff](../../data/processed/zimbabwe_midterm_v2/README.md).

**Rainfall and temperature.** Each column shows January–March weather in one harvest year. Brown indicates drier conditions, teal wetter conditions, blue cooler temperatures and red warmer temperatures relative to 1991–2020. Shading blends adjacent POWER values within the archived footprint. The 86 dots identify native cell centers inside the country. All 97 original cells contribute to the reported summaries, including 11 whose footprints cross the Zimbabwe border. The native spacing is 0.5° latitude × 0.625° longitude. In 2024, median rainfall across cells was 62% of normal and median temperature was 1.34 °C above normal. [Full-size weather figure](weather_map.png) · [Processed weather](../../data/processed/zimbabwe_weather_v2/README.md).

## Other figures

| Figure | What it shows |
|---|---|
| [Yield distributions](yield_distributions.png) | Cumulative proportions for all screened yields and for the v2 primary-label population, including screened records outside the map outline. |
| [Seasonal greenness by yield group](seasonal_gcvi.png) | Monthly median and interquartile range of observed GCVI in three measured-yield groups. Counts beneath each panel show imagery coverage. |
| [Crop-cut and model agreement](yield_agreement.png) | A1 and frozen Presto predictions on 1,504 held-out fields, followed by means for the same fields in 19 provider administrative units. |
| [Weather and yield correlations](weather_yield_correlations.png) | Correlations across cells with at least five v2 primary records from that harvest. The 2023 panel covers 31 cells and 1,871 fields. The 2024 panel covers 61 cells and 2,435 fields. [Cell means](weather_yield_cell_means.csv). |

## Sources and reproduction

The designs adapt the overview and linked zooms in Fig. 5 and the crop-cut, distribution and correlation comparisons in Jin et al. The grayscale basemap uses the 2016 EOxCloudless mosaic by EOX IT Services GmbH, containing modified Copernicus Sentinel data 2016. The national backdrop and the two regional crops were converted to grayscale and reprojected. The same historical mosaic supplies geographic context across seasons. The boundary and city locations come from Natural Earth. [Jin et al. (2019)](https://doi.org/10.1016/j.rse.2019.04.016) · [EOX Maps](https://maps.eox.at/) · [EOX CC BY 4.0 licence](https://creativecommons.org/licenses/by/4.0/) · [Imagery provenance and checksums](sources/satellite_basemap_provenance.json) · [Boundary and cities](sources/natural_earth_provenance.json).

The [figure inventory](figure_inventory.csv) traces 106 gallery figures to 118 source occurrences. Each of the 106 figures has its own explanation embedded below the gallery previews in the notebook and recorded in the inventory. Of the 106, 84 are saved visuals and 22 are reconstructions from committed data. Each contact sheet links to the originals. Enter a gallery ID in the last notebook cell to open the figure at full resolution. [GitHub source snapshot](https://github.com/FelixYu120/DSC-291-Final-Project/tree/8de629aba00ea3cda483fc8f113db38fe8961869).

To rebuild, run the notebook in a Git checkout containing the gallery source revision, using the repository's Python environment. The figure code reads tracked tables and local georeferenced imagery. [Requirements](../../requirements.txt) · [Main map code](../../scripts/paper/atlas_maps.py) · [Greenness map code](../../scripts/paper/atlas_greenness_map.py) · [Basemap reader](../../scripts/paper/atlas_basemap.py).
