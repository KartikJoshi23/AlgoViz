import { expect, test } from "@playwright/test";

import { panel, ROUTES, trackErrors, waitForLiveData } from "./helpers";

test.describe("routes", () => {
  for (const route of ROUTES) {
    test(`${route} renders without errors`, async ({ page }) => {
      const errors = trackErrors(page);
      await page.goto(route);
      await expect(page).toHaveTitle(/AlgoViz/);
      await expect(page.locator("main h1").first()).toBeVisible();
      // the nav highlights the current route once the client has hydrated
      await expect(page.locator('header a[data-active="true"]').first()).toHaveAttribute("href", route);
      await page.waitForTimeout(1500);
      expect(errors()).toEqual([]);
    });
  }

  test("404 page", async ({ page }) => {
    await page.goto("/nope");
    await expect(page.locator("main")).toContainText(/not found|404/i);
  });
});

test("dashboard streams live data and renders every panel", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/");
  await waitForLiveData(page);

  // market strip: six stat tiles with numbers
  await expect(page.locator('section[aria-label="Key metrics"] .stat-value')).toHaveCount(6);

  // the liquidity hero opens on the heatmap (2D on every tier)
  const hero = panel(page, "Liquidity");
  await expect(hero).toBeVisible();
  await expect(hero.locator('canvas[aria-label^="Liquidity heatmap"]')).toBeVisible();

  // price chart, order book depth curve, tape and model panel
  await expect(page.locator('[aria-label="Price chart"] canvas').first()).toBeVisible();
  await expect(panel(page, "Order book").locator('canvas[aria-label^="Cumulative depth"]')).toBeVisible();
  await expect(panel(page, "Tape").locator("li").first()).toBeVisible();
  // ready (the barrier probabilities), warming (labelled samples) or before the first prediction frame
  await expect(panel(page, "Model")).toContainText(/Chance the mid touches|labelled samples|model stream/);

  expect(errors()).toEqual([]);
});

test("command palette navigates", async ({ page }) => {
  await page.goto("/");
  await waitForLiveData(page); // hydrated: the global shortcut listener is attached
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox").fill("intelli");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/intelligence$/);
  await expect(page.locator("main h1")).toContainText("Intelligence");
});
