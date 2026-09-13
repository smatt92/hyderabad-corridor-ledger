# Ledger intervals: calibration

Generated 2026-09-13 18:36 UTC by `scripts/dev/ledger_intervals.py` at 28884dc (plus uncommitted changes), 400 simulated panels per scenario and tier, truth from one 4800-day panel each, 3 min.

.venv/bin/python scripts/dev/ledger_intervals.py [--replicates N] [--processes N] [--quick]

The ledger publishes a call-level percentile bootstrap interval beside each pooled
peak-hour p95 travel time, BTI and PTI (corridor_stats, 90-day read window), each
hour's p95 and BTI in the 24-hour profile (120-day profile window), and the p95
advantage of a pair's primary over its alternate per hour
(pair_advantage_hourly). Resampling calls treats every call in a window as
independent. Traffic is not: a city-wide shock moves every corridor on the same
day and each corridor drifts from week to week, so calls from one day or one week
move together. The intervention audit's interval, built the same way, failed when
that drift was large.

Each replicate simulates one 120-day panel of three corridors with fixed profiles
(scripts/dev/panel_model.py): c00 and c01 identical, a pair whose true advantage
is zero, and c02 more congested. It computes every interval with the pipeline's
own functions over the pipeline's windows, and compares it with the true value:
the same statistic of the stationary process, from one panel of TRUTH_DAYS days.
Scenarios:
  independent calls    no shared shock, no drift: checks the harness itself
  default correlation  panel_model's daily shock (sd 0.10) and weekly drift (0.08)
  weekly drift 0.20    the drift at which the audit interval failed

Coverage is nominal at 0.95; SE/SD is 1 when the interval reports the spread the value actually has, below 1 when it is too narrow. Size (pair rows, `excludes zero`) is nominal at 0.05.

## Pooled by scenario

