# CLAUDE.md — working on AlgoViz

Read this first. It is the hand-off between sessions: how the owner wants the
work done, where the project stands, and what was learned the hard way.

- **What it is:** a real-time market-microstructure platform. FastAPI backend (`backend/algoviz`), Next.js 16 frontend (`frontend/`). See `README.md` and `ARCHITECTURE.md`.
- **The plan and full delivery history:** `docs/implementation-plan.md`. §10 is Phase 4; §10.6 is the delivery log, one entry per stage with its measurements, deviations and limits. Read §10.6 before starting anything.
- **What changed, in short:** `CHANGELOG.md`.

## How the owner wants the work done

These rules come from the owner and still apply:

1. **Never `git commit`, `git push` or otherwise write to git history unless explicitly asked.** The working tree is the review surface.
2. **Work in reviewable stages.** For any task: present the plan or approach, build, then **stop and summarise for review**. Don't chain several major changes without a checkpoint.
3. **Verify empirically.** Run the servers, hit the endpoints, look at the rendered UI (real-GPU screenshots). Report failures honestly, with the actual output.
4. **Keep every gate green** (list below). If you touch the API, re-run `backend/scripts/export_openapi.py` and `npm run types`: CI fails on stale contracts.
5. **Match the existing code's style,** comment density and naming. No placeholder or dead code.
6. **Quality bar:**
   - The backend stays genuinely rigorous: honest walk-forward metrics, no leakage, O(1) event-time features.
   - The frontend stays polished: the "midnight glass" design system, hover states on every interactive element, motion that reflects live market state, and full `prefers-reduced-motion` and low-GPU-tier fallbacks.
   - Dark theme only, WCAG AA, axe-clean.

## Where it stands (2026-10-03)

- **Phase 4 is complete:** stages G, J, K, L, H, M, plus the theme v3 overhaul. Stage M was approved 2026-10-01.
- **Phase 5** (`docs/implementation-plan.md` §11) was approved 2026-10-01 with every recommendation (E1–E8). The order is N → P → Q → R → S.
  - **Stage N's repository side is pushed** (`ef448e3`) and awaits the owner's cutover.
  - The hang fix and **Stage P** are pushed (`bea471a`, `6fe1575`); CI #14 was all green.
  - **Stage Q** (reliability) is pushed (`91af87b`); CI #16 was all green.
  - Its last item, the Linux visual baselines, waits on Docker Desktop. Its engine didn't start on 2026-10-02 or 2026-10-03: the app runs, but the `docker-desktop` WSL distribution stays stopped. The owner should check its window for a prompt.
  - **Stages R and S are pushed** (`c3b7e9b`, `addf995`), with a security update (`36b1463`: sharp 0.35.5, source-map-js 1.2.2, CI audits what ships). CI #19 was all green.
    - S's verdict is preliminary until 7 days of live bars exist (E7). On 2026-10-07 there were 0.17 days.
    - **Collection runs on this machine** from 2026-10-07, through the scheduled task "AlgoViz live collector" (see Running it). Earlier collectors ran as session preview servers and stopped when their session ended, which lost four days.
    - **E9 is approved (2026-10-07):** the rule requires beating both the class prior and the trailing prior. It was amended before the deciding data existed.
    - E9 and the live collector were pushed as `b2e3404`; CI #22 was all green.
- **Phase 6** (`docs/implementation-plan.md` §12, "make the edge question answerable, and visible") was **approved 2026-10-08** with the recommended decisions F1–F6. The order is T → V → U → X.
  - **Stage T** (the study, as served) was pushed 2026-10-08 (`e421d27`); CI #23 was all green.
  - **Stage V** is delivered in the working tree: Dependabot #11 and #13 each pass the full gates and e2e (39/39) merged onto `main`. Merging them is the owner's call. Next is Stage U (the edge study in the product).
  - **The protocol is frozen** at 2026-10-08 14:55 UTC (`docs/edge-study-protocol.md`, `study.FREEZE_MS`). Never examine bars from the freeze on, except through `ml_study.py --decide`, which refuses until 7 days of them exist. A change to the protocol after the freeze must be logged in its "Changes" section.
  - **Pushed 2026-10-07:** the fix for Dependabot PR #12's failing install (`constraints.txt` no longer pins `pydantic-core`; plan §11.5). Dependabot replaced #12 with #13 (9 updates, including SQLAlchemy 2.1.3 and FastAPI 0.142.2); CI #21 on it was all green, and Stage V verified it against `main`. Merging it waits on the owner's word.
  - The owner's cutover steps are listed at the end of that entry: the push, the Render Blueprint, the Vercel environment variables.
  - After the cutover, verify with `python backend/scripts/smoke_deploy.py https://<backend>`. Only the owner runs it `--with-token`: the token never passes through Claude.
