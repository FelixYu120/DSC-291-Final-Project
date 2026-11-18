# Post-hoc arm P3 (A3-FT recipe): malawi_2022

Not in PLAN.md. Written after the first scores were seen, so read it as exploration. Coordinates masked. Recipe: posthoc_a3ft.py docstring.

Chosen stage-2 epochs per test fold (median inner best epoch): {'1': 40, '2': 40, '3': 41, '4': 29}.

| Arm | RMSE, t/ha | R2 | Rank inside clusters |
|---|---:|---:|---:|
| A1 | 1.551 | 0.393 | 0.299 |
| R1 | 1.624 | 0.335 | -0.072 |
| P0 | 1.462 | 0.461 | 0.260 |
| P0_noloc | 1.523 | 0.415 | 0.244 |
| P1 | 1.449 | 0.470 | 0.276 |
| P1_noloc | 1.486 | 0.443 | 0.244 |
| X1 | 1.406 | 0.502 | 0.400 |
| P3 | 1.528 | 0.411 | 0.248 |

| Pair | RMSE, a minus b | Rank, a minus b |
|---|---|---|
| P3 minus A1 | -0.023 (-0.101 to +0.064) | -0.051 (-0.148 to +0.036) |
| P3 minus R1 | -0.096 (-0.254 to +0.060) | +0.320 (+0.161 to +0.503) |
| P3 minus P0_noloc | +0.006 (-0.026 to +0.040) | +0.004 (-0.043 to +0.050) |
| P3 minus P1_noloc | +0.043 (+0.005 to +0.082) | +0.004 (-0.032 to +0.036) |
| P3 minus P0 | +0.067 (+0.013 to +0.131) | -0.012 (-0.070 to +0.046) |
| P3 minus X1 | +0.123 (+0.022 to +0.225) | -0.152 (-0.263 to -0.043) |