| scenario | tier | statistic | coverage mean | coverage worst | SE/SD mean | SE/SD worst | excludes zero (pair) |
|---|---|---|---|---|---|---|---|
| independent calls | A | ledger BTI | 0.95 | 0.93 | 1.03 | 1.01 | — |
| independent calls | A | ledger PTI (p5) | 0.92 | 0.89 | 0.98 | 0.87 | — |
| independent calls | A | ledger PTI (tomtom) | 0.95 | 0.94 | 1.03 | 1.02 | — |
| independent calls | A | ledger p95 travel time | 0.95 | 0.94 | 1.03 | 1.02 | — |
| independent calls | A | pair p95 advantage | 0.97 | 0.97 | 1.03 | 1.00 | 0.03 |
| independent calls | A | profile BTI | 0.96 | 0.94 | 1.01 | 0.97 | — |
| independent calls | A | profile p95 travel time | 0.95 | 0.94 | 1.00 | 0.96 | — |
| independent calls | B | ledger BTI | 0.95 | 0.94 | 1.02 | 0.98 | — |
| independent calls | B | ledger PTI (p5) | 0.93 | 0.90 | 0.98 | 0.88 | — |
| independent calls | B | ledger PTI (tomtom) | 0.95 | 0.94 | 1.01 | 0.96 | — |
| independent calls | B | ledger p95 travel time | 0.95 | 0.94 | 1.01 | 0.96 | — |
| independent calls | B | pair p95 advantage | 0.98 | 0.97 | 1.05 | 1.05 | 0.02 |
| independent calls | B | profile BTI | 0.94 | 0.91 | 0.97 | 0.94 | — |
| independent calls | B | profile p95 travel time | 0.93 | 0.90 | 0.95 | 0.92 | — |
| default correlation | A | ledger BTI | 0.92 | 0.91 | 0.92 | 0.85 | — |
| default correlation | A | ledger PTI (p5) | 0.71 | 0.68 | 0.56 | 0.50 | — |
| default correlation | A | ledger PTI (tomtom) | 0.73 | 0.68 | 0.58 | 0.50 | — |
| default correlation | A | ledger p95 travel time | 0.73 | 0.68 | 0.58 | 0.50 | — |
| default correlation | A | pair p95 advantage | 0.96 | 0.95 | 0.95 | 0.94 | 0.04 |
| default correlation | A | profile BTI | 0.95 | 0.93 | 0.99 | 0.97 | — |
| default correlation | A | profile p95 travel time | 0.90 | 0.89 | 0.90 | 0.84 | — |
| default correlation | B | ledger BTI | 0.94 | 0.92 | 0.94 | 0.90 | — |
| default correlation | B | ledger PTI (p5) | 0.82 | 0.81 | 0.70 | 0.67 | — |
| default correlation | B | ledger PTI (tomtom) | 0.84 | 0.81 | 0.73 | 0.67 | — |
| default correlation | B | ledger p95 travel time | 0.84 | 0.81 | 0.73 | 0.67 | — |
| default correlation | B | pair p95 advantage | 0.96 | 0.96 | 1.06 | 1.05 | 0.04 |
| default correlation | B | profile BTI | 0.95 | 0.92 | 1.00 | 0.96 | — |
| default correlation | B | profile p95 travel time | 0.92 | 0.90 | 0.93 | 0.88 | — |
| weekly drift 0.20 | A | ledger BTI | 0.75 | 0.70 | 0.60 | 0.54 | — |
| weekly drift 0.20 | A | ledger PTI (p5) | 0.46 | 0.41 | 0.32 | 0.27 | — |
| weekly drift 0.20 | A | ledger PTI (tomtom) | 0.45 | 0.41 | 0.32 | 0.27 | — |
| weekly drift 0.20 | A | ledger p95 travel time | 0.45 | 0.41 | 0.32 | 0.27 | — |
| weekly drift 0.20 | A | pair p95 advantage | 0.80 | 0.80 | 0.67 | 0.66 | 0.20 |
| weekly drift 0.20 | A | profile BTI | 0.93 | 0.90 | 0.93 | 0.88 | — |
| weekly drift 0.20 | A | profile p95 travel time | 0.79 | 0.75 | 0.68 | 0.62 | — |
| weekly drift 0.20 | B | ledger BTI | 0.85 | 0.82 | 0.75 | 0.69 | — |
| weekly drift 0.20 | B | ledger PTI (p5) | 0.58 | 0.53 | 0.44 | 0.40 | — |
| weekly drift 0.20 | B | ledger PTI (tomtom) | 0.58 | 0.53 | 0.43 | 0.40 | — |
| weekly drift 0.20 | B | ledger p95 travel time | 0.58 | 0.53 | 0.43 | 0.40 | — |
| weekly drift 0.20 | B | pair p95 advantage | 0.90 | 0.90 | 0.85 | 0.81 | 0.10 |
| weekly drift 0.20 | B | profile BTI | 0.93 | 0.89 | 1.00 | 0.89 | — |
| weekly drift 0.20 | B | profile p95 travel time | 0.86 | 0.82 | 0.82 | 0.70 | — |

## Every interval

