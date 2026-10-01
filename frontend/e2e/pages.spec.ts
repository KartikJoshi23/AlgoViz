import { expect, test } from "@playwright/test";

import { panel, trackErrors } from "./helpers";

test("preferences persist across reloads and the engine metrics load", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/settings");

  const motion = () => page.getByRole("tablist").nth(1);
  await motion().getByRole("tab", { name: "reduced", exact: true }).click();
  await expect(motion().getByRole("tab", { name: "reduced", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.reload();
  await expect(motion().getByRole("tab", { name: "reduced", exact: true })).toHaveAttribute("aria-selected", "true");

  const engine = panel(page, "Engine");
  await expect(engine).toContainText(/events \/ s/i);
  await expect(engine).toContainText("synced");
  await expect(panel(page, "Connection")).toContainText("open");

  // back to defaults for the next spec
  await page.getByRole("button", { name: "Reset preferences" }).click();
  await expect(motion().getByRole("tab", { name: "auto", exact: true })).toHaveAttribute("aria-selected", "true");
  expect(errors()).toEqual([]);
});

test("book page: terrain, ladder and liquidity", async ({ page }) => {
  await page.goto("/book");
  await expect(panel(page, "Ladder").locator(".row").first()).toBeVisible();
  await expect(panel(page, "Liquidity bands")).toContainText("±10 bps");
  await expect(panel(page, "Liquidity").locator('canvas[aria-label^="Liquidity heatmap"]')).toBeVisible();
});

test("intelligence page: model panels populate", async ({ page }) => {
  await page.goto("/intelligence");
  await expect(panel(page, "Drift monitor")).toBeVisible();
  // the seeded model (scripts/seed_e2e.py) is served from the first second: four held-out folds
  const folds = panel(page, "Walk-forward validation");
  await expect(folds.locator("tbody tr")).toHaveCount(4);
  await expect(folds).toContainText("isotonic");
  await expect(panel(page, "Reliability")).toContainText(/walk-forward folds · \d+ held-out forecasts/);
  const rules = panel(page, "Signal rules");
  await expect(rules).toContainText(/\d+ rules on z-scores/);
  await expect(rules.locator(".row").first()).toBeVisible();
});
