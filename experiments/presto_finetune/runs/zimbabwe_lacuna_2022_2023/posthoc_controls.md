# Post-hoc controls: zimbabwe_lacuna_2022_2023

Not in PLAN.md. Written after the first scores were seen, so read them as exploration.

X1 = Ridge on the 99 raw monthly inputs (10 bands + NDVI x 9 months, mean-filled + missing flags). X2 = frozen random-weights Presto + Ridge.

| Arm | RMSE, t/ha | R2 | Rank inside clusters |
|---|---:|---:|---:|
| A1 | 1.785 | 0.191 | 0.299 |
| R1 | 1.854 | 0.127 | -0.054 |
| P0 | 1.657 | 0.302 | 0.358 |
| P1 | 1.652 | 0.307 | 0.353 |
| X1 | 1.626 | 0.328 | 0.350 |
| X2 | 1.665 | 0.296 | 0.341 |

| Pair | RMSE, a minus b | Rank, a minus b |
|---|---|---|
| X1 minus A1 | -0.159 (-0.244 to -0.084) | +0.051 (-0.004 to +0.108) |
| X2 minus A1 | -0.120 (-0.186 to -0.053) | +0.042 (-0.008 to +0.093) |
| P0 minus X1 | +0.031 (-0.016 to +0.078) | +0.008 (-0.029 to +0.043) |
| P0 minus X2 | -0.008 (-0.055 to +0.041) | +0.017 (-0.014 to +0.047) |
| P1 minus X1 | +0.026 (-0.013 to +0.065) | +0.003 (-0.029 to +0.032) |
