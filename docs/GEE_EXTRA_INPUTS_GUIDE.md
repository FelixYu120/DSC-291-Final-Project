# Browser handoff: Earth Engine and Planet

Only these steps require Allen to use a browser. All public, no-login downloads
and the local matching/auditing are handled by the repository scripts.

## A. Export the exact missing Presto inputs and AlphaEarth from Earth Engine

1. Open the [Earth Engine Code Editor](https://code.earthengine.google.com/) and
   sign in to an approved Earth Engine project.
2. In **Assets**, choose **NEW → Table upload**. Upload
   `presto_extra_inputs_2026-11-09/derived/zimbabwe_field_months_2022_2023.csv`.
   Select `longitude` and `latitude` as the point-coordinate columns. Wait for
   ingestion to finish.
3. Copy the resulting asset ID. Open
   `scripts/optional/extra_inputs/gee_export_zimbabwe_presto_inputs.js`, paste it into a new
   Code Editor script, and replace `FIELD_MONTH_ASSET` with that asset ID.
4. Click **Run**. The Console must show **20,394 expected rows** and **20,394
   export rows**. Open **Tasks**, click **RUN** on the CSV export, and leave the
   default Drive folder/name unchanged.
5. Download `zimbabwe_presto_s1_era5_srtm_2022_2023.csv` from the Google Drive
   folder `DSC291_Zimbabwe_Presto` and put it in
   `presto_extra_inputs_2026-11-09/incoming/`.

The export includes raw values, Presto-normalized values, and the 64 AlphaEarth
annual embedding dimensions for the observation's season/harvest year. Sentinel-1 is
exported separately for ascending and descending passes so that the local
integration step can choose one pass per observation without mixing radar
viewing geometries within a season. Missing pixels are `-9999` and scene-count
columns are included; no missing data are silently replaced by zero.

## B. PlanetScope access/coverage check

1. Apply with the university email for [Planet Education & Research
   Basic](https://account.planet.com/industries/education-and-research/).
2. After approval, search the 2,266 points for October 2021–June 2023 using
   PlanetScope Surface Reflectance, then export only a coverage/metadata CSV
   first. Do not order imagery before the monthly area allowance is checked.
3. Save the metadata CSV in `presto_extra_inputs_2026-11-09/incoming/`.

For NICFI, after the account has permission to the publisher collection, paste
`scripts/optional/extra_inputs/gee_check_zimbabwe_nicfi.js` into Earth Engine, replace its
asset ID, and run it. It exports only a small coverage table, not imagery, so
the team can decide whether the source is usable before spending download or
processing time.

Planet approval is not guaranteed. The former NICFI public program ended in
January 2025; its historical 2022–2023 Africa mosaics may still be visible only
under purpose-restricted access. PlanetScope is therefore an optional extension,
not a dependency of the core Presto experiment.
