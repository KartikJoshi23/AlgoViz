import { existsSync } from "node:fs";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end smoke against a real backend in synthetic mode (no internet).
 *
 *   npm run e2e            # builds the app, starts both servers, runs Chromium
 *   ALGOVIZ_PYTHON=...     # interpreter with the backend installed (default: repo venv / `python`)
 */
const API_PORT = 8010;
const WEB_PORT = 3100;
const API = `http://127.0.0.1:${API_PORT}`;
const WEB = `http://127.0.0.1:${WEB_PORT}`;

const backendDir = path.resolve(__dirname, "../backend");
const venvPython = path.resolve(__dirname, "../../.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const PYTHON = process.env.ALGOVIZ_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");

export default defineConfig({
  testDir: "./e2e",
  // CI runners have no GPU, so Chromium runs on SwiftShader: every accelerated 2D
  // canvas is rasterised on the CPU (the app detects the software renderer as the
  // low tier and drops glass blur), and the page's main thread stalls on "GPU
  // backpressure" for seconds at a time. The dashboard settles in ~2 s on a real
  // GPU but 60–100 s here, hence the budget.
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: WEB,
    trace: "retain-on-failure",
    launchOptions: {
      // software WebGL2 so the terrain path is exercised headlessly
      args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
    },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } }, testIgnore: /webgl\.spec\.ts/ },
    // The detected tier on a software renderer is "low" (2D only); this project forces "mid" so the
    // WebGL terrain path runs headlessly too.
    { name: "webgl-mid", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } }, testMatch: /webgl\.spec\.ts/ },
  ],
  webServer: [
    {
      // Every run starts from the same seeded database and trained model (scripts/seed_e2e.py:
      // built once, then copied fresh), so no run inherits another's rows.
      command: `"${PYTHON}" scripts/seed_e2e.py --db data/e2e.db --models data/e2e_models && "${PYTHON}" -m uvicorn algoviz.main:app --host 127.0.0.1 --port ${API_PORT} --no-proxy-headers`,
      cwd: backendDir,
      url: `${API}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        ENVIRONMENT: "test",
        DATA_SOURCE: "synthetic",
        DATABASE_URL: "sqlite+aiosqlite:///./data/e2e.db",
        ML_MODEL_DIR: "./data/e2e_models",
        BACKTEST_MIN_BARS: "50",
        BACKTEST_SYNTHETIC_BARS: "600",
        CORS_ORIGINS: JSON.stringify([WEB, `http://localhost:${WEB_PORT}`]),
        RATE_LIMIT_RPM: "2000",
        RATE_LIMIT_WRITE_RPM: "600",
        RATE_LIMIT_BACKTEST_RPM: "60",
        PYTHONIOENCODING: "utf-8",
        LOG_LEVEL: "WARNING",
      },
    },
    {
      command: `npm run build && npm run start -- -p ${WEB_PORT}`,
      url: WEB,
      reuseExistingServer: !process.env.CI,
      timeout: 360_000,
      env: { NEXT_PUBLIC_API_URL: API, NEXT_PUBLIC_WS_URL: `ws://127.0.0.1:${API_PORT}/ws`, NEXT_TELEMETRY_DISABLED: "1" },
    },
  ],
});
