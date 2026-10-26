# Roadmap

Seven weeks from 26 October to 7 December 2026. Course deadlines in bold. Plan about 8–10 project hours per person per week; HW2 (27 Oct) and HW3 (10 Nov) fall inside weeks 0–2.

| Week | Dates | Milestone | Course |
|---|---|---|---|
| 0 | 26 Oct – 1 Nov | Kickoff: roles, repo, environment. 48-record pilot (pairing, coverage, tensor, trainability). Offset check on two scenes. Provider emails. Season windows and split rules frozen. | HW2 due 27 Oct |
| 1 | 2 – 8 Nov | Full Sentinel-2 extraction on the cluster. Split files committed. Baselines on Malawi and Kenya. Frozen Presto embeddings cached. **Signal-gate decision 8 Nov.** | HW2 oral |
| 2 | 9 – 12 Nov | Midterm report: data table, pipeline figure, baselines and frozen Presto under spatial CV, noise ceiling, plan for the rest. | HW3 due 10 Nov; **midterm report 12 Nov** |
| 3 | 13 – 19 Nov | Fine-tuned Presto (LP-FT) and ablations; label-budget curve; MOSAIKS; GRU; leave-zone-out and leave-district-out; Kenya 2019 → 2020. Photo model training starts. | Midterm oral |
| 4 | 20 – 26 Nov | Photo fusion and PPI on Zimbabwe 2024; unseen-country transfer; targeting metrics; robustness checks. **Results frozen 24 Nov.** | Last lecture 24 Nov |
| 5 | 27 Nov – 3 Dec | Final figures and tables; 10-minute talk, every member presents one result; paper draft in Overleaf. | **Presentation 1 or 3 Dec** |
| 6 | 4 – 7 Dec | Paper polish, limitations, reproducibility; code release tag; oral-exam preparation. | **Paper and oral 7 Dec** |

## First tasks, one per role

- **Data and labels:** build `labels.parquet` from the audited CSVs for the four cohorts; select the 48 pilot records; send the three provider emails (Pula / Li et al., One Acre Fund, FAO/NASA Harvest); audit the Zimbabwe zero rows.
- **Satellite pipeline:** scene search per tile and window; pixel reads (polygon interior, 3×3 around points); offset rule verified on two scenes; cloud mask; monthly composites; cluster batch job.
- **Baselines:** experiment runner writing `results/metrics.csv`; seasonal GCVI/NDVI features; location-only, index ridge and tree baselines.
- **Foundation model:** Presto tensor builder with masks; frozen embeddings; fine-tuning smoke test on the pilot records.
- **Evaluation and writing:** spatial split files; metrics and noise ceilings; targeting metrics; PPI; Overleaf skeleton.

## Gates

| Gate | Pass | Fail |
|---|---|---|
| Pilot (1 Nov) | pairing, coverage, tensor and trainability pass per cohort | repair in week 1 or drop the cohort |
| H1 signal (8 Nov) | best satellite model beats a location-only baseline within zone | zone-level PPI becomes the main result |
| H2 gain | fine-tuned beats frozen Presto by at least 5 % RMSE | "frozen features suffice" is the finding |
| RQ2 photos | fusion beats satellite-only under the same folds | photos add nothing at test time |

The visual version of this page is `docs/project_map.html`. A detailed week-0 task list with acceptance criteria exists at git tag `backup/full-skeleton` (`docs/WEEK0.md`) if the team wants it.