- **Git:** the whole rebuild (Phases 3 and 4) is on `main`, pushed 2026-10-01 at the owner's request as a fast-forward. `overhaul/phase-3-4` is the merged branch and can be deleted.
  - **Every push to `main` deploys:** `render.yaml` has `autoDeploy: true`, and Vercel builds from `main`.
  - CI (`.github/workflows/ci.yml`) runs on pushes to `main` and on pull requests. CI #1 on `3d542f4` was all green, e2e included.
  - **The 2026-10-01 deploy did not go live** (checked through the public GitHub API, without `gh`):
    - Vercel's production deploys of `ba73a7c` and `3d542f4` failed (commit status "Vercel: failure"), and `algorithmic-viz.vercel.app` still serves the old Vite app.
    - The Render backend (`algoviz-52q2.onrender.com`) still reports version 2.0.0.
    - The logs need the owner's dashboards (§11.1).
- **Production setup** (Stage N, decisions E1–E3 in plan §11.4):
  - **Render (backend):** a Blueprint from `render.yaml`. That means service `algoviz-backend`: 1 CPU / 2 GB, a 5 GB disk at `/var/data` holding SQLite and `ml_models`, 60-day bar retention, training pinned to 1 thread, and generated `SECRET_KEY` and `ADMIN_TOKEN`.
    - Without an `ADMIN_TOKEN` of ≥ 32 characters, production refuses to start.
    - The old hand-made service (`algoviz-52q2`, still on 2.0.0) is retired once the Blueprint serves.
  - **Vercel (frontend):** project `algo-viz`, root directory `frontend`. `frontend/vercel.json` pins the Next.js build.
    - `NEXT_PUBLIC_API_URL=https://<backend>` and `NEXT_PUBLIC_WS_URL=wss://<backend>/ws` must be set for Production.
    - A production build without them fails on purpose (`next.config.ts`).
  - CORS defaults and `render.yaml` allow only `https://algorithmic-viz.vercel.app`; the WebSocket allowlist follows.
  - Then the owner pastes the `ADMIN_TOKEN` into the frontend's Settings → Access to make changes.
- **Open items the owner must clear** (they need permission):
  - Linux visual baselines. These need the `mcr.microsoft.com/playwright` Docker image (~2 GB); CI skips the visual spec off Windows meanwhile.
  - A migration run against a real Postgres (Docker image). The DDL was only verified offline. Hosting now uses SQLite (E1), so this matters only if Postgres is adopted later.
  - `gh` CLI auth on this machine was invalid at hand-off: `gh auth login`.
- **Honest model finding:** on live BTC at a 5 s horizon the calibrated model has ~no edge over the class prior (edge −0.045 … +0.0015 through v40; v41 on 2026-10-03: −0.024 vs the class prior, −0.052 vs the trailing prior). Never present it as predictive.
  - The evidence is only 3.2 h of live bars (8 sessions over 4 days), and bar retention is 7 days.
  - The edge study (Stage S, `docs/edge-study.md`) tests 60 label definitions against a rule fixed in advance.
    - On 1.8 h of live bars it is preliminary and decides nothing.
    - No definition beats both priors convincingly; fold dispersion exceeds every mean edge.
    - Exploratory runs (`scripts/ml_study.py`) see only bars from before the freeze. The deciding run is `scripts/ml_study.py --decide`, once 7 days of bars from the freeze on exist.

## Running it

