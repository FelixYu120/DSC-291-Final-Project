# Post-hoc controls: malawi_2022

Not in PLAN.md. Written after the first scores were seen, so read them as exploration.

X1 = Ridge on the 99 raw monthly inputs (10 bands + NDVI x 9 months, mean-filled + missing flags). X2 = frozen random-weights Presto + Ridge.

| Arm | RMSE, t/ha | MAE, t/ha | Bias, t/ha | R2 | Rank inside clusters |
|---|---:|---:|---:|---:|---:|
| A1 | 1.551 | 1.191 | -0.015 | 0.393 | 0.299 |
| R1 | 1.624 | 1.174 | -0.087 | 0.335 | -0.072 |
| P0 | 1.462 | 1.119 | -0.040 | 0.461 | 0.260 |
| P1 | 1.449 | 1.119 | +0.002 | 0.470 | 0.276 |
| X1 | 1.406 | 1.075 | -0.067 | 0.502 | 0.400 |
| X2 | 1.714 | 1.275 | -0.005 | 0.259 | 0.065 |

| Pair | RMSE, a minus b | Rank, a minus b |
|---|---|---|
| X1 minus A1 | -0.146 (-0.250 to -0.046) | +0.100 (-0.005 to +0.194) |
| X2 minus A1 | +0.163 (+0.003 to +0.350) | -0.234 (-0.356 to -0.124) |
| P0 minus X1 | +0.056 (-0.031 to +0.140) | -0.140 (-0.230 to -0.047) |
| P0 minus X2 | -0.253 (-0.449 to -0.096) | +0.195 (+0.079 to +0.317) |
| P1 minus X1 | +0.044 (-0.043 to +0.129) | -0.124 (-0.217 to -0.027) |
