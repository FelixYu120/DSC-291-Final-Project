# Zimbabwe merge and transfer diagnosis, v2 (team training-row rule)

Small copies of the v2 step 9 and step 10 outputs. The full releases are in `data/runs/zimbabwe_merge_v2/` and
`data/runs/zimbabwe_transfer_diagnosis_v2/`; `data/runs/` is git-ignored, so these copies keep the scores in Git.
Each folder holds the release `manifest.json`; every copied file is a listed release output with its SHA-256.

**Why v2 exists.** The v1 pooled arms trained on all 4,332 screened Zimbabwe 2024 rows, including the 1,874 recorded
zeros that `labels_v1.include_primary` excludes (`zimbabwe_2024_zero_likely_not_measured`). That broke the team rule.
v2 sets `"training_rows": "include_primary"`, so every training pool holds only `include_primary` rows:
1,880 Lacuna 2023 rows and 2,458 Zimbabwe 2024 rows. Evaluation fields, folds, fold 0, buffer, inner CV, seeds,
bootstrap draws and the December–June window are unchanged. The v1 releases are unchanged.

| Folder | Source release | Config | Command |
|---|---|---|---|
| `merge/` | `data/runs/zimbabwe_merge_v2` | `configs/zimbabwe_merge_v2.json` | `python scripts/step9_compare_zimbabwe_merge.py --config configs/zimbabwe_merge_v2.json` |
| `diagnosis/` | `data/runs/zimbabwe_transfer_diagnosis_v2` | `configs/zimbabwe_transfer_diagnosis_v2.json` | `python scripts/step10_diagnose_zimbabwe_transfer.py --config configs/zimbabwe_transfer_diagnosis_v2.json` |

The v1 versus v2 comparison is in `docs/zimbabwe/MERGE_RESULTS.md` and `docs/zimbabwe/TRANSFER_FINDINGS.md`.
All results are exploratory nested spatial cross-validation on the same 1,504 Lacuna 2023 fields, not a blind test.
