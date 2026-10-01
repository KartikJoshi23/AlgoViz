import { expect, test } from "@playwright/test";

import { panel, trackErrors } from "./helpers";

test("an alert rule fires, shows in history, can be acknowledged and deleted", async ({ page }) => {
  const errors = trackErrors(page);
  page.on("dialog", (d) => d.accept());
  await page.goto("/alerts");

  await page.getByRole("button", { name: "New rule" }).first().click();
  const form = page.getByRole("dialog", { name: "New alert rule" });
  const name = `e2e rule ${Date.now()}`;
  await form.getByPlaceholder("Spread blow-out").fill(name);
  await form.getByLabel("Feature").selectOption("velocity");
  await form.getByLabel("Comparison").selectOption("gt");
  await form.getByLabel(/Threshold/).fill("0");
  await form.getByRole("button", { name: "Create" }).click();

  const rules = panel(page, "Rules");
  await expect(rules).toContainText(name);

  // velocity > 0 fires within a second or two; the WS frame shows it before the REST refresh
  const history = panel(page, "History");
  await expect(history.locator("li", { hasText: name }).first()).toBeVisible({ timeout: 30_000 });
  await history.locator("li", { hasText: name }).first().getByRole("button", { name: "Acknowledge" }).click();

  await rules.locator("tr", { hasText: name }).getByRole("button", { name: "Delete rule" }).click();
  await expect(rules).not.toContainText(name);
  expect(errors()).toEqual([]);
});

test("a refused change explains itself, above the form that caused it", async ({ page }) => {
  // what a server that gates changes answers without the admin token
  await page.route("**/api/v1/alerts/rules", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 401,
          contentType: "application/problem+json",
          headers: { "WWW-Authenticate": "Bearer" },
          body: JSON.stringify({ type: "about:blank", title: "Unauthorized", status: 401, detail: "Changes need the admin token" }),
        })
      : route.fallback(),
  );
  await page.goto("/alerts");
  await page.getByRole("button", { name: "New rule" }).first().click();
  const form = page.getByRole("dialog", { name: "New alert rule" });
  await form.getByPlaceholder("Spread blow-out").fill(`refused ${Date.now()}`);
  await form.getByRole("button", { name: "Create" }).click();

  const toast = page.getByRole("status").filter({ hasText: "Settings → Access" });
  await expect(toast).toBeVisible();
  // visible is not enough: it must be the topmost element where it is drawn, not under the drawer
  const onTop = await toast.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!hit && el.contains(hit);
  });
  expect(onTop).toBe(true);
});