| scenario | tier | statistic | corridor | hour | panels | calls | coverage | SE/SD | excludes zero | bias % | median width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| independent calls | A | ledger BTI | c00 | peak | 400 | 2827 | 0.93 | 1.02 | — | -0.6 | 0.058 |
| independent calls | A | ledger BTI | c01 | peak | 400 | 2825 | 0.95 | 1.01 | — | 0.1 | 0.058 |
| independent calls | A | ledger BTI | c02 | peak | 400 | 2666 | 0.96 | 1.04 | — | -0.6 | 0.096 |
| independent calls | A | ledger PTI (p5) | c00 | peak | 400 | 2827 | 0.94 | 1.04 | — | -0.3 | 0.177 |
| independent calls | A | ledger PTI (p5) | c01 | peak | 400 | 2825 | 0.95 | 1.02 | — | -0.0 | 0.175 |
| independent calls | A | ledger PTI (p5) | c02 | peak | 400 | 2666 | 0.89 | 0.87 | — | -0.6 | 0.330 |
| independent calls | A | ledger PTI (tomtom) | c00 | peak | 400 | 2827 | 0.94 | 1.04 | — | -0.3 | 0.177 |
| independent calls | A | ledger PTI (tomtom) | c01 | peak | 400 | 2825 | 0.95 | 1.02 | — | -0.0 | 0.175 |
| independent calls | A | ledger PTI (tomtom) | c02 | peak | 400 | 2666 | 0.96 | 1.02 | — | -0.2 | 0.419 |
| independent calls | A | ledger p95 travel time | c00 | peak | 400 | 2827 | 0.94 | 1.04 | — | -0.3 | 141.235 |
| independent calls | A | ledger p95 travel time | c01 | peak | 400 | 2825 | 0.95 | 1.02 | — | -0.0 | 139.999 |
| independent calls | A | ledger p95 travel time | c02 | peak | 400 | 2666 | 0.96 | 1.02 | — | -0.2 | 502.399 |
| independent calls | A | pair p95 advantage | c00-c01 | 9 | 400 | 436 | 0.97 | 1.00 | 0.03 | — | 652.593 |
| independent calls | A | pair p95 advantage | c00-c01 | 18 | 400 | 431 | 0.97 | 1.06 | 0.03 | — | 673.161 |
| independent calls | A | profile BTI | c00 | 9 | 400 | 440 | 0.97 | 0.99 | — | 0.9 | 0.174 |
| independent calls | A | profile BTI | c00 | 18 | 400 | 435 | 0.95 | 1.01 | — | -1.6 | 0.163 |
| independent calls | A | profile BTI | c01 | 9 | 400 | 440 | 0.95 | 0.98 | — | 1.9 | 0.180 |
| independent calls | A | profile BTI | c01 | 18 | 400 | 435 | 0.95 | 1.04 | — | -0.7 | 0.161 |
| independent calls | A | profile BTI | c02 | 9 | 400 | 414 | 0.94 | 0.97 | — | -2.8 | 0.280 |
| independent calls | A | profile BTI | c02 | 18 | 400 | 405 | 0.97 | 1.05 | — | -0.9 | 0.269 |
| independent calls | A | profile p95 travel time | c00 | 9 | 400 | 440 | 0.96 | 0.99 | — | 0.5 | 438.477 |
| independent calls | A | profile p95 travel time | c00 | 18 | 400 | 435 | 0.95 | 1.01 | — | -0.6 | 446.458 |
| independent calls | A | profile p95 travel time | c01 | 9 | 400 | 440 | 0.95 | 0.98 | — | 0.8 | 445.614 |
| independent calls | A | profile p95 travel time | c01 | 18 | 400 | 435 | 0.94 | 1.03 | — | -0.1 | 443.246 |
| independent calls | A | profile p95 travel time | c02 | 9 | 400 | 414 | 0.94 | 0.96 | — | -0.9 | 1496.148 |
| independent calls | A | profile p95 travel time | c02 | 18 | 400 | 405 | 0.96 | 1.05 | — | 0.1 | 1596.553 |
| independent calls | B | ledger BTI | c00 | peak | 400 | 1412 | 0.95 | 0.98 | — | -0.4 | 0.081 |
| independent calls | B | ledger BTI | c01 | peak | 400 | 1413 | 0.96 | 1.08 | — | 0.2 | 0.082 |
| independent calls | B | ledger BTI | c02 | peak | 400 | 1336 | 0.94 | 0.98 | — | -0.7 | 0.132 |
| independent calls | B | ledger PTI (p5) | c00 | peak | 400 | 1412 | 0.94 | 1.01 | — | -0.2 | 0.246 |
| independent calls | B | ledger PTI (p5) | c01 | peak | 400 | 1413 | 0.95 | 1.07 | — | 0.0 | 0.245 |
| independent calls | B | ledger PTI (p5) | c02 | peak | 400 | 1336 | 0.90 | 0.88 | — | -0.4 | 0.450 |
| independent calls | B | ledger PTI (tomtom) | c00 | peak | 400 | 1412 | 0.94 | 1.01 | — | -0.2 | 0.246 |
| independent calls | B | ledger PTI (tomtom) | c01 | peak | 400 | 1413 | 0.95 | 1.07 | — | 0.0 | 0.245 |
| independent calls | B | ledger PTI (tomtom) | c02 | peak | 400 | 1336 | 0.94 | 0.96 | — | -0.0 | 0.574 |
| independent calls | B | ledger p95 travel time | c00 | peak | 400 | 1412 | 0.94 | 1.01 | — | -0.2 | 197.029 |
| independent calls | B | ledger p95 travel time | c01 | peak | 400 | 1413 | 0.95 | 1.07 | — | 0.0 | 196.060 |
| independent calls | B | ledger p95 travel time | c02 | peak | 400 | 1336 | 0.94 | 0.96 | — | -0.0 | 689.062 |
| independent calls | B | pair p95 advantage | c00-c01 | 9 | 400 | 218 | 0.98 | 1.05 | 0.02 | — | 892.175 |
| independent calls | B | pair p95 advantage | c00-c01 | 18 | 400 | 215 | 0.97 | 1.05 | 0.03 | — | 910.266 |
| independent calls | B | profile BTI | c00 | 9 | 400 | 220 | 0.91 | 0.96 | — | -5.9 | 0.236 |
| independent calls | B | profile BTI | c00 | 18 | 400 | 218 | 0.91 | 0.98 | — | -5.5 | 0.219 |
| independent calls | B | profile BTI | c01 | 9 | 400 | 220 | 0.96 | 0.94 | — | 1.2 | 0.236 |
| independent calls | B | profile BTI | c01 | 18 | 400 | 218 | 0.97 | 1.01 | — | 1.0 | 0.218 |
| independent calls | B | profile BTI | c02 | 9 | 363 | 208 | 0.96 | 0.96 | — | 1.2 | 0.378 |
| independent calls | B | profile BTI | c02 | 18 | 278 | 206 | 0.95 | 1.00 | — | -2.9 | 0.359 |
| independent calls | B | profile p95 travel time | c00 | 9 | 400 | 220 | 0.90 | 0.96 | — | -1.8 | 579.461 |
| independent calls | B | profile p95 travel time | c00 | 18 | 400 | 218 | 0.90 | 0.95 | — | -1.8 | 590.630 |
| independent calls | B | profile p95 travel time | c01 | 9 | 400 | 220 | 0.94 | 0.92 | — | 0.5 | 576.340 |
| independent calls | B | profile p95 travel time | c01 | 18 | 400 | 218 | 0.96 | 0.98 | — | 0.4 | 589.707 |
| independent calls | B | profile p95 travel time | c02 | 9 | 363 | 208 | 0.94 | 0.93 | — | 0.9 | 2028.204 |
| independent calls | B | profile p95 travel time | c02 | 18 | 278 | 206 | 0.95 | 0.94 | — | -0.3 | 2144.113 |
| default correlation | A | ledger BTI | c00 | peak | 400 | 2823 | 0.91 | 0.85 | — | -0.5 | 0.060 |
| default correlation | A | ledger BTI | c01 | peak | 400 | 2826 | 0.91 | 0.91 | — | -1.2 | 0.060 |
| default correlation | A | ledger BTI | c02 | peak | 400 | 2669 | 0.94 | 0.99 | — | -0.8 | 0.095 |
| default correlation | A | ledger PTI (p5) | c00 | peak | 400 | 2823 | 0.68 | 0.50 | — | -0.3 | 0.182 |
| default correlation | A | ledger PTI (p5) | c01 | peak | 400 | 2826 | 0.69 | 0.57 | — | -1.0 | 0.183 |
| default correlation | A | ledger PTI (p5) | c02 | peak | 400 | 2669 | 0.76 | 0.62 | — | -1.1 | 0.333 |
| default correlation | A | ledger PTI (tomtom) | c00 | peak | 400 | 2823 | 0.68 | 0.50 | — | -0.3 | 0.182 |
| default correlation | A | ledger PTI (tomtom) | c01 | peak | 400 | 2826 | 0.69 | 0.57 | — | -1.0 | 0.183 |
| default correlation | A | ledger PTI (tomtom) | c02 | peak | 400 | 2669 | 0.81 | 0.66 | — | -0.6 | 0.422 |
| default correlation | A | ledger p95 travel time | c00 | peak | 400 | 2823 | 0.68 | 0.50 | — | -0.3 | 145.737 |
| default correlation | A | ledger p95 travel time | c01 | peak | 400 | 2826 | 0.69 | 0.57 | — | -1.0 | 146.350 |
| default correlation | A | ledger p95 travel time | c02 | peak | 400 | 2669 | 0.81 | 0.66 | — | -0.6 | 506.372 |
| default correlation | A | pair p95 advantage | c00-c01 | 9 | 400 | 436 | 0.96 | 0.96 | 0.04 | — | 568.119 |
| default correlation | A | pair p95 advantage | c00-c01 | 18 | 400 | 431 | 0.95 | 0.94 | 0.05 | — | 609.345 |
| default correlation | A | profile BTI | c00 | 9 | 400 | 440 | 0.94 | 0.99 | — | -2.7 | 0.151 |
| default correlation | A | profile BTI | c00 | 18 | 400 | 435 | 0.95 | 0.98 | — | 0.2 | 0.141 |
| default correlation | A | profile BTI | c01 | 9 | 400 | 440 | 0.93 | 1.03 | — | -3.1 | 0.148 |
| default correlation | A | profile BTI | c01 | 18 | 400 | 435 | 0.94 | 0.97 | — | 0.3 | 0.147 |
| default correlation | A | profile BTI | c02 | 9 | 400 | 414 | 0.97 | 1.02 | — | 1.9 | 0.259 |
| default correlation | A | profile BTI | c02 | 18 | 400 | 405 | 0.95 | 0.99 | — | 0.2 | 0.254 |
| default correlation | A | profile p95 travel time | c00 | 9 | 400 | 440 | 0.89 | 0.87 | — | -1.0 | 388.511 |
| default correlation | A | profile p95 travel time | c00 | 18 | 400 | 435 | 0.90 | 0.85 | — | 0.3 | 407.546 |
| default correlation | A | profile p95 travel time | c01 | 9 | 400 | 440 | 0.89 | 0.94 | — | -1.5 | 376.745 |
| default correlation | A | profile p95 travel time | c01 | 18 | 400 | 435 | 0.89 | 0.84 | — | -0.3 | 419.668 |
| default correlation | A | profile p95 travel time | c02 | 9 | 400 | 414 | 0.93 | 0.94 | — | 0.4 | 1428.144 |
| default correlation | A | profile p95 travel time | c02 | 18 | 400 | 405 | 0.94 | 0.94 | — | -0.3 | 1557.939 |
| default correlation | B | ledger BTI | c00 | peak | 400 | 1413 | 0.92 | 0.90 | — | -1.0 | 0.084 |
| default correlation | B | ledger BTI | c01 | peak | 400 | 1413 | 0.96 | 0.94 | — | 0.4 | 0.084 |
| default correlation | B | ledger BTI | c02 | peak | 400 | 1337 | 0.93 | 0.97 | — | -1.1 | 0.133 |
| default correlation | B | ledger PTI (p5) | c00 | peak | 400 | 1413 | 0.81 | 0.67 | — | -0.7 | 0.255 |
| default correlation | B | ledger PTI (p5) | c01 | peak | 400 | 1413 | 0.84 | 0.72 | — | -0.3 | 0.256 |
| default correlation | B | ledger PTI (p5) | c02 | peak | 400 | 1337 | 0.81 | 0.70 | — | -0.9 | 0.464 |
| default correlation | B | ledger PTI (tomtom) | c00 | peak | 400 | 1413 | 0.81 | 0.67 | — | -0.7 | 0.255 |
| default correlation | B | ledger PTI (tomtom) | c01 | peak | 400 | 1413 | 0.84 | 0.72 | — | -0.3 | 0.256 |
| default correlation | B | ledger PTI (tomtom) | c02 | peak | 400 | 1337 | 0.87 | 0.80 | — | -0.8 | 0.586 |
| default correlation | B | ledger p95 travel time | c00 | peak | 400 | 1413 | 0.81 | 0.67 | — | -0.7 | 203.839 |
| default correlation | B | ledger p95 travel time | c01 | peak | 400 | 1413 | 0.84 | 0.72 | — | -0.3 | 205.033 |
| default correlation | B | ledger p95 travel time | c02 | peak | 400 | 1337 | 0.87 | 0.80 | — | -0.8 | 703.340 |
| default correlation | B | pair p95 advantage | c00-c01 | 9 | 400 | 218 | 0.96 | 1.05 | 0.04 | — | 795.507 |
| default correlation | B | pair p95 advantage | c00-c01 | 18 | 400 | 215 | 0.96 | 1.08 | 0.04 | — | 854.499 |
| default correlation | B | profile BTI | c00 | 9 | 400 | 220 | 0.94 | 1.00 | — | -1.2 | 0.214 |
| default correlation | B | profile BTI | c00 | 18 | 400 | 217 | 0.96 | 1.00 | — | 1.6 | 0.206 |
| default correlation | B | profile BTI | c01 | 9 | 400 | 220 | 0.97 | 0.99 | — | 1.7 | 0.209 |
| default correlation | B | profile BTI | c01 | 18 | 400 | 218 | 0.95 | 1.05 | — | -1.9 | 0.206 |
| default correlation | B | profile BTI | c02 | 9 | 371 | 208 | 0.95 | 1.00 | — | -1.1 | 0.354 |
| default correlation | B | profile BTI | c02 | 18 | 278 | 206 | 0.92 | 0.96 | — | -2.6 | 0.334 |
| default correlation | B | profile p95 travel time | c00 | 9 | 400 | 220 | 0.92 | 0.94 | — | -0.6 | 529.490 |
| default correlation | B | profile p95 travel time | c00 | 18 | 400 | 217 | 0.93 | 0.92 | — | 0.2 | 563.010 |
| default correlation | B | profile p95 travel time | c01 | 9 | 400 | 220 | 0.94 | 0.91 | — | 0.2 | 521.169 |
| default correlation | B | profile p95 travel time | c01 | 18 | 400 | 218 | 0.93 | 0.99 | — | -0.8 | 559.935 |
| default correlation | B | profile p95 travel time | c02 | 9 | 371 | 208 | 0.92 | 0.93 | — | -0.2 | 1920.467 |
| default correlation | B | profile p95 travel time | c02 | 18 | 278 | 206 | 0.90 | 0.88 | — | -2.0 | 1989.042 |
| weekly drift 0.20 | A | ledger BTI | c00 | peak | 400 | 2826 | 0.70 | 0.55 | — | -1.3 | 0.064 |
| weekly drift 0.20 | A | ledger BTI | c01 | peak | 400 | 2823 | 0.70 | 0.54 | — | -0.6 | 0.064 |
| weekly drift 0.20 | A | ledger BTI | c02 | peak | 400 | 2672 | 0.85 | 0.72 | — | -0.7 | 0.098 |
| weekly drift 0.20 | A | ledger PTI (p5) | c00 | peak | 400 | 2826 | 0.41 | 0.27 | — | -0.4 | 0.197 |
| weekly drift 0.20 | A | ledger PTI (p5) | c01 | peak | 400 | 2823 | 0.42 | 0.31 | — | 0.5 | 0.198 |
| weekly drift 0.20 | A | ledger PTI (p5) | c02 | peak | 400 | 2672 | 0.55 | 0.38 | — | -0.5 | 0.342 |
| weekly drift 0.20 | A | ledger PTI (tomtom) | c00 | peak | 400 | 2826 | 0.41 | 0.27 | — | -0.4 | 0.197 |
| weekly drift 0.20 | A | ledger PTI (tomtom) | c01 | peak | 400 | 2823 | 0.42 | 0.31 | — | 0.5 | 0.198 |
| weekly drift 0.20 | A | ledger PTI (tomtom) | c02 | peak | 400 | 2672 | 0.51 | 0.36 | — | -0.0 | 0.430 |
| weekly drift 0.20 | A | ledger p95 travel time | c00 | peak | 400 | 2826 | 0.41 | 0.27 | — | -0.4 | 157.841 |
| weekly drift 0.20 | A | ledger p95 travel time | c01 | peak | 400 | 2823 | 0.42 | 0.31 | — | 0.5 | 158.265 |
| weekly drift 0.20 | A | ledger p95 travel time | c02 | peak | 400 | 2672 | 0.51 | 0.36 | — | -0.0 | 515.529 |
| weekly drift 0.20 | A | pair p95 advantage | c00-c01 | 9 | 400 | 436 | 0.80 | 0.67 | 0.20 | — | 571.415 |
| weekly drift 0.20 | A | pair p95 advantage | c00-c01 | 18 | 400 | 431 | 0.80 | 0.66 | 0.20 | — | 641.723 |
| weekly drift 0.20 | A | profile BTI | c00 | 9 | 400 | 440 | 0.90 | 0.90 | — | -1.1 | 0.150 |
| weekly drift 0.20 | A | profile BTI | c00 | 18 | 400 | 435 | 0.93 | 0.88 | — | -0.7 | 0.148 |
| weekly drift 0.20 | A | profile BTI | c01 | 9 | 400 | 440 | 0.94 | 0.93 | — | -0.9 | 0.149 |
| weekly drift 0.20 | A | profile BTI | c01 | 18 | 400 | 435 | 0.94 | 0.91 | — | -1.6 | 0.153 |
| weekly drift 0.20 | A | profile BTI | c02 | 9 | 400 | 414 | 0.93 | 1.00 | — | -1.8 | 0.248 |
| weekly drift 0.20 | A | profile BTI | c02 | 18 | 400 | 406 | 0.93 | 0.99 | — | -1.4 | 0.241 |
| weekly drift 0.20 | A | profile p95 travel time | c00 | 9 | 400 | 440 | 0.75 | 0.62 | — | -0.4 | 385.808 |
| weekly drift 0.20 | A | profile p95 travel time | c00 | 18 | 400 | 435 | 0.75 | 0.62 | — | -0.0 | 427.128 |
| weekly drift 0.20 | A | profile p95 travel time | c01 | 9 | 400 | 440 | 0.80 | 0.68 | — | 0.2 | 378.697 |
| weekly drift 0.20 | A | profile p95 travel time | c01 | 18 | 400 | 435 | 0.81 | 0.66 | — | 0.2 | 436.584 |
| weekly drift 0.20 | A | profile p95 travel time | c02 | 9 | 400 | 414 | 0.85 | 0.77 | — | -0.6 | 1361.119 |
| weekly drift 0.20 | A | profile p95 travel time | c02 | 18 | 400 | 406 | 0.80 | 0.74 | — | 0.2 | 1481.206 |
| weekly drift 0.20 | B | ledger BTI | c00 | peak | 400 | 1412 | 0.82 | 0.69 | — | -1.5 | 0.093 |
| weekly drift 0.20 | B | ledger BTI | c01 | peak | 400 | 1414 | 0.83 | 0.71 | — | -0.6 | 0.092 |
| weekly drift 0.20 | B | ledger BTI | c02 | peak | 400 | 1337 | 0.90 | 0.85 | — | 0.2 | 0.142 |
| weekly drift 0.20 | B | ledger PTI (p5) | c00 | peak | 400 | 1412 | 0.53 | 0.40 | — | -1.0 | 0.281 |
| weekly drift 0.20 | B | ledger PTI (p5) | c01 | peak | 400 | 1414 | 0.56 | 0.41 | — | -0.6 | 0.281 |
| weekly drift 0.20 | B | ledger PTI (p5) | c02 | peak | 400 | 1337 | 0.65 | 0.50 | — | -0.2 | 0.490 |
| weekly drift 0.20 | B | ledger PTI (tomtom) | c00 | peak | 400 | 1412 | 0.53 | 0.40 | — | -1.0 | 0.281 |
| weekly drift 0.20 | B | ledger PTI (tomtom) | c01 | peak | 400 | 1414 | 0.56 | 0.41 | — | -0.6 | 0.281 |
| weekly drift 0.20 | B | ledger PTI (tomtom) | c02 | peak | 400 | 1337 | 0.66 | 0.49 | — | 0.2 | 0.619 |
| weekly drift 0.20 | B | ledger p95 travel time | c00 | peak | 400 | 1412 | 0.53 | 0.40 | — | -1.0 | 225.154 |
| weekly drift 0.20 | B | ledger p95 travel time | c01 | peak | 400 | 1414 | 0.56 | 0.41 | — | -0.6 | 224.969 |
| weekly drift 0.20 | B | ledger p95 travel time | c02 | peak | 400 | 1337 | 0.66 | 0.49 | — | 0.2 | 742.298 |
| weekly drift 0.20 | B | pair p95 advantage | c00-c01 | 9 | 400 | 218 | 0.90 | 0.89 | 0.10 | — | 799.497 |
| weekly drift 0.20 | B | pair p95 advantage | c00-c01 | 18 | 400 | 215 | 0.91 | 0.81 | 0.10 | — | 897.509 |
| weekly drift 0.20 | B | profile BTI | c00 | 9 | 400 | 220 | 0.89 | 0.96 | — | -5.4 | 0.209 |
| weekly drift 0.20 | B | profile BTI | c00 | 18 | 400 | 217 | 0.95 | 1.00 | — | -0.1 | 0.216 |
| weekly drift 0.20 | B | profile BTI | c01 | 9 | 400 | 220 | 0.90 | 0.97 | — | -5.0 | 0.201 |
| weekly drift 0.20 | B | profile BTI | c01 | 18 | 400 | 218 | 0.94 | 0.89 | — | -1.8 | 0.209 |
| weekly drift 0.20 | B | profile BTI | c02 | 9 | 367 | 208 | 0.93 | 1.11 | — | -3.7 | 0.334 |
| weekly drift 0.20 | B | profile BTI | c02 | 18 | 291 | 205 | 0.95 | 1.10 | — | -3.5 | 0.339 |
| weekly drift 0.20 | B | profile p95 travel time | c00 | 9 | 400 | 220 | 0.83 | 0.80 | — | -2.4 | 517.175 |
| weekly drift 0.20 | B | profile p95 travel time | c00 | 18 | 400 | 217 | 0.89 | 0.83 | — | -0.6 | 610.195 |
| weekly drift 0.20 | B | profile p95 travel time | c01 | 9 | 400 | 220 | 0.82 | 0.79 | — | -2.0 | 508.957 |
| weekly drift 0.20 | B | profile p95 travel time | c01 | 18 | 400 | 218 | 0.84 | 0.70 | — | -0.7 | 581.531 |
| weekly drift 0.20 | B | profile p95 travel time | c02 | 9 | 367 | 208 | 0.87 | 0.87 | — | -0.9 | 1842.808 |
| weekly drift 0.20 | B | profile p95 travel time | c02 | 18 | 291 | 205 | 0.91 | 0.92 | — | -0.5 | 2070.723 |
