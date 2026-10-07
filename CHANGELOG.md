# Changelog

Notable changes, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — Phase 5: ship, harden, test the model for an edge

### Deployment (Stage N)
- `render.yaml` is a Blueprint for an always-on backend: 1 CPU / 2 GB, with a 5 GB disk holding SQLite and the trained models. Bars are kept 60 days.
- `frontend/vercel.json` pins the Next.js build. A production build fails unless the backend URLs are `https://` and `wss://`.
- The default CORS origins no longer include two third-party sites.
- Training and HMM fits run at a lower OS priority (POSIX), so on one CPU they can't starve the live feed.
- `scripts/smoke_deploy.py` checks a running deployment from the outside.

### Edge study (Stage S)
- `scripts/ml_study.py` runs the pre-registered edge study. It covers 60 label definitions (horizons of 5–120 s, three barrier widths, four floors) and two feature ablations. Each is scored walk-forward with the served recipe on the earlier 75 % of the bars, and the best one is scored once on the rest. The rule decides only with at least 7 days of bars.
- `scripts/export_bars.py` saves bars as gzipped NDJSON, so they outlive retention. The study reads the exports and the database together.
- `scripts/collect_live.py` runs the live backend as a long-lived collector on :8001, with bars kept 60 days and training on one thread. Without a console it logs to a file, so a task started at logon can keep it running.
- The rule requires beating both the class prior and the trailing prior (E9, 2026-10-07, amended before the deciding data existed). As first written it tested the trailing prior alone, which at long horizons was the weaker baseline.
- A trailing-prior baseline: the class mix of the labels already resolved at each prediction. It is scored in every walk-forward fold, and shown on the Intelligence page and in the drift monitor. The drift monitor starts it from the labels rebuilt from stored bars, so a restart doesn't score new predictions against a uniform guess. The drift status reads "edge" only when the model beats both the class prior and the trailing prior.

### Heatmap and read-outs (Stage R)
- The liquidity heatmap is whole the moment a page loads. The engine keeps the last three minutes (one column a second, whoever is watching), and the WebSocket snapshot carries them. Before, the map filled in over three minutes after every load.
- Panel subtitles, tile hints and feature names wrap on narrow screens instead of being cut off. The drift panel names its real window, and the model card's drift line fits.

### Reliability (Stage Q)
- An async test that hangs is failed after 5 minutes, with every asyncio task's stack in its report. pytest's `faulthandler_timeout` covers synchronous hangs.
- `npm start` serves the standalone build exactly as the Docker image does, and e2e runs against it.
- CI runs current action majors on a pinned `ubuntu-24.04` runner. Dependabot sends each major version as a PR of its own and holds the Docker runtimes (Python 3.11, Node 22).
- `backend/constraints.txt` pins the transitive Python dependencies for Render, Docker and CI, and pip-audit covers them. `scripts/freeze_constraints.py` regenerates it.
- Node 22 everywhere (`engines`), including Vercel builds.
- `threadpoolctl` is declared, the OpenAPI export writes LF, and the Vitest config is native ESM.

### Security
- `sharp` 0.35.5 (its libvips carries the librsvg fix for CVE-2026-96889) and `source-map-js` 1.2.2, both high advisories published after Stage S was gated.
- CI blocks on advisories in what ships (`npm audit --omit=dev`) and reports dev tooling without failing. braces ≤ 3.0.3, reached only through eslint-config-next, has a high advisory and no patched release.

### Fixed
- `constraints.txt` no longer pins `pydantic-core`, which pydantic pins exactly. Dependabot had bumped it alone, and the install could not resolve (PR #12).
- Calibration could serve certainty in a rare class. This happened when a calibration split's training rows lacked one of the window's classes, for example no "up" before the window's last quarter. scikit-learn then calibrated that split model's p(flat) as "down", and the ensemble predicted p(down) = 1 for every row. Split models now answer for every class in the window.
- An intermittent hang in shutdown and in the test suite. On Python 3.11, `asyncio.wait_for` swallowed a cancellation that raced with a prediction completing. It is replaced by `asyncio.timeout`, and CI jobs now have time limits.
- Synthetic backtest history was capped at 600 bars whatever `BACKTEST_SYNTHETIC_BARS` said.
- Trade frames kept only the last 100 fills of each 100 ms tick, which dropped 22.6 % of live BTC fills in a 5-minute sample. Every fill is sent now.
- The drift monitor compared the live hit rate with uniform chance. It now shows the prior's own hit rate, and the model card shows the edge vs the prior.
- The engine read the global settings, rather than its own, for the depth profile.

## Phase 4: professional hardening and redesign (on `main` since 2026-10-01)

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