- The Python venv lives **outside** the repo: `D:\My_Work\Projects\AlgoViz\.venv` (Python 3.11). Elsewhere: `pip install -e "backend[dev]" -c backend/constraints.txt`.
- On this machine, dev servers are launched from `D:\My_Work\Projects\AlgoViz\.claude\launch.json`:
  - `backend-synthetic` on :8000;
  - `frontend-live` on :3000: the dev frontend pointed at the live collector on :8001;
  - `frontend` (dev) and `frontend-prod` on :3000.
  - `frontend-prod` runs `npm start`, which is `scripts/start-standalone.mjs`: the standalone `server.js` with its static and public files, as the Docker image serves it. e2e uses the same launcher.
- Use the preview tools to start servers, never Bash.
- **The live backend is the collector, not a preview server.**
  - The scheduled task "AlgoViz live collector" runs `backend/scripts/collect_live.py` under `pythonw` on 127.0.0.1:8001. It starts at logon, has a watchdog trigger every 5 minutes, keeps bars for 60 days and trains on one thread.
  - Its log is `backend/data/logs/collector.log`.
  - It is the live database's only writer: never start another live backend beside it.
  - Stop it with `Stop-ScheduledTask -TaskName "AlgoViz live collector"`. Remove it with `Unregister-ScheduledTask -TaskName "AlgoViz live collector"`.
- `justfile` lists every task (`just --list`). `just` isn't installed on the dev machine; the commands inside work by hand.

## Gates (what CI runs)

- **Backend** (in `backend/`):
  - `ruff check .`, `ruff format --check .`, `mypy`
  - `pytest -q --cov` — 173 tests (one is POSIX-only, so 172 pass and 1 skips on Windows), coverage floor 90 % (92.76 % now)
  - `pip-audit -r requirements.txt -r constraints.txt --strict`
  - OpenAPI freshness
- **Frontend** (in `frontend/`): `npm run format:check`, `npm run check` (tsc · eslint · vitest 29 · next build), `npm audit --omit=dev --audit-level=high`.
  - The full `npm audit --audit-level=high` runs too, reported but not blocking. braces ≤ 3.0.3 (dev only, via eslint-config-next) has a high advisory and no patched release; the owner chose this scope on 2026-10-07. Make it blocking again once braces ships a fix.
- **E2E:** `npx playwright test` — 38 tests, plus the toast-stacking test; about 10–13 min on SwiftShader.
  - Projects: `chromium` and `webgl-mid`.
  - Specs: smoke, pages, strategies, alerts, axe (WCAG 2.2 AA), visual (Windows baselines), budgets, webgl.
  - The backend is seeded from `backend/scripts/seed_e2e.py`: a template built once (~30 s), then copied fresh per run.

## Lessons that cost time (don't relearn them)

**Build and tooling**
- `npx playwright test` rebuilds `.next` with the e2e API URL (port 8010). Run `npm run build` again before serving `frontend-prod`.
- Lightning CSS (Tailwind 4) keeps only the last of a prefixed/unprefixed pair. Declare `backdrop-filter` and `background-clip` unprefixed only, and check the compiled CSS in `.next/static/chunks/*.css`.
- A `--color-x` token generates `text-x` / `bg-x` utilities; don't name custom classes that way.
- Rules in `@layer components` lose to Tailwind utilities regardless of specificity, so an override must be unlayered.

**Frontend correctness**
- **Hydration:** the first render must come from the server snapshot, never from mutable rings (bars, heat) or from TanStack queries the shell already fetched (`useBars`, `useHydrationDone`, the heatmap's `bookHead` gate).
- **Stacking:** app bar 40 · tooltips 60 · drawer 70/71 · palette 75 · toasts 80.

**Testing and measurement**
- Run axe only after the GSAP entrance tween has cleared its inline opacity.
- Check mobile overflow against the device width (390), not `innerWidth`: emulation widens the layout viewport.
- `toBeVisible` does not detect occlusion; use `elementFromPoint`.
- Headless Playwright auto-dismisses `window.confirm`; accept dialogs in probe scripts.
- The e2e backend retrains about 10 minutes into a run. Requests slow to seconds around then; once, a strategy DELETE got no answer within the spec's 20 s. Check the trace's request timings and rerun before chasing it.
- The visual spec leaves every REST call unanswered, so it pins panel anatomy, not model data. When training changes what the model records, bump `SEED_VERSION` in `scripts/seed_e2e.py`, because the seed's stamp doesn't see it.
- Timing on SwiftShader is noise (LCP 3–9 s for the same build). Budget bytes and CLS, and only hang-guard timings. Judge visuals and fps on the real GPU (headless Chromium with `--use-angle=d3d11 --enable-gpu`).
- Judge microstructure visuals on the live feed (`frontend-live` against the collector); the synthetic book slides its levels with the mid.
- Playwright prints a web server's stderr only. To see its stdout (Next's "Ready", the launcher command), run with `DEBUG=pw:webserver`. Outside CI it reuses any server already listening on :3100 or :8010, so stop stray servers before trusting a run.
- Local npm 9.6 exits 0 on a critical `npm audit` finding at `--audit-level=high`; npm 10 (CI) exits 1. Audit locally with `npx -y npm@10 audit --audit-level=high`.

