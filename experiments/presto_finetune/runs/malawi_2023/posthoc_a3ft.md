# Post-hoc arm P3 (A3-FT recipe): malawi_2023

Not in PLAN.md. Written after the first scores were seen, so read it as exploration. Coordinates masked. Recipe: posthoc_a3ft.py docstring.

Chosen stage-2 epochs per test fold (median inner best epoch): {'1': 32, '2': 36, '3': 49, '4': 35}.

| Arm | RMSE, t/ha | R2 | Rank inside clusters |
|---|---:|---:|---:|
| A1 | 1.406 | 0.154 | 0.425 |
| R1 | 1.634 | -0.142 | 0.048 |
| P0 | 1.459 | 0.090 | 0.299 |
| P0_noloc | 1.458 | 0.090 | 0.321 |
| P1 | 1.405 | 0.156 | 0.390 |
| P1_noloc | 1.420 | 0.137 | 0.379 |
| X1 | 1.460 | 0.088 | 0.389 |
| P3 | 1.452 | 0.098 | 0.342 |

| Pair | RMSE, a minus b | Rank, a minus b |
|---|---|---|
| P3 minus A1 | +0.046 (-0.039 to +0.117) | -0.082 (-0.189 to +0.047) |
| P3 minus R1 | -0.182 (-0.392 to +0.005) | +0.294 (+0.077 to +0.527) |
| P3 minus P0_noloc | -0.006 (-0.054 to +0.036) | +0.021 (-0.061 to +0.112) |
| P3 minus P1_noloc | +0.032 (-0.015 to +0.079) | -0.037 (-0.094 to +0.026) |
| P3 minus P0 | -0.006 (-0.044 to +0.035) | +0.043 (-0.027 to +0.118) |
| P3 minus X1 | -0.008 (-0.099 to +0.083) | -0.047 (-0.193 to +0.098) |
