# Post-hoc arm P3 (A3-FT recipe): zimbabwe_lacuna_2022_2023

Not in PLAN.md. Written after the first scores were seen, so read it as exploration. Coordinates masked. Recipe: posthoc_a3ft.py docstring.

Chosen stage-2 epochs per test fold (median inner best epoch): {'1': 32, '2': 22, '3': 27, '4': 28}.

| Arm | RMSE, t/ha | R2 | Rank inside clusters |
|---|---:|---:|---:|
| A1 | 1.785 | 0.191 | 0.299 |
| R1 | 1.854 | 0.127 | -0.054 |
| P0 | 1.657 | 0.302 | 0.358 |
| P0_noloc | 1.654 | 0.305 | 0.335 |
| P1 | 1.652 | 0.307 | 0.353 |
| P1_noloc | 1.652 | 0.307 | 0.339 |
| X1 | 1.626 | 0.328 | 0.350 |
| P3 | 1.643 | 0.314 | 0.340 |

| Pair | RMSE, a minus b | Rank, a minus b |
|---|---|---|
| P3 minus A1 | -0.142 (-0.212 to -0.076) | +0.041 (-0.002 to +0.083) |
| P3 minus R1 | -0.210 (-0.340 to -0.080) | +0.393 (+0.296 to +0.477) |
| P3 minus P0_noloc | -0.010 (-0.041 to +0.020) | +0.004 (-0.013 to +0.022) |
| P3 minus P1_noloc | -0.009 (-0.030 to +0.011) | +0.000 (-0.013 to +0.014) |
| P3 minus P0 | -0.014 (-0.052 to +0.023) | -0.018 (-0.038 to -0.000) |
| P3 minus X1 | +0.017 (-0.030 to +0.060) | -0.010 (-0.045 to +0.021) |
