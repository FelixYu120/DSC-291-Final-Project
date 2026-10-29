-- Schema of data/cropyield.duckdb: one CREATE TABLE per table, in pipeline order.
--
-- scripts/build_database.py runs this file on a new, empty database, fills every table from
-- Python, and then runs views.sql. Nobody needs to run this file by hand.
--
-- The key of every table is obs_id = "<dataset>:<source_id>": one field in one season. Two
-- tables join on obs_id; the monthly tables also need the month ('YYYY-MM').
--
-- Vectors are stored as arrays, one value per row: FLOAT[128] is a fixed length, FLOAT[] any
-- length. Read them with embedding[1] (arrays start at 1), len(embedding), or in Python with
-- cropyield.data.database.wide(), which turns one array column into numbered columns.


-- 1. labels: one row per observation of every cohort, with or without imagery.
--    Source: the committed audit CSVs, filtered by cropyield.data.cohorts.
CREATE TABLE labels (
    obs_id              VARCHAR NOT NULL,  -- "<dataset>:<source_id>", the key of every table
    cohort              VARCHAR NOT NULL,  -- cohort name, cropyield.data.cohorts.COHORTS
    dataset             VARCHAR NOT NULL,  -- audit dataset, data/audit/<dataset>_screened_candidates.csv
    source_id           VARCHAR NOT NULL,  -- the provider's id of the observation
    source_row          INTEGER NOT NULL,  -- row in the provider file
    country             VARCHAR NOT NULL,  -- lower case, e.g. malawi
    year                INTEGER NOT NULL,  -- harvest year
    yield_kg_ha         DOUBLE NOT NULL,   -- the label: maize yield in kg per hectare
    source_yield        DOUBLE,            -- yield as the provider wrote it, in source_yield_units
    source_yield_units  VARCHAR,           -- unit of source_yield, e.g. t/ha
    yield_field         VARCHAR,           -- provider column the yield came from
    latitude            DOUBLE NOT NULL,   -- WGS84 degrees; polygon centroid for polygon fields
    longitude           DOUBLE NOT NULL,   -- WGS84 degrees
    geometry_type       VARCHAR,           -- Point, Polygon or MultiPolygon
    field_area_ha       DOUBLE,            -- only where the provider gives it (Malawi)
    label_date          DATE,              -- harvest date, else crop-cut date; NULL if neither is known
    season_start        DATE NOT NULL,     -- fixed season window per agro-zone (docs/DECISIONS.md)
    season_end          DATE NOT NULL,     -- last day of the season window
    intercropping       VARCHAR,           -- provider flag as text ("0", "no", "yes"); NULL if absent
    field_polygon       VARCHAR            -- GeoJSON geometry text of the field (Malawi); NULL for points
);


-- 2. downloads: one row per observation that has a Sentinel-2 chip folder.
--    Source: record.json of each folder under data/imagery/sentinel2/run-*/records/.
CREATE TABLE downloads (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    record_dir          VARCHAR NOT NULL,  -- chip folder, relative to the repository root
    status              VARCHAR NOT NULL,  -- downloader status: complete, no_clear_scenes, error, ...
    aoi_type            VARCHAR NOT NULL,  -- field_polygon or point_pixel
    aoi_pixels          INTEGER NOT NULL,  -- pixels the field polygon touches (or the one point pixel)
    field_pixels        INTEGER NOT NULL,  -- pixels used as the field: centres inside the polygon
    aoi_inside_chip     BOOLEAN NOT NULL,  -- whole field inside the 64 x 64 chip
    catalog_scenes      INTEGER,           -- scenes the STAC catalogue offered for the window
    accepted_months     INTEGER NOT NULL,  -- months with an accepted (clear enough) scene
    crs                 VARCHAR NOT NULL,  -- chip grid, e.g. EPSG:32736
    search_start        DATE,              -- window the downloader searched (= the season window)
    search_end          DATE               -- end of that window
);


-- 3. scenes: one row per accepted Sentinel-2 scene (at most one per month per observation).
CREATE TABLE scenes (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    item_id             VARCHAR NOT NULL,  -- STAC item, e.g. S2B_T36LWL_20230113T080204_L2A
    acquired            DATE NOT NULL,     -- day the satellite took the image
    month               VARCHAR NOT NULL,  -- 'YYYY-MM' of acquired
    satellite           VARCHAR NOT NULL,  -- S2A, S2B or S2C
    tile                VARCHAR NOT NULL,  -- MGRS tile, e.g. 36LWL
    tile_cloud_cover    DOUBLE,            -- percent cloud over the whole tile (catalogue value)
    clear_fraction_aoi  DOUBLE NOT NULL,   -- clear, valid share of the AOI pixels (downloader check)
    field_valid_pixels  INTEGER NOT NULL   -- field pixels that are clear and valid in this scene
);


