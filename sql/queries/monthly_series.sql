-- monthly_series: the month-by-month sequence of every field of one cohort, in time order.
-- This is the input of a sequence model (GRU): every field has one row per month of its season
-- window; a month without a clear scene has NULL in every band, index and MOSAIKS column.
-- Change the cohort name in the WHERE line.
SELECT obs_id,
       month,
       coverage_state,
       b02, b03, b04, b05, b06, b07, b08, b8a, b11, b12,   -- median field reflectance
       ndvi, gcvi, mtci, ndvi705, ndvi740,                 -- vegetation indices of the month
       mosaiks_chip,                                       -- FLOAT[K] or NULL
       mosaiks_field,                                      -- FLOAT[K] or NULL
       yield_kg_ha                                         -- the label, same on every row of a field
FROM monthly
WHERE cohort = 'malawi_2023'
ORDER BY obs_id, month;
