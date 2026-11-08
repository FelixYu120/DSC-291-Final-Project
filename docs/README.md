# Documentation

For the current deliverable, start with the [Zimbabwe project guide](zimbabwe/README.md).

## Current explanations

| Topic | Document |
|---|---|
| Seasonal aggregation V0–V3 | [zimbabwe/AGGREGATION_RESULTS.md](zimbabwe/AGGREGATION_RESULTS.md), [protocol](zimbabwe/AGGREGATION_PROTOCOL.md) |
| Expanded Lacuna/2024 training and 2022 imagery exclusions | [zimbabwe/MULTIYEAR_RESULTS.md](zimbabwe/MULTIYEAR_RESULTS.md), [protocol](zimbabwe/MULTIYEAR_PROTOCOL.md) |
| R² calculation, exact scores and Claude review packet | [zimbabwe/R2_AUDIT.md](zimbabwe/R2_AUDIT.md) |
| One-page basic Ridge summary | [zimbabwe/SUMMARY.md](zimbabwe/SUMMARY.md) |
| Zimbabwe data, steps 8–15 and result locations | [zimbabwe/README.md](zimbabwe/README.md) |
| Complete merge/weather methods and conclusions | [zimbabwe/METHODS.md](zimbabwe/METHODS.md) |
| Initial merge comparison and compatibility fixes | [zimbabwe/MERGE_RESULTS.md](zimbabwe/MERGE_RESULTS.md) |
| Why 2024 adds little; source quality and model diagnostics | [zimbabwe/TRANSFER_FINDINGS.md](zimbabwe/TRANSFER_FINDINGS.md) |
| Reproducing published runs after code changes | [zimbabwe/REPRODUCING.md](zimbabwe/REPRODUCING.md) |
| Cross-country integrity review | [quality/DATA_QUALITY.md](quality/DATA_QUALITY.md) |
| Separate cloud/date/location review variant | [quality/QUALITY_REMEDIATION.md](quality/QUALITY_REMEDIATION.md) |
| Earlier spatial baselines | [quality/BASELINES.md](quality/BASELINES.md) |

## Reference contracts and recorded protocols

These documents retain their existing paths because code and historical manifests refer to them.
The dated protocols describe the recorded experiments; use the reproduction guide for commands on current main.

| Reference | Purpose |
|---|---|
| [DATA.md](DATA.md) | Frozen cohort definitions, label schema and measurement rules |
| [EVALUATION.md](EVALUATION.md) | Spatial splits, metrics and restrictions on historical test observations |
| [ZIMBABWE_DATA_HANDOFF.md](ZIMBABWE_DATA_HANDOFF.md) | Source handbook used to generate the handoff; read its [released copy](../data/processed/zimbabwe_midterm_v1/README.md) alongside the data |
| [ZIMBABWE_MERGE_PROTOCOL.md](ZIMBABWE_MERGE_PROTOCOL.md) | Step 9 compatibility register and comparison |
| [ZIMBABWE_TRANSFER_DIAGNOSIS_PROTOCOL.md](ZIMBABWE_TRANSFER_DIAGNOSIS_PROTOCOL.md) | Step 10 diagnostic design |
| [ZIMBABWE_WEATHER_PROTOCOL.md](ZIMBABWE_WEATHER_PROTOCOL.md) | Steps 11–12 weather extraction and comparison |
| [ZIMBABWE_COMPACT_WEATHER_PROTOCOL.md](ZIMBABWE_COMPACT_WEATHER_PROTOCOL.md) | Step 13 feature reduction and comparisons |

## Team rules

1. Branch per task, pull request, one reviewer. `main` always passes `python -m pytest`.
2. Models read `labels_v1` (or `labels_v2` for data v2) only (`docs/DATA.md`), never a raw or audit CSV.
3. Split files are created before any model is trained and never edited afterwards (`docs/EVALUATION.md`).
4. One model per cohort; every metric is reported within cohort. No pooled R².
5. Every run keeps its settings in one place; every metric lands in the results table with its commit, split
   hash and seed.
6. Models that are compared get the same rows, the same splits, the same head and the same tuning effort,
   and each is reported next to the coordinates-only baseline R1.
7. MOSAIKS filters are refitted once after the core download, before the first MOSAIKS result, then frozen.
8. No stretch item starts before gate G3 (`docs/ROADMAP.md`).
9. Imagery, features, checkpoints and the photo archive stay off git.
10. One dated line per decision in `docs/DECISIONS.md`.

These rules came from the removed `STRUCTURE.md`. Also: labels and survey dates (crop-cut, planting, harvest)
are never model inputs or window anchors; training rows follow `include_primary`; folds 1–4 of `s1_cc2km` are
cross-validated and fold 0 is held back for one final test.

## Research background and history

- [ROADMAP.md](ROADMAP.md): broader multi-country research plan; current Zimbabwe deliverables are indexed above.
- [RELATED_WORK.md](RELATED_WORK.md): research papers and representation choices.
- [DECISIONS.md](DECISIONS.md): dated decisions, including changes to earlier scope and data policies.
- [Branch history](archive/BRANCH_HISTORY.md): consolidation onto main and recovery tags.
- [Earlier archived work](../_parked/LANDING.md): unique historical code and results with an integrity manifest.

Folder layout and setup live in the [root README](../README.md). The obsolete separate structure guide and stale
private-Page metadata were removed; readable reports are maintained here in the repository.
