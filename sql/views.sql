-- Views of data/cropyield.duckdb. scripts/build_database.py runs this file after the tables are
-- filled (schema.sql). A view is a saved SELECT: it stores no data and is always up to date.
--
--   season_indices   one row per observation with data: season max and mean of each index
--   master           one row per labelled observation: labels + status + every feature (NULL if missing)
--   monthly          one row per downloaded observation x month: the sequence for GRU-type models


-- season_indices: the five monthly indices summarised over the season window.
-- max = the greenest month, mean = the average over the months that have a value (NULL months
-- are skipped by max() and avg()). This is a STARTING POINT for the baseline: its owner may
-- change the statistics (for example a peak window) and master follows automatically.
CREATE VIEW season_indices AS
SELECT obs_id,
       max(ndvi)    AS ndvi_season_max,
       avg(ndvi)    AS ndvi_season_mean,
       max(gcvi)    AS gcvi_season_max,
       avg(gcvi)    AS gcvi_season_mean,
       max(mtci)    AS mtci_season_max,
       avg(mtci)    AS mtci_season_mean,
       max(ndvi705) AS ndvi705_season_max,
       avg(ndvi705) AS ndvi705_season_mean,
       max(ndvi740) AS ndvi740_season_max,
       avg(ndvi740) AS ndvi740_season_mean
FROM vegetation_indices
GROUP BY obs_id;


-- master: one row per labelled observation, every feature next to its label.
-- LEFT JOIN keeps every label row; an observation without imagery gets NULL in every feature
-- column and has_imagery = FALSE. Filter with WHERE has_imagery for modelling.
CREATE VIEW master AS
WITH months_with_data AS (
    SELECT obs_id,
           count(*) FILTER (WHERE NOT missing) AS months_with_data
    FROM monthly_bands
    GROUP BY obs_id
)
SELECT labels.*,                                        -- every label column
       downloads.obs_id IS NOT NULL                     AS has_imagery,
       downloads.status                                 AS download_status,
       coalesce(months_with_data.months_with_data, 0)   AS months_with_data,
       season_indices.* EXCLUDE (obs_id),               -- ndvi_season_max ... ndvi740_season_mean
       presto_embeddings.embedding                      AS presto_embedding,     -- FLOAT[128]
       mosaiks_season.chip                              AS mosaiks_chip,         -- FLOAT[K]
       mosaiks_season.field                             AS mosaiks_field,        -- FLOAT[K]
       mosaiks_season.months_used                       AS mosaiks_months_used
FROM labels
LEFT JOIN downloads         USING (obs_id)
LEFT JOIN months_with_data  USING (obs_id)
LEFT JOIN season_indices    USING (obs_id)
LEFT JOIN presto_embeddings USING (obs_id)
LEFT JOIN mosaiks_season    USING (obs_id);


-- monthly: one row per downloaded observation x month of its season window, in time order
-- when you ORDER BY obs_id, month. For sequence models (GRU, Presto fine-tuning): the bands,
-- indices and MOSAIKS vectors of one month, NULL when that month has no clear scene, and the
-- label repeated on every row. coverage has exactly one row per month, so it is the spine.
CREATE VIEW monthly AS
SELECT coverage.obs_id,
       labels.cohort,
       coverage.month,
       coverage.state                AS coverage_state,  -- clear, cloudy, no_scene or download_error
       monthly_bands.b02,
       monthly_bands.b03,
       monthly_bands.b04,
       monthly_bands.b05,
       monthly_bands.b06,
       monthly_bands.b07,
       monthly_bands.b08,
       monthly_bands.b8a,
       monthly_bands.b11,
       monthly_bands.b12,
       vegetation_indices.ndvi,
       vegetation_indices.gcvi,
       vegetation_indices.mtci,
       vegetation_indices.ndvi705,
       vegetation_indices.ndvi740,
       mosaiks_monthly.chip          AS mosaiks_chip,    -- FLOAT[K], NULL when missing
       mosaiks_monthly.field         AS mosaiks_field,   -- FLOAT[K], NULL when missing
       labels.yield_kg_ha
FROM coverage
JOIN labels                  USING (obs_id)
LEFT JOIN monthly_bands      USING (obs_id, month)
LEFT JOIN vegetation_indices USING (obs_id, month)
LEFT JOIN mosaiks_monthly    USING (obs_id, month);
