> **Copy of the owner's plan of 5 Nov 2026** (file time 2026-11-05 08:00 CET), taken on 7 Nov 2026 so that the team can read the
> rules that were written before any v2 score (section 6). The first v2 scores ran on 7 Nov 2026 at 18:43. The text is unchanged except
> one line: the local folder of the advisor reports is left out. Later decisions are in `docs/DECISIONS.md`.

# Crop yield v2 data plan: more photos per month, and Malawi 2022

5 November 2026. A plan, not code: nothing in `C:\Dev\DSC-291-Final-Project` has been changed.
Sources: my own read-only checks, and four independent read-only advisors on one shared fact sheet:
Fable 5.1 at xhigh effort (lever 1), Opus 5.5 (lever 2 and the freeze), Codex CLI (code audit), Grok CLI (time and payoff).
Their reports and scripts stay with the owner (local folder, not in the repo).

---

## 1. What we found before planning

| # | Finding | Checked by |
|---:|---|---|
| 1 | **The recovered Malawi 2022 data is there:** 529 of 529 fields `complete`, every polygon inside its chip, 5–9 clear months per field, March clear in 87 %. Window = the frozen label window. | me, Codex, Fable, Opus |
| 2 | **309 of its 4,209 scenes are 0.1 too low in every band** (negative blue). They come from **6 satellite images** of April–June 2022 (processing baseline 04.00) that lack Earth Search's "offset already removed" flag; the recovery script then subtracted 0.1 a second time. | me, Codex, Fable, Opus |
| 3 | **The 3 Nov Malawi 2022 yield probe used these wrong values.** `ndvi_season_max` is above 1 in 150 fields; 243 field maxima come from the bad images. Spearman(max, yield) is −0.026 as stored and +0.047 after the fix. The Malawi 2022 numbers in `Crop yield experiments and findings 2026-11-05.pdf` (§7) must be computed again. | Opus |
| 4 | **The label-free datum result stands.** Run again on a 6 m grid, the minimum sits at (−24 m E, +24 m N) as stored, without the 309 scenes, and with the fix. That is exactly the named transformation EPSG:1113. | Opus |
| 5 | **More tries alone fill little.** With the current tile-cloud limit (≤ 80 %), only 1,361 non-clear model field-months have any untried photo (4,400 untried photos in total). Malawi: 125 of 433 cloudy months, not 221 as an earlier review said. Malawi March: 20 of 128. | me, Codex, Fable |
| 6 | **Most empty months are catalogue gaps** (6,048 field-months: Oct–Nov 2022 in Malawi 2023 and Lacuna 2023, Feb 2019 in Kenya). Only another collection can fill them. | me, all advisors |
| 7 | **The catalogue cache is exactly what v1 saw** (all 11,364 records: same matches, same order). So extra tries need **no new catalogue search**. | Fable |
| 8 | **A command-line trap:** typing `--max-cloud-cover 80` makes it the float 80.0, not the integer 80. That gives a new run folder and a full new catalogue search. Never pass that flag. | Fable |
| 9 | **v1 is reproducible today:** `build_labels()` gives `labels_v1` byte for byte; the default downloader config still gives `run-517bfcf0a69c6cac`. | Opus, my notebooks |

---

## 2. Decisions, where the advisors disagreed

| Question | Options raised | Decision | Why |
|---|---|---|---|
| How to fix the 309 bad scenes | add 0.1 to copies (Codex, Grok); re-download those 309 (Fable); **download all 529 again** with the fixed rule and the shifted polygons (Opus) | **Download all 529 again** into the v2 folder | The shifted polygons need new chips anyway (49 scenes fall below the 0.8 rule on the shifted field, and chips are centred on the field point). One clean run costs about 15–20 minutes. The recovered chips stay untouched as evidence. |
| Offset rule for the older collection | "always 0" (too wide); "baseline ≥ 04 → 0" (Fable, Grok); **only the 4 measured cases → 0, anything else rejected** (Opus) | **Whitelist of the 4 measured cases** | 3 unflagged images of baseline 05.10 were never measured. A whitelist cannot silently store a wrong value. |
| Polygon position | measured offset (−20, +30) or **EPSG:1113** | **EPSG:1113** | A named transformation, no fitted number, and it sits at the minimum of the label-free test. |
| Where the new photos live | new run folder plus an explicit record list (Codex); **a separate v2 imagery root** (Fable, Grok) | **`data/imagery/sentinel2_v2/`** | The v1 folder and the v1 database build never see v2. No change to `records.py`. |
| How extra tries keep v1 scenes | new full run (4 h, and the catalogue may have changed) or **top-up with hard links** (Fable) | **Top-up from the v1 run** | Each v1-accepted scene is hard-linked by month: same image, same bytes, no download. Only months without a v1 scene get new tries. |
| Fill the catalogue gaps now? | yes (Grok); later (Codex, Opus) | **Later, as a separate go / no-go** | These are mostly months before planting. Two collections inside one record need care. The top-up mechanism allows this later as a second chained run. |
| Lacuna 2022 (156 fields) | in v2 / later | **Later** | Adding them would join clusters and change the Lacuna 2023 folds, so v1 Lacuna scores would no longer compare. |
| Folder layout for v2 | `data/cropyield_v2.duckdb` (Opus); **`data/v2/` mirroring `data/`** (Codex, Grok) | **`data/v2/`** | `load_xy(cohort, data_dir="data/v2")` then works with no code change. |
| Presto and MOSAIKS in v2 | copy v1 rows / recompute / leave empty | **Presto empty; MOSAIKS recomputed later with the frozen v1 filters** (`filters.npz`, SHA `f801e568…`) | v1 vectors were made from v1 months, so copying them would mix versions. A refit would change every vector. |

