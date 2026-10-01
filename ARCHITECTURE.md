# Architecture

How AlgoViz is put together, and the decisions behind it. The README covers
what it does and how to run it; this file covers why it is built this way.

## Runtime

```
 one process (uvicorn)                                                     spawned processes
 ┌────────────────────────────────────────────────────────────────────┐    ┌──────────────────────┐
 │ event loop                                                         │    │ model training       │
 │   MarketSource ─► SymbolEngine (per symbol)                        │───►│ HMM regime fits      │
 │     per event   book diff (O(1)) · trade windows · OFI             │    │ (capped BLAS/OpenMP, │
 │     5 Hz        book metrics + depth profile (dirty flag)          │    │  single-flight,      │
 │     1 Hz        bar close: z-scores, regime, bar persistence       │    │  timeout)            │
 │     intel tier  signals · alerts · ML bookkeeping (off bar close)  │    └──────────────────────┘
 │   WebSocket hub (per-client queues, latest-wins for high rate)     │
 │   REST API (FastAPI)                                               │    threads
 │                                                                    │    ┌──────────────────────┐
 │   BarWriter · PredictionStore (batched, re-queued on failure)      │───►│ inference + SHAP     │
 └────────────────────────────────────────────────────────────────────┘    │ (one per model)      │
                                                                           └──────────────────────┘
```

The loop only does bookkeeping. Anything CPU-bound (fits, predictions, SHAP,
bcrypt, history rebuilds) runs elsewhere, and a loop-lag monitor proves it:
p99 is exported on `/metrics` and gates `/health/ready`.

**Data flow.** Exchange events are processed in event time. Features are
rolling windows with O(1) updates, baselines are EWMAs, and bars close on event
time (with a wall-clock flush for quiet markets). Each closed bar feeds the
regime detector, the ML engine (labels resolve `horizon` bars later) and the
intelligence tier: signals, alerts and the prediction. The bar is persisted
and streamed.

**Contracts.** REST responses and WebSocket frames are Pydantic models. The
OpenAPI document (`frontend/lib/api/openapi.json`) is generated from them and
the frontend's TypeScript types from that; CI fails if either is stale.
Errors are RFC 9457 problems, so the error shape is typed too.

**Frontend.** A Next.js app over one WebSocket. Streamed data lands in
zustand stores backed by typed-array rings, and charts read the rings
directly (canvas, lightweight-charts, R3F) without React re-rendering per
frame. REST data goes through TanStack Query. The design system is CSS tokens
(`app/globals.css`), mirrored for drawing code in `lib/theme`.

## Decisions

Short records: the context, what was decided, and what it costs.

### ADR-1 · One event loop per process; CPU work in threads and spawned processes

*Context.* sklearn and hmmlearn release the GIL but open OpenMP regions whose
barriers stalled the loop for seconds under load, dropping exchange keepalives.
*Decision.* The loop never runs model code. Inference and SHAP run on one
thread per model with OpenMP pinned to a single thread. Training and HMM fits
run in freshly spawned processes with capped threads, single-flight and a
timeout. *Consequence.* Training results cross a process boundary (pickled
artefacts), and SHAP explainers, which are not reliably picklable, are rebuilt
on the inference thread one at a time.

### ADR-2 · Event time everywhere

*Context.* Replay at any speed and the simulator must produce the same bars as
live data. *Decision.* Bars, windows and labels key on exchange timestamps. A
gap longer than `SESSION_GAP_MS` starts a new session: no feature window or
label straddles one. *Consequence.* A wall-clock flush is still needed so a
quiet market produces empty bars.

### ADR-3 · One condition language

*Context.* Signals, alerts and strategies all need "when X > y and regime is Z".
*Decision.* One JSON condition tree (`all` / `any` / `not` over
`{f, op, v}` leaves), validated against the feature catalog, evaluated by the
same code in the engine, the alert evaluator and the backtester. *Consequence.*
A new feature becomes usable everywhere by adding it to the catalog. Renaming
a categorical value needs a data migration (see `4c1e7b2a9d30`).

### ADR-4 · Evaluate what we serve

*Context.* The walk-forward numbers once described an uncalibrated model with
random-split early stopping, while the served model was calibrated.
*Decision.* One recipe (`fit_model`: early stopping on the time-ordered tail,
calibration on embargoed time splits) builds both the served model and every
fold model. Folds are scored held-out against the class prior and a
regularised logistic baseline, with reliability curves and the Brier
decomposition. Importance is held-out log-loss. *Consequence.* Training costs
about 3× the compute, which is why it runs in a spawned process. The numbers
can, and on live BTC at 5 s do, show no edge; the UI says so.

### ADR-5 · Regime as two axes

*Context.* "Quiet / trending / volatile / breakout" came entirely from volatility
z, yet "trending" implied direction. *Decision.* The HMM gives a volatility
state (calm → extreme). A separate trend (down / flat / up) comes from a
Newey–West t-statistic on the drift, with hysteresis. *Consequence.* Stored
labels and saved strategies were migrated; trend-aware rules are possible.

### ADR-6 · Reads public, writes gated

*Context.* A single-operator deployment on a public URL. *Decision.* Reads,
including the WebSocket, are public. Mutations need a bearer credential when
`MUTATIONS_REQUIRE_AUTH` is on (production by default): the `ADMIN_TOKEN` or a
user's JWT. Registration is off in production. Rate limits key on the client
address, resolved only through `TRUSTED_PROXIES`, with stricter buckets for
writes and backtests. *Consequence.* The operator pastes the token into the
frontend (Settings → Access); it stays in that browser.

### ADR-7 · SQLite locally, Postgres hosted

*Context.* Render's disk is ephemeral. *Decision.* SQLite with WAL for local
and Docker use. Postgres via `DATABASE_URL` (asyncpg) for hosted deployments.
Alembic migrations run at startup and are written to work on both.
*Consequence.* Migrations avoid SQLite-only SQL; batch operations cover the
ALTERs SQLite can't do.

### ADR-8 · WebGL only where depth carries information

*Context.* The first redesign drew decorative 3D everywhere; it was slow on
integrated GPUs and hard to read. *Decision.* The hero heatmap is Canvas 2D
image data, the same view on every tier. The 3D terrain is opt-in, and every
other chart is 2D. A detected software renderer gets the low tier.
*Consequence.* The terrain path needs its own test project (forced mid tier).

### ADR-9 · Deterministic end-to-end runs

*Context.* A growing e2e database made runs depend on each other, and the
Intelligence page was empty until a model trained. *Decision.*
`scripts/seed_e2e.py` builds a template once (30 min of fixed-seed synthetic
history and a model trained on it), and every run starts from a fresh copy.
Visual baselines pin a silent WebSocket, a frozen clock and reduced motion.
*Consequence.* The template rebuilds when the migrations, the model manifest
or the seed version change (about 30 s).

### ADR-10 · Observability from existing stats

*Context.* The engine already kept counters for the UI. *Decision.* `/metrics`
reads them at scrape time through one custom collector. The only hot-path
instrument is the feed-latency histogram. Repeated warnings are collapsed to
one line a minute with a count. *Consequence.* Metric values are as fresh as
the stats (per scrape), and the hot paths carry no extra cost.
