# Edge study protocol

**Frozen 2026-10-08 14:55 UTC** (`FREEZE_MS = 1_791_471_300_000` in `backend/algoviz/ml/study.py`).

- Bars with an open time at or after the freeze decide.
- Earlier bars shaped this protocol, so they only explore.
- Every report prints the first 16 hex digits of this file's SHA-256. Any change to the file changes that digest and must be logged under "Changes" below.

Plan: `docs/implementation-plan.md` §11 (W5), §12 (W1–W3), decisions E9 and F1–F6.

## Question

Does the served model beat both the class prior and the trailing prior on live BTCUSDT 1-second bars, under any of the tested label definitions and training windows?

## Data

- **Source.** Live BTCUSDT 1-second bars from the collector's database and from the export files (`scripts/export_bars.py`). There is one bar per open time; exports and the database deduplicate by it.
- **Deciding data.** Bars with an open time at or after the freeze, **at least 7 days of them**: 604,800 bars, counted as bars, not as calendar span.
  - A deciding run on fewer is refused. The deciding data stay unexamined until they are complete.
- **Samples.**
  - Every bar with a full lookback, run through the engine's own bookkeeping (`MLEngine.ingest_bar`): its feature vectors, rolling medians and session splits.
  - A gap of more than 5 s between bars starts a new session.

## Labels: 60 definitions

- **Method:** the served triple barrier (`barrier_bps`, `triple_barrier`). No label reaches across a session gap.
- **Horizons:** 5, 15, 30, 60 and 120 s.
- **Barrier k:** 0.5, 1 and 2.
- **Barrier floor:** 0.5, 1, 2 and 4 bps.

## Configurations: 75

1. **Base grid (60).** Every label definition, with all features and the served training window (`ML_MAX_SAMPLES` = 20,000 samples).
2. **Refinements (15).** For the three best label definitions by development edge:
   - **Ablations,** on the served window:
     - without the hour-of-day features (`hour_sin`, `hour_cos`);
     - without the median-scaled quantities.
   - **Training variants,** with all features:
     - a 1 h window (3,600 samples);
     - a 4 h window (14,400 samples);
     - the served window with recency weights that halve with every hour of bar time.
   - **How recency-weighted fits are binned.** Each feature is replaced by its bin among 255 unweighted quantiles of the training window: the edges an unweighted fit uses. The weights shape the trees and the calibration, not the bin edges.

## Evaluation, as served

- **Recipe:** the served one, `fit_model` (calibrated gradient boosting, early stopping on the time-ordered tail). The seed is 7.
- **Split.** Per configuration, the first 75 % of its labelled samples are the development part; the rest is the holdout.
- **Blocks.** A block is 600 samples, the served retrain cadence.
  - For each block, the recipe is fitted on a training window that ends one horizon before the block: the embargo, so no training label reaches into it.
  - The window is capped at the configuration's size, with at least 300 samples (`ML_MIN_DATA_POINTS`) and two classes.
  - Then the block is predicted.
- **Development.** The development samples after the first 300 + horizon are cut into 4 quarters, with 8 evenly spaced blocks in each. A quarter pools its blocks.
- **Holdout.** Every block from the 75 % mark plus one horizon to the end, for the selected configuration only.
- **Baselines, per block:**
  - the class prior of the training window, Laplace-smoothed;
  - the trailing prior: the last 600 labels resolved by each prediction, Laplace-smoothed.
- **Score.** Mean log-loss in nats. **Edge** = min(class prior's log-loss, trailing prior's log-loss) − the model's log-loss.

## Selection and rule

- **Selection:** the configuration with the highest mean development edge across its quarters.
- **Adopt it only if all of these hold:**
  - its edge is positive in at least 3 of the 4 development quarters;
  - its edge on the holdout is positive;
  - the run used at least 7 days of deciding bars.
- **Otherwise,** the finding is "no edge at any tested definition on N days". It is recorded in the plan, and the product says so.

## What adoption would change

- New served defaults: the label definition, and the training window or weights.
- A retrain.
- A `FEATURE_SCHEMA_VERSION` bump, if an ablation wins.
- The UI copy.
- If the recency-weighted variant wins, the engine has to train on bin codes with recency weights, which it does not do today.

## Commands

```bash
python backend/scripts/ml_study.py --out docs/edge-study.md            # exploratory: bars before the freeze
python backend/scripts/ml_study.py --decide --out docs/edge-study.md   # deciding: refused below 7 days
```

## Changes

None since the freeze.
