# AlgoViz — Overhaul Implementation Plan

> **Status:** approved (revision 2, post-audit). Development proceeds stage by stage per §7. Stages A–F delivered (§9). **Phase 4 (§10) approved 2026-09-24 with all recommendations (D1–D6); Stages G, J, K, L, H and M delivered, plus the theme v3 overhaul (§10.6): Phase 4 is complete, and Stage M was approved 2026-10-01. Phase 5 (§11) was approved 2026-10-01; Stage N's repository side is delivered and awaits review and cutover.**
> **Scope:** complete overhaul of `AlgoViz-Professional/` — core algorithmic engine, backend architecture, and a full frontend rebuild on Next.js + React + Three.js/WebGL + GSAP with a glassmorphism dark theme tied to the product's purpose.
> **Supersedes:** `implementation_plan.md.resolved` (the stale plan from the earlier Streamlit → FastAPI/React migration).

---

## 0. Executive summary

AlgoViz is a real-time **market-microstructure intelligence** platform for BTC/USDT. Today it has a correct-but-naïve feature engine, a real ML loop wrapped in careless validation, a backend where roughly half the advertised features are scaffolded but not wired, and a frontend whose Analytics, Strategies, Alerts, and Order Book views are non-functional because of contract drift.

The overhaul does three things:

1. **Rebuilds the algorithmic core** into a streaming, O(1)-per-event microstructure engine with full L2 order-book reconstruction, order-flow imbalance (OFI), microprice, adaptive z-score baselines, HMM regime detection, volatility-scaled triple-barrier labelling, embargoed time-series validation, calibrated gradient boosting, a stateful signal engine with hysteresis, a working alert evaluator, and a real event-driven backtester — all fed by a 1 Hz bar stream that is persisted, replayable, and reconstructable.
2. **Hardens the backend** into a proper Python package with pinned deps, registered middleware, migrations, persistence that actually persists, typed WebSocket contracts with snapshot-on-connect, per-client subscriptions with backpressure, a replay/synthetic data source for offline development, and tests that run.
3. **Replaces the frontend** with a Next.js (App Router) application: a typed-array Zustand data layer fed by a module-level WebSocket client, TypeScript types generated from the backend's OpenAPI (eliminating contract drift as a bug class), GSAP for all motion, Three.js for the visuals where depth carries information — a **3D order-book liquidity terrain**, GPU **trade-flow particles**, and a **regime-driven shader field** behind the glass — under a dark "Depth" visual identity built from the bid/ask/mid semantics of the order book itself.

Delivery is staged (six stages, each ending in a review stop), backend first.

---

## 1. Current-state findings

Full detail was presented and confirmed in Phase 1. Condensed here so this document stands alone.

### 1.1 Algorithmic core — basic / under-engineered

| Area | Today | Why it's weak |
|---|---|---|
| Feature computation | Every feature (VWAP, TWAP, velocity, buy pressure, volatility) is a Python list-comprehension rescan of the 1000-trade deque, 5× per 500 ms tick | O(n) per feature per tick; cost grows with buffer size; recomputes identical windows |
| Trigger model | Features computed on a wall-clock timer, not on events | Bursty markets are under-sampled; quiet markets are over-sampled |
| Order book | 10-level snapshots from `@depth10@100ms`; only *total* bid/ask volume is used | No microprice, no depth-weighted imbalance, no OFI, no liquidity-at-N-bps; depth `timestamp` is receipt time not exchange time |
| Baselines / thresholds | `velocity_baseline = 20` constant; all rule thresholds are absolute bps constants | Meaningless across assets and market eras; rules flicker on/off at the boundary (no hysteresis) |
| Volatility | `std(returns)` over a 60 s window, not time-scaled | Not comparable across activity levels |
| Regime | `if volatility > 20 and velocity_ratio > 2: "breakout"` | Hard-coded, not learned |
| ML labels | Direction of *last-trade* price 10 **ticks** ahead, fixed ±3 bps | Tick horizon drifts with load; last-trade price is bid-ask-bounce noise; fixed bps ignores volatility |
| ML validation | Random `cross_val_score` on time-series data | Leaks future into past; reported F1 is optimistic |
| ML training | `run_in_executor(self._train)` with no lock; training buffer in RAM only | Concurrent training races; restart loses every label |
| Explainability | `shap` not in requirements; `TreeExplainer` built per request | Always `ImportError` → `None` |
| Backtester | Inserts a row of zeros | Doesn't exist |
| Alerts | Rules stored, never evaluated; `AlertHistory` never written | Doesn't exist |
| Persistence | `MarketSnapshot`, `MLModel` tables never written; APScheduler unused | No history to replay, no model lineage |
| Offline dev | None — live Binance or nothing | Geo-blocked regions (HTTP 451) and tests get no data |

### 1.2 Backend architecture — scaffolded but not wired

- Middleware (`RequestId`, `Timing`, `RateLimit`) defined, never registered.
- Rule engine lives inside an API router (`api/analytics.py`), causing a circular import worked around with a lazy import.
- `broadcast_trade` / `broadcast_alert` never called.
- Flat module layout (`from config import settings`), no `pyproject.toml`, unpinned `>=` deps, no migrations, no lint/type config.
- `passlib` (unmaintained since 2020; incompatible with bcrypt ≥ 4.1 — the reason a bcrypt hash is hard-coded in `strategies.py`) and `python-jose` (open CVEs 2024-33663/33664).
- Backend cannot boot from the repo venv (stale Streamlit-era environment; `pydantic_settings`, `sqlalchemy`, `scikit-learn`, etc. missing).
- `tests/test_features.py` (460 lines) imports from a deleted `src/` tree; `backend/tests/test_api.py` asserts headers that are never set.

### 1.3 Frontend — visually decent, functionally broken

- **Contract drift**: Analytics page expects `trained`/`pending_samples`/`feature_count`, backend sends `model_trained`/`pending_labels`/`feature_names`; SHAP shapes incompatible; regime names disagree; momentum scale off by 100×; backtest POST always 422; alert history expects `rule_name`.
- **Fabricated data**: `OrderBookChart` generates depth with `Math.random()` while the backend holds real depth.
- **Dropped messages**: `prediction` WS messages ignored; `trade` messages never sent.
- **Empty on load**: histories start empty and take minutes to fill after every reload.
- **Build broken**: `npm run build` fails on unused imports; Vercel deploys by skipping `tsc`.
- Dead code (`Sidebar`, `ErrorBoundary`), inert settings controls, placeholder On-Chain page.
- Chart histories rebuilt via array spread every 500 ms.
- Generic cyan/purple palette with no relationship to what the product does.

---

## 2. Algorithmic & backend overhaul

This is the substance of the upgrade. Each item names what replaces what, and why it is a genuine step up rather than a refactor.

### 2.1 Streaming feature engine — O(1) amortised per event

**Replace** the rescanning `calculate_features()` with `market/features.py`: a `StreamingFeatureEngine` built on **time-windowed ring buffers with running accumulators** (`market/ring.py`).

- `TimeWindowSum`: a deque of `(ts, value)` plus a running sum; `push()` appends and evicts expired head entries; `value()` is O(1). Used for Σpq, Σq (VWAP), Σp, n (TWAP), buy-volume, trade count (velocity). **Float drift is bounded** by Kahan-compensated accumulation plus a full recompute every N evictions (invariant-tested against brute force).
- `EwmVariance`: Welford/EWMA online variance of log mid-price returns on the **1 Hz bar stream** (§2.9), **time-scaled** to a canonical horizon so volatility is comparable across activity regimes; an event-time EWMA supplements it for intra-second reactivity.
- Features are updated **on trade / book events**, not on a timer. A separate 4 Hz coalescing broadcaster reads the latest state. Compute is decoupled from transport (cadence tiers in §2.12).
- z-scores are emitted only after a warm-up minimum (else `null`), so the UI can show "calibrating" instead of garbage.
- All windows are configurable per symbol; the engine is instantiated **per symbol** (ships with `BTCUSDT` default plus an `ETHUSDT`/`SOLUSDT` allowlist).

*Why next-level:* moves from O(n·k) per tick to O(1) amortised per event; sub-millisecond feature latency; correct time-scaling; event-driven semantics.

### 2.2 Full L2 order-book reconstruction

**Replace** 10-level snapshots with `market/book.py`: a `LocalOrderBook` maintained from Binance's **diff-depth stream** (`<symbol>@depth@100ms`) synchronised against a REST snapshot (`/api/v3/depth?limit=1000`) using the documented `lastUpdateId / U / u` sequencing (`U ≤ lastUpdateId+1 ≤ u` for the first event, `U == prev_u + 1` thereafter), with automatic resync on gap.

