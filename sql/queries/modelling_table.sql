-- modelling_table: one cohort, one row per field with imagery: the label and every feature.
-- Change the cohort name in the WHERE line (see labels.cohort for the names). In Python,
-- cropyield.data.database.wide() turns the array columns into numbered columns for scikit-learn.
SELECT obs_id,
       cohort,
       yield_kg_ha,              -- the label (y)
       months_with_data,         -- months with a clear scene: 0 up to the window length (9 Oct-Jun, 8 Feb-Sep)
       ndvi_season_max,          -- season index summaries (X for the Ridge baseline) ...
       ndvi_season_mean,
       gcvi_season_max,
       gcvi_season_mean,
       mtci_season_max,
       mtci_season_mean,
       ndvi705_season_max,
       ndvi705_season_mean,
       ndvi740_season_max,
       ndvi740_season_mean,
       presto_embedding,         -- FLOAT[128]: the frozen Presto embedding
       mosaiks_chip,             -- FLOAT[K]: MOSAIKS season mean of the chip (NULL until built)
       mosaiks_field,            -- FLOAT[K]: MOSAIKS season mean of the field pixels
       mosaiks_months_used
FROM master
WHERE cohort = 'malawi_2023'
  AND has_imagery
  AND months_with_data > 0
ORDER BY obs_id;