---

## 3. What changes, and what never changes

**Changes, all switched off by default, so v1 behaves byte for byte as today:**

| File | Change | Size (estimate) |
|---|---|---:|
| `scripts/step5_download_imagery.py` | `--base-run <run folder>`: per month, hard-link the base run's accepted scene, skip candidates it already tried, try only the rest. `--catalog-dir <dir>`: reuse the v1 catalogue cache read-only. `--collection <name>` with the whitelist offset rule for `sentinel-2-l2a`. A guard that refuses a base run made with other chip, band or threshold settings. | ~50 lines |
| `scripts/step2_audit_labels.py` | `--only malawi_2022 --out-dir data/v2/audit --datum-operation EPSG:1113`: the same audit, with the named transformation. | ~15 lines |
| `src/cropyield/data/labels.py` | a `version` argument: v2 reads the Malawi 2022 audit from `data/v2/audit`, gives Malawi 2022 the role "second" and keeps all its 529 rows (3 zeros stay). `EXPECTED_ROWS` and `cohorts.py` do not change. A raw check for Malawi 2022 (yield = AVG_YLD × 1000, polygon = the EPSG:1113 transform). | ~25 lines |
| `scripts/step3_build_labels.py` | `--version 2` writes `data/v2/processed/labels_v2.parquet`. It asserts that every non-Malawi-2022 row equals v1 in all 44 columns. v1 writes only if its hash is still `49aae383…`. | ~20 lines |
| `src/cropyield/eval/splits.py`, `scripts/step4_build_splits.py` | `--version 2` writes `data/v2/splits/`. It rebuilds the 13 v1 files and asserts they equal `data/splits/` byte for byte before copying them. Adds Malawi 2022: `s1_cc2km` (96 groups), `s2_region` (20 k-means blocks, because there is no district column), `random_diag`, and `temporal_rank` (Kasungu 2022 ↔ 2023, rank only, the 184 Malawi 2022 fields within 20 km of a 2023 field). | ~40 lines |
| `scripts/step6_build_database.py` | `--version 2` (paths under `data/v2/` and `data/imagery/sentinel2_v2/`). A guard: refuse to overwrite any database whose `presto_embeddings` has rows, so the team file is safe. | ~20 lines |
| `scripts/step8_run_baseline.py` | `--version 2`: v2 labels and manifest, row counts measured at the freeze, folds 1–4 only, results in `results/v2/`, adds Malawi 2022. | ~20 lines |
| `.gitignore` | `data/v2/*.duckdb` | 1 line |
| `tests/` | top-up keeps base scenes (same files, `os.path.samefile`); default digest = `517bfcf0a69c6cac`; offset whitelist; `build_labels(v1)` hash; v1 split files byte-equal | ~100 lines |

**Never changes** (proved with a before / after list of SHA-256 and size per file):
`data/raw/*`, `data/audit/*`, `data/processed/labels_v1.parquet`, `data/splits/*` and `manifest.json`, `data/cropyield.duckdb`
(872,689,664 bytes, `e192b9d6…`), `configs/sentinel2_scenes_v1.parquet`, `configs/team_database_v1.json`,
`data/imagery/sentinel2/run-517bfcf0a69c6cac/` (every `record.json` and `scene.json` hash), `data/features/mosaiks/*`,
`results/baseline_*`, `data/imagery/malawi_2022_recovered/`, `cohorts.py`, `satellite/*.py`, `indices.py`, `sql/*`.

**New, with new hashes:** `data/v2/audit/malawi_2022_*`, `data/v2/processed/labels_v2.parquet`, `data/v2/splits/*` +
manifest, `data/imagery/sentinel2_v2/`, `configs/sentinel2_scenes_v2.parquet`, `data/v2/cropyield.duckdb` +
`configs/team_database_v2.json`. One line per item in `docs/DECISIONS.md`; git tags `labels-v2` and `splits-v2`.

