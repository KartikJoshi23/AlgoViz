# Edge study

- Data: 15,824 bars (0.18 days of bars) in 12 sessions, 2026-09-26 13:17 to 2026-10-07 19:00 UTC; 15,114 samples with a full lookback.
- Rule, fixed in advance: adopt only if the model beats both the class prior and the trailing prior in at least 3 development folds and on the holdout, with at least 7 days of bars.
- **Verdict: preliminary: 0.18 days of bars, the rule needs 7; nothing is decided.**
- Holdout (120 s · k 2 · floor 0.5 bps, all features): 3,370 samples, log-loss 1.3784 vs class prior 0.8396 and trailing prior 1.0262.

Development walk-forward, best first. Edges are log-loss improvements in nats; the trailing prior is the class mix of the labels already resolved at each prediction. The rule's edge is over the better of the two priors, fold by fold.

| Label | Features | Samples | Flat | Edge vs prior | Edge vs trailing prior | Edge vs the better prior | Folds beating both |
|---|---|--:|--:|--:|--:|--:|--:|
| 120 s · k 2 · floor 0.5 bps | all features | 13,957 | 71% | +0.0482 | +0.3229 | +0.0482 ± 0.0345 | 4 of 4 |
| 120 s · k 2 · floor 1 bps | all features | 13,957 | 72% | +0.0396 | +0.2460 | +0.0396 ± 0.0489 | 3 of 4 |
| 5 s · k 2 · floor 1 bps | without hour of day | 15,114 | 93% | +0.0010 | +0.0019 | -0.0031 ± 0.0191 | 2 of 4 |
| 5 s · k 2 · floor 1 bps | without scaled quantities | 15,114 | 93% | -0.0084 | -0.0074 | -0.0124 ± 0.0226 | 2 of 4 |
| 5 s · k 2 · floor 1 bps | all features | 15,114 | 93% | -0.0086 | -0.0076 | -0.0126 ± 0.0212 | 1 of 4 |
| 5 s · k 2 · floor 0.5 bps | all features | 15,114 | 92% | -0.0118 | -0.0102 | -0.0151 ± 0.0171 | 1 of 4 |
| 5 s · k 1 · floor 1 bps | all features | 15,114 | 89% | +0.0055 | -0.0196 | -0.0222 ± 0.0595 | 3 of 4 |
| 120 s · k 2 · floor 2 bps | all features | 13,957 | 74% | -0.0256 | +0.3556 | -0.0256 ± 0.0655 | 2 of 4 |
| 120 s · k 2 · floor 0.5 bps | without scaled quantities | 13,957 | 71% | -0.0282 | +0.2465 | -0.0282 ± 0.1242 | 2 of 4 |
| 5 s · k 2 · floor 4 bps | all features | 15,114 | 99% | -0.0203 | -0.0277 | -0.0289 ± 0.0309 | 0 of 4 |
| 5 s · k 2 · floor 2 bps | all features | 15,114 | 97% | -0.0199 | -0.0261 | -0.0296 ± 0.0346 | 2 of 4 |
| 120 s · k 2 · floor 4 bps | all features | 13,957 | 80% | -0.0298 | +0.1848 | -0.0298 ± 0.0352 | 1 of 4 |
| 5 s · k 1 · floor 0.5 bps | all features | 15,114 | 85% | -0.0078 | -0.0297 | -0.0318 ± 0.0642 | 2 of 4 |
| 120 s · k 2 · floor 1 bps | without scaled quantities | 13,957 | 72% | -0.0444 | +0.1620 | -0.0444 ± 0.1594 | 2 of 4 |
| 15 s · k 2 · floor 2 bps | all features | 15,004 | 91% | -0.0406 | -0.0238 | -0.0444 ± 0.0604 | 0 of 4 |
| 15 s · k 2 · floor 4 bps | all features | 15,004 | 97% | -0.0281 | -0.0412 | -0.0446 ± 0.0498 | 0 of 4 |
| 15 s · k 2 · floor 1 bps | all features | 15,004 | 87% | -0.0423 | -0.0159 | -0.0462 ± 0.0485 | 1 of 4 |
| 60 s · k 2 · floor 4 bps | all features | 14,552 | 88% | -0.0465 | -0.0167 | -0.0468 ± 0.0616 | 1 of 4 |
| 5 s · k 0.5 · floor 1 bps | all features | 15,114 | 88% | +0.0022 | -0.0466 | -0.0474 ± 0.1016 | 3 of 4 |
| 120 s · k 2 · floor 1 bps | without hour of day | 13,957 | 72% | -0.0475 | +0.1589 | -0.0475 ± 0.1344 | 2 of 4 |
| 5 s · k 0.5 · floor 4 bps | all features | 15,114 | 99% | -0.0310 | -0.0494 | -0.0504 ± 0.0627 | 0 of 4 |
| 5 s · k 1 · floor 4 bps | all features | 15,114 | 99% | -0.0310 | -0.0494 | -0.0504 ± 0.0627 | 0 of 4 |
| 5 s · k 1 · floor 2 bps | all features | 15,114 | 96% | -0.0204 | -0.0492 | -0.0526 ± 0.0626 | 1 of 4 |
| 15 s · k 2 · floor 0.5 bps | all features | 15,004 | 86% | -0.0533 | -0.0267 | -0.0560 ± 0.0558 | 1 of 4 |
| 30 s · k 2 · floor 1 bps | all features | 14,852 | 82% | -0.0579 | +0.0128 | -0.0579 ± 0.0461 | 0 of 4 |
| 15 s · k 1 · floor 1 bps | all features | 15,004 | 76% | -0.0367 | -0.0432 | -0.0622 ± 0.0635 | 1 of 4 |
| 120 s · k 1 · floor 4 bps | all features | 13,957 | 69% | -0.0577 | +0.0561 | -0.0632 ± 0.0904 | 1 of 4 |
| 30 s · k 1 · floor 2 bps | all features | 14,852 | 75% | -0.0428 | -0.0251 | -0.0646 ± 0.0529 | 1 of 4 |
| 5 s · k 0.5 · floor 2 bps | all features | 15,114 | 96% | -0.0194 | -0.0620 | -0.0656 ± 0.0799 | 1 of 4 |
| 30 s · k 2 · floor 0.5 bps | all features | 14,852 | 81% | -0.0671 | +0.0042 | -0.0671 ± 0.0235 | 0 of 4 |
| 5 s · k 0.5 · floor 0.5 bps | all features | 15,114 | 80% | -0.0104 | -0.0698 | -0.0698 ± 0.1075 | 2 of 4 |
| 30 s · k 2 · floor 2 bps | all features | 14,852 | 86% | -0.0698 | -0.0252 | -0.0698 ± 0.0474 | 0 of 4 |
| 60 s · k 1 · floor 2 bps | all features | 14,552 | 62% | -0.0595 | +0.0688 | -0.0703 ± 0.1127 | 2 of 4 |
| 15 s · k 0.5 · floor 1 bps | all features | 15,004 | 70% | -0.0173 | -0.0532 | -0.0710 ± 0.1114 | 1 of 4 |
| 15 s · k 1 · floor 4 bps | all features | 15,004 | 96% | -0.0320 | -0.0720 | -0.0758 ± 0.0971 | 0 of 4 |
| 60 s · k 1 · floor 0.5 bps | all features | 14,552 | 52% | -0.0611 | +0.0402 | -0.0772 ± 0.0685 | 1 of 4 |
| 120 s · k 1 · floor 0.5 bps | all features | 13,957 | 43% | -0.0516 | +0.0923 | -0.0810 ± 0.0663 | 1 of 4 |
| 15 s · k 1 · floor 2 bps | all features | 15,004 | 86% | -0.0424 | -0.0679 | -0.0839 ± 0.0961 | 1 of 4 |
| 15 s · k 0.5 · floor 4 bps | all features | 15,004 | 96% | -0.0329 | -0.0807 | -0.0847 ± 0.1073 | 0 of 4 |
| 120 s · k 1 · floor 1 bps | all features | 13,957 | 45% | -0.0624 | +0.0757 | -0.0885 ± 0.0856 | 1 of 4 |
| 30 s · k 0.5 · floor 2 bps | all features | 14,852 | 72% | -0.0512 | -0.0540 | -0.0900 ± 0.0744 | 1 of 4 |
| 15 s · k 0.5 · floor 2 bps | all features | 15,004 | 85% | -0.0485 | -0.0959 | -0.1097 ± 0.1394 | 1 of 4 |
| 60 s · k 1 · floor 4 bps | all features | 14,552 | 81% | -0.0864 | -0.1012 | -0.1106 ± 0.1123 | 1 of 4 |
| 60 s · k 2 · floor 1 bps | all features | 14,552 | 78% | -0.1059 | -0.0369 | -0.1138 ± 0.1296 | 1 of 4 |
| 120 s · k 1 · floor 2 bps | all features | 13,957 | 53% | -0.1232 | +0.2072 | -0.1232 ± 0.1812 | 2 of 4 |
| 30 s · k 1 · floor 0.5 bps | all features | 14,852 | 63% | -0.1323 | -0.0884 | -0.1346 ± 0.0834 | 0 of 4 |
| 15 s · k 1 · floor 0.5 bps | all features | 15,004 | 73% | -0.1200 | -0.1244 | -0.1378 ± 0.1158 | 0 of 4 |
| 30 s · k 1 · floor 1 bps | all features | 14,852 | 65% | -0.1360 | -0.0827 | -0.1397 ± 0.0963 | 0 of 4 |
| 30 s · k 1 · floor 4 bps | all features | 14,852 | 91% | -0.0934 | -0.1404 | -0.1409 ± 0.1898 | 1 of 4 |
| 30 s · k 0.5 · floor 1 bps | all features | 14,852 | 54% | -0.1092 | -0.0880 | -0.1419 ± 0.0646 | 0 of 4 |
| 60 s · k 2 · floor 2 bps | all features | 14,552 | 80% | -0.1446 | -0.0166 | -0.1446 ± 0.0977 | 0 of 4 |
| 60 s · k 0.5 · floor 2 bps | all features | 14,552 | 55% | -0.1141 | -0.0520 | -0.1484 ± 0.1350 | 1 of 4 |
| 60 s · k 1 · floor 1 bps | all features | 14,552 | 54% | -0.1386 | -0.0121 | -0.1537 ± 0.1724 | 1 of 4 |
| 120 s · k 2 · floor 0.5 bps | without hour of day | 13,957 | 71% | -0.1550 | +0.1197 | -0.1550 ± 0.2881 | 2 of 4 |
| 60 s · k 0.5 · floor 4 bps | all features | 14,552 | 80% | -0.1183 | -0.1516 | -0.1580 ± 0.1052 | 0 of 4 |
| 30 s · k 0.5 · floor 0.5 bps | all features | 14,852 | 47% | -0.1204 | -0.1268 | -0.1665 ± 0.1547 | 1 of 4 |
| 60 s · k 2 · floor 0.5 bps | all features | 14,552 | 77% | -0.1646 | -0.0838 | -0.1720 ± 0.0952 | 0 of 4 |
| 30 s · k 0.5 · floor 4 bps | all features | 14,852 | 91% | -0.1086 | -0.1710 | -0.1737 ± 0.2126 | 0 of 4 |
| 120 s · k 0.5 · floor 2 bps | all features | 13,957 | 38% | -0.2132 | +0.0866 | -0.2132 ± 0.2811 | 2 of 4 |
| 30 s · k 2 · floor 4 bps | all features | 14,852 | 93% | -0.2013 | -0.2234 | -0.2236 ± 0.3408 | 0 of 4 |
| 15 s · k 0.5 · floor 0.5 bps | all features | 15,004 | 61% | -0.1998 | -0.2407 | -0.2536 ± 0.3560 | 2 of 4 |
| 120 s · k 0.5 · floor 4 bps | all features | 13,957 | 66% | -0.2739 | -0.1490 | -0.2794 ± 0.4455 | 0 of 4 |
| 120 s · k 0.5 · floor 0.5 bps | all features | 13,957 | 21% | -0.3062 | -0.2006 | -0.3377 ± 0.3056 | 0 of 4 |
| 60 s · k 0.5 · floor 0.5 bps | all features | 14,552 | 34% | -0.2738 | -0.2680 | -0.3439 ± 0.2500 | 0 of 4 |
| 60 s · k 0.5 · floor 1 bps | all features | 14,552 | 38% | -0.3486 | -0.2962 | -0.4034 ± 0.4833 | 0 of 4 |
| 120 s · k 0.5 · floor 1 bps | all features | 13,957 | 23% | -0.5067 | -0.3543 | -0.5374 ± 0.7094 | 1 of 4 |
