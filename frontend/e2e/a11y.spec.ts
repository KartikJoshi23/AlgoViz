import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { ROUTES, waitForLiveData } from "./helpers";

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/**
 * WCAG 2.2 AA violations once the page has settled, one line per failing
 * node. The entrance tween fades panels in with inline opacity (cleared when
 * it ends); text measured mid-fade would fail contrast it doesn't have.
 */
async function violations(page: Page): Promise<string[]> {
  await page.waitForFunction(() => ![...document.querySelectorAll<HTMLElement>(".panel")].some((p) => p.style.opacity !== ""));
  const res = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  return res.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")}`));
}

test.describe("accessibility (axe, WCAG 2.2 AA)", () => {
  for (const route of ROUTES) {
    test(`${route} has no violations`, async ({ page }) => {
      await page.goto(route);
      if (route === "/") await waitForLiveData(page);
      await expect(page.locator("main h1").first()).toBeVisible();
      expect(await violations(page)).toEqual([]);
    });
  }

  test("the strategy feature catalog drawer has no violations", async ({ page }) => {
    await page.goto("/strategies");
    await page.getByRole("button", { name: "New strategy" }).first().click();
    await page.getByRole("button", { name: "Browse features" }).first().click();
    const dialog = page.getByRole("dialog", { name: "Feature catalog" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("textbox")).toBeFocused(); // focus moves into the drawer
    expect(await violations(page)).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("the alert rule drawer has no violations", async ({ page }) => {
    await page.goto("/alerts");
    await page.getByRole("button", { name: "New rule" }).first().click();
    await expect(page.getByRole("dialog", { name: "New alert rule" })).toBeVisible();
    expect(await violations(page)).toEqual([]);
  });
});