---

## 4. Run order and time

| Stage | What | Network | Time (estimate) |
|---|---|---|---:|
| 0 | Pin v1: the SHA-256 list of everything in "never changes" | none | 5 min |
| 1 | Write the code changes and tests; `pytest`; `/verify-change` | none | 4–6 h |
| 2 | Malawi 2022 audit v2 and `labels_v2` | none | 2 min |
| 3a | **Lever 1 top-up** for Kenya, Malawi 2023, Lacuna, Zimbabwe 2024 (no Malawi 2022; use a copy of `sentinel2_windows_all.csv` without its 529 Malawi 2022 rows, and `--datasets` without `malawi_2022`): `--base-run …/run-517bfcf0a69c6cac --catalog-dir …/sentinel2/catalog_cache --candidates-per-month 24`, 32 slices. Never pass `--max-cloud-cover`, never `--refresh-catalog`. | about 8.5 GB | **10–20 min** |
| 3b | **Malawi 2022 v2 download**: older collection, whitelist offsets, EPSG:1113 polygons, 24 candidates, the recovered catalogue cache copied first (no new search), 32 slices | about 35 GB | **15–20 min** |
| 4 | `splits_v2`; step 6 into `data/v2/cropyield.duckdb`; freeze the v2 scene list and database hash | none | 15–35 min |
| 5 | Checks (section 5) | none | 20–30 min |
| 6 | Pre-registered scores (section 6) | none | 10 min |
| opt. | MOSAIKS v2 with the frozen v1 filters | none | about 1 h (not measured) |

**Total: about one working day, and less than 1 hour of it is download.** The line speed is not the main cost: the code, the tests and the checks are.

**Expected gain, from v1's own acceptance rates (Fable):** about 810 of the 2,388 cloudy model field-months get filled:

| Cohort | Cloudy months filled (estimate) |
|---|---:|
| Kenya | ~268 of 566 |
| Malawi 2023 | ~50 of 433, but March only ~12 of 128 |
| Lacuna 2023 | ~356 of 1,150 |
| Zimbabwe 2024 | ~136 of 239 |

Malawi 2022 adds 529 polygon fields with a well-covered March. It also adds the first season test on polygons, Kasungu 2022 → 2023, rank only.

---

## 5. Checks that decide go or no-go

1. **v1 is untouched:** the stage 0 list is identical afterwards. (Hard-linked files show 2 links; their bytes and times stay the same.)
2. **v2 only adds months:** in the v2 database, every v1 `(obs_id, month, item_id)` is still there; v1-clear months have identical band values; coverage only moves cloudy → clear.
3. **Offsets are right:** no older-collection scene has a field-median blue below 0; any 05.10 image is rejected unread; the haze share (blue > 0.15) is close to Malawi 2023's.
4. **Malawi 2022 comes only from the v2 older-collection run;** every polygon is inside its chip.
5. **Labels and splits:** `labels_v2` equals v1 outside Malawi 2022; the 13 v1 split files equal v1 byte for byte; Malawi 2022 groups do not cross folds.
6. **Coverage gates, written before any score:** Malawi 2022 has at least 4 clear months in at least 95 % of its fields. Lever 1 fills at least half of its estimate.

---

## 6. The scores, written down before anyone looks

- **Lever 1:** for each v1 cohort, A1 on v2 against A1 on v1, on the **same fields**, on folds 1–4 of the frozen `s1_cc2km`. Rank inside clusters, with a paired cluster bootstrap (seed 20261029). A win means the interval lies above 0 and the paired RMSE interval does not lie entirely on the worse side. Fields that newly reach 4 clear months are counted and reported apart, never mixed into the paired test.
- **Malawi 2022:** R0, R1 and A1 on its own splits, folds 1–4 (fold 0 kept back, like the other cohorts). Then `temporal_rank` Kasungu 2022 ↔ 2023 as a Spearman only. Malawi 2022 yields are never pooled with 2023 yields: the cut protocol differs.
- **Then lever 3**, the point-window test, reads the frozen v2 chips, with its rules committed first.

---

## 7. What the owner must decide

1. **Go:** start stages 0 and 1 (pin v1, write code and tests). Nothing downloads until stage 1 passes `/verify-change`.
2. **Fold 0 for Malawi 2022:** keep it back as in the other cohorts (recommended), or use all 5 folds.
3. **Malawi 2022 unit:** the audit assumes `AVG_YLD` is t/ha. Confirm this in the provider files before any Malawi 2022 score.
4. **Later, a separate go / no-go:** filling the catalogue gaps from the older collection, and a higher tile-cloud limit (this needs a new catalogue search, with an unknown number of extra photos).
