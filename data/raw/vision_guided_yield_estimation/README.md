# Vision-guided crop-yield dataset

Source: [Zenodo record 17626117](https://zenodo.org/records/17626117), *Scalable Vision-Guided Crop Yield Estimation Dataset*, CC BY 4.0.

The record covers maize and rice fields in Nigeria (2022) and Zimbabwe (2024). It provides `metadata.csv` with crop, year, country, plot identifier, field-photo URLs, crop-cut box measurements, mean yield, and point coordinates. The optional `q_field_photo.zip` archive is about 4.9 GB and contains the field photographs. The provider reports that identifiable individuals were removed from released images.

The metadata CSV is retained in this repository. The photo archive is local-only because GitHub cannot store a file of this size; download or resume it with:

```bash
python scripts/download_vision_guided_yield_data.py
```

To fetch only the metadata CSV, run:

```bash
python scripts/download_vision_guided_yield_data.py --metadata-only
```

The script writes Zenodo's record JSON to `data/metadata/zenodo_17626117_record.json` and file sizes/checksums to `data/metadata/vision_guided_yield_download_manifest.json`. It verifies the publisher's MD5 and stores SHA-256 values. Interrupted photo downloads can be resumed by rerunning the command.

The audit treats `Avg_yield_mt_ha` as metric tonnes per hectare and converts it to `yield_kg_ha`. It retains zero yields and records the field-photo URL and per-box measurement fields. It extracts an approximate observation date from the field-photo filename because the CSV has no planting or harvest dates; this timestamp is only a proxy for survey/crop-cut timing and is flagged for review. A passing location check is only a candidate: the coordinate must be checked against the field and the satellite observation window before it is used as a field-level label. The published dataset includes rice rows, which are retained in the source CSV but are not in the maize audit output.

Attribute the data to the dataset authors and retain the CC BY 4.0 notice when using or redistributing material. See the Zenodo record for the complete author list and citation.
