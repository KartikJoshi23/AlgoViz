# Changelog

Notable changes, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — Phase 4: professional hardening and redesign

### Security and API
- Mutations need a bearer credential when `MUTATIONS_REQUIRE_AUTH` is on (production by default): the `ADMIN_TOKEN` or a user's JWT. Reads stay public. Production refuses to start without an `ADMIN_TOKEN`, and registration is off there.
- Errors are RFC 9457 `application/problem+json`, with a request id and per-field validation errors. The OpenAPI document describes them.
- Cursor pagination (`limit` + `before` → `items`, `next_before`) on alert history, backtests and the model registry.
- CORS is limited to configured origins; the host-wide wildcard pattern is gone. `X-Forwarded-For` is believed only from `TRUSTED_PROXIES`, and uvicorn runs with `--no-proxy-headers`.
- Stricter per-client rate limits for writes and for backtest submissions. The WebSocket gets a connection cap (close 1013) and an origin allowlist.
- `GET /api/v1/auth/access` reports whether changes are gated and whether the caller may make them. The frontend has Settings → Access for the token.
- Response models for the feature catalog, symbols, market stats, system metrics and backtest trades: no hand-written TypeScript response types remain.

### Operations
- Prometheus `/metrics`: event-loop lag, feed events, rate and latency, WebSocket clients, frames and backlog, writer queues, database errors, training and inference timings, alerts and backtests.
- Repeated warnings are collapsed to one line a minute with a count.
- Shutdown order: backtests (marked failed), feeds and ML engines, then the bar writer's final flush.
- A stored model is served after a restart without retraining.
- The first WebSocket connection no longer flashes a status banner, which had caused a layout shift of up to 0.15 on every page load.
- Error toasts from a drawer form (e.g. a refused change) showed underneath the drawer; toasts and the command palette now stack above it.
- Postgres via `DATABASE_URL` (asyncpg; `postgres://` URLs are normalised).

### ML rigor (Stage H)
- Walk-forward folds are built with the served recipe (time-tail early stopping, calibration on embargoed splits) and scored held-out: log-loss (calibrated and raw), reliability curves, and the Brier reliability / resolution / uncertainty terms.
- The logistic baseline is regularised, with clipped inputs.
- Permutation importance is held-out and scored on log-loss.
- SHAP explains the served ensemble.
- Model manifests are checked on load; the registry id is restored on restart.
- Quantity features are divided by their symbol's rolling 30-minute medians.
- The regime is split into a volatility state (calm / normal / elevated / extreme) and a trend (down / flat / up, Newey–West t-statistic). Stored labels and saved strategies are migrated.

### Runtime and correctness (Stage G)
- Inference moved to a dedicated thread; training and HMM fits to spawned processes (single-flight, capped threads, timeout).
- Book metrics are computed at 5 Hz behind a dirty flag.
- Commits happen before the response is sent.
- History is session-aware; the replay source keeps trade ids monotonic.
- Backtests apply stops and targets only after the fill bar, and are capped and queued.
- Retention for predictions and alert history.

### Design (Stages J–L, theme v3)
- New design system and app shell.
- A liquidity heatmap hero with a reworked, legible 3D terrain.
- Every route redesigned (Intelligence, Strategies, Alerts, Settings), responsive to 390 px and axe-clean.
- Theme v3, "midnight glass": a navy palette validated for colour-vision deficiency, lit panel edges, section icons, gradient fills and a regime-tinted aurora. On low-tier GPUs it drops the blur and looping motion.
- Fixed: the frosted glass never blurred in Chrome, because the build kept only the prefixed `-webkit-backdrop-filter`.

### Quality
- Property tests (hypothesis) for book sync, rolling windows and bars.
- Coverage is reported in CI with a 90 % floor.
- The e2e database is seeded deterministically (`scripts/seed_e2e.py`).
- Playwright now includes a WebGL (forced mid-tier) project, performance budgets on the non-3D routes, WCAG 2.2 AA axe checks and visual baselines.
- prettier, pre-commit hooks, a justfile, Dependabot and `.gitattributes`.

## [3.0.0] — 2026-09-19 — Phase 3: rebuild

- FastAPI backend with a streaming, event-time feature engine: an L2 book with sequence-checked sync, OFI, microprice and depth profile, EWMA z-score baselines, 1-second bars, an HMM regime detector, triple-barrier labels, calibrated gradient boosting with a registry and a drift monitor, signals, alerts with Discord delivery, and an event-driven backtester.
- Live Binance, replay and synthetic data sources.
- Next.js 16 frontend on a typed WebSocket and a generated REST client.