**Backend and ML**
- Coverage needs `concurrency = ["thread", "greenlet"]` (SQLAlchemy async runs in greenlets). Without it the API modules read ~60 %.
- In-process training tests need the `capped_threads` fixture, module-scoped. A session-wide `threadpool_limits` hangs the ML engine test on Windows (vcomp OpenMP is process-wide).
- **Never use `asyncio.wait_for` (Python 3.11); use `async with asyncio.timeout(...)`.**
  - On 3.11, `wait_for` swallows a cancellation that races with the inner awaitable completing (gh-86296).
  - In `MLEngine.predict` this left the intelligence loop alive after `stop()` cancelled it, so `stop()` waited forever. That was the intermittent `test_ml_engine` hang on Windows and on CI #11 (Linux), and a shutdown hang in production.
  - Fixed 2026-10-02 in `predict` and `run_isolated` (the hub had already been fixed), with a regression test.
- To diagnose a hang: `py-spy dump` shows thread stacks (idle threads here). The answer came from asyncio *task* stacks, via a scratch pytest plugin that calls `task.print_stack()` on a timer (loaded with `-p`).
- Training and HMM fits run in spawned processes. On Windows, `Process.start()` blocks while pickling arguments, so start them off the loop.
- SHAP explainers aren't picklable; they are built on the inference thread one at a time.
- **Weighted HistGradientBoosting fits are slow** (scikit-learn 1.9). With `sample_weight`, every bin edge of every feature is a weighted percentile: 35,000 calls a fit, 5 to 17 times slower. With no more distinct values than `max_bins`, HGB bins at midpoints instead, so the study bins weighted windows at their unweighted quantiles first (`study.bin_codes`).
- **`CalibratedClassifierCV` and rare classes.**
  - If a calibration split's fit rows lack one of the window's classes, scikit-learn (1.9) pairs the two-class split model's single probability column with the wrong class, and the ensemble serves p = 1 for a rare class.
  - `TailStoppedHGB(classes=…)` answers for every class in the window, which prevents it. Keep that when changing the recipe.
  - Isotonic calibration still fits exact zeros when a class has only a handful of examples. A label definition where a class is about 1 % will show that as huge log-loss.
- Model artefacts carry a manifest (feature-schema hash, horizon, labels). Bump `FEATURE_SCHEMA_VERSION` in `ml/features.py` whenever a feature's definition changes.
- The regime is two axes: a volatility state (calm / normal / elevated / extreme) and a trend (down / flat / up). Renaming categorical values needs an Alembic data migration (see `4c1e7b2a9d30`).

**Long-running processes on Windows**
- Preview servers stop when their Claude session ends, so they can't collect data for days.
- Task Scheduler's "restart on failure" covers a task that fails to start, not a process that dies while running. A repeating trigger with `MultipleInstances IgnoreNew` works as a watchdog: tested, a killed collector was back in 59 s.
- uvicorn starts the app (feed, writer, engine) before it binds its port. A second instance that fails to bind still writes for a moment, so `collect_live.py` checks the port first.

**Shell on Windows**
- Bash tool: an odd number of apostrophes in a command breaks parsing; write such scripts with a file instead.
- Python `print` uses cp1252 here; avoid printing non-ASCII.
- Use `MSYS_NO_PATHCONV=1` when passing `/route` arguments in Git Bash.
