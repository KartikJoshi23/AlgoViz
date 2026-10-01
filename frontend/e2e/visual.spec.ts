import { expect, test } from "@playwright/test";

import { ROUTES } from "./helpers";

/*
 * Visual baselines of every route's layout, desktop and mobile.
 *
 * Live data never repeats, so the page is pinned to one exact state: the
 * WebSocket is accepted but silent, every REST call is left unanswered (each
 * query stays in its loading state), the clock is frozen, the timezone is UTC
 * and motion is reduced. What remains is what a design-system baseline should
 * catch: the shell, the grid, panel anatomy, type and the empty states.
 *
 * Font rendering differs by platform, and the committed baselines were
 * recorded on Windows.
 */
test.skip(process.platform !== "win32", "Baselines are recorded on Windows; other platforms render text differently.");

const FROZEN = new Date("2026-09-25T12:00:00Z");
const PREFS = {
  state: { prefs: { perfTier: "auto", motion: "reduced", accentIntensity: 1, bookSubscribed: true, symbol: null } },
  version: 0,
};

test.use({ timezoneId: "UTC", locale: "en-US" });

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(FROZEN);
  await page.addInitScript((prefs) => window.localStorage.setItem("algoviz.prefs", JSON.stringify(prefs)), PREFS);
  await page.routeWebSocket(/\/ws$/, () => {}); // accepted, never speaks
  await page.route(/\/(api\/v1|health)\b/, () => {}); // never answered
});

const slug = (route: string) => (route === "/" ? "overview" : route.slice(1));

for (const [device, viewport] of [
  ["desktop", { width: 1280, height: 800 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test.describe(device, () => {
    test.use({ viewport, isMobile: device === "mobile", hasTouch: device === "mobile" });
    for (const route of ROUTES) {
      test(`${route} matches its baseline`, async ({ page }) => {
        await page.goto(route);
        await expect(page.locator("main h1").first()).toBeVisible();
        await expect(page).toHaveScreenshot(`${device}-${slug(route)}.png`, {
          fullPage: true,
          animations: "disabled",
          maxDiffPixelRatio: 0.002,
        });
      });
    }
  });
}
