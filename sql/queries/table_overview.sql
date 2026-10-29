-- table_overview: every table and view with its row count.
-- Run first after a build to see what the database holds. Views count the rows they return.
SELECT 'labels'             AS name, 'table' AS kind, count(*) AS rows FROM labels
UNION ALL
SELECT 'downloads',                  'table',         count(*)         FROM downloads
UNION ALL
SELECT 'scenes',                     'table',         count(*)         FROM scenes
UNION ALL
SELECT 'coverage',                   'table',         count(*)         FROM coverage
UNION ALL
SELECT 'monthly_bands',              'table',         count(*)         FROM monthly_bands
UNION ALL
SELECT 'vegetation_indices',         'table',         count(*)         FROM vegetation_indices
UNION ALL
SELECT 'presto_embeddings',          'table',         count(*)         FROM presto_embeddings
UNION ALL
SELECT 'mosaiks_monthly',            'table',         count(*)         FROM mosaiks_monthly
UNION ALL
SELECT 'mosaiks_season',             'table',         count(*)         FROM mosaiks_season
UNION ALL
SELECT 'build_info',                 'table',         count(*)         FROM build_info
UNION ALL
SELECT 'season_indices',             'view',          count(*)         FROM season_indices
UNION ALL
SELECT 'master',                     'view',          count(*)         FROM master
UNION ALL
SELECT 'monthly',                    'view',          count(*)         FROM monthly;
