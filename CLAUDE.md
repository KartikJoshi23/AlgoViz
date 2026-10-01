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

## Where it stands (2026-10-01)

- **Phase 4 is complete:** stages G, J, K, L, H, M, plus the theme v3 overhaul. **Stage M awaits the owner's review.** If they approve, there is no further planned stage; ask what comes next.
- **Git:** the whole rebuild (Phases 3 and 4) is on `main`, pushed 2026-10-01 at the owner's request as a fast-forward. `overhaul/phase-3-4` is the merged branch and can be deleted.
  - **Every push to `main` deploys:** `render.yaml` has `autoDeploy: true`, and Vercel builds from `main`.
  - CI (`.github/workflows/ci.yml`) runs on pushes to `main` and on pull requests.
  - The deploy outcome of 2026-10-01 was not verified from here (no Render or Vercel access): ask the owner how it went.
- **Production checklist** (what the rebuild needs from the hosts):
  - **Render (backend):**
    - `ENVIRONMENT=production`, `SECRET_KEY`, and an `ADMIN_TOKEN` of ≥ 32 characters. Without `ADMIN_TOKEN` the app refuses to start, and Render keeps the previous deploy serving.
    - `TRUSTED_PROXIES` set to Render's private ranges.
    - A Postgres `DATABASE_URL`, because the disk is ephemeral.
    - A Blueprint-managed service picks all of these up from `render.yaml`; a hand-made one needs them set in the dashboard.
  - **Vercel (frontend):**
    - Framework preset **Next.js**, root directory `frontend`. The old project was Vite, and `frontend/vercel.json` is gone.
    - `NEXT_PUBLIC_API_URL=https://<backend>` and `NEXT_PUBLIC_WS_URL=wss://<backend>/ws`, set before the build.
    - The frontend's origin must be in the backend's `CORS_ORIGINS` (the defaults list the old `*.vercel.app` names).
  - Then paste the `ADMIN_TOKEN` into the frontend's Settings → Access to make changes.
- **Open items the owner must clear** (they need permission):
  - Linux visual baselines. These need the `mcr.microsoft.com/playwright` Docker image (~2 GB); CI skips the visual spec off Windows meanwhile.
  - A migration run against a real Postgres (Docker image). The DDL was only verified offline.
  - `gh` CLI auth on this machine was invalid at hand-off: `gh auth login`.
- **Honest model finding:** on live BTC at a 5 s horizon the calibrated model has ~no edge over the class prior (edge −0.045 … +0.001). Never present it as predictive. Candidate improvements for a future phase: a longer horizon, labels with a floor above spread noise, features that survive regime drift.

## Running it

- The Python venv lives **outside** the repo: `D:\My_Work\Projects\AlgoViz\.venv` (Python 3.11). Elsewhere: `pip install -e "backend[dev]"`.
- On this machine, dev servers are launched from `D:\My_Work\Projects\AlgoViz\.claude\launch.json`:
  - `backend-synthetic` and `backend-live` on :8000;
  - `frontend` (dev) and `frontend-prod` (`next start`) on :3000.
- Use the preview tools to start servers, never Bash.
- `justfile` lists every task (`just --list`). `just` isn't installed on the dev machine; the commands inside work by hand.

## Gates (what CI runs)

- **Backend** (in `backend/`):
  - `ruff check .`, `ruff format --check .`, `mypy`
  - `pytest -q --cov` — 152 tests, coverage floor 90 % (92.5 % now)
  - `pip-audit -r requirements.txt --strict`
  - OpenAPI freshness
- **Frontend** (in `frontend/`): `npm run format:check`, `npm run check` (tsc · eslint · vitest 27 · next build), `npm audit --audit-level=high`.
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
- Timing on SwiftShader is noise (LCP 3–9 s for the same build). Budget bytes and CLS, and only hang-guard timings. Judge visuals and fps on the real GPU (headless Chromium with `--use-angle=d3d11 --enable-gpu`).
- Judge microstructure visuals on `backend-live`; the synthetic book slides its levels with the mid.

**Backend and ML**
- Coverage needs `concurrency = ["thread", "greenlet"]` (SQLAlchemy async runs in greenlets). Without it the API modules read ~60 %.
- In-process training tests need the `capped_threads` fixture, module-scoped. A session-wide `threadpool_limits` hangs the ML engine test on Windows (vcomp OpenMP is process-wide).
- Training and HMM fits run in spawned processes. On Windows, `Process.start()` blocks while pickling arguments, so start them off the loop.
- SHAP explainers aren't picklable; they are built on the inference thread one at a time.
- Model artefacts carry a manifest (feature-schema hash, horizon, labels). Bump `FEATURE_SCHEMA_VERSION` in `ml/features.py` whenever a feature's definition changes.
- The regime is two axes: a volatility state (calm / normal / elevated / extreme) and a trend (down / flat / up). Renaming categorical values needs an Alembic data migration (see `4c1e7b2a9d30`).

**Shell on Windows**
- Bash tool: an odd number of apostrophes in a command breaks parsing; write such scripts with a file instead.
- Python `print` uses cp1252 here; avoid printing non-ASCII.
- Use `MSYS_NO_PATHCONV=1` when passing `/route` arguments in Git Bash.
