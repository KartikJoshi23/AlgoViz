<div align="center">

# AlgoViz

### Real-time market-microstructure intelligence

L2 order book · order-flow imbalance · regime detection · calibrated next-move probabilities · signals · alerts · event-driven backtests — rendered live as a price × time liquidity heatmap, with an orbitable 3D terrain on request.

[![CI](https://github.com/KartikJoshi23/AlgoViz/actions/workflows/ci.yml/badge.svg)](https://github.com/KartikJoshi23/AlgoViz/actions/workflows/ci.yml)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev)
[![Three.js](https://img.shields.io/badge/Three.js-r186-000000?logo=threedotjs&logoColor=white)](https://threejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

</div>

---

## What it does

AlgoViz consumes the Binance trade and diff-depth streams for a symbol, rebuilds the full L2 order book, and turns the raw event flow into a small set of honest, well-defined numbers a trader can act on — every 200 ms, in the browser:

| Layer | What you get |
|---|---|
| **Order book** | Full L2 reconstruction with `U/u` sequencing and automatic resync; microprice, weighted queue imbalance, liquidity within 5/10/25 bps, book slopes, a 128-bin cumulative **depth profile** streamed at 5 Hz |
| **Order flow** | Cont–Kukanov–Stoikov OFI over 1 s / 5 s / 30 s, trade velocity, buy pressure, VWAP/TWAP, volatility — all in event time, O(1) per event |
| **Baselines** | EWMA mean/variance per feature → z-scores with warm-up guards, so "unusual" means *unusual for the last 15 minutes*, not a hard-coded threshold |
| **Regime** | Two separate axes: a **volatility state** from a Gaussian HMM over 1-second bars (calm / normal / elevated / extreme, with min-dwell hysteresis) and a **trend** (down / flat / up) that is called only while the drift's Newey–West t-statistic clears ±2 |
| **Model** | Triple-barrier, volatility-scaled labels; 46 scale-free features (quantities over their rolling 30-minute medians); gradient boosting early-stopped on a time-ordered tail and calibrated on embargoed time splits. **Evaluated as served**: every walk-forward fold (`TimeSeriesSplit(gap = horizon)`) runs the same recipe and is scored held-out — log-loss, reliability curve, Brier reliability / resolution / uncertainty — against the class prior and a regularised logistic baseline. Held-out permutation importance on log-loss; SHAP of the served ensemble; a manifest check refuses models trained for other features or labels; live **drift monitor** that scores every prediction against what the market did |
| **Signals** | 18 rules with hysteresis, minimum duration and cooldown, expressed in one condition language shared with alerts and strategies |
| **Alerts** | Threshold rules on any catalog feature, evaluated every second, history + acknowledgement, Discord delivery |
| **Backtests** | Declarative strategies (entries, exits, stops, targets, max hold, cooldown, model probabilities) run event-by-event on real 1-second bars with next-bar fills, slippage and commission |

The frontend is a Next.js app.
- **The hero** is a price × time **liquidity heatmap**: resting size per price bin over the last three minutes, with trade bubbles and the mid trail. It is Canvas 2D, the same view on every tier.
- **On request,** where WebGL exists, the same depth renders as an orbitable **3D terrain**: price × time × cumulative depth, displaced in a vertex shader.
- **Surfaces:** panels sit on a navy "midnight glass" surface under a slow, regime-tinted aurora; frosted glass is kept for the floating chrome.
- **Fallbacks:** motion pauses off-screen and follows `prefers-reduced-motion`, and software renderers get a quieter low tier.

Everything runs offline too: a structurally honest **synthetic exchange** (GBM with a sticky volatility chain, Hawkes-style trades, a mean-reverting book with far-liquidity walls) and a **replay** mode for recorded streams drive the same pipeline.

---

## Architecture

```
                 Binance WS (trades, diff-depth)            recorded NDJSON            synthetic exchange
                              │                                    │                          │
                              └────────────────── MarketSource ────┴──────────────────────────┘
                                                        │
      ┌─────────────────────────────────────────────────┼──────────────────────────────────────────┐
      │  SymbolEngine (per symbol, single asyncio task)  │                                          │
      │   L2 book ──► book metrics (5 Hz)                ▼                                          │
      │   rolling windows ──► FeatureSnapshot ──► EWMA baselines ──► z-scores                       │
      │   1-second bars ──► HMM regime ──► ML engine (labels, train, predict, drift)                │
      │                 └──► signal engine ──► alert evaluator ──► Discord                           │
      │   persistence: bars, predictions, alerts, strategies, backtests (SQLite / Postgres, Alembic) │
      └───────────────────────────────┬───────────────────────────────────┬────────────────────────┘
                                      │ typed WS frames (channels,        │ REST (OpenAPI → generated TS types)
                                      │ snapshot-on-connect, backpressure) │
                              ┌───────▼───────────────────────────────────▼────────┐
                              │  Next.js 16 · React 19 · zustand rings · TanStack  │
                              │  canvas heatmap · Three.js terrain · GSAP          │
                              └────────────────────────────────────────────────────┘
```

- **Backend** — FastAPI 0.141 · Python 3.11 · SQLAlchemy 2 (async) + Alembic · numpy/scipy/scikit-learn/shap/hmmlearn · orjson · pure-ASGI middleware (request IDs, timing, rate limiting) · bcrypt + PyJWT · prometheus-client. Why it is built this way: [ARCHITECTURE.md](./ARCHITECTURE.md).
- **Frontend** — Next.js 16 (App Router, standalone output) · React 19 · TypeScript strict · Tailwind CSS 4 (CSS-first tokens) · zustand 5 with typed-array ring buffers · TanStack Query 5 · `openapi-typescript` + `openapi-fetch` · Three.js + React Three Fiber · GSAP · lightweight-charts.
- **Contracts** — `backend/scripts/export_openapi.py` writes `frontend/lib/api/openapi.json`; `npm run types` generates `lib/api/schema.d.ts`. CI fails if either is stale. The WebSocket frame types come from the same document (`/api/v1/ws/schema`).

---

## Quick start

### Prerequisites

Python 3.11 · Node.js 22 · npm — or Docker.

### One command (Docker)

```bash
docker compose up --build                        # live Binance feed
DATA_SOURCE=synthetic docker compose up --build  # no internet needed
```

Frontend → http://localhost:3002 · Backend → http://localhost:8002 (`/docs` for the API).

### Two terminals (development)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]" -c constraints.txt
uvicorn algoviz.main:app --reload --port 8000        # DATA_SOURCE=synthetic for offline
```

```bash
# frontend
cd frontend
npm install
cp .env.example .env.local                           # backend origin, defaults to localhost:8000
npm run dev                                          # http://localhost:3000
```

### Data sources

| `DATA_SOURCE` | Behaviour |
|---|---|
| `live` (default) | Binance `@trade` + `@depth@100ms`, REST snapshot with diff bracketing; falls back across hosts on HTTP 451 |
| `replay` | `REPLAY_FILE=path.ndjson.gz` through the same pipeline at `REPLAY_SPEED` (0 = as fast as possible). Record with `python scripts/record_stream.py --seconds 120 --out data/recordings/btc.ndjson.gz` |
| `synthetic` | Built-in exchange simulator — deterministic per seed, regimes and breakouts included |

Symbols: `SYMBOLS=["BTCUSDT"]` (allowlist: BTCUSDT, ETHUSDT, SOLUSDT). Synthetic and replay runs use their own database and model store (`data/algoviz-<source>.db`, `ml_models/<source>/`) so simulator bars never train the live model. All settings are in [`.env.example`](.env.example).

---

## The frontend

| Route | Content |
|---|---|
| `/` | KPI strip (z-annotated), liquidity heatmap (3D terrain on request), mid/VWAP/microprice chart, model panel, volatility state and trend, cumulative depth, order-flow strips, signals feed, trade tape, session z-scores |
| `/book` | Full-width liquidity heatmap / terrain with hover readout, cumulative depth curve, ladder, liquidity bands and slopes, OFI / imbalance / spread strips |
| `/intelligence` | Calibrated probabilities, drift monitor (rolling hit rate and log-loss vs prior), SHAP contributions, held-out permutation importance, walk-forward folds with held-out reliability and the Brier decomposition, model registry, signal rules with live state |
| `/strategies` | Condition editor over the feature catalog, templates, backtest runner with WebSocket progress, equity/drawdown chart, trade list |
| `/alerts` | Rule CRUD, live + persisted history, acknowledge, Discord |
| `/settings` | Symbol, book stream, performance tier, motion, ambient tint, connection, access (admin token), engine metrics |

⌘/Ctrl-K opens the command palette. Preferences live in `localStorage` and sync across tabs. Motion respects `prefers-reduced-motion`; software renderers get the low tier automatically (2D hero, no glass blur, no looping ambient motion).

### Visual identity — "midnight glass"

A navy theme. Colour carries meaning only: bids teal, asks crimson and the mid gold — the order book's own semantics, checked with colour-vision-deficiency simulation to stay distinguishable. The volatility state is a single violet lightness ramp (calm → extreme), which also tints the slow aurora behind the page. Status colours are reserved for state and always come with a label. All text meets WCAG AA.

---

## API

Interactive docs at `/docs` (Swagger) and `/redoc`. Highlights:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` · `/health/live` · `/health/ready` | Summary (always 200, `ok`/`degraded`); liveness probe; readiness probe — 503 until the schema is migrated, every book is synced and fresh, and event-loop lag p99 is under `LOOP_LAG_DEGRADED_MS` |
| `GET` | `/api/v1/market/features` · `/book` · `/trades` · `/bars` | Current features, L2 book + depth profile, tape, 1-second bars (ring or history) |
| `GET` | `/api/v1/market/feature-catalog` | The one list of features the condition language accepts |
| `GET` | `/api/v1/analytics/prediction` · `/model-info` · `/shap` · `/drift` · `/model-registry` | Model state, walk-forward metrics, explanations, live drift, training history |
| `GET` | `/api/v1/analytics/signals` · `/signals/rules` | Active signals, recent transitions, rule definitions |
| `CRUD` | `/api/v1/strategies` · `POST …/{id}/backtest` · `GET …/{id}/backtests/{bid}` | Strategies, asynchronous backtests, results with equity curve and trades |
| `CRUD` | `/api/v1/alerts/rules` · `/api/v1/alerts/history` | Alert rules and history with acknowledgement |
| `GET` | `/api/v1/system/metrics` · `/metrics` | Engine, writer, alert evaluator and WebSocket statistics (JSON for the UI; Prometheus text for scrapers) |
| `POST` `GET` | `/api/v1/auth/login` · `/auth/access` | JWT login; whether changes are gated here and whether the caller may make them |
| `WS` | `/ws?symbol=BTCUSDT` | Channels: `features` `book` `trades` `bars` `regime` `prediction` `signals` `alerts` `backtests` `status`; `hello` + `snapshot` on connect; per-client latest-wins queues for high-rate channels |

Reads are public. Changes (every `POST` / `PATCH` / `DELETE` above) need `Authorization: Bearer <ADMIN_TOKEN>` or a user's JWT when `MUTATIONS_REQUIRE_AUTH` is on (production by default). Errors are RFC 9457 `application/problem+json` (`title`, `status`, `detail`, `request_id`, per-field `errors`). History lists are paged newest first: pass `next_before` back as `before`.

### Condition language

Shared by signal rules, alert rules and strategies, validated against the feature catalog:

```json
{"all": [{"f": "ofi_z", "op": ">", "v": 1.5}, {"f": "regime", "op": "not_in", "v": ["calm"]}]}
```

Leaves are `{"f", "op", "v"}`; groups are `all` / `any` / `not`. Missing values make a leaf false, never an error, so rules stay quiet during warm-up.

---

## Honesty notes

- Model metrics are **walk-forward and evaluated as served**. Each fold is built with the same recipe as the live model (time-tail early stopping, calibration on embargoed splits), inside `TimeSeriesSplit` with an embargo equal to the label horizon. It is scored held-out against the class prior, the trailing prior (the class mix of the labels already resolved at each prediction) and a regularised logistic baseline, with reliability curves and the Brier decomposition. "Edge" means beating both priors out of sample. On live BTC at a 5 s horizon it does not, and the UI says so.
- Other label definitions are tested by an edge study (`backend/scripts/ml_study.py`, report in `docs/edge-study.md`) against a protocol fixed in advance (`docs/edge-study-protocol.md`): it refits the model as served, and only 7 days of bars collected after the protocol was frozen can decide.
- Feature importance is the rise in held-out log-loss when a feature is shuffled. SHAP explains the served ensemble's tree models before calibration, and is labelled as such.
- The drift monitor scores live predictions against realised moves; the registry keeps every training run.
- Backtests fill at the next bar's close with slippage and commission, check stops and targets against the extremes of the bars *after* the fill, and are labelled `synthetic` when fewer than `BACKTEST_MIN_BARS` real bars were available. Sharpe/Sortino are annualised from 1-minute returns over a short window — treat them as indicative.

---

## Development

With [`just`](https://just.systems): `just setup`, then `just check` runs every CI gate, and `just --list` shows the rest (backend, frontend, e2e, contracts, format, docker). Without it:

```bash
# backend gate (what CI runs)
cd backend && ruff check . && ruff format --check . && mypy
pytest -q --cov                       # coverage floor 90 % (pyproject.toml); -m "not slow" skips the ML integration test
pip-audit -r requirements.txt -r constraints.txt --strict

# frontend gate
cd frontend && npm run format:check && npm run check    # prettier · tsc · eslint · vitest · next build
npm run e2e                           # Playwright: seeds the e2e DB, builds the app, boots a synthetic backend

# contracts
python backend/scripts/export_openapi.py && (cd frontend && npm run types)
```

The Playwright suite covers smoke and page flows, strategies and alerts, WCAG 2.2 AA (axe), visual baselines (recorded on Windows), performance budgets on the non-3D routes, and a WebGL project forcing the mid tier. Every run starts from the same seeded database and trained model (`backend/scripts/seed_e2e.py`). Hooks: `pip install pre-commit && pre-commit install` runs ruff, prettier and eslint with the project's own pinned versions.

Migrations: `cd backend && alembic upgrade head` (run automatically at startup). Record a stream for replay: `python backend/scripts/record_stream.py --seconds 120`. Collect live bars for the edge study with a long-running live backend: `python backend/scripts/collect_live.py` (port 8001, bars kept 60 days; under `pythonw` it logs to `backend/data/logs/collector.log`, so a task started at logon can run it). Save bars past retention: `python backend/scripts/export_bars.py`; then run the edge study on them: `python backend/scripts/ml_study.py --out docs/edge-study.md` explores the bars from before the protocol's freeze, and `--decide` runs the deciding study once 7 days of later bars exist (`docs/edge-study-protocol.md`).

### Project structure

```
backend/
  algoviz/
    market/      sources (binance, replay, synthetic), book, features, baselines, bars, regime, catalog, persistence, service
    ml/          features, labels, train, evaluation, registry, explain, drift, engine, study
    signals/     rules, engine            alerts/   notify, evaluator
    backtest/    strategy, engine, metrics, service
    api/         market, analytics, strategies, alerts, auth, system     ws/  hub
    core/        time, logging, auth, middleware, problems, metrics, workers, looplag, users, conditions
    schemas/     rest, ws                  db/  session, migrations, types  models/
  alembic/  scripts/ (export_openapi, freeze_constraints, record_stream, seed_e2e, smoke_deploy,
           export_bars, ml_study, collect_live)  tests/  Dockerfile  pyproject.toml
frontend/
  app/           routes (/, /book, /intelligence, /strategies, /alerts, /settings), globals.css (tokens), ds.css (components)
  components/    ds (design system), panels, charts, three (Terrain, shaders), conditions, strategies, alerts, intelligence, ui
  lib/           api (generated types + hooks), ws (client, types), store (rings, heat, depth), gsap, perf, theme, features, reliability, format
  e2e/  tests/   Playwright · Vitest       Dockerfile  next.config.ts  playwright.config.ts
docker-compose.yml  render.yaml  justfile  .pre-commit-config.yaml  .github/ (ci.yml, dependabot.yml)
ARCHITECTURE.md  CHANGELOG.md  CLAUDE.md (hand-off notes)  docs/implementation-plan.md (plan + delivery log)
```

---

## Deployment

- **Backend → Render** — create it as a **Blueprint** (New → Blueprint, this repo) so `render.yaml` is the source of truth. It provisions an always-on Python web service in Singapore (Binance returns 451 to US IPs).
  - Instance and storage:
    - 1 CPU / 2 GB, with a 5 GB persistent disk at `/var/data`.
    - SQLite and the model store live on the disk, so bars, predictions and trained models survive deploys and restarts. Render snapshots the disk daily.
    - Bars are kept 60 days. Migrations run at startup.
    - A disk rules out zero-downtime deploys: each deploy restarts the service briefly.
  - Configuration:
    - It generates `SECRET_KEY` and `ADMIN_TOKEN`.
    - It trusts forwarded addresses only from Render's private proxy ranges.
    - It allows the production frontend's origin in CORS and on the WebSocket.
    - It health-checks `/health/live`.
  - Paste the generated `ADMIN_TOKEN` into the frontend's Settings → Access to make changes.
  - Add `DISCORD_WEBHOOK_URL` if you want alert deliveries.
  - Scrape `/metrics` with Prometheus if you run one.
  - Postgres is supported too: set `DATABASE_URL` (`postgres://…` URLs are accepted and use asyncpg). Keep `ML_MODEL_DIR` on a persistent disk either way, or every restart retrains.
- **Frontend → Vercel** — import the repo with **Root Directory** `frontend`. `frontend/vercel.json` pins the Next.js build.
  - Set `NEXT_PUBLIC_API_URL=https://<backend>.onrender.com` and `NEXT_PUBLIC_WS_URL=wss://<backend>.onrender.com/ws` for Production. A production build without them fails on purpose, rather than shipping a site that talks to localhost.
  - Add the frontend's origin to the backend's `CORS_ORIGINS` (the WebSocket allowlist follows it). For preview deployments, set a narrow `CORS_ORIGIN_REGEX`.
- **Check a deployment** — `python backend/scripts/smoke_deploy.py https://<backend>`. It confirms the deployed version, readiness, that changes are gated, and the CORS and WebSocket origin checks. With `ADMIN_TOKEN` set and `--with-token`, it also makes a change and deletes it again.
- **Anywhere → Docker** — both images are multi-stage and non-root; the frontend image takes the browser-facing backend origin as build args (see `docker-compose.yml`).

---

## License

MIT — see [LICENSE](./LICENSE).

<div align="center">

Built by [Kartik Joshi](https://github.com/KartikJoshi23)

</div>
