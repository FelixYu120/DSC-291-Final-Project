# United States: USDA NASS Quick Stats

This folder is reserved for the optional U.S. corn-yield extension. The USDA
NASS Quick Stats API publishes state and county agricultural estimates; these
are **not field-level yield measurements and do not identify individual
farms**. Keep this benchmark separate from the Africa field-level models.

Download annual county-level corn yield rows for 2019–2024 (the default period
that overlaps the currently listed AlphaEarth annual collection) with:

```bash
export USDA_NASS_API_KEY="your-key"
python scripts/download_usda_nass.py
```

Request an API key on the [USDA NASS Quick Stats API page](https://quickstats.nass.usda.gov/api).
The downloader reads the key from the `USDA_NASS_API_KEY` environment
variable, checks the API's count endpoint before requesting the rows, and does
not save the key. The CSV and `query_provenance.json` are created in
`county_yield/`. A state+county FIPS column is added where both identifiers
are available. The other NASS values and units are left as returned; inspect
`short_desc`, `unit_desc`, and `Value` before selecting a corn-grain target.

County yields can support a separate regional-scale regression: join the rows
to county polygons by FIPS, summarize AlphaEarth pixels or field predictions
within those polygons, and compare at the county-year level. Do not replace a
county boundary with a centroid and call it a farm location, or combine these
rows with field-level labels as independent field observations. County
estimates may be missing or suppressed in some years; preserve those statuses
as published.

NASS states that most information on its site is public domain and may be
freely downloaded and reproduced, and requests appropriate USDA-NASS
acknowledgement. See its [citation request](https://www.nass.usda.gov/Data_and_Statistics/Citation_Request/)
and the applicable Quick Stats terms. Do not commit your API key.
