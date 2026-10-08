# Edge study

- Data, exploratory (before the freeze): 24,018 bars (0.28 days of bars) in 13 sessions, 2026-09-26 13:17 to 2026-10-08 14:54 UTC; 23,244 samples with a full lookback.
- Protocol: `docs/edge-study-protocol.md` (sha256 b0d882428954f5df), frozen 2026-10-08 14:55 UTC.
- Evaluation as served: a refit every 600 samples; 8 blocks in each of 4 development quarters (the earlier 75%); every block of the holdout.
- Rule, fixed in advance: adopt only if the model beats both the class prior and the trailing prior in at least 3 development quarters and on the holdout, with at least 7 days of bars from the freeze on.
- **Verdict: exploratory: bars from before the protocol was frozen; nothing is decided.**
- Holdout (5 s · k 1 · floor 0.5 bps (without hour of day, served window)): 5,806 samples, log-loss 0.6219 vs class prior 0.6735 and trailing prior 0.6620.

Development, best first. Edges are log-loss improvements in nats; the trailing prior is the class mix of the labels already resolved at each prediction. The rule's edge is over the better of the two priors, quarter by quarter.

| Label | Features | Training | Samples | Flat | Edge vs prior | Edge vs trailing prior | Edge vs the better prior | Quarters beating both |
|---|---|---|--:|--:|--:|--:|--:|--:|
| 5 s · k 1 · floor 0.5 bps | without hour of day | served window | 23,244 | 83% | +0.0250 | +0.0151 | +0.0151 ± 0.0471 | 2 of 4 |
| 5 s · k 1 · floor 0.5 bps | all features | served window | 23,244 | 83% | +0.0210 | +0.0111 | +0.0111 ± 0.0503 | 2 of 4 |
| 5 s · k 1 · floor 0.5 bps | without scaled quantities | served window | 23,244 | 83% | +0.0210 | +0.0111 | +0.0111 ± 0.0533 | 2 of 4 |
| 5 s · k 1 · floor 0.5 bps | all features | 4 h window | 23,244 | 83% | +0.0200 | +0.0102 | +0.0102 ± 0.0494 | 2 of 4 |
| 5 s · k 1 · floor 1 bps | all features | served window | 23,244 | 87% | +0.0209 | +0.0091 | +0.0075 ± 0.0327 | 2 of 4 |
| 5 s · k 1 · floor 1 bps | all features | 4 h window | 23,244 | 87% | +0.0206 | +0.0088 | +0.0073 ± 0.0324 | 2 of 4 |
| 5 s · k 1 · floor 1 bps | without hour of day | served window | 23,244 | 87% | +0.0197 | +0.0079 | +0.0063 ± 0.0311 | 2 of 4 |
| 5 s · k 2 · floor 0.5 bps | without scaled quantities | served window | 23,244 | 91% | +0.0062 | +0.0092 | +0.0060 ± 0.0196 | 2 of 4 |
| 5 s · k 2 · floor 0.5 bps | without hour of day | served window | 23,244 | 91% | +0.0054 | +0.0084 | +0.0052 ± 0.0205 | 2 of 4 |
| 5 s · k 1 · floor 1 bps | without scaled quantities | served window | 23,244 | 87% | +0.0172 | +0.0054 | +0.0038 ± 0.0389 | 2 of 4 |
| 5 s · k 2 · floor 0.5 bps | all features | served window | 23,244 | 91% | +0.0036 | +0.0066 | +0.0034 ± 0.0213 | 2 of 4 |
| 5 s · k 2 · floor 0.5 bps | all features | 4 h window | 23,244 | 91% | +0.0029 | +0.0059 | +0.0027 ± 0.0204 | 2 of 4 |
| 5 s · k 0.5 · floor 0.5 bps | all features | served window | 23,244 | 78% | +0.0333 | +0.0022 | +0.0007 ± 0.0710 | 2 of 4 |
| 5 s · k 2 · floor 1 bps | all features | served window | 23,244 | 92% | -0.0003 | +0.0007 | -0.0013 ± 0.0285 | 2 of 4 |
| 5 s · k 0.5 · floor 1 bps | all features | served window | 23,244 | 86% | +0.0216 | -0.0007 | -0.0027 ± 0.0459 | 2 of 4 |
| 5 s · k 2 · floor 0.5 bps | all features | served window, 1 h half-life | 23,244 | 91% | -0.0031 | -0.0001 | -0.0033 ± 0.0052 | 1 of 4 |
| 15 s · k 2 · floor 2 bps | all features | served window | 23,124 | 90% | -0.0044 | +0.0064 | -0.0057 ± 0.0247 | 2 of 4 |
| 15 s · k 2 · floor 1 bps | all features | served window | 23,124 | 86% | -0.0078 | +0.0149 | -0.0078 ± 0.0373 | 2 of 4 |
| 15 s · k 1 · floor 0.5 bps | all features | served window | 23,124 | 69% | -0.0077 | -0.0027 | -0.0089 ± 0.0442 | 2 of 4 |
| 5 s · k 2 · floor 2 bps | all features | served window | 23,244 | 96% | -0.0062 | -0.0069 | -0.0093 ± 0.0200 | 2 of 4 |
| 5 s · k 1 · floor 1 bps | all features | served window, 1 h half-life | 23,244 | 87% | +0.0038 | -0.0080 | -0.0095 ± 0.0143 | 1 of 4 |
| 5 s · k 2 · floor 4 bps | all features | served window | 23,244 | 99% | -0.0074 | -0.0097 | -0.0107 ± 0.0125 | 2 of 4 |
| 5 s · k 2 · floor 0.5 bps | all features | 1 h window | 23,244 | 91% | -0.0098 | -0.0072 | -0.0108 ± 0.0278 | 2 of 4 |
| 60 s · k 2 · floor 4 bps | all features | served window | 22,584 | 86% | -0.0123 | +0.0163 | -0.0123 ± 0.0865 | 2 of 4 |
| 15 s · k 2 · floor 0.5 bps | all features | served window | 23,124 | 85% | -0.0125 | +0.0123 | -0.0125 ± 0.0359 | 2 of 4 |
| 30 s · k 0.5 · floor 1 bps | all features | served window | 22,944 | 49% | +0.0111 | +0.0195 | -0.0133 ± 0.0406 | 2 of 4 |
| 5 s · k 1 · floor 0.5 bps | all features | served window, 1 h half-life | 23,244 | 83% | -0.0036 | -0.0135 | -0.0135 ± 0.0231 | 2 of 4 |
| 5 s · k 1 · floor 2 bps | all features | served window | 23,244 | 96% | -0.0038 | -0.0123 | -0.0148 ± 0.0207 | 2 of 4 |
| 5 s · k 1 · floor 0.5 bps | all features | 1 h window | 23,244 | 83% | -0.0026 | -0.0166 | -0.0184 ± 0.0491 | 2 of 4 |
| 5 s · k 0.5 · floor 2 bps | all features | served window | 23,244 | 95% | -0.0023 | -0.0158 | -0.0188 ± 0.0237 | 2 of 4 |
| 5 s · k 0.5 · floor 4 bps | all features | served window | 23,244 | 99% | -0.0134 | -0.0206 | -0.0215 ± 0.0280 | 1 of 4 |
| 5 s · k 1 · floor 4 bps | all features | served window | 23,244 | 99% | -0.0134 | -0.0206 | -0.0215 ± 0.0280 | 1 of 4 |
| 30 s · k 2 · floor 0.5 bps | all features | served window | 22,944 | 80% | -0.0218 | +0.0437 | -0.0218 ± 0.0297 | 2 of 4 |
| 15 s · k 2 · floor 4 bps | all features | served window | 23,124 | 96% | -0.0161 | -0.0186 | -0.0233 ± 0.0278 | 0 of 4 |
| 30 s · k 2 · floor 1 bps | all features | served window | 22,944 | 81% | -0.0234 | +0.0401 | -0.0234 ± 0.0343 | 1 of 4 |
| 5 s · k 1 · floor 1 bps | all features | 1 h window | 23,244 | 87% | -0.0040 | -0.0224 | -0.0235 ± 0.0232 | 1 of 4 |
| 15 s · k 1 · floor 4 bps | all features | served window | 23,124 | 96% | -0.0106 | -0.0193 | -0.0254 ± 0.0272 | 0 of 4 |
| 15 s · k 1 · floor 1 bps | all features | served window | 23,124 | 73% | -0.0170 | -0.0155 | -0.0254 ± 0.0827 | 2 of 4 |
| 120 s · k 1 · floor 2 bps | all features | served window | 21,869 | 47% | -0.0254 | +0.2198 | -0.0254 ± 0.0498 | 2 of 4 |
| 15 s · k 0.5 · floor 4 bps | all features | served window | 23,124 | 96% | -0.0134 | -0.0248 | -0.0311 ± 0.0323 | 0 of 4 |
| 30 s · k 2 · floor 4 bps | all features | served window | 22,944 | 92% | -0.0216 | -0.0243 | -0.0358 ± 0.0401 | 1 of 4 |
| 15 s · k 0.5 · floor 0.5 bps | all features | served window | 23,124 | 56% | -0.0109 | -0.0383 | -0.0383 ± 0.0750 | 1 of 4 |
| 30 s · k 0.5 · floor 0.5 bps | all features | served window | 22,944 | 42% | -0.0054 | -0.0208 | -0.0394 ± 0.0310 | 1 of 4 |
| 120 s · k 0.5 · floor 2 bps | all features | served window | 21,869 | 33% | -0.0403 | +0.1608 | -0.0403 ± 0.0395 | 0 of 4 |
| 120 s · k 1 · floor 0.5 bps | all features | served window | 21,869 | 40% | -0.0447 | +0.1249 | -0.0447 ± 0.0433 | 1 of 4 |
| 120 s · k 1 · floor 1 bps | all features | served window | 21,869 | 41% | -0.0448 | +0.1174 | -0.0448 ± 0.0411 | 0 of 4 |
| 15 s · k 0.5 · floor 1 bps | all features | served window | 23,124 | 66% | -0.0196 | -0.0393 | -0.0455 ± 0.1033 | 2 of 4 |
| 60 s · k 2 · floor 1 bps | all features | served window | 22,584 | 76% | -0.0466 | +0.0305 | -0.0466 ± 0.0245 | 0 of 4 |
| 30 s · k 2 · floor 2 bps | all features | served window | 22,944 | 84% | -0.0482 | -0.0086 | -0.0482 ± 0.0592 | 1 of 4 |
| 60 s · k 2 · floor 2 bps | all features | served window | 22,584 | 78% | -0.0546 | +0.0491 | -0.0546 ± 0.0800 | 1 of 4 |
| 30 s · k 1 · floor 4 bps | all features | served window | 22,944 | 89% | -0.0311 | -0.0399 | -0.0570 ± 0.0651 | 1 of 4 |
| 60 s · k 0.5 · floor 2 bps | all features | served window | 22,584 | 49% | -0.0402 | +0.0079 | -0.0622 ± 0.0280 | 0 of 4 |
| 30 s · k 0.5 · floor 4 bps | all features | served window | 22,944 | 89% | -0.0330 | -0.0463 | -0.0635 ± 0.0703 | 1 of 4 |
| 60 s · k 1 · floor 4 bps | all features | served window | 22,584 | 77% | -0.0603 | -0.0399 | -0.0643 ± 0.1237 | 1 of 4 |
| 15 s · k 1 · floor 2 bps | all features | served window | 23,124 | 84% | -0.0504 | -0.0588 | -0.0646 ± 0.1089 | 2 of 4 |
| 30 s · k 1 · floor 2 bps | all features | served window | 22,944 | 71% | -0.0524 | -0.0343 | -0.0676 ± 0.1183 | 2 of 4 |
| 60 s · k 1 · floor 0.5 bps | all features | served window | 22,584 | 48% | -0.0677 | +0.0187 | -0.0677 ± 0.0823 | 2 of 4 |
| 60 s · k 1 · floor 2 bps | all features | served window | 22,584 | 57% | -0.0695 | +0.0209 | -0.0695 ± 0.0503 | 1 of 4 |
| 60 s · k 1 · floor 1 bps | all features | served window | 22,584 | 49% | -0.0695 | +0.0321 | -0.0695 ± 0.0855 | 2 of 4 |
| 60 s · k 2 · floor 0.5 bps | all features | served window | 22,584 | 76% | -0.0696 | +0.0156 | -0.0696 ± 0.0643 | 0 of 4 |
| 60 s · k 0.5 · floor 4 bps | all features | served window | 22,584 | 76% | -0.0614 | -0.0476 | -0.0714 ± 0.1214 | 2 of 4 |
| 120 s · k 1 · floor 4 bps | all features | served window | 21,869 | 62% | -0.0753 | +0.0295 | -0.0753 ± 0.0974 | 2 of 4 |
| 15 s · k 0.5 · floor 2 bps | all features | served window | 23,124 | 83% | -0.0508 | -0.0688 | -0.0756 ± 0.1062 | 2 of 4 |
| 30 s · k 0.5 · floor 2 bps | all features | served window | 22,944 | 68% | -0.0588 | -0.0521 | -0.0792 ± 0.1075 | 1 of 4 |
| 120 s · k 0.5 · floor 0.5 bps | all features | served window | 21,869 | 17% | -0.0895 | +0.0244 | -0.0895 ± 0.0519 | 0 of 4 |
| 120 s · k 0.5 · floor 4 bps | all features | served window | 21,869 | 58% | -0.0920 | +0.0120 | -0.0920 ± 0.0999 | 2 of 4 |
| 120 s · k 2 · floor 4 bps | all features | served window | 21,869 | 76% | -0.0944 | +0.0628 | -0.0944 ± 0.1279 | 1 of 4 |
| 120 s · k 0.5 · floor 1 bps | all features | served window | 21,869 | 19% | -0.0955 | +0.0349 | -0.0955 ± 0.0521 | 0 of 4 |
| 30 s · k 1 · floor 1 bps | all features | served window | 22,944 | 61% | -0.1013 | -0.0536 | -0.1013 ± 0.1869 | 2 of 4 |
| 120 s · k 2 · floor 0.5 bps | all features | served window | 21,869 | 68% | -0.1147 | +0.1192 | -0.1147 ± 0.1648 | 2 of 4 |
| 60 s · k 0.5 · floor 1 bps | all features | served window | 22,584 | 33% | -0.1076 | -0.0805 | -0.1368 ± 0.0957 | 1 of 4 |
| 30 s · k 1 · floor 0.5 bps | all features | served window | 22,944 | 59% | -0.1405 | -0.0961 | -0.1405 ± 0.2193 | 2 of 4 |
| 60 s · k 0.5 · floor 0.5 bps | all features | served window | 22,584 | 28% | -0.1096 | -0.1110 | -0.1453 ± 0.0307 | 0 of 4 |
| 120 s · k 2 · floor 2 bps | all features | served window | 21,869 | 70% | -0.2520 | +0.0282 | -0.2520 ± 0.3463 | 2 of 4 |
| 120 s · k 2 · floor 1 bps | all features | served window | 21,869 | 69% | -0.2605 | -0.0640 | -0.2605 ± 0.3095 | 2 of 4 |
