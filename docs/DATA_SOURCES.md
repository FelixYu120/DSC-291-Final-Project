# Crop-yield data and geospatial predictor catalog

This catalog combines field-label sources and predictor products for the project. Availability and product contents can change between releases; use each provider's record for the exact version, terms, citation, and download instructions. Public or no-cost access does not make sources comparable in measurement method or geographic scale.

## How these sources fit the study

The primary experiment is field-level maize yield prediction at previously unseen locations. Only observations with a defensible field location, documented yield definition, and matching season belong in its training labels. Keep crop cuts, farmer reports, photos, and statistical estimates identifiable as separate label types.

Administrative and national yields are useful for separate regional benchmarks and long-term comparisons, but they are not extra field labels. Satellite, weather, soil, crop-mask, and field-boundary products are predictors or geographic support layers; they do not supply measured yield. The source and scale of every training and test record should remain visible in outputs.

## Field-level and plot-level yield labels

| Source | Coverage and content | Access and project use |
|---|---|---|
| [One Acre Fund full monitoring and evaluation release](https://data.harvestportal.org/dataset/oaf_mel) | Multi-country workbook (2015–2020) with crop-cut yield, field-coordinate columns, dates, and management variables. | Public catalogue, CC BY as reported by the provider. Already downloaded under `data/raw/one_acre_fund_full/`. Some locations may be homestead/site points; review the source flags. |
| [One Acre Fund curated maize release](https://doi.org/10.5281/zenodo.11122388) | Maize in pure stands in seven countries, 2016–2022, with yield and management/environmental fields. | Zenodo, CC BY 4.0. Already downloaded. It overlaps the full OAF workbook and mixes field, town, and district coordinate precision, so do not add its count to the primary total. |
| [Zimbabwe Lacuna yield data](https://doi.org/10.5281/zenodo.10060610) | Multi-crop point observations with harvest weights, yield, and dates; the local release includes maize from 2022–2023. | Zenodo, CC BY 4.0. Already downloaded under `data/raw/zimbabwe/`. Verify the provisional yield-unit interpretation before pooling. |
| [FAO / NASA Harvest Malawi crop cuts](https://data.harvestportal.org/dataset/fao-bha-nasa-harvest-public-yield-datasets) | Malawi maize crop-cut yields and field polygons for 2022 and 2023, with dictionaries and campaign methods. | Public Harvest Portal release; downloaded files state CC BY. Already under `data/raw/malawi/`, `data/raw/malawi_metadata/`, and `data/raw/malawi_field_dictionary/`. Crop-cut designs differ between years. |
| [Vision-guided crop-yield dataset](https://zenodo.org/records/17626117) | Field photographs, coordinates, box weights, and plot-level yields for maize and rice in Zimbabwe (2024) and Nigeria (2022). The record lists 6,932 rows; all 5,729 maize rows have field-photo links, and the project audit screens 4,712 yield/location candidates (4,332 Zimbabwe; 380 Nigeria). The archive member name contains the `cce_id`, which is retained in the audit output. | Zenodo, CC BY 4.0. `metadata.csv` is in `data/raw/vision_guided_yield_estimation/`; the roughly 4.9 GB `q_field_photo.zip` is local-only and fetched with `python scripts/download_vision_guided_yield_data.py`. Candidate locations still require field/imagery validation. |
| [GROW-Africa v2](https://zenodo.org/records/16544448) | 535,844 georeferenced yield observations across 25 crops in Africa, 1960–2023, from crop cuts, household surveys, point observations, and regional statistics. | Public Zenodo files, CC BY 4.0. A useful source for identifying measured maize subsets and expanding country/year coverage after filtering by source table, method, and spatial precision. Its rows are not all field-level. |
| [TAMASA](https://tamasa.cimmyt.org/tools-data/tamasa-data/) | Maize agronomy research in Ethiopia, Nigeria, and Tanzania, including surveys, crop cuts, soils, and management measurements; years and protocols depend on the component. | Access through CIMMYT data pages (some components require portal registration). Useful for measured-yield and management analyses; verify exact coordinate availability and crop-cut protocol for each release. |
| [LSMS-ISA](https://www.worldbank.org/en/programs/lsms/initiatives/lsms-ISA) | Household and agricultural plot surveys in several African countries, with reported harvest/area and some crop cuts, depending on round. | Public microdata access through the World Bank survey catalog, generally with a free account/registration. Coordinates may be masked or displaced; do not assume they align to individual 10 m pixels. |
| [YieldSAT](https://yieldsat.github.io/) | GPS combine-harvester yield maps for maize, soybean, wheat, and rapeseed in Argentina, Brazil, Uruguay, and Germany (2016–2024); the cited source note reports 303 maize fields. | Access through the linked request form. A useful field-scale comparison for mechanized farming, but not automatically representative of smallholder African systems. |
| [SICKLE](https://github.com/Depanshu-Sani/SICKLE) | Plot-level rice crop/yield and crop-calendar labels in Tamil Nadu, paired with Sentinel-1, Sentinel-2, and Landsat sequences. | Access through the repository-linked form. Rice-only, so it is not a maize training set; it can test whether the Presto pipeline handles smallholder temporal sequences. |

## Regional and national yield benchmarks

| Source | Coverage and content | Access and project use |
|---|---|---|
| [CY-Bench](https://zenodo.org/records/17279151) | Subnational annual crop-yield statistics and predictors for maize (38 countries) and wheat (29 countries), with coverage varying by country. | Public Zenodo record; the record identifies EUPL-1.2. The main archive is about 6.2 GB, plus polygon and centroid files. Keep these administrative-unit labels in a separate regional forecasting benchmark, never in the field-level candidate count. |
| [HarvestStat-Africa](https://github.com/HarvestStat/HarvestStat-Africa) | Harmonized subnational production, area, and yield statistics compiled from FEWS NET, FAO, and national agencies. | Public GitHub repository. Good for regional trends and cross-region transfer at matching administrative units; these are statistical estimates, not direct field measurements. |
| [USDA NASS Quick Stats](https://quickstats.nass.usda.gov/) | U.S. county/state crop statistics, including corn yield, area, and production; coverage varies by crop, year, and geography. | Free API after requesting a key. The project has an optional county-yield downloader under `scripts/download_usda_nass.py`. Keep county estimates separate from African field labels. |
| [FAOSTAT](https://www.fao.org/faostat/en/#data) | National crop yield, production, and area time series for many countries, with reported, estimated, or imputed values identified by flags. | Public database. Use for national context, trends, and consistency checks, not field-level ground truth. |

## Satellite and environmental predictors

| Source | Coverage and resolution | Use and access notes |
|---|---|---|
| [Sentinel-2](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2) | Multispectral surface reflectance, generally 10/20/60 m, with coverage from 2015 onward. | Seasonal field features for completed-season or cutoff-defined prediction. The project downloader uses public Sentinel-2 L2A cloud-optimized scenes from Earth Search; document scene IDs, dates, clouds, and processing. |
| [NASA Harmonized Landsat and Sentinel-2 (HLS)](https://www.earthdata.nasa.gov/centers/lp-daac) | Harmonized 30 m Landsat/Sentinel-2 surface reflectance, with series beginning in 2013. | Denser time series for larger fields or regional work; Earthdata login may be needed. Mixed pixels can limit small-field use. |
| [CHIRPS v3](https://www.chc.ucsb.edu/data/chirps3) | Rainfall estimates blended with gauges at 0.05° from 1981 to near-present. | Rain totals, anomalies, dry spells, and timing. Grid-cell rainfall is not a field weather-station measurement. |
| [ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land) | Global modeled land variables from 1950 onward, hourly, approximately 9 km. | Temperature, soil moisture, radiation, and extremes; use as coarse context, not field microclimate. CDS account/API setup is required. |
| [NASA POWER](https://power.larc.nasa.gov/) | Global daily meteorology and radiation; variable histories and resolutions differ. | Rapid weather baseline with a documented API. Check parameter source and native resolution. |
| [SoilGrids](https://isric.org/explore/soilgrids/) | Global modeled soil properties at 250 m and standard depth intervals. | Static soil context, with uncertainty layers; not seasonal field soil measurements. |
| [FAO WaPOR](https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data-access/en) | Remote-sensing/model products such as evapotranspiration and net primary production; coverage, resolution, and periods depend on level/product. | Water-use and stress covariates, not direct yield or farmer irrigation records. Check current access requirements and product version. |
| [WorldCereal](https://esa-worldcereal.org/en/products/global-maps) | Satellite-derived crop and irrigation maps, including a 2021 global product family at 10 m. | Maize/cropland masks and irrigation strata. These are classification outputs; confirm year and season compatibility before use. |
| [SRTM](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-shuttle-radar-topography-mission-srtm) | Radar-derived elevation observed primarily in 2000, near 30 m, approximately 60°N–56°S. | Static elevation/slope/aspect covariates, not seasonal weather or soil. |
| [AlphaEarth Foundations annual embeddings](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL) | 64 learned features per 10 m pixel per year; the Earth Engine catalog lists 2017–2024. | Downstream regression features, not an encoder checkpoint to fine-tune. Same-year embeddings are retrospective; use a prior-year embedding for a pre-harvest task. Earth Engine access and terms apply. |

## Field boundaries and other spatial support

| Source | Content | Use and access notes |
|---|---|---|
| [Fields of The World](https://fieldsofthe.world/) | A benchmark with labeled parcels and separate model-predicted field-boundary products. | Use for boundary extraction or field-size support, not as yield labels. Keep surveyed/reference boundaries distinct from predicted polygons and verify year/location coverage. |

## Suggested use in this project

1. Use Malawi crop cuts and boundaries as the initial field-level satellite benchmark, then add the best-verified Zimbabwe, OAF, and vision-guided maize observations with source-specific metrics.
2. Treat GROW-Africa as a discovery/expansion source. First isolate maize and crop-cut or otherwise documented plot-level measurements; use its spatial-precision field and source table to screen locations. Do not count all 535,844 rows as usable field labels.
3. Keep CY-Bench, HarvestStat-Africa, USDA NASS, and FAOSTAT in scale-matched regional or national benchmarks. Do not upsample their statistical units into fictitious field observations.
4. Use Sentinel-2 or HLS as seasonal inputs; AlphaEarth as a frozen annual-embedding baseline; and Presto as a fine-tunable time-series model. Join weather, soils, crop masks, and terrain only at their documented native scale and respect forecast cutoffs.
5. Report the number of raw rows, maize rows, valid yield/location rows, field-photo/image availability, and imagery-matched rows separately. Keep all repeated fields and spatial clusters together when splitting train and test data.

## License and data handling

Check each record's license before downloading, storing, or redistributing. The Zenodo photo archive is CC BY 4.0 and is excluded from Git because of its size; the dataset authors and source record must be cited. CY-Bench's Zenodo record lists EUPL-1.2, which differs from the CC BY terms on several other sources. Respect access forms, registration requirements, disclosure rules, and coordinate-privacy conditions for each provider. Store raw files by source release under `data/raw/` and derived, harmonized tables under `data/processed/by_country/` or a clearly scale-labeled regional benchmark folder.
