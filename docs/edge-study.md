# Edge study

- Data: 6,562 bars (0.08 days of bars) in 6 sessions, 2026-09-26 13:17 to 2026-10-02 17:16 UTC; 6,178 samples with a full lookback.
- Rule, fixed in advance: adopt only if the edge over the trailing prior is positive in at least 3 development folds and on the holdout, with at least 7 days of bars.
- **Verdict: preliminary: 0.08 days of bars, the rule needs 7; nothing is decided.**
- Holdout (120 s · k 2 · floor 2 bps, without scaled quantities): 1,252 samples, log-loss 0.7365 vs class prior 0.6916 and trailing prior 0.8078.

Development walk-forward, best first. Edges are log-loss improvements in nats; the trailing prior is the class mix of the labels already resolved at each prediction.

| Label | Features | Samples | Flat | Edge vs prior | Edge vs trailing prior | Folds beating it |
|---|---|--:|--:|--:|--:|--:|
| 120 s · k 2 · floor 2 bps | without scaled quantities | 5,488 | 75% | -0.0160 | +0.1634 ± 0.2369 | 3 of 4 |
| 120 s · k 2 · floor 2 bps | all features | 5,488 | 75% | -0.0161 | +0.1633 ± 0.2371 | 3 of 4 |
| 120 s · k 2 · floor 2 bps | without hour of day | 5,488 | 75% | -0.0458 | +0.1336 ± 0.3053 | 3 of 4 |
| 120 s · k 2 · floor 0.5 bps | all features | 5,488 | 71% | +0.0218 | +0.0412 ± 0.2362 | 2 of 4 |
| 120 s · k 2 · floor 1 bps | all features | 5,488 | 73% | +0.0218 | +0.0412 ± 0.2362 | 2 of 4 |
| 120 s · k 2 · floor 0.5 bps | without scaled quantities | 5,488 | 71% | +0.0178 | +0.0373 ± 0.2249 | 2 of 4 |
| 120 s · k 2 · floor 1 bps | without scaled quantities | 5,488 | 73% | +0.0178 | +0.0373 ± 0.2249 | 2 of 4 |
| 120 s · k 2 · floor 0.5 bps | without hour of day | 5,488 | 71% | -0.0079 | +0.0115 ± 0.2732 | 2 of 4 |
| 120 s · k 2 · floor 1 bps | without hour of day | 5,488 | 73% | -0.0079 | +0.0115 ± 0.2732 | 2 of 4 |
| 30 s · k 0.5 · floor 4 bps | all features | 6,028 | 91% | +0.0058 | +0.0032 ± 0.0176 | 2 of 4 |
| 30 s · k 1 · floor 4 bps | all features | 6,028 | 92% | +0.0058 | +0.0032 ± 0.0176 | 2 of 4 |
| 30 s · k 2 · floor 4 bps | all features | 6,028 | 94% | +0.0048 | +0.0024 ± 0.0191 | 2 of 4 |
| 5 s · k 0.5 · floor 1 bps | all features | 6,178 | 88% | +0.0039 | +0.0014 ± 0.0179 | 2 of 4 |
| 5 s · k 1 · floor 1 bps | all features | 6,178 | 90% | +0.0039 | +0.0014 ± 0.0179 | 2 of 4 |
| 30 s · k 0.5 · floor 1 bps | all features | 6,028 | 62% | -0.0288 | -0.0040 ± 0.0513 | 2 of 4 |
| 15 s · k 0.5 · floor 2 bps | all features | 6,118 | 87% | -0.0083 | -0.0106 ± 0.0787 | 2 of 4 |
| 15 s · k 1 · floor 2 bps | all features | 6,118 | 89% | -0.0083 | -0.0106 ± 0.0787 | 2 of 4 |
| 60 s · k 1 · floor 2 bps | all features | 5,848 | 70% | -0.0139 | -0.0197 ± 0.2422 | 2 of 4 |
| 5 s · k 2 · floor 0.5 bps | all features | 6,178 | 93% | -0.0169 | -0.0198 ± 0.0195 | 0 of 4 |
| 5 s · k 0.5 · floor 4 bps | all features | 6,178 | 99% | -0.0226 | -0.0216 ± 0.0409 | 2 of 4 |
| 5 s · k 1 · floor 4 bps | all features | 6,178 | 99% | -0.0226 | -0.0216 ± 0.0409 | 2 of 4 |
| 5 s · k 2 · floor 4 bps | all features | 6,178 | 99% | -0.0226 | -0.0216 ± 0.0409 | 2 of 4 |
| 15 s · k 1 · floor 1 bps | all features | 6,118 | 80% | -0.0396 | -0.0250 ± 0.0359 | 1 of 4 |
| 30 s · k 1 · floor 1 bps | all features | 6,028 | 70% | -0.0742 | -0.0308 ± 0.1505 | 2 of 4 |
| 60 s · k 2 · floor 2 bps | all features | 5,848 | 81% | -0.1167 | -0.0349 ± 0.1590 | 2 of 4 |
| 5 s · k 0.5 · floor 0.5 bps | all features | 6,178 | 82% | -0.0223 | -0.0367 ± 0.0377 | 0 of 4 |
| 15 s · k 0.5 · floor 0.5 bps | all features | 6,118 | 65% | -0.0028 | -0.0379 ± 0.0513 | 1 of 4 |
| 15 s · k 0.5 · floor 1 bps | all features | 6,118 | 74% | -0.0442 | -0.0399 ± 0.0303 | 1 of 4 |
| 5 s · k 2 · floor 1 bps | all features | 6,178 | 94% | -0.0417 | -0.0403 ± 0.0790 | 2 of 4 |
| 30 s · k 0.5 · floor 0.5 bps | all features | 6,028 | 53% | +0.0019 | -0.0405 ± 0.0711 | 1 of 4 |
| 15 s · k 1 · floor 0.5 bps | all features | 6,118 | 76% | -0.0351 | -0.0457 ± 0.0290 | 0 of 4 |
| 15 s · k 0.5 · floor 4 bps | all features | 6,118 | 96% | -0.0515 | -0.0507 ± 0.0662 | 1 of 4 |
| 15 s · k 1 · floor 4 bps | all features | 6,118 | 96% | -0.0515 | -0.0507 ± 0.0662 | 1 of 4 |
| 15 s · k 2 · floor 4 bps | all features | 6,118 | 97% | -0.0515 | -0.0507 ± 0.0662 | 1 of 4 |
| 5 s · k 1 · floor 0.5 bps | all features | 6,178 | 86% | -0.0403 | -0.0548 ± 0.0530 | 0 of 4 |
| 30 s · k 1 · floor 0.5 bps | all features | 6,028 | 67% | -0.0857 | -0.0625 ± 0.1384 | 2 of 4 |
| 30 s · k 2 · floor 1 bps | all features | 6,028 | 83% | -0.1413 | -0.0661 ± 0.1750 | 2 of 4 |
| 30 s · k 2 · floor 0.5 bps | all features | 6,028 | 82% | -0.1395 | -0.0671 ± 0.1588 | 2 of 4 |
| 5 s · k 0.5 · floor 2 bps | all features | 6,178 | 95% | -0.0837 | -0.0821 ± 0.1373 | 1 of 4 |
| 5 s · k 1 · floor 2 bps | all features | 6,178 | 96% | -0.0837 | -0.0821 ± 0.1373 | 1 of 4 |
| 5 s · k 2 · floor 2 bps | all features | 6,178 | 97% | -0.0837 | -0.0821 ± 0.1373 | 1 of 4 |
| 60 s · k 0.5 · floor 2 bps | all features | 5,848 | 65% | -0.0707 | -0.0858 ± 0.2888 | 2 of 4 |
| 30 s · k 2 · floor 2 bps | all features | 6,028 | 88% | -0.1146 | -0.0942 ± 0.1486 | 1 of 4 |
| 15 s · k 2 · floor 0.5 bps | all features | 6,118 | 88% | -0.1198 | -0.0949 ± 0.1188 | 1 of 4 |
| 30 s · k 0.5 · floor 2 bps | all features | 6,028 | 78% | -0.0991 | -0.0974 ± 0.1482 | 1 of 4 |
| 30 s · k 1 · floor 2 bps | all features | 6,028 | 82% | -0.0991 | -0.0974 ± 0.1482 | 1 of 4 |
| 15 s · k 2 · floor 1 bps | all features | 6,118 | 89% | -0.1236 | -0.0999 ± 0.1331 | 1 of 4 |
| 60 s · k 2 · floor 0.5 bps | all features | 5,848 | 78% | -0.1115 | -0.1073 ± 0.0977 | 1 of 4 |
| 60 s · k 0.5 · floor 1 bps | all features | 5,848 | 47% | -0.0738 | -0.1134 ± 0.1330 | 1 of 4 |
| 60 s · k 2 · floor 1 bps | all features | 5,848 | 79% | -0.1176 | -0.1152 ± 0.1019 | 0 of 4 |
| 15 s · k 2 · floor 2 bps | all features | 6,118 | 93% | -0.1265 | -0.1260 ± 0.1976 | 1 of 4 |
| 60 s · k 1 · floor 0.5 bps | all features | 5,848 | 56% | -0.1109 | -0.1343 ± 0.1868 | 1 of 4 |
| 60 s · k 1 · floor 1 bps | all features | 5,848 | 58% | -0.1195 | -0.1402 ± 0.1854 | 1 of 4 |
| 120 s · k 0.5 · floor 2 bps | all features | 5,488 | 46% | -0.2155 | -0.1949 ± 0.7552 | 3 of 4 |
| 120 s · k 1 · floor 2 bps | all features | 5,488 | 54% | -0.3451 | -0.2215 ± 0.7310 | 3 of 4 |
| 120 s · k 1 · floor 0.5 bps | all features | 5,488 | 41% | -0.2566 | -0.2488 ± 0.4106 | 1 of 4 |
| 120 s · k 1 · floor 1 bps | all features | 5,488 | 44% | -0.2622 | -0.2517 ± 0.4092 | 1 of 4 |
| 60 s · k 0.5 · floor 0.5 bps | all features | 5,848 | 39% | -0.2082 | -0.2917 ± 0.1964 | 0 of 4 |
| 60 s · k 2 · floor 4 bps | all features | 5,848 | 91% | -0.3359 | -0.3127 ± 0.4311 | 1 of 4 |
| 120 s · k 0.5 · floor 0.5 bps | all features | 5,488 | 21% | -0.2440 | -0.3142 ± 0.5815 | 2 of 4 |
| 60 s · k 0.5 · floor 4 bps | all features | 5,848 | 84% | -0.3401 | -0.3223 ± 0.4336 | 1 of 4 |
| 60 s · k 1 · floor 4 bps | all features | 5,848 | 86% | -0.3401 | -0.3223 ± 0.4336 | 1 of 4 |
| 120 s · k 0.5 · floor 1 bps | all features | 5,488 | 25% | -0.2864 | -0.3692 ± 0.6307 | 1 of 4 |
| 120 s · k 0.5 · floor 4 bps | all features | 5,488 | 73% | -0.4765 | -0.5003 ± 0.7047 | 1 of 4 |
| 120 s · k 1 · floor 4 bps | all features | 5,488 | 77% | -0.4765 | -0.5003 ± 0.7047 | 1 of 4 |
| 120 s · k 2 · floor 4 bps | all features | 5,488 | 84% | -0.7036 | -0.6381 ± 1.3645 | 2 of 4 |