-- 4. coverage: one row per downloaded observation x month of its season window.
--    Says why a month has or has no data.
CREATE TABLE coverage (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    month               VARCHAR NOT NULL,  -- 'YYYY-MM', every month of the season window
    state               VARCHAR NOT NULL,  -- clear, cloudy, no_scene or download_error
    item_id             VARCHAR            -- the accepted scene when state = clear
);


-- 5. monthly_bands: one row per observation x month: median reflectance of the field pixels.
--    Sentinel-2 L2A surface reflectance, 0 to 1. Only observations with at least one scene.
CREATE TABLE monthly_bands (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    month               VARCHAR NOT NULL,  -- 'YYYY-MM'
    b02                 DOUBLE,            -- blue; NULL when the month has no clear field pixel
    b03                 DOUBLE,            -- green
    b04                 DOUBLE,            -- red
    b05                 DOUBLE,            -- red edge 1 (705 nm)
    b06                 DOUBLE,            -- red edge 2 (740 nm)
    b07                 DOUBLE,            -- red edge 3 (783 nm)
    b08                 DOUBLE,            -- near infrared (NIR)
    b8a                 DOUBLE,            -- narrow NIR (865 nm)
    b11                 DOUBLE,            -- shortwave infrared 1 (1610 nm)
    b12                 DOUBLE,            -- shortwave infrared 2 (2190 nm)
    field_pixels        INTEGER NOT NULL,  -- clear field pixels behind the medians (0 when missing)
    missing             BOOLEAN NOT NULL   -- no accepted scene, or no clear field pixel, this month
);


-- 6. vegetation_indices: one row per observation x month, computed from monthly_bands.
--    The five indices of Lobell et al. (2020), Table 2; cropyield.features.indices.
CREATE TABLE vegetation_indices (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    month               VARCHAR NOT NULL,  -- 'YYYY-MM'
    ndvi                DOUBLE,            -- (b08 - b04) / (b08 + b04); NULL when the month is missing
    gcvi                DOUBLE,            -- b08 / b03 - 1
    mtci                DOUBLE,            -- (b08 - b05) / (b05 - b04)
    ndvi705             DOUBLE,            -- (b08 - b05) / (b08 + b05)
    ndvi740             DOUBLE             -- (b08 - b06) / (b08 + b06)
);


-- 7. presto_embeddings: one row per observation with at least one month of data.
--    Output of the frozen, pretrained Presto encoder (cropyield.models.presto).
CREATE TABLE presto_embeddings (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    embedding           FLOAT[128]         -- the 128 Presto numbers; embedding[1] is the first
);


-- 8. mosaiks_monthly: one row per observation x month from data/features/mosaiks/monthly.parquet.
--    Random convolutional features (MOSAIKS) of the chip; K = build_info.mosaiks_features.
--    Empty when the features were not made yet: python scripts/features/mosaiks_features.py
CREATE TABLE mosaiks_monthly (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    month               VARCHAR NOT NULL,  -- 'YYYY-MM'
    chip                FLOAT[],           -- K features of the whole 64 x 64 chip; NULL when the month is missing
    field               FLOAT[]            -- K features of the field pixels only; NULL when missing
);


-- 9. mosaiks_season: one row per observation from data/features/mosaiks/season.parquet.
--    The season mean of the monthly MOSAIKS vectors.
CREATE TABLE mosaiks_season (
    obs_id              VARCHAR NOT NULL,  -- key, see labels
    months_used         INTEGER,           -- months in the chip mean; the field mean skips months whose field pixels were all invalid
    chip                FLOAT[],           -- K features, season mean over the whole chip
    field               FLOAT[]            -- K features, season mean over the field pixels
);


-- 10. build_info: exactly one row: when, from which code and from which folders this file was built.
CREATE TABLE build_info (
    built_at                TIMESTAMP NOT NULL,  -- UTC
    git_commit              VARCHAR,             -- repository commit the script ran from
    presto_commit           VARCHAR,             -- nasaharvest/presto commit of the vendored code and weights
    presto_weights_sha256   VARCHAR,             -- checksum of the weights file; NULL with --no-presto
    presto_embeddings_built BOOLEAN NOT NULL,    -- FALSE when built with --no-presto
    imagery_dir             VARCHAR NOT NULL,    -- chip folder the build read
    n_labels                INTEGER NOT NULL,    -- rows in labels
    n_downloads             INTEGER NOT NULL,    -- rows in downloads
    n_embeddings            INTEGER NOT NULL,    -- rows in presto_embeddings
    mosaiks_features        INTEGER,             -- K, the length of every MOSAIKS vector; NULL when not built
    mosaiks_params          VARCHAR              -- data/features/mosaiks/params.json as text; NULL when not built
);
