import { expect, test } from "@playwright/test";

import { panel, trackErrors } from "./helpers";

test("create a strategy from a template, backtest it, delete it", async ({ page }) => {
  const errors = trackErrors(page);
  page.on("dialog", (d) => d.accept());
  await page.goto("/strategies");

  await page.getByRole("button", { name: "New strategy" }).first().click();
  const editor = panel(page, "New strategy");
  await editor.getByLabel("Load a template").selectOption("ofi_momentum");
  const name = `e2e ${Date.now()}`;
  await editor.getByPlaceholder("OFI momentum").fill(name);
  await editor.getByRole("button", { name: "Create" }).click();
  await expect(panel(page, "Library")).toContainText(name);

  // the definition reloads with the template's conditions
  const definition = panel(page, "Definition");
  await expect(definition).toContainText("ofi_z > 1.5");

  // run a backtest; progress arrives on the WebSocket and the result panel fills in
  await page.getByRole("button", { name: /Run on/ }).click();
  const result = panel(page, "Result #[0-9]+");
  await expect(result).toBeVisible();
  await expect(result.locator(".badge", { hasText: "completed" })).toBeVisible({ timeout: 90_000 });
  await expect(result).toContainText("P&L");
  await expect(result).toContainText(/Sharpe/);
  await expect(result.locator('[aria-label="Equity and drawdown"] canvas').first()).toBeVisible();

  await definition.getByRole("button", { name: "Delete strategy" }).click();
  await expect(panel(page, "Library")).not.toContainText(name);
  expect(errors()).toEqual([]);
});
