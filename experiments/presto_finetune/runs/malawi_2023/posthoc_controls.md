# Post-hoc controls: malawi_2023

Not in PLAN.md. Written after the first scores were seen, so read them as exploration.

X1 = Ridge on the 99 raw monthly inputs (10 bands + NDVI x 9 months, mean-filled + missing flags). X2 = frozen random-weights Presto + Ridge.

| Arm | RMSE, t/ha | MAE, t/ha | Bias, t/ha | R2 | Rank inside clusters |
|---|---:|---:|---:|---:|---:|
| A1 | 1.406 | 1.103 | -0.043 | 0.154 | 0.425 |
| R1 | 1.634 | 1.282 | -0.000 | -0.142 | 0.048 |
| P0 | 1.459 | 1.129 | -0.035 | 0.090 | 0.299 |
| P1 | 1.405 | 1.098 | -0.045 | 0.156 | 0.390 |
| X1 | 1.460 | 1.131 | +0.017 | 0.088 | 0.389 |
| X2 | 1.561 | 1.240 | -0.031 | -0.042 | -0.026 |

| Pair | RMSE, a minus b | Rank, a minus b |
|---|---|---|
| X1 minus A1 | +0.054 (-0.068 to +0.171) | -0.036 (-0.183 to +0.133) |
| X2 minus A1 | +0.155 (+0.047 to +0.265) | -0.451 (-0.632 to -0.249) |
| P0 minus X1 | -0.002 (-0.094 to +0.095) | -0.090 (-0.223 to +0.040) |
| P0 minus X2 | -0.102 (-0.218 to +0.005) | +0.325 (+0.124 to +0.508) |
| P1 minus X1 | -0.055 (-0.115 to +0.013) | +0.001 (-0.124 to +0.121) |
