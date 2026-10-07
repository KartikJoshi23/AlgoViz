# AlgoViz tasks — `just --list` shows them all. Needs `just` (https://just.systems)
# and the backend's Python environment active (or PYTHON pointing at it).

set shell := ["bash", "-uc"]
set windows-shell := ["bash", "-uc"]

python := env_var_or_default("PYTHON", "python")

# List the tasks
default:
    @just --list

# Install the backend (with dev tools), the frontend and Playwright's Chromium
setup:
    {{python}} -m pip install -e "backend[dev]" -c backend/constraints.txt
    cd frontend && npm ci && npx playwright install chromium

# Backend on the live Binance feed, reloading on change
backend:
    cd backend && {{python}} -m uvicorn algoviz.main:app --reload --no-proxy-headers

# Backend on the built-in exchange simulator (no internet needed)
backend-synthetic:
    cd backend && DATA_SOURCE=synthetic {{python}} -m uvicorn algoviz.main:app --reload --no-proxy-headers

# Frontend dev server (http://localhost:3000)
frontend:
    cd frontend && npm run dev

# Every gate CI runs, backend and frontend
check: check-backend check-frontend

# ruff · mypy · pytest with the coverage floor · pip-audit · contract freshness
check-backend:
    cd backend && ruff check . && ruff format --check . && mypy
    cd backend && {{python}} -m pytest -q --cov --cov-report=term
    cd backend && pip-audit -r requirements.txt -r constraints.txt --strict
    just contracts
    git diff --exit-code --ignore-cr-at-eol -- frontend/lib/api/openapi.json frontend/lib/api/schema.d.ts

# prettier · tsc · eslint · vitest · next build
check-frontend:
    cd frontend && npm run format:check && npm run check

# Playwright: seeds the e2e database, builds the app, boots both servers, drives Chromium
e2e *args:
    cd frontend && npx playwright test {{args}}

# Re-record the visual baselines (Windows set) after an intended visual change
baselines:
    cd frontend && npx playwright test e2e/visual.spec.ts --update-snapshots

# Regenerate the OpenAPI document and the frontend's TypeScript types from it
contracts:
    cd backend && {{python}} scripts/export_openapi.py
    cd frontend && npm run types

# Re-pin the backend's transitive dependencies (backend/constraints.txt) from a clean install
constraints:
    cd backend && {{python}} scripts/freeze_constraints.py

# Collect live bars for the edge study: the live backend on :8001, bars kept 60 days
collect:
    cd backend && {{python}} scripts/collect_live.py

# Save persisted live bars past retention, then run the edge study on everything saved
study:
    cd backend && {{python}} scripts/export_bars.py
    cd backend && {{python}} scripts/ml_study.py --out ../docs/edge-study.md

# Format everything (ruff for Python, prettier for the frontend)
format:
    cd backend && ruff check --fix . && ruff format .
    cd frontend && npm run format

# Rebuild the seeded e2e database from scratch (it rebuilds itself when stale)
seed-e2e:
    rm -rf backend/data/e2e-seed
    cd backend && {{python}} scripts/seed_e2e.py --db data/e2e.db --models data/e2e_models

# The whole stack in Docker (backend :8002, frontend :3002)
docker:
    docker compose up --build