- Storage: two `SortedDict`s (`sortedcontainers`) price → qty; top-N extraction is O(N).
- Derived per update: best bid/ask, mid, spread, **microprice** `(P_bid·Q_ask + P_ask·Q_bid)/(Q_bid+Q_ask)`, **depth-weighted imbalance** with exponential decay by distance from mid, **liquidity within N bps** (5/10/25), **book slope** (linear fit of cumulative depth vs. distance), and **OFI — order-flow imbalance** (Cont, Kukanov & Stoikov 2014) accumulated from best-level changes per event and summed per bar.
- Exchange event time (`E`) used for timestamps.
- **Endpoint fallbacks:** REST and WS hosts are a configurable ordered list (`api.binance.com` / `stream.binance.com`, then Binance's documented market-data-only hosts `data-api.binance.vision` / `data-stream.binance.vision`). HTTP 451 on either REST or WS triggers the next host, then the replay/synthetic source (§2.10).

*Why next-level:* microprice and OFI are the two most cited short-horizon predictive signals in the microstructure literature; the current system has neither. The full book also powers the 3D liquidity terrain — the frontend's signature visual — from real data.

### 2.3 Adaptive baselines and z-scores

**Replace** constants with `market/baseline.py`: every raw feature carries an **EWMA mean + EWMA std** (two half-lives: fast ≈ 1 min, slow ≈ 15 min). The engine emits `*_z` fields (`spread_z`, `velocity_z`, `vol_z`, `ofi_z`, `imbalance_z`).

Signals and rules operate on z-scores ("spread 2.5σ above its 15-min mean"), not absolute bps. `velocity_baseline` becomes the slow EWMA rather than the number 20.

### 2.4 Regime detection — learned, not hard-coded

**Replace** the threshold `if/elif` with `market/regime.py`: a **Gaussian HMM** (`hmmlearn`, 4 states) fitted on 1-second bars of `[log_return, |log_return|, spread_z, ofi_z]` over the trailing ~30 minutes, refit every 5 minutes in an executor. States are labelled by sorting on learned emission variance: `quiet` → `trending` (split by mean return sign) → `volatile` → `breakout`. The current state is decoded by forward filtering on the latest window, with a **minimum dwell time** to prevent flicker. The threshold rules remain as a **fallback** until ≥ N bars exist.

Regime is broadcast as its own WS message and feeds the ML features, the signal engine, the alert evaluator, and — on the frontend — the camera and shader field.

### 2.5 ML pipeline v2

**Replace** `ml_engine.py` with `ml/` (feature pipeline, labels, training, registry, explain, drift, engine). ML operates on the **1 Hz bar stream**, not on raw events.

| Concern | Today | Plan |
|---|---|---|
| Target price | last trade | **mid-price** (removes bid-ask bounce) |
| Horizon | 10 ticks | **time-based**, H seconds (default 5 s) |
| Labels | fixed ±3 bps | **Triple-barrier** (López de Prado): upper/lower barriers at ±k·σ_t (volatility-scaled), vertical barrier at H; label = first barrier touched (3 classes: up / down / timeout) |
| Features | 26 (price/spread/velocity/vol stats) | 26 + microprice deviation, OFI (multi-window), depth-weighted imbalance, liquidity@N bps, book slope, regime one-hot, z-scores |
| Model | RF + GB, 40/60 vote; StandardScaler | **`HistGradientBoostingClassifier`** (`class_weight="balanced"`, early stopping) wrapped in **`CalibratedClassifierCV`** (isotonic ≥ 1 000 samples, sigmoid below) so "confidence" is a calibrated probability; `LogisticRegression` pipeline baseline reported alongside. No scaler needed for HGB |
| Validation | random K-fold | **`TimeSeriesSplit(gap = H bars)`** — the gap is the embargo that purges label overlap; report OOS accuracy, log-loss, **Brier score**, per-fold — honestly |
| Importance | impurity-based | **Permutation importance** on OOS folds + cached SHAP `TreeExplainer` built once at train time |
| Training | unguarded executor; RAM buffer | `threading.Lock(blocking=False)`; train into a fresh `ModelBundle`; **atomic swap**; never block the event loop. **Training set is derived from `market_snapshots`** (features + future mid in the same table), so it is **reconstructed on startup** — a restart no longer resets the model to zero |
| Registry | none | `ml_models` rows written with version, metrics JSON, feature list, path; last N artefacts retained on disk |
| Predictions | not stored | **`predictions` table**: every 1 Hz prediction with probabilities and horizon; resolved against realised mid after H s. Feeds the drift monitor and `ml_signal` backtests |
| Drift | none | `ml/drift.py`: rolling OOS hit-rate & Brier vs. training-time values; **edge-decay alarm** when it drops below threshold → surfaced in UI and as an alert |
| Cold start | silent | explicit `warming_up` state with `samples_collected / samples_required` in every prediction payload |

*Honesty clause:* short-horizon crypto direction is close to unpredictable. The goal is a **calibrated** model with honest walk-forward metrics and a visible drift monitor — not inflated accuracy. The UI will show Brier/log-loss and "edge vs. baseline", not a single accuracy number.

### 2.6 Signal engine (replaces the rule engine)

**Move** the 10 rules out of `api/analytics.py` into `signals/` and **replace** stateless lambdas with declarative, stateful `SignalRule` objects:

```python
SignalRule(
    id="spread_wide", priority="HIGH",
    enter=Cond("spread_z", ">", 2.0), exit=Cond("spread_z", "<", 1.0),   # hysteresis
    min_duration_s=2, cooldown_s=30,
    message="Spread {spread_bps:.1f} bps ({spread_z:+.1f}σ) — liquidity thinning",
    action="Prefer limit orders", impact="…",
)
```

Rules are Pydantic models (JSON-serialisable, later user-editable), evaluated on every feature update, emitting `activated` / `deactivated` transitions rather than a full list every tick. The last 200 transitions are kept in memory and exposed via REST so the feed is populated on reload. Ships with the existing 10 rules re-expressed on z-scores plus OFI/microprice/regime rules.

**One condition evaluator** (`core/conditions.py`) is shared by signals, alerts, and backtest strategies, and validates field names against the **feature catalog** (§2.11).

### 2.7 Alert evaluator — actually wired

**New** `alerts/evaluator.py`: on each **bar close** (1 Hz — bounds DB writes), evaluate enabled `AlertRule` rows (cached in memory, invalidated by the CRUD router), honour `cooldown_seconds`, write `AlertHistory`, broadcast `alert` over WS (never dropped), and dispatch to Discord webhook (`alerts/notify.py`) when configured. Alerts can target raw features, z-scores, regime, or model probability.

### 2.8 Backtester — real, event-driven

**Replace** the stub with `backtest/`:

- **Data**: replays `market_snapshots` (1 Hz bars). If history < N minutes, falls back to the **synthetic generator** (§2.10), clearly labelled as such in the result.
- **Strategy spec** (declarative JSON on the `Strategy.config` column):
  ```json
  { "side": "both", "size_pct": 10,
    "entry": { "all": [ {"f":"ofi_z","op":">","v":1.5}, {"f":"regime","op":"in","v":["trending"]} ] },
    "exit":  { "any": [ {"f":"ofi_z","op":"<","v":0}, {"f":"bars_held","op":">=","v":30} ] },
    "stop_loss_bps": 20, "take_profit_bps": 40 }
  ```
  plus an `ml_signal` strategy type that trades on stored `predictions`.
- **Engine**: bar-by-bar; fills at next bar's mid ± slippage bps; commission bps; position/PnL accounting; produces **equity curve, drawdown series, trade list, Sharpe & Sortino (computed on 1-minute-resampled equity, annualised), max DD, profit factor, win rate, exposure**. Persisted to `backtest_results` (`equity_curve_json`, `trades_json`).
- Runs in an executor; long runs report progress over WS.

### 2.9 Bars, persistence, scheduling, migrations

- **`market/bars.py`** — a 1 Hz bar builder per symbol: OHLC of mid, last trade, volume, buy volume, trade count, OFI sum, spread/microprice/imbalance at close, all z-scores, regime. Bars are the shared substrate for volatility, HMM, ML features and labels, alerts, snapshot persistence, replay, and backtesting.
- `MarketSnapshot` = one row per bar, written via a batched writer (flush every 5 s). Retention prune (default 7 days; ~600 k rows/symbol in SQLite is fine). SQLite runs in **WAL mode** with `synchronous=NORMAL`.
- Background tasks (plain asyncio — no APScheduler): snapshot flush, prediction resolution, retrain check, HMM refit, retention prune, model-registry GC.
- **Alembic** migrations; SQLite stays the default (Postgres is a `DATABASE_URL` change).

### 2.10 Data sources — live, replay, synthetic

`DATA_SOURCE = live | replay | synthetic` (per symbol):

- **live** — Binance with host fallbacks (§2.2).
- **replay** — `market/replay.py` streams a recorded NDJSON file of raw trade + diff-depth events at real or accelerated speed through the *same* pipeline. `scripts/record_stream.py` records live streams; a short recorded fixture ships in `tests/fixtures/` for tests and for a guaranteed-working local demo.
- **synthetic** — `market/synthetic.py`: GBM mid-price with Hawkes-style trade clustering, a spread/queue model that emits plausible diff-depth events. Used when live is blocked (451) and no recording exists, and to pre-warm ML in demos. Every payload carries `source` so the UI badges it.

*Why this matters:* the platform must run, demo, and test deterministically anywhere — including geo-blocked regions and CI.

### 2.11 Transport & API contracts

- **Typed WS messages** in `schemas/ws.py` (discriminated union on `type`); exposed via a documented `GET /api/v1/ws/schema` so they appear in OpenAPI → the frontend generates TS types from one source.
- Message types: `hello` (server capabilities, symbols, source), **`snapshot`** (on connect/subscribe: last 600 bars + current book + regime + signals + prediction — **no more empty charts on reload**), `features` (4 Hz, coalesced), `book` (5 Hz top-50 + OFI/microprice, **subscribers only**), `trades` (batched 10 Hz), `bar` (1 Hz), `prediction` (1 Hz), `regime` (on change), `signals` (transitions), `alert` (on fire), `backtest_progress`. Client → server: `{ "op": "subscribe", "channels": [...], "symbol": "..." }`.
- **Per-client queues** with a drop-oldest policy for `features`/`book` (latest wins) and never-drop for `alert`/`snapshot`; `orjson` serialisation.
- **Feature catalog** — `market/catalog.py` `FEATURE_REGISTRY` (name → unit, description, kind, allowed ops) exposed at `GET /api/v1/market/feature-catalog`; used by API validation, the alert form, and the strategy builder.
- Middleware registered; rate limit exempts `/ws`. Structured logging (`core/logging.py`).
- REST additions: `/market/book`, `/market/bars?from&to`, `/market/feature-catalog`, `/analytics/regime`, `/analytics/model-registry`, `/analytics/drift`, `/analytics/signals/history`, `/system/metrics` (event rates, queue depths, latencies — shown in Settings); backtest request schema fixed.
- `scripts/export_openapi.py` writes `openapi.json` without a running server; the generated `schema.d.ts` is **committed** so Vercel builds without the backend.

### 2.12 Cadence tiers (compute budget)

| Tier | Runs | Work |
|---|---|---|
| per event (100s/s in bursts) | on each trade / depth diff | O(1) feature updates, book apply, OFI accumulation |
| 4–5 Hz | coalescing broadcaster | `features`, `book`, batched `trades` |
| 1 Hz | bar close | bar build, z-scores, ML feature vector + predict, regime decode, signal & alert evaluation, snapshot enqueue, prediction resolution |
| 5 min | scheduled | HMM refit (executor) |
| N samples / T min | scheduled | model retrain (executor, locked, atomic swap) |
| daily | scheduled | retention prune, registry GC |

### 2.13 Backend hygiene & security

- Restructure into a package `backend/algoviz/…` (`uvicorn algoviz.main:app`); Python ≥ 3.11.
- `pyproject.toml` (pinned deps, `ruff`, `mypy`, `pytest` config) + exported `requirements.txt` for Render.
- **`passlib` → `bcrypt`** directly; **`python-jose` → `PyJWT`**. `SECRET_KEY` validator **fails fast** if the dev default is used with `ENVIRONMENT=production`. Timezone-aware datetimes throughout (`datetime.utcnow()` is deprecated).
- Fresh venv; Streamlit-era packages gone; `websockets` unpinned to current. No `uvloop` dependency (Windows dev).
- Multi-stage Dockerfile; no `--reload` in the production CMD. Memory budget ≤ 400 MB RSS (Render free tier); SHAP explainer cached once, explanations computed on request.
- No Redis: single-process pub/sub is sufficient; the hub is an interface so Redis can be added if horizontally scaled.
- Version bumps to **3.0.0**.
- Tests: ring-buffer/feature property tests, book-sync tests (replayed diff sequences incl. gap → resync), triple-barrier vs. brute force, `TimeSeriesSplit(gap)` leakage test (shuffled labels → chance level), backtester accounting, signal hysteresis, alert cooldown, replay determinism, API contract tests. Orphaned `tests/test_features.py` deleted after its intent is ported.

---

## 3. Frontend architecture

### 3.1 Stack

| Layer | Choice | Reason |
|---|---|---|
| Framework | **Next.js** (latest stable, 16.x — verified at scaffold), App Router, React 19, TypeScript strict | Mandated; file routing, `error.tsx`/`loading.tsx`, metadata, Vercel-native; `output: 'standalone'` for Docker |
| 3D | **Three.js** via `@react-three/fiber` v9 + `@react-three/drei` + `@react-three/postprocessing`, custom GLSL | Declarative scene graph inside React, with raw shader access where it matters |
| Motion | **GSAP 3.13+** (fully free incl. all plugins since the Webflow acquisition) + `@gsap/react` (`useGSAP`), ScrollTrigger, Flip, SplitText | Mandated; timelines, counters, camera tweens, layout transitions. Framer Motion removed |
| Styling | **Tailwind CSS 4** — CSS-first (`@import "tailwindcss"` + `@theme` tokens in `globals.css`, `@tailwindcss/postcss`; no `tailwind.config.ts`) + a small `glass.css` component layer | Token discipline without inline styles; glass effects need real CSS |
| State | **Zustand 5** with `useShallow` + `persist` (settings); histories in **typed-array ring buffers** with a `head` counter for React subscribers | O(1) append, zero-allocation, GPU-uploadable; the counter is what notifies 2D charts |
| Server state | **TanStack Query 5** | CRUD pages |
| API client | **`openapi-typescript`** (types) + **`openapi-fetch`** (typed client) from the committed `openapi.json` | Kills contract drift; `npm run types` is a build step; no axios |
| 2D charts | **lightweight-charts 5** (price/VWAP/microprice), custom Canvas for strips | Keep what works; GSAP handles transitions |
| Fonts | Geist Sans / Geist Mono via `next/font` | Self-hosted, no Google Fonts import |
| Perf tier | `detect-gpu` → `low / mid / high` (overridable in Settings) | Terrain resolution and particle cap scale with the GPU |
| Icons | lucide-react | Keep |
| Tests | Vitest + Testing Library; Playwright E2E | Build must pass `tsc` + lint + tests |

### 3.2 Data layer

- `lib/ws/client.ts`: **module-level** WebSocket client (outside React) — reconnect with jittered backoff, heartbeat, subscription management, `snapshot` hydration on connect, symbol switching (rings reset), message dispatch to the store. React only subscribes. A global **connection banner** shows reconnect countdown and the data `source` (live / replay / synthetic).
- `lib/store/`: Zustand slices — `market` (latest features, z-scores), `book` (top-50 bids/asks as `Float32Array`s + a `Float32Array` depth-history ring for the terrain), `trades` (ring), `history` (price/vwap/microprice/spread/vol/ofi rings, `Float64Array` × 600, hydrated from `snapshot`), `intel` (prediction, regime, signals, drift, warm-up), `ui`.
- **Display interpolation**: data arrives at 1–5 Hz; displayed numerics tween between samples with GSAP (`gsap.quickTo`) so the UI feels continuous at 60 fps without React re-renders per frame. Three.js reads store rings directly in `useFrame`.

### 3.3 Visual identity — "Depth"

The product is about **liquidity and order flow**. The identity is built from the order book's own semantics, not from a generic palette.

| Token | Value | Meaning |
|---|---|---|
| `--bg-abyss` | `#05070c` | The floor. Depth is literal depth |
| `--bg-deep` | `#0a0f1a` | Panel base |
| `--bid` | `#19d3c5` (teal) | Liquidity below — support. Keeps the green-side convention traders expect while being distinctive |
| `--ask` | `#ff4d6d` (coral) | Pressure above — resistance. Red-side convention preserved |
| `--mid` | `#ffd166` (gold) | Microprice/mid — the thin line where they meet |
| `--regime-quiet / -trending / -volatile / -breakout` | `#3b6cff` / bid-or-ask tint / `#ffb020` / `#b06cff` | Drives the shader field and accent glows |
| `--glass-*` | blur 16 px, saturate 140 %, border `rgba(255,255,255,.06)`, top-edge highlight, 2 % noise | Glass tiers 1–3 |
| Type | Geist Sans (UI), Geist Mono (numerics, `tabular-nums`) | |

Teal/coral was chosen over pure green/red deliberately: the pair stays distinguishable under deuteranopia and protanopia while preserving the trader's convention.

**Motion language:** everything moves at the speed of the market. Pulse periods, particle emission, shader turbulence, and glow intensity are functions of `velocity_z`, `vol_z`, and regime — the same idea the old MarketPulse gestured at, applied system-wide.

### 3.4 Glassmorphism & interaction system

- `components/glass/`: `GlassPanel` (tiers), `GlassButton`, `GlassTab`, `GlassInput`, `GlassRow`, `GlassBadge`. Each has a **hover contract**: lift (`-2px`), border brightens, semantic glow (`box-shadow` in the panel's accent), and a **cursor-tracking radial highlight** (`--mx/--my` set on `pointermove`, one listener at the root). Focus-visible rings for keyboard.
- Every interactive element (nav, cards, rows, chips, chart legends, gauge segments, 3D terrain hover) has a hover state. No exceptions.
- `prefers-reduced-motion`: particles/turbulence off, tweens → instant, data unchanged.

### 3.5 Three.js / WebGL — only where depth carries information

1. **Order Book Liquidity Terrain** (dashboard hero, `/book` full-screen)
   A surface with X = price bins **relative to mid** (±N bps, 128 bins at high tier / 64 low), Z = time (64 slices scrolling), Y = cumulative depth. Implemented as a `PlaneGeometry` displaced in a **vertex shader** from an `R32F DataTexture` holding the depth ring; time scrolling is a `uHead` uniform (no CPU memmove). Bid side teal, ask side coral, mid line gold; fragment shader shades by depth and adds a fresnel rim. Camera: gentle orbit, GSAP-tweened to a preset per regime; hover raycasts to a price/qty tooltip. The render loop **pauses on `visibilitychange` and when the canvas is off-screen**; DPR clamped `[1, 1.5]`.
2. **Trade-Flow Particles**
   `Points` with a custom shader; each trade spawns a particle whose trajectory is a deterministic function of its spawn params (`birth`, `side`, `size`, `x`), so the CPU writes **only on spawn** and the GPU evaluates `position(t)`. Buys rise from the bid slope, sells fall from the ask slope; size ∝ quantity; density = velocity made visible. Cap 4 096 (high) / 1 024 (low).
3. **Regime Field** (page background, behind the glass)
   Fullscreen quad, simplex-noise flow field; uniforms `uTurbulence` (vol_z), `uHue` (regime), `uFlow` (OFI sign → drift direction). Sub-1 ms; the glass panels literally look into the market's state.
4. Everything else — gauges, SHAP bars, strips, tables — stays **2D** (SVG/Canvas + GSAP). 3D for decoration is explicitly avoided.

Each 3D view has a 2D/textual equivalent (depth curve, tape) for accessibility and for WebGL-less fallback.

### 3.6 Routes

| Route | Content |
|---|---|
| `/` | Bento dashboard: Terrain hero, KPI strip (price, spread, microprice Δ, OFI, velocity, vol — all z-annotated), price/VWAP/microprice chart, regime + prediction panel (with warm-up progress), signals feed, trade tape, spread/vol strips, data-source badge |
| `/book` | Full-screen Terrain, cumulative depth curve, OFI timeline, liquidity@N bps |
| `/intelligence` | Calibrated prediction + probabilities, SHAP (cached), permutation importance, walk-forward metrics per fold (Brier/log-loss), model registry timeline, **drift monitor** |
| `/strategies` | Declarative strategy builder (condition editor populated from the feature catalog), backtest runner with equity/drawdown curves, trade list, metrics, synthetic-data badge; Flip transitions on expand |
| `/alerts` | Rule CRUD (typed form from the feature catalog), live history feed (WS), acknowledge |
| `/settings` | Symbol, data source, perf tier (auto/override), motion, connection + `/system/metrics`, accent intensity (dark-only theme) |
| ⌘K palette, toasts, connection banner, `error.tsx`, `loading.tsx` | App-wide |

**Removed:** `/onchain` (placeholder with no backend; out of scope — §6 decision 1).

### 3.7 Performance & quality gates

- 60 fps on an integrated GPU at 1080p with Terrain 128×64 + 4k particles at high tier; WS → paint < 100 ms.
- `three` and R3F loaded only on routes that use them (`dynamic(..., { ssr: false })`).
- `next build` must pass `tsc`, ESLint, Vitest; Playwright smoke on the main routes.
- Lighthouse Performance ≥ 90 on non-3D routes, Accessibility ≥ 95.

---

## 4. Keep / modify / replace

### 4.1 Backend (`AlgoViz-Professional/backend/`)

| File | Decision | Notes |
|---|---|---|
| `main.py` | **Modify** | Move to `algoviz/main.py`; register middleware; wire new services; WS subscribe protocol |
| `config.py` | **Modify** | Per-symbol settings; data source; host fallbacks; z-score/HMM/label params; `SECRET_KEY` validator; remove absolute-bps rule thresholds |
| `database.py` | **Keep** (relocate) | WAL mode; Alembic |
| `models/models.py` | **Modify** | `MarketSnapshot` → bar row (+microprice/ofi/imbalance_w/regime/z-scores); `MLModel` +metrics JSON, feature list; **new `Prediction`**; `BacktestResult` already fits |
| `schemas/schemas.py` | **Replace** | Split into `schemas/{rest,ws}.py`; single source of truth for generated TS |
| `services/market_data.py` | **Replace** | → `market/{ingest,book,bars,ring,features,baseline,regime,catalog,replay,synthetic,service}.py`. The Binance connection loop and 451 handling are carried over into `ingest.py` |
| `services/ml_engine.py` | **Replace** | → `ml/{features,labels,train,registry,explain,drift,engine}.py`. The 26 feature ideas are carried over and extended |
| `api/analytics.py` | **Modify** | Rule engine extracted to `signals/`; new endpoints; new contracts |
| `api/market.py` | **Modify** | +`/book`, `/bars`, `/feature-catalog` |
| `api/strategies.py` | **Modify** | Real backtest; request schema fixed; default-user hack replaced |
| `api/alerts.py` | **Modify** | Pydantic bodies instead of `dict`; cache invalidation hook |
| `api/auth.py`, `core/auth.py` | **Modify** | `bcrypt` + `PyJWT`; relocate |
| `core/middleware.py` | **Keep** | Finally registered |
| `ws/hub.py` | **Modify** | Typed messages, per-client queues + drop policy, subscriptions, snapshot-on-connect, `orjson` |
| `tests/test_api.py` | **Modify** | Fix assertions; extend |
| `requirements.txt`, `runtime.txt` | **Replace** | `pyproject.toml` + exported pins |
| `Dockerfile` | **Modify** | Multi-stage; prod CMD |

### 4.2 Frontend (`AlgoViz-Professional/frontend/`) — **replaced entirely**

**Justification:** Next.js is mandated and is a different build/runtime model from Vite (App Router, RSC boundaries, file routing) — there is no meaningful in-place migration. Framer Motion → GSAP is a full animation-layer swap. Most page data-binding code is wrong today (contract drift) and would be rewritten against generated types regardless. Rebuilding is cheaper and safer than patching.

What carries over as **design intent**, re-implemented: MarketPulse (→ system-wide motion language), VelocityGauge, SpreadHeatmap and VolatilityChart (→ 2D strips), PriceChart (lightweight-charts wrapper, kept), CommandPalette, ToastProvider, TickerTape, the glass token ideas from `index.css`.
Dropped: `Sidebar.tsx`, `ErrorBoundary.tsx` (dead), `OnChain.tsx` (placeholder), `store.ts` hand-written types (generated instead), Framer Motion, axios.

### 4.3 Repo / infra

| File | Decision |
|---|---|
| `docker-compose.yml` | **Modify** (new start command, Next.js standalone service) |
| `render.yaml` | **Modify** (`uvicorn algoviz.main:app`) |
| `frontend/vercel.json`, `_redirects` | **Replace** / **Delete** (Next.js preset) |
| `README.md` | **Replace** |
| `.env.example` | **Modify** (+ `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `DATA_SOURCE`) |
| `tests/test_features.py` (root) | **Delete** after porting intent |
| `implementation_plan.md.resolved` (root) | **Delete** (stale; superseded by this file) |
| root `.venv` | **Recreate** |
| CI | **New** `.github/workflows/ci.yml` — ruff/mypy/pytest + `pip-audit`; tsc/eslint/vitest/`next build` + `npm audit` |

---

## 5. Project structure going forward

```
AlgoViz-Professional/
├── backend/
│   ├── algoviz/
│   │   ├── main.py                 # app factory, lifespan, middleware, WS endpoint
│   │   ├── config.py               # Settings (per-symbol, data source, hosts, z-score/HMM/label params)
│   │   ├── db/                     # engine (WAL), session, Base
│   │   ├── core/                   # middleware, auth (bcrypt+PyJWT), logging, conditions (shared evaluator)
│   │   ├── market/
│   │   │   ├── ingest.py           # Binance trade + diff-depth streams, host fallbacks, resync, 451 handling
│   │   │   ├── book.py             # LocalOrderBook (L2), microprice, OFI, liquidity@bps, slope
│   │   │   ├── ring.py             # TimeWindowSum (Kahan), EwmVariance, ring buffers
│   │   │   ├── features.py         # StreamingFeatureEngine (event-driven, O(1))
│   │   │   ├── baseline.py         # EWMA mean/std → z-scores (with warm-up)
│   │   │   ├── bars.py             # 1 Hz bar builder — the shared substrate
│   │   │   ├── regime.py           # GaussianHMM regime detector + fallback + min-dwell
│   │   │   ├── catalog.py          # FEATURE_REGISTRY (single source of truth for field names)
│   │   │   ├── replay.py           # NDJSON recording playback
│   │   │   ├── synthetic.py        # GBM + Hawkes + spread/queue simulator
│   │   │   └── service.py          # per-symbol orchestration, cadence tiers, coalescing broadcaster, snapshot writer
│   │   ├── ml/
│   │   │   ├── features.py         # ML feature vector (extended)
│   │   │   ├── labels.py           # triple-barrier, time-based
│   │   │   ├── train.py            # TimeSeriesSplit(gap), calibrated HGB, permutation importance
│   │   │   ├── registry.py         # ml_models rows + artefact retention
│   │   │   ├── explain.py          # cached SHAP explainer
│   │   │   ├── drift.py            # prediction resolution, rolling OOS metrics, edge-decay alarm
│   │   │   └── engine.py           # ingest/predict/guarded-train/atomic-swap; rebuild from snapshots on startup
│   │   ├── signals/                # SignalRule (hysteresis, cooldown), engine, default rules, transition history
│   │   ├── alerts/                 # evaluator (1 Hz), notify (Discord)
│   │   ├── backtest/               # engine, strategy spec, metrics
│   │   ├── api/                    # market, analytics, strategies, alerts, auth, system routers
│   │   ├── ws/                     # hub (queues, subscriptions, snapshot-on-connect), messages
│   │   ├── schemas/                # rest.py, ws.py (OpenAPI source of truth)
│   │   └── models/                 # ORM (+ Prediction)
│   ├── alembic/
│   ├── scripts/                    # record_stream.py, export_openapi.py
│   ├── tests/  (+ fixtures/ recorded stream)
│   ├── pyproject.toml
│   ├── requirements.txt            # exported pins (Render)
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # shell, fonts, RegimeField, nav, palette, toasts, connection banner
│   │   ├── page.tsx                # dashboard
│   │   ├── book/  intelligence/  strategies/  alerts/  settings/
│   │   ├── error.tsx  loading.tsx
│   ├── components/
│   │   ├── glass/                  # GlassPanel, GlassButton, …
│   │   ├── three/                  # Terrain, TradeParticles, RegimeField, shaders/
│   │   ├── charts/                 # PriceChart, DepthCurve, OfiTimeline, strips
│   │   ├── panels/                 # KpiStrip, PredictionPanel, SignalsFeed, TradeTape, DriftMonitor, …
│   │   └── ui/                     # CommandPalette, Toasts, Nav, ConnectionBanner
│   ├── lib/
│   │   ├── ws/client.ts            # module-level WS client (+ snapshot hydration, symbol switch)
│   │   ├── store/                  # Zustand slices, typed-array rings (+ head counters)
│   │   ├── api/                    # committed openapi.json → schema.d.ts, openapi-fetch client
│   │   ├── gsap/                   # registered plugins, shared eases, useCounter
│   │   ├── perf/                   # detect-gpu tiering
│   │   └── theme/                  # tokens, regime → colour maps
│   ├── styles/                     # globals.css (@import tailwindcss + @theme tokens), glass.css
│   ├── tests/  e2e/
│   ├── next.config.ts  postcss.config.mjs  package.json
├── .github/workflows/ci.yml
├── docker-compose.yml  render.yaml  .env.example  README.md
```

---

## 6. Decisions (confirmed)

1. **Drop `/onchain`** — placeholder with no backend; tracked as a future phase. ✅
2. **Multi-symbol** — engine per-symbol; `BTCUSDT` default + `ETHUSDT`/`SOLUSDT` allowlist. ✅
3. **Tailwind CSS 4** (CSS-first) + glass layer. ✅
4. **Backend package restructure** to `backend/algoviz/`. ✅
5. **SQLite stays** (WAL); Alembic makes Postgres a config change. ✅
6. **`hmmlearn`** for regime detection with threshold fallback. ✅
7. **`frontend/` directory name** unchanged. ✅
8. *(added in audit)* **`bcrypt` + `PyJWT`** replace `passlib` + `python-jose`. ✅
9. *(added in audit)* **`DATA_SOURCE` live/replay/synthetic** is in scope. ✅

---

## 7. Delivery stages (Phase 3 onward)

Each stage ends with a review stop; nothing proceeds without sign-off.

| Stage | Scope | Reviewable outcome |
|---|---|---|
| **A — Backend foundation** | Package restructure, `pyproject`, pinned deps, fresh venv, `bcrypt`/`PyJWT`, `SECRET_KEY` validator, tz-aware datetimes, middleware registered, WAL + Alembic, fixed tests, structured logging, CI skeleton. Existing engine kept running in the new layout | `pytest` green; `/health` and `/docs` up; `ruff`/`mypy` clean |
| **B — Market engine** | Ring buffers, O(1) features, L2 book + resync + host fallbacks, microprice/OFI/liquidity/slope, EWMA baselines & z-scores (warm-up), **bars**, HMM regime, **feature catalog**, **replay + synthetic sources + recorder**, snapshot persistence, coalescing broadcaster, typed WS messages + subscriptions + **snapshot-on-connect** | Live or replayed features/book/regime streaming; property + replay tests green; latency numbers in the PR |
| **C — Intelligence** | ML v2 (triple-barrier, `TimeSeriesSplit(gap)`, calibrated HGB, registry, guarded training, rebuild-from-snapshots, **predictions table**, cached SHAP, **drift**), signal engine + shared condition evaluator, alert evaluator + Discord, backtester, final REST/WS contracts, OpenAPI export script | Honest walk-forward metrics; model survives restart; alerts fire; backtests produce equity curves; contract tests green |
| **D — Frontend foundation** | Next.js scaffold, Tailwind tokens, glass system, GSAP setup, WS client + typed-array store + snapshot hydration, generated types (committed), perf tiering, layout/nav/palette/toasts/connection banner, dashboard 2D panels | `next build` passes all gates; live dashboard with 2D panels populated on first paint |
| **E — Frontend visuals & pages** | Terrain, particles, regime field, `/book`, `/intelligence`, `/strategies`, `/alerts`, `/settings` | Every route functional against live/replay backend; 60 fps check; reduced-motion verified |
| **F — Integration & hardening** | Playwright E2E, perf pass, Docker/Render/Vercel configs, README, CI complete (+ `pip-audit`/`npm audit`), stale files removed | One-command local run (replay mode works with no internet); deploy configs verified; final review |

---

## 8. Verification

- **Unit / property:** ring-buffer invariants (window sums equal brute force after 10⁶ pushes), book sync against recorded diff sequences (incl. gap → resync), triple-barrier vs. brute force, `TimeSeriesSplit(gap)` leakage test (shuffled labels → chance level), backtester accounting (PnL = Σ trades − costs), hysteresis & cooldown behaviour, replay determinism (same fixture → identical bars).
- **Integration:** API contract tests against generated schema; WS subscribe/drop-policy/snapshot tests; alert fires end-to-end; model rebuilds from snapshots after restart.
- **Frontend:** Vitest for store rings and WS dispatch; Playwright smoke for all routes; `tsc`/ESLint gates.
- **Manual:** live dashboard on a real Binance feed; Terrain reflects book changes within 100 ms; regime transitions recolour the field; drift monitor updates after training; a strategy backtest produces a plausible equity curve; Discord webhook receives an alert; replay mode runs the full UI offline.

---

## 9. Revision log

**Rev 2 (audit):** fixed Tailwind 4 config model, R3F frameloop wording, `TimeSeriesSplit(gap)` precision, Next.js version; added §2.9 bars, §2.10 data sources (live/replay/synthetic + recorder), §2.12 cadence tiers, feature catalog, shared condition evaluator, `predictions` table + drift resolution, training-set reconstruction from snapshots, snapshot-on-connect WS message, host fallbacks for 451, Kahan/recompute for running sums, z-score warm-up, HMM min-dwell, `bcrypt`/`PyJWT` swap, `SECRET_KEY` fail-fast, tz-aware datetimes, WAL mode, `openapi-fetch`, `detect-gpu` tiering, `next/font`, committed generated types, connection banner, symbol switching, colour-vision rationale, memory budget, no-Redis rationale, security audits in CI.

**Rev 3 (delivery, 2026-09-19):** Stages A–F delivered. Deviations from the plan, all deliberate:
- 3D stack is `three` + `@react-three/fiber` only — no `@react-three/drei` or `@react-three/postprocessing` (OrbitControls is imported from `three/examples`; bloom was not needed once the shader had its own rim/contour lighting). Kept the dependency surface and the 230 KB gz chunk from growing, and the chunk is fetched only after the page settles and never on the low tier.
- GSAP: core + `@gsap/react` are used (entrance, counters, camera rigs, palette/toasts); ScrollTrigger/Flip/SplitText were not needed by the final layouts.
- Added to the backend beyond the plan: a binned cumulative **depth profile** on the book payload (the terrain needs the whole band, not the top-N levels) and a far-liquidity layer with random walls in the synthetic exchange so offline runs have book structure.
- Preferences persistence writes only on change and rehydrates on the `storage` event (two tabs used to clobber each other).
- Docker images were verified by the CI `images` job rather than locally (no daemon on the dev machine); Lighthouse was not run — bundle budgets were checked from `next build` output instead (main ≈ 70 KB gz, charts ≈ 51 KB gz, three ≈ 234 KB gz lazy).

- **Rev 3.1 (final review, 2026-09-19):** the live feed was exercised end to end against the finished frontend. Findings fixed: synthetic bars and synthetic-trained models had been feeding the live model (persisted bars are now loaded per data source, and synthetic/replay runs get their own database and model store by default); the ambient background was invisible because `<body>`'s own background painted over the fixed layers; the depth-profile band is now adaptive per instrument (BTC's book saturates within a few bps, an altcoin's needs the full 25). Visual pass: CSS aurora + dot grid on every tier, WebGL flow field + drifting motes on mid/high, regime-coloured glow and light pool on the terrain, tick flashes on KPIs, entrance motion on live rows.

---

## 10. Phase 4 — Professional hardening & visual redesign (proposed)

> **Status:** approved 2026-09-24 with every recommendation in §10.5. Stages G, J, K, L, H and M delivered, plus a theme v3 overhaul (§10.6); Phase 4 complete; Stage M approved 2026-10-01. Stages G–M keep §7's review-stop discipline.
> **Inputs:** the Phase 1 takeover audit (2026-09-23: gates, live and synthetic runs, py-spy profile) and a real-GPU screenshot review of every route at 1440×900 and 390×844.

### 10.1 Why

**Technical (verified at runtime unless noted):**

| # | Finding | Evidence |
|---|---|---|
| 1 | The 1 Hz HGB `predict_proba` runs on the event loop (`ml/engine.py:317`); under CPU load sklearn's OpenMP regions stall the loop for seconds | py-spy: 86 % of loop samples; `/health` 7.8–19 s; 3 Binance keepalive disconnects in 20 min; one REST call took 27.8 s; a "database is locked" failure lost 7 predictions |
| 2 | `get_db` commits after the response has been sent | 204 at +30 ms, commit at +547 ms; this is the e2e strategy-delete failure |
| 3 | Every retrain (and every HMM refit) runs twice | v12→v13 21 s apart; the same for v10→v11 and v14→v15 |
| 4 | The backtester applies stops/targets to the entry bar's pre-fill range | filled at 100.00, stopped at 99.80 on the same bar |
| 5 | Stale history is spliced into live state (bar ring, ML history) | a 98.8 h gap inside the "last 10 minutes" chart |
| 6 | The replay loop repeats trade ids, which the frontend then drops | 76 of 123 trade frames dropped after the first loop |
| 7 | `regime_quiet` never exits during `trending`; alert templates use unvalidated `str.format` | contradictory UI; an AttributeError and a 50 MB message reproduced |
| 8 | ML honesty gaps: permutation importance is in-sample and scored on accuracy but labelled "log-loss"; fold metrics describe the uncalibrated model, not the served calibrated one; early stopping validates on a random split; SHAP explains a different model | `ml/train.py:168-208`, `components/intelligence/panels.tsx:93` |
| 9 | Book metrics are recomputed on every diff (O(levels), ~7 % of loop time); the SHAP explainer is built on the loop (629 ms); bcrypt runs inline (190 ms) | py-spy, timings |
| 10 | Unauthenticated mutations; backtests with no concurrency cap; `predictions` and `alert_history` never pruned; four endpoints untyped (hand-written TS) | code read |

**Visual (from the real-GPU screenshots):**
- **Background noise.** The high-tier flow field draws worm-like trails and red/green blotches across every page. On sparse pages (Strategies, Alerts) it covers ~70 % of the screen and reads as dirt rather than depth.
- **Illegible hero.** The terrain is a tilted, cropped slab that leaves ~40 % of its panel empty. It uses saturated teal and red over whole areas, has no price, time or depth axes, and its particles render as blurry blobs. It also sits as a black rectangle inside a glass panel.
- **Decorative colour.** Numbers are coloured by channel rather than meaning (spread in pink, "−0.000 bps" in coral, tick flashes recolouring KPIs).
- **Weak hierarchy.** Every panel carries uppercase letter-spaced micro-labels plus a long subtitle ("cumulative depth · adaptive ±band × 19 s · buys lift off, sells rain in"). Primary and secondary information barely differ.
- **Layout holes.** Unequal panel heights leave gaps (Signals, depth curve, Liquidity), and /book has duplicate chip rows. Strategies and Alerts are two small cards on an empty page. On mobile the terrain panel overflows the viewport and the nav scrolls off-screen.
- **Chart scaling.** The depth curve shrinks one side to a sliver. One 16.2 log-loss outlier flattens the walk-forward chart. Strip labels overlap the lines, z-score bands render as flat blocks, and the registry list is clipped.
- **Undesigned states.** Warm-up shows as "calibrating" chips on 4 of 6 KPIs and "—" everywhere else.
- **No elevation.** Every surface sits on the same tier, so the glass reads as plain dark cards.

### 10.2 Technical workstream

**T1 — Real-time isolation: the feed never waits on anything.**
- Inference moves to a dedicated single worker thread under `threadpoolctl.threadpool_limits(1)`. Bar close submits and returns; a late result is published late or dropped, never queued behind the next bar.
- Training and HMM fitting move to a spawned worker process: single-flight, capped BLAS/OpenMP threads, with a timeout. Artefacts are written there and the engine only swaps them in. The "training due" state is updated at submit time, so runs can't double. The SHAP explainer is built in the worker at train time.
- Book: each diff does only O(1) work (apply levels, accumulate OFI). Metrics and the depth profile are computed at most at 10 Hz and at bar close, via a dirty flag. The local book is pruned beyond the snapshot band, which bounds both memory and scans.
- bcrypt and other CPU-bound calls run via `asyncio.to_thread`.
- A 10 Hz event-loop-lag sampler is exported as a metric. Health splits into `/health/live` and `/health/ready` (ready = migrated, book synced, loop lag within bounds). Feed staleness (no event for N s) is pushed to the UI.

**T2 — Data correctness.**
- Commit before the response is sent, using a function-scoped session dependency, with a read-after-write regression test.
- Session-aware history:
  - Gaps longer than N s split the history into segments.
  - The live bar ring is preloaded only when that history is fresh; otherwise charts start from a "resumed after gap" marker.
  - ML features and labels never straddle a gap, and the embargo is measured in time, not index.
- Writers: the prediction store re-queues on failure, as the bar writer already does. Multi-row inserts are chunked. `predictions` and `alert_history` get retention, plus a periodic `PRAGMA optimize`.
- Replay: trade ids stay monotonic across loops at the source, and the frontend dedupe resets on snapshot.
- Backtester:
  - Stops and targets apply only from the bar after the fill.
  - History loads in chunks.
  - Lookback is capped and a semaphore limits concurrent runs.
  - README fill wording corrected.
- Signal and alert semantics: `regime_quiet` exits when the regime leaves quiet. Alert templates use a safe formatter: only `{value} {threshold} {field} {symbol}`, with bounded format specs, validated on create and update.

**T3 — ML rigor: evaluate what we serve.**
- Each walk-forward fold trains *and calibrates* inside its training window (inner time split), then scores the calibrated model on the held-out fold. Add a reliability curve and a Brier decomposition per fold. Regularise the logistic baseline so it stops producing outliers.
- Early stopping validates on a time-ordered tail of each training window.
- Permutation importance runs on held-out data with the fold model and is scored on log-loss, matching what the UI says.
- SHAP comes from the served ensemble's base models (averaged) and is labelled as such.
- A model manifest (feature-schema hash, horizon, label parameters) is checked on load, and the registry id is restored on restart.
- Quantity features are normalised per symbol by a rolling median, so the "scale-free" claim becomes true.
- Regime splits into two honest axes: **volatility state** (calm / normal / elevated / extreme, from the HMM) and **direction** (down / flat / up, from the drift statistic). "Trending" is used only when the direction is significant.

**T4 — API & security.**
- Response models for the feature catalog, system metrics, market stats and backtest trades, leaving zero hand-written TS types.
- Errors as RFC 9457 problem+json; pagination on history endpoints.
- Security:
  - Reads stay public; mutations require authentication (D4). Registration is off in production.
  - CORS is limited to configured origins, and the rate-limit key comes from a trusted proxy only.
  - Mutations and backtests get per-route limits.
  - The WebSocket gets a connection cap and an origin allowlist.

**T5 — Observability & operations.**
- A Prometheus `/metrics` endpoint covering:
  - event-loop lag, event rate and exchange→receive latency;
  - WS clients, backlog and drops;
  - writer queue depths;
  - training duration and inference latency;
  - DB errors.
- De-duplicate the repetitive socket-error log lines.
- Shut down in a defined order with final flushes. Document deployment for the chosen persistence (D5).

**T6 — Engineering quality.**
- A regression test per audit finding; property tests (hypothesis) for book sync, rings and bars; coverage reporting with a floor.
- E2E runs against the standalone server with a pre-warmed, seeded synthetic DB (fast and deterministic). It adds a forced-mid-tier WebGL project, visual-regression baselines and axe accessibility checks.
- CI publishes coverage and Playwright artifacts, keeps separate Docker cache scopes, and enforces Lighthouse budgets on non-3D routes.
- Repo hygiene:
  - `.gitattributes` (LF line endings);
  - pre-commit hooks (ruff, eslint, prettier) and `justfile` tasks;
  - a dependency-update bot;
  - dead settings removed and stale docs fixed;
  - `ARCHITECTURE.md` with short ADRs, and a `CHANGELOG.md`.

### 10.3 Visual workstream

**Direction: "calm terminal".** Dense and legible like a professional trading terminal, finished like a premium product. Colour carries meaning only; motion follows the data and never decorates; glass is reserved for things that float.

**V1 — Design system v2.**
- **Surfaces:** a five-step, slightly cool graphite ramp with 1 px hairlines and a faint top highlight, in three elevation tiers. Frosted glass only on the header, overlays, popovers, palette and tooltips.
- **Colour:**
  - Bid teal and ask rose, re-tuned (slightly desaturated, still separable under colour-vision deficiency), each in three intensities; mid in amber.
  - One neutral-blue accent for interaction, kept separate from market semantics.
  - Muted regime hues; text in four levels that all meet AA contrast.
- **Type:**
  - Geist Sans on a fixed scale (12/13/14/16/20/24/32) with sentence-case labels.
  - Geist Mono only for numerals and tables, with tabular figures.
  - Units smaller and muted; no negative zero; consistent precision per instrument.
- **Grid:** 4-pt spacing and a 12-column bento with fixed row heights so panels align. One panel anatomy everywhere: title, inline meta and actions; body; optional footer.
- **Components:**
  - Panel, and Stat (value, unit, delta, sparkline, z-badge).
  - Badge, SegmentedControl, Tabs, Button and IconButton.
  - Field, Select, Switch and Slider.
  - DataTable with a sticky header, numeric alignment and row hover.
  - Tooltip, Drawer and Skeleton.
  - Designed empty and warm-up states: a progress ring with ETA replaces the "calibrating" chips.
- **Charts:** one theme shared by lightweight-charts and the custom canvases, covering grid, axes, crosshair, tooltip, legends and gap markers.

**V2 — App shell.**
- **Top bar:**
  - Brand, and a nav with an animated active indicator.
  - A market ticker: symbol switcher, last price with tick flash, session change, spread.
  - Connection health (source badge, latency, feed status) and ⌘K.
- **Status bar:** a thin bar along the bottom (events/s, loop lag, model version, last bar time), the terminal cue.
- **Background:** the flow-field trails go. What stays is a quiet regime-tinted vignette with a fine grid and grain, which moves subtly only when the regime changes.
- **Mobile:** a compact header, a bottom tab bar, and single-column panels that never overflow.

**V3 — Dashboard.**
- A market strip of six Stats with sparklines.
- A hero panel with a **Heatmap | Terrain** switch (D2):
  - The Heatmap is the legible default: Bookmap-style price × time liquidity, drawn as a WebGL texture with trade bubbles and a price axis.
  - The Terrain is reworked: camera fitted to its bounds, a floor grid, price/time/depth axes, depth-graded colour, crisp particles, and a crosshair tooltip that follows the displaced surface.
- A price chart with volume, VWAP and microprice overlays, a crosshair, and session-gap markers.
- A model card: probability bar with a calibration note, plus a drift sparkline.
- Regime shown as a timeline ribbon over the last N minutes, replacing the four percentage bars.
- A lower row of equal-height panels:
  - order flow: OFI histogram plus cumulative OFI;
  - signals: active list plus timeline;
  - tape: size-scaled, aggregated prints.

**V4 — Book.** A ladder with inline depth bars and heat, a depth chart on a symmetric clamped scale, liquidity bands as a compact chart, and the heatmap/terrain at full size.

**V5 — Intelligence.**
- A model card, a reliability diagram, and a fold chart with robust scaling.
- A SHAP waterfall with human-readable feature names, alongside permutation importance.
- The registry as a timeline table, a drift panel and a regime timeline.
- The signal rules as a table with live state.

**V6 — Strategies.** Three panes: a library; a builder that shows conditions as visual chips over the feature catalog; and a results tear sheet (equity and drawdown, KPIs, a filterable trade table). Templates appear as a gallery.

**V7 — Alerts.** A rules table with inline enable toggles, the rule form in a drawer, and a history timeline with acknowledge.

**V8 — Settings.** Sections with a side index.

**V9 — Quality bar.**
- Every interactive element has hover, focus, pressed and disabled states.
- AA contrast throughout, and a clean axe run.
- `prefers-reduced-motion` and the in-app motion setting both apply to CSS and to JS, via `data-motion` on `<html>`.
- The low tier keeps the layout and swaps WebGL for 2D.
- Before/after screenshot sets at 1440×900 and 390×844, on a real GPU.

### 10.4 Stages

| Stage | Scope | Reviewable outcome |
|---|---|---|
| **G — Runtime isolation & correctness** | T1, T2, regression tests | Loop p99 < 20 ms while training under CPU load (latency probe + py-spy); e2e 14/14; every audit defect has a test that failed before the fix and passes after |
| **H — ML rigor & regime semantics** | T3, typed contracts (first half of T4) | Walk-forward numbers for the served model, reliability data, honest importance; no hand-written TS types |
| **J — Design system v2 & shell** | V1, V2, plus a restyled dashboard as the **direction check** | Screenshots signed off before the rollout |
| **K — Dashboard & Book** | V3, V4, including the heatmap and the terrain rework | Before/after set; 60 fps on the Iris Xe; low-tier fallback verified |
| **L — Remaining pages, responsive, a11y** | V5–V9, visual-regression baselines | All routes redesigned; axe clean; mobile verified |
| **M — Security, ops, hygiene** | Rest of T4, T5, T6 | `/metrics`, auth on mutations, CI/test/docs upgrades all green |

**Proposed order: G → J → K → L → H → M.**
- G goes first because the loop stalls also make UI verification unreliable.
- The visual stages come next because they are the most visible gap.
- H can move before L if the redesigned Intelligence page should show the new metrics from day one.

### 10.5 Decisions needed

| # | Question | Recommendation |
|---|---|---|
| D1 | Stage order | G → J → K → L → H → M |
| D2 | Dashboard hero | Heatmap by default with a Terrain toggle; the terrain also full-size on /book |
| D3 | Ambient background | Keep a quiet vignette/grid; remove the flow-field trails and motes |
| D4 | Auth model | Reads public; mutations behind a single admin token in production (the JWT login stays available) |
| D5 | Hosted persistence | SQLite locally; Postgres via `DATABASE_URL` for the hosted backend (Render's free disk is ephemeral) |
| D6 | New dependencies | Backend: `threadpoolctl` (already transitive via scikit-learn), `prometheus-client`, `hypothesis` (dev). Frontend: `prettier`, `@axe-core/playwright` (dev). No new runtime UI library |

### 10.6 Delivery log

**Stage G — runtime isolation & correctness (2026-09-24).** Every item in T1/T2 was built, with a regression test for each audit finding (backend tests 87 → 116; Vitest 10 → 11). Two of the tests were checked against the old behaviour, reintroduced temporarily, and failed as expected: request-scoped commits, and stops on the fill bar.

Measured on the Iris Xe laptop, live Binance feed, while a model retrained:

| Condition | `/health` p50 / p99 / max | Before Stage G |
|---|---|---|
| Training, normal desktop load | 2.3 / 12.7 / 137 ms | p99 297 ms, max 410 ms |
| Training, all 8 cores saturated by burner processes | 3.0 / 48 / 121 ms | 3–19 s stalls, keepalive disconnects |

- py-spy under the saturated load shows the event-loop thread busy for ~7 % of samples. Its largest remaining cost is the 5 Hz depth-profile scan; predictions run on the `infer-*` thread.
- The 20 ms p99 target holds while training under normal load. With every core deliberately saturated, p99 is 48 ms: OS scheduling contention across 14 runnable threads, not work on the loop.
- Playwright: 14/14.

Additions and deviations, all deliberate:

- **Spawned-process start runs off the loop.** On Windows, `Process.start()` writes the pickled arguments (megabytes of training data) into the child's pipe and blocks until the still-importing child reads them. Found during the build as multi-second loop stalls.
- **Unpaced sources are lossless.** Replay and synthetic at speed 0 put the intelligence tier into FIFO mode with backpressure (`yield_to_consumer`), so every bar is predicted. Real-time feeds keep latest-bar-wins.
- **The OpenMP limit is process-wide with MSVC's vcomp on Windows** (per-thread with libgomp on Linux). This is harmless: nothing else in the server process uses OpenMP once training runs in its own process. Documented in `core/workers.py`.
- **The SHAP explainer is built on the inference thread when a model is installed**, not inside the training process. Explainer objects are not reliably picklable; it is still never built on the loop.
- **The embargo stays index-based.** Sessions are split at gaps, and there is at most one sample per bar, so an index distance never exceeds the time distance: the index embargo is at least as strict as a time embargo. A test asserts that every feature and label window stays inside its session.
- **The "resumed after gap" chart marker moves to Stage K** (the chart redesign). The backend no longer splices, and charts start fresh after an outage longer than `BAR_RESUME_MAX_GAP_S`.
- **One V9 item pulled forward.** Detected software renderers open the terrain panel on the 2D curve: SwiftShader compiles the terrain shaders on the main thread, a 28 s freeze. The 3D toggle stays.
- **E2E per-test budget raised from 90 to 180 s.** A trace showed the software-rendered dashboard blocks on "GPU backpressure": accelerated 2D canvases and every panel's backdrop blur are rasterised on the CPU. It takes 60–100 s there against ~2 s on a GPU. Restricting glass to floating elements in Stage J (V1) removes most of those blur layers.
- **Startup rebuilds ML history in a thread**, and the loop-lag monitor starts once startup is done.
- **HMM fits now also run in the worker process.** They are single-flight too: the same done-callback race had produced duplicate "v4" fits.

**Stage J — design system v2, app shell, dashboard direction check (2026-09-24).** V1 and V2 were built, and the dashboard was restyled on them. This is the direction check: the rest of V3 (heatmap, terrain rework, regime ribbon, aggregated tape) is Stage K, and the other pages are Stage L.

- **Tokens** (`app/globals.css`, mirrored in `lib/theme`):
  - A graphite surface ramp: page, panel, raised, control, active.
  - Four ink levels, all ≥ 4.9:1.
  - Bid, ask and mid, each with a mark colour and a text colour.
  - One interaction accent; the status scale good/warning/serious/critical; a one-hue violet regime ramp (regime is ordinal).
  - A type scale of 11/12/13/14/16/20/24/32, plus radii.
  - Every palette decision was run through the dataviz validator. Bid/mid/ask pass all pairs (worst CVD ΔE 10.5, normal-vision ΔE 18.5); the regime ramp passes the ordinal checks. The old palette failed the lightness band, which is why it looked harsh.
- **Components:**
  - `app/ds.css` is the component layer. `components/ds` holds Panel, Button, Badge, ZBadge, Input, Select, Textarea, Field, Switch, SegmentedControl, Divider, Tooltip, Kbd, Skeleton, ProgressRing and Stat. `glass.css` and the `Glass*` components are gone.
  - Glass (`.float`) is now only on the app bar, menus, palette, toasts and tooltips. Panels are solid.
  - Text stays in ink; tone is carried by dots, tints and marks.
- **Shell:**
  - The app bar holds the brand, a nav with a sliding indicator, and a market ticker (symbol, tweened mid with tick flash, 5-minute change, spread). It also shows feed health and ⌘K.
  - A terminal-style status bar: ev/s, loop p99, book state, model, last bar, RTT, clock.
  - A bottom tab bar on mobile.
  - A regime-tinted vignette with grid and grain replaces the flow field. The tint cross-fades through a registered `--regime` property.
  - `data-motion` on `<html>` makes the in-app motion setting reach CSS as well as JS.
- **Dashboard:**
  - A 12-column grid with equal-height rows.
  - A market strip of six Stat tiles with 5-minute sparklines, z-badges and a 5-minute delta on mid.
  - A model card with a warm-up ring and ETA; regime on the ramp.
  - An order-book card with a depth curve and touch read-outs, and a live Switch.
  - A tape with side dots; signals with a designed empty state.
  - Order-flow and session strips.
- **One chart theme for every chart** (`CHART`): hairline grids, 2 px lines, 10 % washes, an accent crosshair and DOM labels.
  - Signed series (OFI, imbalance) split bid-above / ask-below at zero.
  - Strip and depth curve now redraw on resize (previously only on the next bar) and have a hover read-out.
  - Price labels use thousands separators.
  - Microprice is a neutral line. The z-strips hold a ±3σ minimum scale and shade the |z| ≥ 2 tails.
- **Checks, all green:**
  - Frontend: tsc, eslint, Vitest 11 → 12, `next build`, npm audit.
  - Backend: ruff, mypy, pytest 116 → 117, pip-audit; OpenAPI current.
  - Playwright 14/14 in 2.2 min. The dashboard test now takes 3–6 s on SwiftShader, down from 60–100 s: the per-panel blur that caused the GPU backpressure is gone. The two tests that had raced passed three more repeats each.
  - Real-GPU captures at 1440×900 and 390×844 on every route: no console errors, no horizontal overflow.

Deviations:

- **Two hydration races, found by e2e** (React #418, intermittent on SwiftShader, where hydration takes seconds). Both were reproduced against the dev server's hydration diff, fixed, and re-probed clean over 24 loads:
  - The bar table is mutated outside React. When bars had already landed before `MarketStrip` hydrated, the sparklines and deltas rendered data where the server HTML had none. `useBars` now hands out an empty table until `barsHead` moves; a Vitest case fails without the fix.
  - The new status bar in the layout polls `/system/metrics`, and the Settings page hydrates later with that query already cached. `useSystemMetrics` reports no data until hydration is done (`useHydrationDone`).
- **The status bar judges bar freshness by arrival time, not event time** (`lastBarAt` in the store), as the server's feed watchdog does. Replay's historical timestamps would otherwise always read as stale.
- **Backend fix: synthetic pacing drifted** (found through the new status bar). The paced source slept a fixed 100 ms *after* each step's work, and Windows' ~15.6 ms timer granularity stretched every sleep. Event time lost ~20 % against the wall clock, 22–25 s after three minutes and growing, so every synthetic-mode time axis was off. It is now paced against a deadline; the lag holds at ~1 s. A regression test fails on the old loop (6.5 s of event time where 20 s were due) and passes on the new one.
- **The tape does not flash per print.** At the synthetic feed's ~100 trades/s the 20 visible rows turn over several times a second, so a per-row flash tinted the whole tape. Aggregated, size-scaled prints are Stage K.
- **Other pages got only what the new system needed to render correctly:** retired `glass`/`chip`/`live-dot` classes replaced, PageHeader tiles, and signal-priority tones aligned. Their redesign is Stage L. Known leftovers for L: Settings uses bid/ask as good/bad tones, and there are raw `text-[11px]` sizes.


**Stage K — dashboard and book (2026-09-25).** Built V3 and V4 on the Stage J system: the hero, the terrain rework, and the rest of the dashboard and book panels.

- **Liquidity hero, Heatmap | Terrain** (D2; heatmap by default).
  - The heatmap plots price × time over 3 minutes of book frames. Each cell is the quantity resting in that price bin: the server's full-book depth profile, differenced, and placed at absolute prices using each frame's mid. This makes resting walls horizontal lines that price moves through.
  - Overlays: the mid trail, and trade bubbles at each column's VWAP with area ∝ traded quantity. There are price and time axes, and a hover read-out of price, age, resting size and trades.
  - Bins are interpolated between their centres, so levels don't speckle as the mid moves. The vertical span follows the price trail up to 2.5 bands; beyond that, older prices scroll out.
- **Terrain rework.**
  - The camera distance is fitted to the terrain's bounds, with room left for its labels.
  - A floor grid, plus price (bps and mid), time and depth axes as projected DOM labels.
  - Colour is graded by depth, and the surface fades with age instead of darkening into a slab. Particles are crisp discs with normal blending.
  - The crosshair ray-marches the height field on the CPU, using the shader's own height mapping, so it lands on the displaced surface rather than the flat plane beneath it.
- **Price chart.**
  - A volume histogram, each bar coloured by its net aggressor side.
  - Session gaps break the lines and carry a "gap N s" marker (deferred from Stage G).
  - The chart opens on the ring's full 10-minute window, right-aligned.
- **Model card:** one down | flat | up probability bar. The note says what the probability means (the first barrier touched within the horizon) and how it is calibrated (on embargoed time splits), with a link to the reliability curve. The footer adds a drift sparkline: rolling log-loss over 30 predictions against the class-prior baseline.
- **Regime:** a ribbon of per-bar regime over the ring on the ordinal ramp, with share-of-time and a hover range. It replaces the four probability bars. It needed one backend addition: a `regime` ordinal code column on streamed bars. Regime is persisted per bar, so history loads too. The OpenAPI contract is unchanged (bar columns are data).
- **Lower row:**
  - Order flow: an OFI histogram and cumulative OFI as two strips (no dual axis).
  - Signals: a per-rule activation timeline over 10 minutes of event time, seeded from `/analytics/signals` history and extended live, above the active list.
  - Tape: fills from one taker sweep (same side, within 100 ms of the group's newest fill) merge into a print at their VWAP. Size bars are on the aggressor's colour, scaled to the 90th percentile; prints of 2× or more are emphasised. The trade buffer grew from 200 to 1,000 fills so the aggregated tape stays full.
- **Book page.**
  - The hero at 520 px.
  - The depth chart moved to the full-book profile. The old top-50-level version covered under 1 bps of BTC's 0.01-tick book, so on the live feed it was a wall at mid and then flat. Its scale is symmetric, and the y-axis is clamped at 2.5× the thinner side, with a clipped side showing its total.
  - A ladder with size heat and cumulative bars; walls (≥ 3× the median) are emphasised.
  - Liquidity bands (±5/±10/±25 bps) as a compact bar chart, followed by the book-shape figures.
- **Measured** on the Iris Xe (headless Chromium, D3D11), final build, live Binance feed:
  - 60 fps, p99 frame 16.8 ms, no frames over 33 ms and no long tasks, on `/` and `/book` in both heatmap and terrain views.
  - The same with a full 3-minute heatmap (900 columns). The Stage J baseline was also 60 fps.
- **Fallbacks verified:**
  - SwiftShader (low tier): the heatmap renders, and the terrain stays opt-in (first frame 8.9 s after the switch, against 28 s for the old terrain).
  - WebGL disabled: the heatmap renders and the Terrain option is hidden.
  - In-app reduced motion: `data-motion="reduced"`, and the particles are off.
  - No console errors in any of the three.
- **Checks, all green:**
  - Vitest 12 → 18: HeatRing differencing and trade folding, anchored sweep aggregation, cumulative. The anchoring test fails on the chained version.
  - pytest 117 → 118: the regime code column.
  - ruff, mypy, pip-audit, tsc, eslint and `next build` clean.
  - Playwright 14/14; dashboard and book tests passed three more repeats.
  - Dev-server hydration probe clean over 18 loads.

Deviations:

- **The heatmap is Canvas 2D image data, not a WebGL texture.** At ≤ 900 × 240 cells it rasterises in a few ms once per book frame, needs no shader compile, and is the same view on every tier.
- **Bugs found while verifying, fixed with the stage:**
  - The depth curve's top-N data (above).
  - The price chart kept the bar spacing it fitted to a half-filled ring after a backend restart, showing seconds instead of minutes.
  - The tape's first grouping chained same-side fills into a few giant prints.
- **Known limits:**
  - Heatmap history is client-side, so it fills in over 3 minutes after a page load (the page says so).
  - The terrain still costs a ~9 s shader compile on software renderers, which is why it stays opt-in there.

**Stage L — remaining pages, responsive, accessibility (2026-09-26).** V5–V9 are built. Every route is on the design system, axe-clean at desktop and mobile, and pinned by visual baselines.

- **Design system:**
  - A `Drawer`: a modal side sheet with focus moved in, Tab trapped, Esc and the backdrop to close, scroll locked, and focus returned to the opener.
  - `TableWrap` + `.data-table`: a focusable, named scroll region, sticky header, numeric alignment and row hover.
  - Condition chips, a slider style, and pressed or disabled states on every interactive primitive that lacked them.
  - Tooltips can anchor to the trigger's end. Panel headers wrap on narrow screens.
- **Intelligence (V5):**
  - Drift monitor on the chart theme (`MiniSeries` rewritten: DOM axes and legend, labelled reference levels, hover read-out).
  - A **reliability diagram of the live predictions**: class-wise or pooled, with calibration error, Brier score and a histogram of predicted probabilities. Training-time reliability does not exist yet (T3).
  - SHAP as a waterfall from the base value to the prediction, with readable feature names and values in units (a label map for all 47 model features). Permutation importance as a bar list.
  - Walk-forward folds as a dot plot on a robust scale (baselines far outside are pinned to the edge with their value), with a fold table.
  - The registry as a timeline table; signal rules as a table with live state and time held.
- **Strategies (V6):** three panes at ≥ 1280 px (library · builder · results).
  - Library: saved strategies (searchable) and quick-start templates; the template gallery is the empty state.
  - Builder: conditions as chips (feature ▸ operator ▸ value), and/or groups, and a searchable feature-catalog drawer that adds to the chosen block.
  - Tear sheet: eight KPIs, equity and drawdown in **two panes on one time axis** (the old chart used two scales on one plot), and a trade table filtered by side, outcome and exit reason.
- **Alerts (V7):** a rules table with inline, named toggles; the rule form in the drawer (a real form, so Enter submits); history as a day-grouped timeline with acknowledge.
- **Settings (V8):** sections with a sticky side index that follows the section in view. The tier copy now matches Stage K, and status tones replace bid/ask.
- **Quality (V9):**
  - `@axe-core/playwright` 4.13.0 (D6) and `e2e/a11y.spec.ts`: WCAG 2.2 AA on every route and on both drawers.
  - The baseline scan found five violation types: warming z-badge contrast, ladder heat-cell contrast, unlabelled canvases, a keyboard-unreachable scroll region, and a nameless switch. The redesign fixed those, and the new scans found five more, all fixed:
    - faint text on selected rows;
    - a 16 px target;
    - an alert role on a list;
    - status-coloured text in the status bar (it failed contrast whenever the loop lagged);
    - the active-signals scroller.
  - `e2e/visual.spec.ts`: 12 baselines (6 routes × desktop and mobile). The page is pinned to one state: WebSocket accepted but silent, REST unanswered, frozen clock, UTC, reduced motion. They passed 24 of 24 on a repeat run. They are Windows baselines, so other platforms skip them.
  - Mobile: every route lays out at exactly 390 px. The earlier "no overflow" checks compared the page with a viewport that emulation had widened to fit it, which hid a 431–546 px layout. The causes were invisible tooltips and panel headers that didn't wrap.
- **Honesty fixes found on the way:**
  - The importance panel said "out-of-sample log-loss increase". It is the accuracy drop, on a fold the measuring model was trained on, so the panel now says so (T3 fixes the computation).
  - SHAP is labelled as explaining the uncalibrated model.
  - Sharpe and Sortino over under a day are labelled "not meaningful yet".
  - The tape no longer claims "50 % bought" before any fill.
- **Checks:**
  - Vitest 18 → 22 (reliability, condition helpers).
  - Playwright 14 → 34 (8 accessibility, 12 visual), all passing.
  - tsc, eslint and `next build` clean. Backend unchanged (pytest 118).

Deviations and limits:

- **The reliability diagram uses live resolved predictions** (the drift window, ≤ 300), not held-out folds. Per-fold reliability comes with T3.
- **The three-pane strategies layout starts at 1280 px**; from 1024 px the results stack under the builder.
- **Visual baselines exist only for Windows.** A Linux set for CI belongs with the seeded, deterministic e2e database in Stage M (T6).

**Theme v3 — "midnight glass" dark theme (2026-09-26).** A full visual overhaul of the dark theme after the Stage L review found v2 dull. Same component names and structure; new tokens, surfaces and chrome.

- **Palette:** a navy ramp (page `#060911` → active `#243049`) replaces graphite. Inks and market colours were re-validated against it.
  - bid/ask/mid pass all-pairs: worst CVD ΔE 11.6, normal-vision ΔE 18.7, all ≥ 3:1.
  - The regime ramp passes the ordinal checks.
  - Every text ink and `*-text` step clears 4.5:1 on all surfaces up to "active".
  - Status colours are brighter but still reserved.
- **Surfaces:**
  - Panels have a gradient body inside a lit edge (a border-box gradient, brightest along the top), a header divider and a section-icon chip in the brand gradient (accent → violet).
  - Controls sit in wells. Selected and primary states are lifted and lit in the accent.
  - Badges are pills with glowing dots.
- **Ambient:** an aurora (brand blue, the live regime colour, a trace of bid teal) drifts on a 48 s composited transform over a night gradient, grid and grain.
- **Components:**
  - Stat tiles: an eyebrow label, a 28 px value, a direction delta pill, accent sparklines with fading fills.
  - Charts: canvas and lightweight-charts areas fade to their baseline; the price mid is an area.
  - Heatmap: the ramp's low end is lifted (gamma 0.8 → 0.65) so the resting book reads on navy.
  - Shell: brand mark and gradient wordmark, an active-route pill, a glowing slide indicator, page eyebrows, and a 26 px title.
- **Fixed on the way — the glass never frosted.** `.float` declared `backdrop-filter` and `-webkit-backdrop-filter`. Lightning CSS kept only the prefixed one, which Chrome ignores, so the app bar, palette, menus and tooltips had no blur (in v2 as well). Only the unprefixed property is declared now, and the build adds the prefix.
- **Fallbacks:**
  - `data-tier` on `<html>`: on the low tier, floats go near-opaque with no blur and the aurora and live ring stop looping.
  - Reduced motion flattens both, as before.
  - Verified by computed styles on a real GPU, SwiftShader and reduced motion.
- **Checks:**
  - axe clean at 1280 and 390 px on every route and both drawers (synthetic), plus the dashboard, book and intelligence on live data.
  - No overflow at 390 px.
  - Frame rate on the Iris Xe, production build: 58–60 fps with p99 16.8 ms in most runs. An A/B test against removing panel shadows, blur, drift or the ambient layer showed no measurable cost; run-to-run noise is equal in every variant.
  - Visual baselines re-recorded (20/20 on a repeat run). Playwright 34/34, Vitest 22, tsc, eslint and build clean. Backend and API unchanged.

**Stage H — ML rigor and regime semantics (2026-09-26).** T3 plus the typed-contract half of T4. The model is now evaluated exactly as it is served, and every number the Intelligence page shows means what its label says.

- **Evaluate what we serve** (`ml/train.py`). One recipe, `fit_model`, builds both the served model and every walk-forward fold model:
  - Boosted trees whose early stopping validates on the time-ordered last 15 % of the training window, after an embargo. Before, it validated on HGB's random split, which interleaves with the fit rows. A test spies on the fit to prove the split.
  - Calibration on embargoed time splits of the same window (`TimeSeriesSplit(3, gap)`, one calibrated tree model per split, averaged). Isotonic from 1,000 samples, sigmoid from 400, none below.
  - Every fold runs the recipe inside its own training window and is scored on the fold it never saw.
- **What each fold reports** (`ml/evaluation.py`):
  - log-loss, calibrated and raw;
  - accuracy;
  - the multiclass Brier score with Murphy's reliability / resolution / uncertainty terms (a test pins the identity);
  - a reliability curve (10 bins per class; folds pool exactly);
  - the same scores for the class prior and a logistic baseline. The baseline is now regularised (C = 0.1, inputs clipped at ±5σ), so heavy-tailed features no longer throw it off the chart.
- **Importance.** Permutation importance runs on held-out folds, with each fold's own served model, scored as the rise in log-loss (mean ± s.d.). The last two folds are used, with at most 1,500 rows each and 3 repeats, to bound the cost. The panel now says exactly this. Before, it was in-sample accuracy labelled as log-loss.
- **SHAP** explains the served ensemble: the tree models' raw log-odds for the class the *calibrated* model predicts, averaged over the tree models. It is labelled so, and a test checks additivity against the models' margins. The explainers are built one per inference-thread task, so a prediction waits behind at most one.
- **Manifest.**
  - Every artefact records the feature-schema hash (names plus a schema version), the lookback, the label horizon and barrier parameters, and the class order.
  - On load a mismatch is refused and retrained. The refused version number is still claimed, so the next model doesn't overwrite it.
  - The registry id is restored on restart, looked up by artefact path, because versions repeat across data sources.
- **Scale-free quantities.** Nine count, volume, order-flow and depth features are divided by their symbol's rolling 30-minute median. The median uses positive values only, kept in a sorted list beside a FIFO, and resets at session gaps. A test shows the feature vector is identical when every size is ×1000.
- **Regime split** into two honest axes:
  - **Volatility state.** The HMM's labels always came from each state's mean volatility z, so they are renamed for what they measure: calm / normal / elevated / extreme. The fallback now uses the same cut-points.
  - **Trend** (down / flat / up). The drift of 2 minutes of 1 s returns as a t-statistic with a Newey–West standard error (lag 5), since 1 s returns are autocorrelated. It enters at |t| ≥ 2 and releases below 1.5. "Trending" appears only then.
  - Bars carry a `trend` code. The backtester recomputes the trend from closes with the same statistic, so older history qualifies.
  - Signals: *Extreme volatility*, *Calm market*, *Trending up*, *Trending down*.
  - Alembic migration `4c1e7b2a9d30`:
    - adds `market_snapshots.trend`;
    - renames stored labels;
    - rewrites saved strategies' regime conditions.
    - Tested in pytest and on a copy of the dev database: up, `alembic check`, down, up.
- **Typed contracts.** Response models for symbols, the feature catalog, market stats, system metrics (with nested source / book / ML / WS / loop models), backtest trades and reliability curves. `hooks.ts` declares no response shape by hand.
- **UI:**
  - Regime panel: a volatility-state ribbon and a separate trend ribbon with a t-gauge (the ±2 zones marked).
  - Walk-forward: calibration method and raw log-loss per fold, plus the Brier terms.
  - Reliability: a Held-out / Live switch; held-out is the default, from the pooled fold curves.
  - SHAP and importance captions describe the new computations.
  - Tick labels no longer repeat on narrow ranges.
- **Result on live BTC (5 s horizon) — the model has no edge.** The first honest run:
  - v35: held-out log-loss 0.808 against the prior's 0.762 (edge −0.045). It beat the prior in 1 of 4 folds.
  - v39: edge +0.001, 2 of 4 folds.
  - Calibration helps (raw → calibrated gains 0.04–0.31 nats) but can't create resolution. The Brier resolution term is ≈ 0.005 against reliability 0.05–0.07.
  - The prior's own log-loss falls from 0.93 to 0.34 across folds as the flat share grows: the class mix drifts, and that is where the miscalibration comes from.
  - The registry shows earlier versions were also negative on live data (−0.2 to −0.3 under the old, uncalibrated fold scoring). The page now says so plainly.
  - Calibration isn't always a gain. On synthetic data, v45's calibrated fold log-loss was 0.672 against 0.612 raw (isotonic on short inner splits overfits). The walk-forward "Raw" column now exposes this rather than assuming calibration helps.
- **Checks:**
  - pytest 118 → 134. The suite runs in 76 s: modules that train in-process get the worker's thread cap. That cap is module-scoped, because held for the whole session it hangs the engine test on Windows.
  - ruff, mypy, pip-audit clean. OpenAPI regenerated (36 paths, 85 schemas).
  - Vitest 22 → 24. tsc, eslint and build clean.
  - Playwright 34/34: Overview and Intelligence baselines re-recorded; visual and accessibility specs 20/20 on a repeat run.
  - One full run had a flake: the backtest spec's 90 s wait for "completed" expired with the run at 100 %. It passed 2/2 in isolation and 34/34 on a full rerun.
  - The suite took 8.6–12.5 min this afternoon against 4.2 min this morning, and tests that never touch the backend slowed as much. The e2e backend measured 0.2 % of one core at steady state, plus one ~22 s training (4 of 8 cores) at startup and about every 10 minutes. So the slowdown is load on this machine, not the app.
  - axe clean at 1280 and 390 px with populated live panels. No overflow at 390 px.

Deviations and limits:

- **Regime labels changed name.** Saved strategies and stored bars are migrated. External consumers of the old labels (none in this repo) would need the same map.
- **Permutation importance covers the two most recent folds**, not all four, to keep training under ~20 s at the 20,000-sample cap.
- **Bars stored before this stage have no trend.** The ribbon leaves them blank; the backtester computes them.
- **No edge on live data is a finding, not something fixed here.** Candidates for a later stage: a longer horizon, labels with a floor above the spread noise, and features that survive the regime drift.

**Stage M — security, operations, engineering quality (2026-09-30).** The rest of T4, plus T5 and T6. This closes Phase 4.

- **Access (D4):**
  - Reads, including the WebSocket, stay public.
  - Every mutation depends on `require_writer`. With `MUTATIONS_REQUIRE_AUTH` on (production by default) it needs `Authorization: Bearer <ADMIN_TOKEN>`, compared in constant time, or an active user's JWT. Covered: strategies, alert rules, backtests, acknowledgements.
  - Production refuses to start without a ≥ 32-character `ADMIN_TOKEN`, and registration is off there.
  - `GET /auth/access` says whether changes are gated and whether the caller passes. Settings → Access stores the token in that browser only; the API client sends it as a bearer header; a 401 names the fix.
  - Verified live against a gated backend: read-only → the change is refused with that message → token saved → the change goes through → token forgotten.
- **Transport:**
  - CORS is limited to configured origins. The host-wide `*.vercel.app / netlify / onrender` pattern is gone (`CORS_ORIGIN_REGEX` is opt-in). Credentials are off (bearer tokens, never cookies), and methods and headers are enumerated.
  - Forwarded addresses are believed only from `TRUSTED_PROXIES`, applied in the app with uvicorn's `--no-proxy-headers`. Before, `--forwarded-allow-ips=*` let any client choose its own rate-limit key.
  - Per-client buckets: every request, writes (60/min) and backtest submissions (6/min).
  - The WebSocket refuses foreign origins (403 handshake) and closes with 1013 beyond `WS_MAX_CLIENTS`.
- **Errors and pagination:**
  - Every error is RFC 9457 `application/problem+json` with the request id. Validation failures list their fields; unhandled errors never leak exception text.
  - The OpenAPI document is rewritten so each error response is a `Problem`; no dangling refs.
  - Alert history, backtests and the model registry are keyset-paged (`limit` + `before` → `items`, `next_before`); the alerts page loads older pages on demand.
- **Observability (T5):**
  - Prometheus `/metrics` from one collector over the stats the engine already keeps:
    - loop lag, feed events, rate and resyncs;
    - WebSocket clients, frames and backlog;
    - writer queue, database errors and failed flushes;
    - training and inference timings, model version;
    - alerts and backtests.
  - A feed-latency histogram (receive − exchange time) is the only hot-path instrument. It is empty on the synthetic source, which has no wall clock.
  - Repeated warnings collapse to one line a minute with a count.
- **Operations:**
  - Shutdown order: backtests are cancelled and their rows marked failed, then feeds and ML engines (prediction flush), then the bar writer's final flush.
  - A stored model is now served after a restart without retraining; before, every restart retrained. The regression test was checked to fail with the fix reverted.
  - Postgres via `DATABASE_URL` (asyncpg, D5); `postgres://` URLs are normalised. The migration chain renders as valid PostgreSQL DDL offline.
  - `render.yaml` generates `ADMIN_TOKEN`, trusts Render's private proxy ranges, and leaves `DATABASE_URL` to set.
- **Engineering quality (T6):**
  - Property tests (hypothesis), each checked against a brute-force reference:
    - order-book sync over snapshot, buffered, stale and duplicate diffs, and a lost diff that must never leave a "synced" book wrong;
    - trade and sum windows;
    - bar contiguity, OHLC consistency and volume conservation.
  - Coverage in CI with a 90 % floor (92.5 % today). It needed `concurrency = greenlet`: SQLAlchemy's async layer runs in greenlets, and the API modules had read 56–61 % instead of 94–95 %.
  - `test_security.py` covers auth, problems, OpenAPI, rate limits, proxy trust, WebSocket guards, metrics, log dedupe, shutdown and pagination.
- **End-to-end:**
  - `scripts/seed_e2e.py` builds a deterministic template once (30 min of fixed-seed synthetic history run through the real engine, plus a model trained on it) in about 30 s, then copies it fresh for every run in about 3 s. Runs no longer inherit each other's rows, and Intelligence tests now assert the seeded model's four isotonic folds.
  - New Playwright project `webgl-mid`: forces the mid tier so the 3D terrain renders on SwiftShader.
  - Performance budgets on /strategies, /alerts and /settings:
    - hard limits: script ≤ 400 KB transferred (measured 325 KB) and CLS ≤ 0.1;
    - LCP is recorded but only guarded against a hang (15 s): on SwiftShader the same build measured 3.2 s and 7.8 s on consecutive runs.
  - The budgets surfaced a real bug: CLS on /strategies ranged 0.02–0.15 between loads. The connection banner rendered during the first WebSocket connect (and in the server HTML), then vanished and pulled the page up 37 px. The first connect is no longer announced (a failed attempt still shows it within ~150 ms). CLS is now 0.004–0.026 on every route.
  - CI uploads coverage and the Playwright report on every run, gives each Docker image its own cache scope, and checks prettier.
- **Hygiene:**
  - prettier 3.9.9 (D6) applied once at the code's own 140-column width.
  - `.gitattributes` (LF), `.pre-commit-config.yaml` (ruff, prettier and eslint from the project's own pinned environments), a `justfile`, and Dependabot (pip, npm, actions, docker; weekly, grouped).
  - Dead settings removed (`APP_VERSION`, `DEBUG`, `HOST`, the five legacy buffer sizes, `BUY_PRESSURE_WINDOW`, `ALERT_DEFAULT_COOLDOWN_S`).
  - `ARCHITECTURE.md` (runtime and ten ADRs), `CHANGELOG.md`, and the README's stale Phase 3 wording fixed.
- **Security fixes found by the gates:** PyJWT 2.14.0 → 2.15.0 (CVE-2026-101918; our decode verifies signatures first, so it was not reachable) and Next.js 16.3.5 → 16.3.8 (critical `next/og` RCE advisory; `next/og` is unused).
- **Found while verifying the UI:** an error toast raised from a drawer form (e.g. a refused change) rendered underneath the drawer and its backdrop; the command palette would have too. Toasts are now z-80 and the palette z-75, above the drawer at 70/71. An e2e test stubs a 401 and asserts the toast is the topmost element at its own centre; it failed with the old stacking and passes with the fix.
- **Checks:**
  - Backend: pytest 134 → 152 with coverage 92.5 % (floor 90 %), ruff, mypy and pip-audit clean. The OpenAPI document is regenerated (38 paths, 89 schemas) with no dangling references.
  - Frontend: prettier, tsc, eslint and build clean; Vitest 24 → 27.
  - Playwright 34 → 38 plus the toast test. The final full run was 38/38 in 9.8 min; after the stacking fix the alerts spec ran again (2/2). The Settings baselines were re-recorded for the Access section.
  - Live: the gated flow ran against a real backend with a temporary `.env` (since removed).

Deviations and limits:

- **Lighthouse is replaced by Playwright budgets** measuring the same things (script bytes, CLS, LCP). The Lighthouse CLI would add a dependency and a CI step that can't run here.
- **Two dependencies beyond D6's list:** `pytest-cov` (T6's coverage floor) and `asyncpg` (D5's hosted Postgres). Both are pinned.
- **Not done, because each needs a Docker image pull I have not been cleared for:**
  - Linux visual baselines (`mcr.microsoft.com/playwright`, ~2 GB); CI still skips the visual spec off Windows.
  - A migration run against a real Postgres; the DDL was verified offline instead.
- **Written but not run here:**
  - The CI workflow (it parses; each step mirrors a gate run locally).
  - The pre-commit config and the justfile, because `pre-commit` and `just` aren't installed on this machine. The hook commands were exercised by hand.
- **npm 9 exits 0 on a critical `npm audit` finding at `--audit-level=high`** (observed locally). CI's npm 10 is expected to fail as documented, but it is worth confirming on the first CI run.
- **Breaking API changes for any outside client:**
  - History lists return pages.
  - Errors are problem+json.
  - Production needs a token for writes.
  - The CORS wildcard is gone, so a preview frontend needs `CORS_ORIGIN_REGEX`.

---

## 11. Phase 5 — Ship, harden, and test the model for an edge (proposed)

> **Status:** approved 2026-10-01 with every recommendation in §11.4. Stage N's repository side is pushed (`ef448e3`) and awaits the owner's cutover. The hang fix and Stages P, Q, R and S are pushed (`bea471a`, `6fe1575`, `91af87b`, `c3b7e9b`, `addf995`), with a security update (`36b1463`); CI #19 was all green. Q's Linux visual baselines wait on Docker Desktop. S's verdict is preliminary until 7 days of live bars exist; a collector runs at logon on this machine, and E9 is approved (§11.4, §11.5). Stages keep §7's review-stop discipline.
> **Inputs:** the 2026-10-01 takeover audit:
> - every gate re-run locally, and CI #1 on `3d542f4`;
> - the GitHub commit and deployment statuses, and the production URLs;
> - a live Binance run with memory sampling through a training run;
> - real-GPU captures of every route at 1440×900 and 390×844.

### 11.1 Why

**Production and operations:**

| # | Finding | Evidence |
|---|---|---|
| 1 | The rebuild is not live. Vercel's production deploys of `ba73a7c` and `3d542f4` failed about 50 s after each push, and the Render backend still serves 2.0.0 | Commit status "Vercel: failure" (project `algo-viz`). `algorithmic-viz.vercel.app` serves the old Vite bundle. `algoviz-52q2.onrender.com/` reports `"version":"2.0.0"`, and `/health/live` returns 404 |
| 2 | Likely causes, unconfirmed without the dashboard logs: (a) the Vercel project still carries the Vite preset that `frontend/vercel.json` used to set; (b) the Render service was made by hand, so it still starts `uvicorn main:app` and has no `ADMIN_TOKEN` | The old `frontend/vercel.json` set `framework: vite` and `outputDirectory: dist`. The service's name (`algoviz-52q2`) is not the Blueprint's `algoviz-backend`. See `render.yaml` at `e8379bc` |
| 3 | Render's free tier does not fit this workload: the live feed and training stop whenever nobody is watching | Free web services sleep after 15 min without inbound traffic, lose their disk on every restart or sleep, and have 512 MB. Free Postgres expires after 30 days. Measured locally (Windows working set, 2 s samples): server ≈ 266 MB plus training child ≈ 157 MB, ≈ 423 MB at peak |
| 4 | Model artefacts live on the instance's disk. On an ephemeral disk, every deploy, restart or sleep retrains, and a persistent Postgres registry would collect repeated version numbers | `ML_MODEL_DIR = BASE_DIR / "ml_models"`; versions are numbered from the files in that directory |
| 5 | Two of the three default CORS origins are other people's sites, and the WebSocket allowlist follows them | `algoviz.vercel.app` is a Gatsby site called "Algoviz"; `algo-viz.vercel.app` is "Explorer: search visualization!". Only `algorithmic-viz.vercel.app` is ours |
| 6 | Dependency automation can merge untested majors | Dependabot PR #9 bundles TypeScript 5.9 → 7.0, ESLint 9 → 10 and `@types/node` 22 → 26 with patch bumps. PRs #2 (Python 3.14 image) and #4 (Node 26 image) are green only because CI builds those images without running anything in them. Every Dependabot branch triggers a Vercel preview, and they all fail |
| 7 | CI's runner and actions are about to change underneath it | CI annotations: actions@v4 target the deprecated Node 20, and `ubuntu-latest` becomes Ubuntu 26 on 2026-10-19 |

**Correctness and honesty:**

| # | Finding | Evidence |
|---|---|---|
| 8 | Synthetic backtest history is capped at 600 bars, whatever `BACKTEST_SYNTHETIC_BARS` says (default 3,600). The generator simulates them all, then returns the engine's 600-bar chart ring | `backtest/service.py:71`: asked for 900, got 600. e2e asks for 600, so it can't see the cap |
| 9 | The drift monitor compares the live hit rate with uniform chance (33 %), but the model is mostly right because it calls "flat": its 77 % hit rate is the flat share of that window. The log-loss tile beside it is honest | `DriftPanel.tsx:57,78`. Live: hit rate 77.2 %, realised flat share 77 %, edge vs the prior −0.055 |
| 10 | Trade frames keep only the last 100 fills of each 100 ms tick, and the dropped ones are not counted | `market/service.py:331`. Live 1 s bars reach 942 trades (p99.9 707), so bursts exceed the cap |
| 11 | e2e and `frontend-prod` run `next start` on a standalone build. Next warns that this "does not work", and the `server.js` that Docker ships is never exercised. §10.2 (T6) says e2e runs against the standalone server | The e2e web-server log |
| 12 | Stale docs | The README opens with the orbitable terrain, trade-flow particles and glass panels, which ADR-8 and theme v3 replaced (`README.md:7,36`), and still has a "Visual identity — Depth" section (`:129`). An e2e test named for the terrain checks the heatmap (`e2e/pages.spec.ts:26`), and a smoke-test comment still describes the old terrain fallback |

**Reliability and hygiene:**

| # | Finding | Evidence |
|---|---|---|
| 13 | The backend suite can hang on Windows inside `test_ml_engine`, after the model has trained, and nothing times it out | 1 hang in 2 full runs, killed after 9 min: the event loop was idle, with no child process. The test alone and the rest of the suite pass. CI (Linux) passed |
| 14 | Python builds are not reproducible, and one directly imported package is undeclared | Only direct dependencies are pinned; transitive ones (numba, llvmlite and pandas, via shap) float. `threadpoolctl` is imported directly but not declared |
| 15 | `export_openapi.py` writes CRLF on Windows, so regenerating the contracts always shows a diff | `git status` after an export, with identical JSON |
| 16 | Small drift in the engine | `book_payload` and `_adaptive_band` read the global `settings` rather than the engine's `cfg`. Snapshot requests are fire-and-forget tasks with no reference kept (`market/service.py:322,550,575`) |

**The model:**

| # | Finding | Evidence |
|---|---|---|
| 17 | "No edge at 5 s" rests on 3.2 h of live data. Retention deletes bars after 7 days, so the data set can never grow past a week | `data/algoviz.db` holds 11,599 bars in 8 sessions over 4 days. `SNAPSHOT_RETENTION_DAYS=7` |
| 18 | With four days of data, the hour-of-day features effectively identify the session | SHAP ranks `hour_cos` first (v39) |
| 19 | The class mix drifts, so a static training prior is a weak baseline. The honest comparator is the prior known at prediction time (trailing) | The prior's own log-loss falls from 0.93 to 0.34 across folds (§10.6, Stage H) |

**Experience:**

| # | Finding | Evidence |
|---|---|---|
| 20 | The hero heatmap is empty for 3 minutes after every page load, because its history is kept client-side | Real-GPU captures |
| 21 | Some read-outs are truncated | Real-GPU captures: the model card's drift line ("edg…"), "Trade velo…" on mobile, and "at the touch or the ho…" |

### 11.2 Workstreams

**W1 — Ship and verify (findings 1–5).**
- Repo side:
  - `frontend/vercel.json` pins `framework: "nextjs"`, which overrides the dashboard preset, so a stale preset can't break the build again.
  - The CORS defaults keep localhost and the production origin only (E2).
  - `render.yaml` states its plan and, under E1(b), mounts a disk for `data/` and `ml_models/`.
  - If E1 keeps Postgres instead: model artefacts (0.4–0.5 MB each) are stored on their registry row (`ml_models.artifact`, a migration) and loaded from there when the file is missing. Versions are numbered from the registry, not the directory.
  - The README's deployment section and the CLAUDE.md checklist are rewritten for the chosen hosting.
- Owner side:
  - Vercel: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, root directory `frontend`.
  - Render: the service per E3.
  - The push to `main`, which deploys.
- Verification once deployed:
  - `/health/ready`.
  - The site loads live data over WSS from the Vercel origin.
  - A change is refused without the token and accepted with it.
  - A restart serves the stored model without retraining.
  - Memory through a training run.

**W2 — Correctness and honesty (8–10, 12, 16).**
- Synthetic backtest history: the generator collects every closed bar instead of reading the chart ring. A regression test asks for more than 600 bars.
- Drift monitor: the backend also reports the prior's hit rate over the same window (always calling the prior's most likely class). The tile and the chart compare against that, and "chance 33 %" goes. Contracts regenerated.
- Trades:
  - Count what the per-tick cap drops (stats and `/metrics`).
  - Then send every fill, and let the hub's existing backpressure (oldest trade batches dropped first) protect slow clients.
  - Measured on the live feed before and after.
- The engine reads `cfg` instead of `settings`, and keeps a reference to each snapshot-request task until it finishes.
- Docs: the README's intro, tagline and visual-identity section; stale e2e names and comments.

**W3 — Test and CI reliability (6, 7, 11, 13–15).**
- The hang:
  - Reproduce it with the asyncio task-stack dump used in the audit, find the cause, fix it, and add a regression guard.
  - `faulthandler_timeout` (built into pytest) makes any future hang dump its stacks.
  - `timeout-minutes` on every CI job.
- e2e and `frontend-prod` run the standalone `server.js`, with the static and public assets copied as the Dockerfile does.
- Dependabot: minor and patch updates grouped, majors one PR each. Docker base images held at Python 3.11 and Node 22 until they are moved deliberately, with CI testing them.
- CI: current major versions of the actions; the runner pinned (`ubuntu-24.04`) instead of `ubuntu-latest`.
- Python: a constraints file of the full resolved set, used by Docker and Render (E5); `threadpoolctl` declared.
- `export_openapi.py` writes LF.
- With permission (E6): Linux visual baselines, and the migration chain against a real Postgres.

**W4 — Heatmap history and read-outs (20, 21).**
- The engine keeps the last 3 minutes of depth-profile columns at 1 Hz, whether or not anyone subscribes: 180 columns × 128 bins, plus each column's mid, band and traded quantity, about 0.1–0.2 MB as JSON.
- The client fills its heat ring from that once, with a REST read on mount, so the hero is complete on first paint. Backfilled columns are 1 s wide; live columns stay at 5 Hz.
- Layouts that fit the truncated read-outs.

**W5 — Does the model have an edge? (17–19).**
- Data:
  - Keep live bars long enough to answer the question: retention raised for the live database.
  - `scripts/export_bars.py` writes bars to gzipped NDJSON, so they outlive retention.
  - Target: at least 7 continuous days (E7).
- `scripts/ml_study.py`:
  - Rebuilds the served feature vectors from stored bars, with the same code.
  - Labels them for a grid of definitions: horizons of 5, 15, 30, 60 and 120 s; barrier floors of 0.5, 1, 2 and 4 bps; k ∈ {0.5, 1, 2}.
  - Ablations: without the hour-of-day features, and without the median-scaled quantities.
  - Runs the served recipe (`fit_model`) walk-forward on every configuration.
- Baselines:
  - the training prior;
  - the **trailing prior**: class shares over the last N resolved labels, known at prediction time;
  - the logistic baseline.
  - Every fold reports its edge, with dispersion.
- Selection is kept honest:
  - The grid is explored on the earlier ~75 % of the data, and the chosen configuration is scored **once** on the untouched last ~25 %.
  - Pre-registered rule: adopt it only if it beats both the class prior and the trailing prior in at least 3 of 4 folds and on the final holdout. As first approved, the rule tested the trailing prior alone; it was amended by E9 on 2026-10-07, before the deciding data existed.
- Outcome:
  - If adopted: new defaults, a feature-schema bump where features change, a retrain, and UI copy.
  - If not: the finding becomes "no edge at any tested horizon on N days", recorded here, and the UI keeps saying so.
  - Either way, the trailing-prior baseline ships on the Intelligence page and in the drift monitor.

### 11.3 Stages

Stage letters continue from Phase 4, skipping O (as I was skipped).

| Stage | Scope | Reviewable outcome |
|---|---|---|
| **N — Ship** | W1 | The production URLs serve 3.0.0 end to end, verified against the checklist. Needs E1–E3 and your push |
| **P — Correctness and honesty** | W2 | Each finding has a test that failed before the fix; the drift panel compares with the prior's hit rate; trade drops measured on the live feed |
| **Q — Reliability** | W3 | The hang root-caused, or bounded and documented; e2e green on the standalone server; CI pinned; Dependabot regrouped |
| **R — Heatmap history** | W4 | The hero complete on first paint (real-GPU captures, before and after); no truncated read-outs at 1440 and 390 px; axe clean |
| **S — Edge study** | W5 | A study report: the grid, the holdout result, and the decision made by the pre-registered rule |

**Proposed order: N → P → Q → R → S.**
- Data collection for S starts now: it needs days of continuous feed and costs nothing to start.
- N goes first because production still runs the pre-rebuild app.
- P comes before Q because its fixes are small and user-visible.
- S comes last because it waits for the data.

### 11.4 Decisions needed

| # | Question | Recommendation |
|---|---|---|
| E1 | Backend hosting | **(b)** An always-on Render instance with a 1 GB persistent disk, SQLite on the disk: the simplest durable setup, with no Postgres expiry. A disk means a short restart on each deploy.<br>• 1 CPU / 2 GB ($25/month) for training headroom.<br>• 0.5 CPU / 512 MB ($7/month) also works, with slower training and about 90 MB of headroom.<br>Alternatives: **(a)** free tier with Postgres, which sleeps and loses models; **(c)** paid instance with paid Postgres, which also works, with W1's artefact-in-database change |
| E2 | Production frontend origin | `https://algorithmic-viz.vercel.app`, plus a custom domain if there is one. Drop the other two defaults |
| E3 | The Render service | Recreate it from `render.yaml` as a Blueprint, so the repo is the source of truth. The hand-made service keeps its old settings |
| E4 | Open Dependabot PRs | Close #9, #2 and #4. Fold the action bumps (#1, #3, #5–#7) into Stage Q's CI change, after which those PRs close too |
| E5 | Python lock | A `constraints.txt` generated with pip itself from a clean install, so no new tool. Hashes would need pip-tools, a new dev dependency |
| E6 | Docker image pulls | `mcr.microsoft.com/playwright` (~2 GB) for the Linux baselines, and `postgres` (~150 MB) for one real migration run, the latter only if E1 keeps Postgres. Both in Stage Q |
| E7 | Data for the edge study | Run the live backend continuously for at least 7 days, on the E1 host or this machine, with live-bar retention raised to 60 days |
| E8 | Stage order | N → P → Q → R → S |
| E9 | The edge rule's baseline (raised in Stage S, 2026-10-03; **approved 2026-10-07**) | Require the edge over **both** priors, the class prior and the trailing prior, in at least 3 folds and on the holdout, and select on the same. As approved, the rule tests only the trailing prior, which at long horizons was the weaker of the two (§11.5, Stage S) |

### 11.5 Delivery log

**Stage N — ship: the repository side (2026-10-01).** The owner approved every recommendation in §11.4, and Stage M. W1's repository side is built and verified locally. Going live needs the cutover at the end of this entry, which only the owner can do.

- **Hosting (E1, E3).** `render.yaml` is now a Blueprint for an always-on `algoviz-backend`:
  - `plan: 1c-2g` (1 CPU / 2 GB), in Singapore.
  - A 5 GB disk at `/var/data` holds SQLite (`sqlite+aiosqlite:////var/data/algoviz.db`) and the model store (`/var/data/ml_models`). Render snapshots the disk daily.
  - Bars are kept for 60 days (E7). Measured at 495 B per bar, that is about 43 MB a day and 2.6 GB over 60 days. That is why the disk is 5 GB rather than the 1 GB first proposed: about $1 a month more. A disk can grow but never shrink.
  - `ML_TRAIN_THREADS=1`, because `os.cpu_count()` reports the host's cores, not the instance's one CPU.
  - `CORS_ORIGINS` is set explicitly, to the production frontend only.
- **Training yields the CPU.**
  - Spawned training runs and HMM fits now run at POSIX nice +10 (`core/workers.py`). On one CPU, a fit at equal priority would take half the core from the loop that carries the feed.
  - A test checks the child's niceness on Linux. It is skipped on Windows, which has no `nice()`.
- **CORS defaults (E2).** Localhost plus `https://algorithmic-viz.vercel.app`. The two third-party origins are gone.
- **Vercel.**
  - `frontend/vercel.json` pins the framework (`nextjs`), `npm ci`, `npm run build` and output `.next`, whatever the dashboard still holds from the Vite project.
  - `next.config.ts` fails a production build (`VERCEL_ENV=production`) unless `NEXT_PUBLIC_API_URL` starts with `https://` and `NEXT_PUBLIC_WS_URL` with `wss://`. Without them the build would ship a site that talks to localhost.
  - Checked four ways:
    - no URLs → the build fails;
    - an `http://` API URL → it fails;
    - `https` and `wss` URLs → it builds, with the URL inlined;
    - a preview build → unaffected.
- **Docs.** The README's deployment section; ADR-7, now "SQLite on a persistent disk; Postgres optional"; `.env.example`; the production setup in CLAUDE.md.
- **`scripts/smoke_deploy.py`** checks a running deployment from the outside:
  - the deployed version is this checkout's, and `/health/ready` returns 200;
  - changes are gated: refused without a token and, with `--with-token` and `$ADMIN_TOKEN`, accepted and deleted again;
  - CORS and the WebSocket admit the frontend origin and refuse a foreign one.
  - Against the production configuration it passed 8 of 8 anonymously and 10 of 10 with the token.
- **Not built.** Storing model artefacts on the registry rows was needed only with Postgres, and E1 chose a disk.
- **Checks:**
  - Backend: ruff, ruff format and mypy clean (mypy for both the Windows and the Linux target). pytest: 152 passed and 1 skipped (the POSIX test), coverage 92.31 %. pip-audit clean. OpenAPI unchanged.
  - Frontend: prettier, tsc, eslint, Vitest 27 and the build pass. npm audit is clean under npm 9 and npm 10.
  - Playwright: 39 of 39.
  - **Production-configuration smoke test, 11 of 11.** It ran the Blueprint's environment on this machine, with a scratch folder standing in for `/var/data` and a throwaway admin token:
    - a fresh database migrated on the "disk", JSON logs, and `/health/ready` returning 200;
    - anonymous access reports that writes are gated; a change is refused without the token (401, problem+json) and accepted with it;
    - the CORS preflight and the WebSocket are accepted from `algorithmic-viz.vercel.app` and refused from a third-party origin (400 and 403);
    - after a restart, the charts resumed from the bars on the disk and the stored model was served without retraining.
- **Cutover, by the owner, in this order:**
  1. Approve the commit and the push of this stage to `main`. Nothing live changes yet:
     - The old Render service fails to deploy it, as it failed before, and keeps serving 2.0.0.
     - Vercel's production build fails on the new guard until step 3.
  2. Render: New → Blueprint → this repo. That creates `algoviz-backend` from `render.yaml`, which needs a payment method for the paid instance and disk. Note its URL once `/health/ready` returns 200.
  3. Vercel, project `algo-viz` → Settings → Environment Variables, Production:
     - set `NEXT_PUBLIC_API_URL=https://<url>` and `NEXT_PUBLIC_WS_URL=wss://<url>/ws`;
     - confirm the Root Directory is `frontend`;
     - then redeploy the latest production deployment.
  4. I run `scripts/smoke_deploy.py` against the production backend, plus a real-GPU pass on the live site.
  5. The owner pastes the Blueprint's `ADMIN_TOKEN` into Settings → Access and makes one change, or runs the script with `--with-token`. The token never passes through me.
  6. Retire the hand-made service (`algoviz-52q2`).
  7. Close Dependabot PRs #9, #2 and #4 (E4).
- **Pushed** as `ef448e3` (2026-10-01). Vercel's production build failed, as expected before step 3. CI #11 then exposed the hang below.

**Stage N follow-up — the intermittent test hang, root-caused (2026-10-02).** CI #11 on `ef448e3` ran the backend pytest for more than two hours; a normal run takes 3 minutes. It was the same hang seen once in the 2026-10-01 audit, before Stage N existed.
- **Captured locally.** Looping the full suite with an asyncio task-stack dump caught it in the second run:
  - The test was at `await engine.stop()`, waiting on the intelligence task.
  - That task was marked "cancelling", yet it had gone back to `await self._intel_wake.wait()` and was waiting for work forever.
- **Cause.** On Python 3.11, `asyncio.wait_for` returns the inner result when a cancellation races with the inner awaitable completing (gh-86296; fixed in 3.12).
  - `MLEngine.predict` wrapped the inference thread in `wait_for`. A `stop()` that landed just as a prediction finished was swallowed, and `stop()` then awaited the loop forever.
  - The same race can hang a production shutdown, such as a deploy restart.
  - `ws/hub.py` had already been fixed for this; `predict` and `run_isolated` had not. In `run_isolated`, the race would let a cancelled fit be installed.
- **Fix.** `async with asyncio.timeout(...)` in `predict` and `run_isolated`.
- **Test.** It cancels a prediction at each of the first six loop turns after the inference thread answers, and requires every cancel that lands to stick. It failed on the old code ("DID NOT RAISE CancelledError") and passes now.
- **CI.** Every job has `timeout-minutes` (backend 20, frontend 15, e2e 45, images 30), so a hang fails in minutes instead of running for GitHub's six hours.
- **Checks.** Eight consecutive full runs with coverage were clean (153 passed, 1 skipped, about 2.3 min each, coverage 92 %); the same suite hung in 2 of 6 runs before the fix. ruff, ruff format and mypy (Windows and Linux targets) clean.
- **Vercel** (the owner deploys it).
  - A local `vercel build` (CLI 62.1) with this repo's `vercel.json` runs `npm ci` and the full `next build`. Locally it then stops on a Windows-only symlink permission (EPERM), which Vercel's Linux builders don't hit.
  - Vercel builds with Node 24.x, because `engines: ">=20.9.0"` overrides the project's Node setting.
  - A production build fails until both `NEXT_PUBLIC_*` URLs are set, by design.
- **Render.** `algoviz-backend.onrender.com` belongs to another account, so the Blueprint's service will get a suffixed URL. The script examples now say `<backend>`.

**Stage P — correctness and honesty (2026-10-02).** W2, with a test for each finding that fails on the old code and passes now.

- **Synthetic backtest history (finding 8).**
  - The generator now collects every closed bar through a `BarCollector` sink, instead of reading the engine's 600-bar chart ring.
  - `BarSink`, a protocol in `market/persistence.py`, types the engine's writer. Only a real `BarWriter` turns on prediction persistence.
  - `scripts/seed_e2e.py` uses the same collector instead of its own copy. The template is unchanged.
  - Test: a request for 700 bars returns 700 contiguous bars. The old generator returned 600.
- **Drift monitor (finding 9).**
  - The summary now reports `prior_hit_rate`: the hit rate of always calling the prior's most likely class over the same window.
  - The hit-rate tile and the rolling chart compare against it; "chance 33 %" is gone.
  - The model card's drift line shows edge vs the prior instead of a bare hit rate.
  - Contracts regenerated (one field).
  - Test: a model that always calls "flat" scores exactly the prior's hit rate.
  - Live, v40: hit rate 54.9 %, prior's own calls 54.9 %, edge −0.215. The old panel showed that as "54.9 % vs chance 33 %".
- **Trade frames (finding 10).**
  - Measured first: over 5 minutes of live BTCUSDT, replaying the engine's 100 ms batching, the per-tick cap of 100 would have dropped 5,365 of 23,788 fills (22.6 %). The busiest tick had 492 fills, and 71 ticks went over 100.
  - Now every fill is sent. The hub already bounds a slow client by dropping whole trade frames, oldest first.
  - Test: a 500-fill burst arrives whole. Under the old cap only fills 400–499 arrived.
  - Live, 3 minutes: the engine counted 32,666 fills and a WebSocket client received 32,666, with no gaps in the trade ids. The largest frame held 802 fills.
- **Engine (finding 16).** `book_payload` and `_adaptive_band` read the engine's own `cfg`. Snapshot-request tasks are held until they finish, and `stop()` cancels them.
- **Docs (finding 12).** The README's tagline and frontend paragraph now describe the heatmap hero, the opt-in terrain and midnight glass. The visual-identity section is retitled. A stale e2e test name and comment are fixed.
- **Checks:**
  - Backend: ruff, ruff format and mypy clean. pytest: 156 passed and 1 skipped, coverage 92.45 %. pip-audit clean. OpenAPI regenerated and fresh.
  - Frontend: prettier, tsc, eslint, Vitest 27 and the build pass; npm audit clean.
  - Playwright: 39 of 39, visual baselines unchanged.
  - Real-GPU captures of the drift panel and the model card on the live feed, with no console errors.
- **Left for Stage R:**
  - The model card's drift line still truncates at 1440 px ("n 1…").
  - The "Resolved 156 / 40" tile reads as a fraction, but it is the window count against the minimum.
- **Pushed** as `bea471a` (the hang fix) and `6fe1575` (Stage P) on 2026-10-02. CI #14 was green in all four jobs; the backend ran in 3 minutes on Linux with no hang. Vercel failed, as expected until its environment variables are set.

**Stage Q — reliability (2026-10-02).** W3. The hang it was meant to chase was already root-caused and fixed in the Stage N follow-up; what remains makes CI, the builds and the hosts agree.

- **A hang explains itself.**
  - `tests/conftest.py` puts a guard on every async test. A test still running after 300 s gets every asyncio task's stack attached to its report, and is then cancelled, so the hang becomes a failure that shows the await that never returned.
  - `faulthandler_timeout = 600` covers synchronous hangs with thread stacks.
  - Checked with a throwaway test that awaited forever under a 2 s limit: it failed with "still running after 2 s" and both task stacks in the report.
- **e2e runs what Docker ships.**
  - `npm start` is now `scripts/start-standalone.mjs`: the standalone `server.js`, with `.next/static` and `public` copied beside it as the Dockerfile does.
  - It binds to `0.0.0.0` like the image. Linux shells export `HOSTNAME` as the machine's name, which the server would otherwise bind to.
  - Playwright and `frontend-prod` use it, and the "next start does not work with output: standalone" warning is gone.
  - Verified: the page, chunks, CSS, `public/` and security headers are served; Playwright's web-server output shows `node scripts/start-standalone.mjs -p 3100`; e2e 39 of 39.
- **CI.**
  - Every action is on its current major: checkout, setup-python and setup-node v7, upload-artifact v7, setup-buildx v4, build-push v7. That ends the Node 20 deprecation warnings. Dependabot's own CI had already validated all but setup-python, which it never proposed because of its default five-PR limit.
  - The runner is pinned to `ubuntu-24.04` instead of `ubuntu-latest`, which moves to Ubuntu 26 on 2026-10-19.
- **Dependabot.**
  - Minor and patch bumps are grouped per ecosystem; each major version gets a PR of its own.
  - The Docker base images are held at Python 3.11 and Node 22, because CI builds those images but tests on its own runtime.
- **One set of Python versions everywhere (E5).**
  - `backend/constraints.txt` pins the 31 transitive runtime packages (numba, llvmlite, pandas, starlette, …). It is generated from a clean virtual environment by `scripts/freeze_constraints.py`; a `just constraints` recipe runs it.
  - Direct dependencies stay in `requirements.txt` only, so a Dependabot bump needs no second edit.
  - Render, the Docker image and CI install with `-c constraints.txt`, and pip-audit now covers the transitive set too: clean.
  - The dev virtual environment was 7 packages behind the pins (numba 0.67 → 0.68, starlette 1.6 → 1.7, …). It was aligned, and every gate re-ran on the pinned set.
  - Limit: generated on Windows, so `uvloop` (Linux-only) is left to the resolver.
- **Node 22 everywhere.** `engines` is now `22.x`, matching CI and the Docker image. With `>=20.9.0`, Vercel had chosen Node 24.x.
- **Hygiene.**
  - `threadpoolctl` is declared; it is imported directly.
  - `export_openapi.py` writes LF, so a regeneration no longer shows a diff on Windows.
  - The Vitest config is native ESM (`vitest.config.mts`, using `import.meta.dirname`), which ends Vite's CommonJS warning.
- **Not done: Linux visual baselines (E6).**
  - Docker Desktop was started, but its engine never came up: after more than 5 minutes it still reported 0 CPUs, and `wsl -l -v` hung. That points to a dialog waiting for the owner in the Docker Desktop window.
  - The baselines and the CI change that needs them land together: the e2e job running in `mcr.microsoft.com/playwright:v1.63.0-noble` (the tag exists; Ubuntu 24.04, as the runner), and the visual spec enabled on Linux. Enabling the spec without the baselines would fail CI.
- **Checks:**
  - Backend: ruff, ruff format and mypy clean. pytest: 156 passed and 1 skipped, coverage 92.45 %. pip-audit (direct and transitive) clean. OpenAPI fresh.
  - Frontend: prettier, tsc, eslint, Vitest 27 and the build pass; npm audit clean.
  - Playwright: 39 of 39 on the standalone server.
- **Pushed** as `91af87b` (2026-10-02). CI #16 was green in all four jobs: the new action versions, the constrained installs and image builds, and the Linux e2e on the standalone launcher.

**Stage R — heatmap history and read-outs (2026-10-02).** W4.

- **The hero is whole on first paint.**
  - The engine records one heatmap column a second, whether or not anyone is subscribed: the adaptive depth profile, the mid, the band, and the buy and sell prints of that second (accumulated in O(1) per fill).
  - It keeps 180 of them, the client's three-minute window.
  - **Deviation from §11.2:** the history travels in the WebSocket snapshot, not a REST read on mount. The client clears its heat ring on every snapshot (connect, reconnect, symbol switch), so the snapshot is the one point where a refill can't race the live frames or miss a reconnect.
  - Measured on live BTC: the snapshot is 276 KB uncompressed (216 KB of it is 180 columns spanning 180 s, before the WebSocket's per-message deflate) and arrives 80 ms after connect.
  - The client writes each history second as five columns (columns are placed by index at the live 5 Hz), with that second's prints in the middle one and real 200 ms timestamps, then the live column.
  - A snapshot without `heat`, from a backend deployed earlier, still hydrates: the map then fills in live, as before. Vercel and Render deploy separately, so this ordering can happen.
- **Read-outs.**
  - Panel subtitles wrap below 640 px instead of cutting off mid-sentence; wider screens keep the single-line ellipsis, and nothing truncated there.
  - Tile hints and the feature names in the SHAP and importance lists wrap.
  - The model card's drift row wraps its text under the sparkline on narrow cards and drops the trailing "n".
  - "Trade velocity" becomes "Velocity" (the unit says trades/s).
  - The drift panel's subtitle names the real window ("the latest N resolved", up to 300). It used to say "rolling window of 40", which is the minimum. "Resolved" shows the window count, with the all-time total as its hint.
- **Checks:**
  - Backend: ruff, ruff format and mypy clean. pytest: 157 passed and 1 skipped, coverage 92.49 %. pip-audit clean. OpenAPI regenerated and fresh (`HeatColumn`, `SnapshotPayload.heat`).
    - New test: a synced book and three prints make a column that the snapshot carries; the snapshot validates against its schema; the window is bounded at 180; each column holds only its own second's prints.
  - Frontend: prettier, tsc, eslint, Vitest 27 → 29 (backfill expansion and placement; hydration from an older backend), build, npm audit.
  - Playwright: 37 of 39, then the two intended mobile baseline changes (overview and intelligence, where subtitles now wrap) re-recorded. Compared side by side, the subtitles are the only difference. The visual spec then passed 24 of 24 with `--repeat-each=2`. axe was clean on every route.
  - Real GPU, live feed:
    - 3 s after loading `/`, the hero shows the full three minutes, and the "history fills in" note is gone. The audit's capture showed about 10 % of the map 12 s after load.
    - A truncation scan of every route at 1440 and 390 px finds no text cut by an ellipsis. Before, it found the drift hint and long feature names on desktop, and panel subtitles, the model card's drift line and a WalkForward hint on mobile.
    - No console errors.

**Stage S — the edge study (2026-10-03).** W5. The study is built, tested and run end to end. Its verdict is preliminary: the live database holds 1.8 h of bars, and the rule needs 7 days (E7). The run also found a calibration defect in the served recipe, now fixed, and a weakness in the approved rule (E9).

- **Data.**
  - `scripts/export_bars.py` writes a source's persisted bars to gzipped NDJSON in `data/exports/` (gitignored), one file per run, named by symbol, source and span. The helpers are `write_bar_export` and `read_bar_exports` in `market/persistence.py`.
  - The study reads every export plus the database and keeps one bar per open time, so overlapping exports are harmless.
  - Exported 2026-10-02: 6,562 live bars (6 sessions, 2026-09-26 13:17 to 2026-10-02 17:16 UTC) and 16,278 synthetic. The local database keeps bars for 7 days, so the oldest live session would have been pruned on 2026-10-03.
- **The study** (`algoviz/ml/study.py`, run by `scripts/ml_study.py`; `just study` exports first).
  - **Samples are the engine's own.** The bars go through `MLEngine.ingest_bar`, so feature vectors, rolling medians and session splits are as served. Each label definition relabels them with the served `barrier_bps` and `triple_barrier`, never across a session gap. A test checks that the served definition reproduces the engine's labels exactly, and that a 60 s horizon drops each session's last minute.
  - **The grid.** Horizons 5, 15, 30, 60 and 120 s; k 0.5, 1 and 2; floors 0.5, 1, 2 and 4 bps: 60 label definitions. The three best are re-run without the hour-of-day features and without the median-scaled quantities.
  - **Scoring.** Each configuration gets the served recipe's walk-forward on the first 75 % of its labelled samples, with training windows capped at `ML_MAX_SAMPLES`. It is scored against the class prior, the trailing prior and the logistic baseline.
  - **The holdout.** The best configuration, by mean edge over the trailing prior, is scored once on the last 25 %. It is trained on the end of the development part, with an embargo of one horizon.
  - **The rule.** `decide()` implements the rule as approved. Below 7 days of bars (counted as bars, not calendar span) it reports "preliminary" and decides nothing.
    - A test plants an edge and checks that it is adopted on 8 days of bars but not on 1.
    - The same test checks that shuffled labels are rejected.
  - **The report** is Markdown with the data's span, the rule, the verdict, the holdout and every configuration: `docs/edge-study.md`. The full grid takes 3–4 minutes on today's bars, and two runs produced byte-identical tables.
- **The trailing prior.**
  - **Definition.** For each prediction, the class mix of the last 600 labels already resolved at that point (index ≤ i − horizon), Laplace-smoothed.
  - **Walk-forward.** Every fold scores it (`FoldMetrics.trailing_prior_log_loss`; older artefacts load without it), and the out-of-sample summary adds `edge_vs_trailing_prior`.
  - **Drift monitor.** The same baseline from live outcomes, lagged by the horizon, so it uses only outcomes resolved before each prediction. Its status reads "edge" only when both edges are positive. Tests check that neither version sees a label unresolved at prediction time.
  - **Primed at startup** with the labels rebuilt from stored bars, all resolved before the first live prediction.
    - Found on the live feed: after a restart the monitor knew no outcomes, so the first predictions were scored against a uniform trailing prior. Log-loss was 0.283 against 0.191 for the class prior, on 43 outcomes that were all flat, which flattered the edge.
    - Primed, the prior starts from what was known. After this restart that was a mix half from yesterday's livelier session (30 % non-flat), so it lags a quiet market, as a trailing prior should.
  - **UI.**
    - The walk-forward panel draws the trailing prior on each fold's dot plot and adds a Trailing column. Its sentence counts the folds that beat the trailing prior.
    - The edge badge is amber unless both edges are positive.
    - The drift panel's edge tile shows the edge over the trailing prior.
    - Models trained before Stage S render as before.
- **Found by the study: calibration could serve certainty in a rare class (fixed).**
  - **Symptom.** In the first full run, 9 configurations scored an edge of about −9 nats. In one fold of 5 s · k 1 · floor 2 bps, the raw model scored 0.10 nats and the calibrated model 36: it said p(down) = 1 on every row.
  - **Cause** (scikit-learn 1.9.1, `CalibratedClassifierCV`).
    - The window held all three classes, but the fit rows of every calibration split lacked "up".
    - A two-class split model returns a single probability column, p(flat). scikit-learn fits that column's calibrator against the first class's indicator (down), and fills only that column.
    - Normalising then turned the down column into certainty.
  - **Fix.** `TailStoppedHGB(classes=…)` answers for every class in the window, with probability 0 for a class its fit rows lacked. Each class then gets its own calibrator, and an unseen class calibrates to its base rate.
    - A regression test rebuilds the case and fails on the old code: mean p(flat) was 0 against a 95.7 % share.
    - Models pickled before the change still load, predict and print (checked on live v40).
  - **Reach.** At the served label (5 s, about 7 % per side) every split sees every class, so the served model was not affected in practice. The defect bit label definitions with a rare class.
  - **Recorded, not changed.** Isotonic calibration still fits exact zeros where a class has only a handful of examples. In one fold at 5 s · floor 2 bps, 10 of 926 rows got p = 0 for their class. This is how isotonic calibration behaves, not a mapping error. Definitions where a class is about 1 % pay for it in this study.
- **Preliminary result: 1.8 h of live bars, which decides nothing** (`docs/edge-study.md`).

  | Label | Features | Edge vs class prior | Edge vs trailing prior | Folds beating it |
  |---|---|--:|--:|--:|
  | 120 s · k 2 · floor 2 bps | without scaled quantities | −0.016 | +0.163 ± 0.237 | 3 of 4 |
  | 120 s · k 2 · floor 0.5 bps | all features | +0.022 | +0.041 ± 0.236 | 2 of 4 |
  | 5 s · k 1 · floor 1 bps | all features | +0.004 | +0.001 ± 0.018 | 2 of 4 |
  | 5 s · k 1 · floor 0.5 bps (served) | all features | −0.040 | −0.055 ± 0.053 | 0 of 4 |

  - **The holdout** for the best (1,252 samples): log-loss 0.7365, against 0.8078 for the trailing prior and 0.6916 for the class prior. It beats the trailing prior and loses to the class prior.
  - **The served definition** has no edge over either prior, in line with the standing finding.
  - **Fold dispersion** (±0.2 nats at 60–120 s) exceeds every mean edge. 1.8 h of bars can't separate these configurations.
  - **Fewer distinct labelings than definitions.** Where the floor exceeds k · σ · √h, k changes nothing; for example, the three k at 5 s · floor 4 bps are identical.
  - **Calibration fallbacks.** 24 calibrations fell back to the uncalibrated model, because a class had fewer than 3 examples in the window. These are the served recipe's own fallbacks, logged as warnings.
- **Decision needed (E9, §11.4): the rule's baseline.**
  - At 60–120 s the trailing prior was a weaker baseline than the class prior: 0.81 against 0.69 on the holdout. A window of labels resolved two minutes earlier tracks noise.
  - As approved, the rule tests only the trailing prior. It would therefore adopt this preliminary best, which loses to the class prior.
  - **Recommendation:** require the edge over both priors, and select on the same. The drift monitor and the walk-forward badge already require both.
  - Changing the rule now, before the deciding data exists, still pre-registers it for that data. But this run informed the change, so it is the owner's call. The code implements the rule as approved until then.
- **Still needed (E7):** at least 7 days of live bars, from the Render Blueprint after the cutover or from `backend-live` on this machine. Then `just study` (or the two scripts) produces the deciding report.
  - **Collection started on this machine on 2026-10-03.** The `backend-live` launch configuration (machine-local, `D:\My_Work\Projects\AlgoViz\.claude\launch.json`) now sets production's `SNAPSHOT_RETENTION_DAYS=60` and `ML_TRAIN_THREADS=1`, so its database keeps every session until the study runs.
  - The study counts bars, not calendar days, so intermittent sessions add up: about 86,400 bars a day while it runs.
  - Run one live backend at a time. A second would share the database and model directory, and their model versions would collide.
- **e2e seed.** `SEED_VERSION` 2: the template is rebuilt only when its stamp changes, and the model manifest doesn't cover what training records. Without the bump, local e2e would keep serving a model without trailing-prior folds, while CI builds a fresh one.
- **Checks:**
  - **Backend.**
    - ruff, ruff format and mypy are clean.
    - pytest: 165 passed and 1 skipped, coverage 92.86 % (`study.py` 95 %). The run took 6.5 min with both dev servers running alongside, against the CI job's 20-minute limit.
    - After the priming fix: 166 passed and 1 skipped, coverage 92.67 %, in 4.7 min with the live collector running.
  - **Live feed, 2026-10-03.** v41 is the first live model trained with this stage's code: 8,144 samples, isotonic calibration.
    - Held out, its log-loss is 0.464, against 0.440 for the class prior and 0.412 for the trailing prior. That is an edge of −0.024 and −0.052: still no edge.
    - At the served 5 s horizon the trailing prior is the stronger baseline, the reverse of 120 s in the study. Requiring both (E9) means requiring the stronger one at each horizon.
    - The Intelligence page on the production build shows the amber badge, the Trailing column and "…the trailing prior in 1 (mean edge −0.052)".
    - pip-audit is clean. OpenAPI is fresh: the only additions over `main` are Stage R's heat columns and the two trailing-prior fields.
    - New tests:
      - the trailing prior sees only resolved labels, both in folds and in the drift monitor;
      - the drift monitor's trailing prior starts from the labels rebuilt at startup;
      - older artefacts load;
      - the rule adopts a planted edge and nothing less;
      - the study labels exactly as the engine does;
      - the study scores, ablates and renders without deciding;
      - exports round-trip and overlap without duplicates;
      - calibration survives a class missing from its split models.
  - **Frontend.** Prettier, tsc, eslint, Vitest 29, the build and npm@10 audit all pass.
  - **Playwright.**
    - First run: 38 of 39. The strategies spec timed out on its last step, because the DELETE got no response within 15.7 s. Every request in that test was slow (4–6 s), so the e2e backend was starved, most likely by its scheduled retrain about 10 minutes into the run alongside SwiftShader.
    - Second run, on the rebuilt seed: 39 of 39.
    - The visual baselines are unchanged. That spec leaves REST unanswered, so it pins panel anatomy, not model data.
  - **Browser, synthetic backend.**
    - A model trained before Stage S renders as before: no Trailing column, and the sentence is unchanged.
    - After the engine retrained (v29), the dot plot shows the trailing-prior marker beside the class-prior ring. The Trailing column, the legend entry and the fold labels are present, and the sentence reads "…the trailing prior in 4 (mean edge +0.202)…".
    - The drift tile reads "vs trailing prior +0.437 · at training +0.135".
    - At 390 px the document is 390 wide, and the longer hint wraps without truncating.

**Pre-push audit (2026-10-07).** Before pushing R and S, the audits were re-run: four days had passed since Stage S was gated.

- **pip-audit:** clean.
- **npm audit:** 7 new high advisories.
  - `sharp` 0.35.4 (through `next`, ships in the image) → 0.35.5, whose libvips 1.3.4 carries the librsvg fix.
  - `source-map-js` 1.2.1 (postcss, Tailwind, jsdom) → 1.2.2.
  - Both are lockfile-only updates from `npm audit fix`. The lockfile diff is exactly those packages and sharp's platform binaries.
- **braces ≤ 3.0.3** has no patched release. It is reached only through `eslint-config-next` → fast-glob → micromatch, at lint time, on the repo's own patterns. npm's only offer is downgrading eslint-config-next to 14.
- **The owner's decision:** CI blocks on `npm audit --omit=dev --audit-level=high` (what ships, clean) and runs the full audit as a reported, non-blocking step. Make it blocking again once braces is patched.

**Dependabot PR #12 (2026-10-07).** The grouped Python update (SQLAlchemy 2.0.54 → 2.1.1, uvicorn 0.53 → 0.54, PyJWT 2.15.1, …) failed CI at install.

- **Cause.** Dependabot treats `constraints.txt` as a requirements file. It bumped `pydantic_core` to 2.49.0 on its own, while pydantic 2.13.5 pins `pydantic-core==2.46.5` exactly. This is a gap in Stage Q's constraints design (E5).
- **Fix** (pushed 2026-10-07).
  - `scripts/freeze_constraints.py` leaves out packages a direct dependency already pins exactly (`DETERMINED`, today only `pydantic-core`).
  - The line is removed from `constraints.txt` by hand. Re-running the generator would also move every other transitive pin.
  - Dry-run resolution: `main` still installs `pydantic_core` 2.46.5 through pydantic, and PR #12's other bumps resolve against the fixed constraints. pip-audit is clean.
- **After the push** (`7fff831`, CI #20 green), Dependabot closed #12 and opened #13 without the core bump. #13 has 9 updates: SQLAlchemy 2.1.3, FastAPI 0.142.2, uvicorn 0.54.0, websockets 17.2, PyJWT 2.15.1, and others.
  - CI #21 on #13 was all green, e2e included. SQLAlchemy 2.1 is a minor release with behaviour changes, so that run is the check.
  - Merging it waits on the owner's word.

**E7 collection and E9 (2026-10-07).** The owner chose a Windows startup task for collection and approved E9.

- **Why a task.** Collectors started as preview servers stopped with their Claude session. The 2026-10-03 one ran a few hours, so by 2026-10-07 there were 0.12 days of bars.
- **The collector.** `scripts/collect_live.py` is the live backend with production's collection settings: bars kept 60 days, training on one thread, bound to 127.0.0.1:8001.
  - Under `pythonw` (no console) it sends its output to `data/logs/collector.log`, rotated at 20 MB. Spawned training processes re-import the file and write there too.
  - It exits if the port is in use: uvicorn starts the app before it binds, so a second instance would otherwise write beside the first for a moment.
- **The task.** "AlgoViz live collector" runs as the owner's user (not elevated). It starts at logon, plus a repeating trigger every 5 minutes with `MultipleInstances IgnoreNew`, no time limit, and it runs on battery.
  - Task Scheduler's "restart on failure" did not bring back a killed process (still down after 222 s). The repeating trigger did: back in 59 s. A crash now costs at most 5 minutes of bars.
  - It is the live database's only writer. The machine-local `backend-live` preview configuration is replaced by `frontend-live`, the dev frontend pointed at :8001. Checked: REST and the WebSocket reach the collector, and the source is live.
- **E9.** The rule and the selection now use the edge over the **better** of the two priors, fold by fold and on the holdout. The report adds a column for it, and "Folds beating both".
  - A test builds a configuration that beats the trailing prior but loses to the class prior. The amended rule rejects it; the old one counted 4 of 4 beating folds and would have adopted it.
- **Preliminary re-run** (`docs/edge-study.md`): 15,824 bars, 0.18 days, 12 sessions.
  - The development best, 120 s · k 2 · floor 0.5 bps, beat both priors in **4 of 4** folds (+0.048 ± 0.035 nats over the better prior).
  - On the holdout, the newest quarter and mostly a quiet day, its log-loss was 1.378, against 0.840 for the class prior: worse by 0.54 nats. With 7 days of bars the rule would reject it, at the holdout.
  - This is the regime drift §11.1 expected, and why the holdout is scored once and kept out of selection.

## 12. Phase 6 — Make the edge question answerable, and visible (proposed)

> **Status:** proposed 2026-10-08, after the owner chose this direction over housekeeping only or a pause. Approved the same day ("continue") with the recommended decisions F1–F6. Stage T was pushed on 2026-10-08, and the protocol is frozen (14:55 UTC). Stage V is pushed, and Dependabot #11 and #13 are merged. Stage U was pushed on 2026-10-08. Only Stage X, gated on data, remains. Stages keep §7's review-stop discipline.
> **Inputs:**
> - the Stage S study runs of 2026-10-03 and 2026-10-07 (`docs/edge-study.md`);
> - the live collector's first hours: 18,310 bars (0.21 days) on 2026-10-07, one bar a second while it runs;
> - a timing of the served recipe on live data: one fit on 19,683 samples takes 1.6 s on 8 threads (3.4 s on one), and predicting 600 rows about 20 ms;
> - Dependabot PRs #11 and #13 and their CI runs.

### 12.1 Why

| # | Finding | Evidence |
|---|---|---|
| 1 | At study scale the walk-forward stops being "evaluated as served". Stage S trains one model per fold and scores it on the whole next fold. On 7 days of bars a fold is about 1.75 days, scored by a model the engine would have replaced about 250 times: it refits every 600 samples (10 min) | `train.walk_forward`: `TimeSeriesSplit(n_splits=4)`. `ML_RETRAIN_EVERY_SAMPLES = 600` |
| 2 | Regime drift is the live failure mode, and the study tests only one way of training: the served 20,000-sample window. Nothing tests whether a shorter or recency-weighted window survives drift better | 2026-10-07 run: the development best (120 s · k 2 · floor 0.5 bps) beat both priors in 4 of 4 folds (+0.048 nats), then lost to the class prior by 0.54 nats on the holdout, the newest quarter and mostly a quiet day |
| 3 | The grid, the rule (E9) and any new variants were shaped by bars already examined. If those bars also decide, the decision is circular | The preliminary runs on 2026-10-03 (0.08 days) and 2026-10-07 (0.18 days) |
| 4 | The study and its verdict live only in `docs/edge-study.md`. The product shows the served model's metrics, but not whether any tested label definition has an edge, or how close the data is to deciding | No endpoint or panel reads the study |
| 5 | Collection runs headless, and its progress and health are invisible. A stall shows only in `data/logs/collector.log` | Settings → Engine shows the feed, the WebSocket and the loop. `count_bars` exists, but nothing calls it |
| 6 | Dependabot #11 (npm group: React 19.3, three 0.186.1, …) was tested against a base that predates Stages R and S and the lockfile security update. #13 (Python group, SQLAlchemy 2.1.3) is green | CI #17 on #11 (2026-10-02); CI #21 on #13 (2026-10-07). Both branches merge cleanly into `main` |

### 12.2 Workstreams

**W1 — Evaluate as served, at study scale (findings 1, 2).**
- **Rolling refits.** For an evaluation block of 600 samples (the served retrain cadence), fit the served recipe on the configuration's training window, which ends one horizon before the block starts (the embargo). Then predict the block. Score it against the class prior of that window and against the trailing prior.
- **Development:** 32 blocks, 8 evenly spaced in each quarter of the development period. A quarter's edge pools its 8 blocks, so the rule's "3 of 4 folds" becomes "3 of 4 quarters".
- **Holdout:** every block of the last 25 %, after the embargo, for the selected configuration only.
- **Cost on 7 days** (about 600,000 samples):
  - 75 configurations × 32 development blocks, plus about 250 holdout blocks, comes to about 2,650 fits: roughly 70 min serially at 1.6 s each.
  - Configurations can run in parallel processes, one thread each.
  - Building the samples takes about 3–4 min (21,000 bars took 6.9 s).
- **Tests:**
  - no training row reaches a block (embargo included);
  - one refit per block;
  - a planted edge is adopted, and shuffled labels are not;
  - at today's scale it runs end to end.

**W2 — Drift-robust variants, fixed in advance (finding 2).**
- **Training windows:** 1 h (3,600 samples), 4 h (14,400) and the served 20,000 (about 5.6 h).
- **Recency weighting:** exponential sample weights with a 1 h half-life on the served window. Both the HGB and the calibration accept sample weights.
- **Where they run:** on the three best label definitions with all features, like the ablations.
- **If one is adopted,** the served recipe takes it through configuration: `ML_MAX_SAMPLES` exists, and a new `ML_SAMPLE_HALF_LIFE_S` would carry the weighting. Both are covered by the model manifest.

**W3 — Freeze the protocol; decide on unseen data (finding 3).**
- **`docs/edge-study-protocol.md`** states, before the deciding data exists:
  - the grid, ablations and variants;
  - the evaluation (blocks, cadence, embargo);
  - the baselines and the rule;
  - the deciding-data window.
  - It is committed with the code that implements it, and every report carries its hash.
- **The deciding data** are bars stamped after the freeze. The 0.21 days examined so far may inform the protocol but may not decide it.
- **`ml_study.py --decide`** uses only post-freeze bars and refuses below 7 days of them. Without `--decide` the run uses everything and is labelled exploratory.

**W4 — The finding in the product (findings 4, 5).**
- **Data.**
  - `ml_study.py` also writes its report as JSON (`data/edge-study/latest.json`, host-local).
  - `GET /api/v1/analytics/edge-study` returns that report plus collection progress: live bars stored, days of bars, post-freeze days toward 7, the newest bar's age and retention.
  - A host where no study has run returns the progress alone.
- **Intelligence: an "Edge study" panel.**
  - A verdict badge: exploratory, preliminary, no edge or adopt.
  - Progress toward 7 post-freeze days, the rule and the protocol hash.
  - The best configurations, and the holdout.
  - It is built on the design system and is axe-clean, with reduced-motion and mobile layouts.
- **Settings → Engine: "Data collection".** Bars stored, days of bars, the oldest and newest bar, retention, and the writer's queue and failed flushes.
- **Contracts and checks.** Contracts regenerated. The e2e spec covers the panel's "no study on this host" state, and real-GPU captures cover desktop and mobile.

**W5 — Housekeeping (finding 6).**
- **Dependabot #11 and #13:** merge each onto current `main` in a local worktree, run the full gates and e2e, and report so the owner can make the merge call.
- **Unchanged and still waiting:** the Linux visual baselines (Docker's engine) and re-blocking the dev-tooling npm audit (a braces fix).

### 12.3 Stages

| Stage | Scope | Reviewable outcome |
|---|---|---|
| **T — The study, as served** | W1, W2, W3 | Rolling evaluation and variants, with tests; the protocol written; an exploratory run on today's bars with the cost measured. **The freeze is the push of this stage:** deciding data accrue from then |
| **V — Housekeeping** | W5 | #11 and #13 verified against `main` (gates and e2e), for the owner's merge call |
| **U — The edge study in the product** | W4 | The panel and the collection block on the live collector; contracts; e2e and axe; real-GPU captures at 1440 and 390 px |
| **X — The deciding run** (data-gated) | — | Once 7 post-freeze days exist: `ml_study.py --decide`, and the verdict recorded. If a configuration is adopted: new served defaults, a retrain, a schema bump if features change, and UI copy. If not: "no edge at any tested definition on N days", recorded here and shown by the panel |

**Proposed order: T → V → U → X.**
- T comes first because the deciding-data clock starts at its push. Every day before the freeze is a day that can't decide.
- V is small, and unblocks the owner's merges.
- U shows T's output format, so it follows T.

### 12.4 Decisions needed

| # | Question | Recommendation |
|---|---|---|
| F1 | How the study evaluates at scale | Rolling refits at the served cadence (600 samples) on 32 sampled development blocks (8 per quarter), plus every holdout block. The rule reads quarters (≥ 3 of 4) and the holdout. Alternative: refit hourly on every block, which is staler than serving at about the same cost |
| F2 | Which drift-robust variants | 1 h, 4 h and served training windows, plus a 1 h recency half-life on the served window, run on the three best label definitions. Fixed in the protocol |
| F3 | Which bars decide | Only bars stamped after the protocol freeze (T's push), at least 7 days of them. Earlier bars stay exploratory |
| F4 | Where the deciding run happens | This machine, on the collector's database. After the cutover, Render's bars can join through `export_bars.py` (exports deduplicate by open time) |
| F5 | What the product shows | The study's verdict and collection progress on Intelligence, and collection health under Settings → Engine. The study JSON is host-local, so production shows progress alone until a study runs there |
| F6 | Stage order | T → V → U → X |

### 12.5 Delivery log

**Stage T — the study, as served (2026-10-08).** W1, W2 and W3. The owner approved §12 with the recommended decisions ("continue", 2026-10-08).

- **Evaluation as served** (`algoviz/ml/study.py`).
  - A block is 600 samples, the engine's retrain cadence. For each block the study fits the served recipe on the configuration's training window, which ends one horizon before the block, then scores the block. The window is capped at the configuration's size, with at least `ML_MIN_DATA_POINTS` samples.
  - Development: 8 evenly spaced blocks in each of 4 quarters of the earlier 75 %. A quarter pools its blocks. Holdout: every block of the rest, after an embargo of one horizon.
  - Baselines per block: the class prior of the training window, and the trailing prior. The rule's edge is over the better of the two, and the rule reads quarters: at least 3 of 4, and the holdout.
  - Labels are cached per definition. Before, each ablation relabelled every sample, which at 7 days would have cost about 20 minutes.
- **Variants, fixed in advance** (F2): 1 h and 4 h windows, and the served window with recency weights (1 h half-life of bar time). They run with all features on the three best label definitions, next to the two ablations: 75 configurations in all.
  - `fit_model` and `TailStoppedHGB` take sample weights, which reach the trees and the calibrators. The served path passes none.
  - **Weighted fits were 5 to 17 times slower.** With `sample_weight`, scikit-learn 1.9 computes every bin edge of every feature as a weighted percentile: 35,000 calls a fit, 93 % of its time. With no more distinct values than bins, it bins at midpoints instead. So weighted windows are first binned at their unweighted quantiles (`bin_codes`), the edges an unweighted fit uses. A weighted fit on 20,000 samples now takes 2.2 s, against 1.5 s unweighted.
- **The protocol is frozen** (F3): `docs/edge-study-protocol.md`, at 2026-10-08 14:55 UTC (`FREEZE_MS`).
  - Bars from the freeze on decide.
  - `ml_study.py --decide` refuses until 7 days of them exist, so the deciding data stay unexamined until they are complete. Checked: it refused with 0 days.
  - Without `--decide`, the study runs on earlier bars only, and is labelled exploratory. Every report carries the protocol's SHA-256 prefix.
- **Found and fixed: calibration fell back when a split saw one class.**
  - A boosting model fitted on a single class reports one class but answers with two probability columns. `TailStoppedHGB.predict_proba` mapped them as if they were one per class. Calibration raised a shape error, and the recipe served an uncalibrated model.
  - It surfaced in the first exploratory run on the most lopsided definitions, such as 5 s · k 2 · floor 4 bps, about 99 % flat. It predates Stage T.
  - A regression test fails on the old code ("none" instead of "sigmoid"). Split models now keep only their own classes' columns.
  - The protocol is unchanged: it names the served recipe, and this is a fix inside it. The run was restarted on the fixed code.
- **Exploratory run under the frozen protocol** (`docs/edge-study.md`): 24,018 bars from before the freeze (0.28 days, 13 sessions); 75 configurations in 37 minutes (2,202 s).
  - Under evaluation as served, the 5 s definitions lead, the served one among them.
  - The best is 5 s · k 1 · floor 0.5 bps, without the hour-of-day features: +0.015 ± 0.047 nats over the better prior, beating both priors in only **2 of 4** quarters. On the holdout it scored +0.040 (log-loss 0.622, against 0.674 for the class prior and 0.662 for the trailing prior).
  - The 120 s definitions, which led every earlier run, fall to the bottom (−0.115 and −0.252). They beat the trailing prior but lose heavily to the class prior: the trap E9 closed.
  - Refitting as served helps the short horizon, but the evidence is thin: 2 of 4 quarters, and a spread larger than the mean. Nothing is decided. That waits for 7 days of bars from the freeze on.
  - 25 fits fell back to an uncalibrated model because a class had fewer than 3 examples in the window. That is the served recipe's intended fallback.
  - **Cost at 7 days**, from these timings: about 35 s per configuration here, and about 30 % more fit time on the larger windows. The deciding run should take 1–2 hours.
- **Checks:**
  - Backend: ruff, ruff format and mypy clean. pytest: 172 passed and 1 skipped, coverage 92.76 %, in 5.1 min. pip-audit clean.
  - No API or UI change, so the contracts and the frontend are untouched. e2e runs in CI on the push.
  - New tests:
    - a planted edge is adopted only when deciding (never on exploratory bars or on a day of data), and E9's weaker case and shuffled labels are rejected;
    - one refit per block, the window caps respected, and every training label resolved before its block;
    - recency weights halve every half-life;
    - sample weights reach every tree model, while the served fit stays unweighted;
    - bin codes keep the unweighted bins and their order;
    - the freeze splits bars;
    - calibration survives a split model that saw one class.
- **Pushed 2026-10-08** at the owner's word. The freeze took effect at 14:55 UTC: bars from then on are deciding data, and nothing has examined them.

**Stage V — Dependabot #11 and #13, verified against `main` (2026-10-08).** W5.

- **Method.**
  - Each PR's merge with `main` (`e421d27`) was written out with `git merge-tree` and a temporary index, into a scratch directory: no branch, commit or worktree.
  - Both merge cleanly. Both PRs change only dependency files, so each merge is `main`'s code on the new dependencies.
- **#13, the Python group (9 updates):** SQLAlchemy 2.0.54 → 2.1.3, FastAPI 0.141.1 → 0.142.2, uvicorn 0.53 → 0.54, websockets 17.1 → 17.2, PyJWT 2.15.0 → 2.15.1, and transitive pins.
  - Installed into a throwaway Python 3.11 venv with the PR's `constraints.txt`. `pydantic-core` resolved to 2.46.5 through pydantic's own pin: the 2026-10-07 constraints fix works.
  - Backend gate: ruff, ruff format and mypy clean; pip-audit clean; pytest 172 passed and 1 skipped, coverage 92.93 %.
  - e2e with the backend on these dependencies (Playwright started the seed and uvicorn with the throwaway venv), and the seed template rebuilt through SQLAlchemy 2.1: **39 of 39** in 12.9 min.
- **#11, the npm group (10 updates):** React and React DOM 19.2.8 → 19.3.0, three 0.186.0 → 0.186.1, `@react-three/fiber` 9.8.1, React Query 5.104.0, `lucide-react` 1.48.0, Vitest 5.0.2, jsdom 30.1.1, and the React types.
  - The merge keeps the security update: `sharp` stays at 0.35.5.
  - A fresh `npm ci` (500 packages). Frontend gate: Prettier, tsc, eslint, Vitest 29 and the build pass; npm audit of what ships is clean.
  - e2e from the merged tree: **39 of 39** in 10.7 min, the Windows visual baselines included, so the icon and React bumps move nothing on screen.
- **The owner's call.** Both are ready to merge, and a merge to `main` deploys. #13 carries the larger change (SQLAlchemy 2.1), which its own CI run #21 and this local run both passed.
- **Stale Dependabot branches.** These were reported as 11 branches of closed PRs, but that came from out-of-date local tracking refs. On `origin` they had already been removed when their PRs closed. `git fetch --prune` cleared the local copies, so there was nothing to delete.

**Merges and Stage U (2026-10-08).**

- **Merged at the owner's word:** Dependabot #13 (`00f19a0`) and #11 (`5db36bb`), as merge commits on the Stage V notes (`c1fc6f8`).
  - The merged tree is byte-identical to the trees Stage V tested: `backend/` matches #13's verified tree, `frontend/` matches #11's.
  - GitHub marked both PRs merged, and Dependabot removed their branches. CI #24 was all green.
  - The dev venv and `node_modules` were brought to the new pins. The collector was stopped for about a minute so the venv could be updated, then restarted on the new versions.
  - There was nothing else to delete: the 11 "stale branches" were out-of-date local tracking refs (see Stage V).
- **Stage U — the edge study in the product.** W4.
  - **`GET /api/v1/analytics/edge-study`** returns two parts:
    - `study`: the latest report on this host, which `ml_study.py` now also writes as JSON (`EDGE_STUDY_FILE`: `data/edge-study.json` for live, a file per source otherwise, `/var/data` on Render). A report the server can't read counts as none, and is logged.
    - `collection`: bars stored, bars and days since the freeze, the oldest and newest bar, the newest bar's age, and retention. The counts are cached for 30 s; the newest bar is read fresh on every request, so its age never lags.
  - **An index for it** (migration `b7d2f05c1e94`, `ix_market_symbol_source_ts`).
    - Counting one source's bars scanned the whole table: the (symbol, timestamp) index can't serve the source filter.
    - Measured on a copy of the live database (36,178 bars): 27.7 ms as a scan, 7.0 ms on the new covering index. The scan grows with the table, to seconds at 60 days.
  - **Intelligence: an "Edge study" panel.**
    - A progress ring toward 7 days of bars from the freeze on, with the stored bars, the newest bar's age and retention.
    - The verdict as a badge and a sentence, and tiles for the best development edge, the holdout against the better prior, the data and the rule.
    - The best eight configurations, with their spread.
    - A host with no study says so, and names the commands.
  - **Settings → Engine: "Data collection"**, a fourth column: bars stored, days of bars, days since the freeze, the newest bar (flagged past 60 s) and retention.
  - e2e pins its own study file (`EDGE_STUDY_FILE`, never written), so a developer's study can't leak into a run.
  - **Checks:**
    - Backend: ruff, ruff format and mypy clean. pytest: 173 passed and 1 skipped, coverage 93.23 % (17.7 min, sharing the CPU with a study run). pip-audit clean. OpenAPI regenerated: 39 paths, 98 schemas.
    - New API test: no report, then a report written by `report_dict` and validated by the schema, then an unreadable file. It also checks bars counted on both sides of the freeze.
    - Frontend: Prettier, tsc, eslint, Vitest 32 (3 new: the report's verdict, tiles, holdout against the better prior, rows and spread), the build, and npm audit of what ships.
    - Playwright: 37 of 39, then the two intended intelligence baselines re-recorded. The diff showed the new panel, inserted in its loading state, and two earlier subtitle changes the pixel tolerance had absorbed. The visual spec then passed 24 of 24 with `--repeat-each=2`, and axe was clean on every route.
    - Browser, live collector (`frontend-live` on :8001, with the regenerated report):
      - The panel shows the protocol digest, 75 configurations and the "exploratory" badge.
      - The ring reads 0.18 of 7 days since the freeze, beside 39,380 live bars stored, kept 60 days.
      - Then the verdict, the tiles (+0.015 in development, 2 of 4 quarters; holdout +0.040, log-loss 0.622 vs 0.662) and eight rows with their spread.
      - At 390 px the page is 390 wide and nothing is truncated; the table scrolls in its wrapper. The no-study state checked the same way, on the synthetic backend.
    - The regenerated `docs/edge-study.md` is byte-identical to Stage T's. The migration applied on the live database at the collector's restart.

**Check of the app as it stands (2026-10-09).** Only Stage X remains, gated on data, so the app was checked again before proposing anything further.

- **Collector:** healthy (loop lag p99 25 ms, connected). The 11 skipped inferences in its log all fell within heavy local runs (studies, e2e, pytest), and none happened under normal load.
- **Storage, measured on a vacuumed copy:** 556 bytes per bar with both indexes (2.9 GB at 60 days), plus 0.1 GB of predictions at 7-day retention. That fits Render's 5 GB disk.
- **UI:** every route at 1440 and 390 px on the live feed: no overflow, no alerts, no panel stuck loading.
  - One read-out was cut off: the signal rules' descriptions (`truncate`, the full text only in a `title`, which touch never shows). They now wrap, between 14 and 22 rem.
  - A console "Object is disposed" from the charts came from the inspection shim, not the app: it replaced `requestAnimationFrame` but not `cancelAnimationFrame`.
- **Nothing found warrants a Phase 7.** The next step is Stage X once 7 days of bars from the freeze on exist (0.21 days on 2026-10-09).

