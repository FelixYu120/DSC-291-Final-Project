-- coverage_by_cohort: how many field-months of each cohort are clear, cloudy, without a scene
-- or failed to download, and the share of clear months.
-- One row per cohort. Only observations with a chip folder have coverage rows.
SELECT labels.cohort,
       count(DISTINCT coverage.obs_id)                            AS fields_with_imagery,
       count(*)                                                   AS field_months,
       count(*) FILTER (WHERE coverage.state = 'clear')           AS clear,
       count(*) FILTER (WHERE coverage.state = 'cloudy')          AS cloudy,
       count(*) FILTER (WHERE coverage.state = 'no_scene')        AS no_scene,
       count(*) FILTER (WHERE coverage.state = 'download_error')  AS download_error,
       round(100.0 * count(*) FILTER (WHERE coverage.state = 'clear') / count(*), 1) AS clear_percent
FROM coverage
JOIN labels USING (obs_id)
GROUP BY labels.cohort
ORDER BY labels.cohort;
